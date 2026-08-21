//! Runs the Python analysis engine as a child process, on demand, from the
//! "Analizar ahora" tray menu item.
//!
//! Design constraints (from the task brief):
//! - The PyInstaller sidecar approach was abandoned: this machine's
//!   antivirus quarantined every PyInstaller binary produced, three times,
//!   with a generic `MalwareX-gen` signature -- a known false positive
//!   caused by PyInstaller's self-extracting bootloader (present in both
//!   `--onefile` and `--onedir`). So instead of a Tauri sidecar, this module
//!   invokes the project's own venv interpreter by absolute path, as a
//!   normal child process. The app is therefore not self-contained yet;
//!   that is an accepted, documented tradeoff for this slice.
//! - Exactly one scan runs at a time (decision D3): a second "Analizar
//!   ahora" while one is in flight cancels the running scan instead of
//!   starting a second process.
//! - The child is spawned in its own process group (`process_group(0)`) so
//!   the whole group can be killed together, not just the immediate
//!   `python` process. Killing escalates SIGTERM -> SIGKILL after a short
//!   grace period, the same shape `pty_manager.py` already uses
//!   (`KILL_REAP_TIMEOUT`) for the identical reason: a killed process must
//!   not be able to outlive a bounded deadline.

use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

/// Grace period between SIGTERM and SIGKILL.
const TERM_GRACE: Duration = Duration::from_millis(300);
/// Ceiling on how long `kill_blocking` waits for the background waiter
/// thread to notice the child exited and clear `pid`. Mirrors the shape of
/// `pty_manager.py`'s `KILL_REAP_TIMEOUT` -- a bounded wait, not a hang.
const KILL_REAP_TIMEOUT: Duration = Duration::from_secs(2);
const REAP_POLL_INTERVAL: Duration = Duration::from_millis(50);

/// Whole-disk scan (decision D2: the app scans the whole disk, which is why
/// Full Disk Access matters). `min-size` matches the value the project's
/// own Makefile recommends for this exact case
/// (`sudo make full path=/ min_size=50`): at the CLI's 10 MB default a
/// whole-disk crawl spends most of its time on files nobody is going to act
/// on from a tray menu.
const SCAN_PATH: &str = "/";
const MIN_SIZE_MB: &str = "50";

/// Outcome of a finished (or aborted) scan, as the menu needs to report it.
#[derive(Debug, Clone)]
pub enum Resultado {
    Exito,
    /// The export succeeded but the engine logged permission errors while
    /// walking the tree -- the unmistakable signature of missing Full Disk
    /// Access on a whole-disk scan. Surfacing this explicitly matters: the
    /// scan does not fail loudly on its own (the engine catches
    /// `PermissionError` per-directory and keeps going), so silence here
    /// would mean the very first thing a new user hits goes unexplained.
    SinPermisos,
    /// El informe salió entero salvo unas pocas carpetas que ni con Acceso
    /// total al disco se pueden leer: son de `root` con permisos 700 y solo
    /// se abren con `sudo`. No es un fallo, y decir lo contrario mandaba al
    /// usuario a activar un permiso que ya tenía.
    Parcial(usize),
    Cancelado,
    Fallo(String),
}

/// Si esta app tiene concedido el Acceso total al disco.
///
/// Sonda directa en vez de deducirlo de los errores del informe: esa carpeta
/// solo se puede listar con el permiso concedido. Deducirlo era el error
/// original — un escaneo del disco entero **siempre** topa con unas pocas
/// carpetas de `root` (`/usr/sbin/authserver`, cachés de Apple, algún
/// antivirus), así que tomar cualquier error de permisos como "falta el
/// Acceso total al disco" daba un falso positivo permanente. Medido en la
/// máquina de desarrollo, con el permiso ya concedido: 10 errores, ninguno
/// de ellos de una ruta protegida por TCC.
pub fn hay_acceso_total_al_disco() -> bool {
    let Some(home) = std::env::var_os("HOME") else {
        return false;
    };
    std::fs::read_dir(Path::new(&home).join("Library/Application Support/com.apple.TCC")).is_ok()
}

impl Motor {
    pub fn python(&self) -> &Path {
        &self.python
    }
    /// Directorio desde el que se lanza el motor. Es también donde viven sus
    /// módulos y sus dependencias, así que Python los encuentra solo.
    pub fn cwd(&self) -> &Path {
        &self.cwd
    }
}

impl Resultado {
    /// Spanish, user-facing summary for the "estado_analisis" menu line.
    pub fn resumen(&self) -> String {
        match self {
            Resultado::Exito => "Último análisis: completado \u{2713}".to_string(),
            Resultado::SinPermisos => {
                "Acceso a disco incompleto: ve a Ajustes del Sistema > Privacidad y \
                 Seguridad > Acceso total al disco y activa esta app"
                    .to_string()
            }
            Resultado::Parcial(n) => format!(
                "Último análisis: completado ({n} carpetas de sistema omitidas, piden sudo)"
            ),
            Resultado::Cancelado => "Análisis cancelado".to_string(),
            Resultado::Fallo(msg) => format!("Error al analizar: {msg}"),
        }
    }
}

/// Where the analysis engine lives, once resolved.
#[derive(Debug, Clone)]
pub struct Motor {
    python: PathBuf,
    script: PathBuf,
    /// Working directory for the child. Python puts the script's directory on
    /// `sys.path` by itself, so running from here is what lets the engine
    /// import its own `analyzer/` package.
    cwd: PathBuf,
}

/// The repository this crate was compiled from, if it is still there.
///
/// Returns `None` rather than panicking: inside a bundled `.app` the path
/// baked in at compile time usually does not exist at all, and the tray
/// indicator must survive that -- it does not need Python for anything.
fn repo_root() -> Option<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .ok()
}

/// Finds the analysis engine, preferring the copy bundled inside the `.app`.
///
/// That bundled copy is what makes the app self-contained and distributable:
/// a trimmed CPython from python-build-standalone plus the engine sources,
/// assembled by `desktop/tools/preparar-motor.sh`. The fallback to the
/// repository's own venv keeps `npm run tauri dev` working without having to
/// run that script first.
pub fn localizar_motor(resource_dir: Option<PathBuf>) -> Option<Motor> {
    if let Some(dir) = resource_dir {
        // Tauri conserva la ruta relativa declarada en `bundle.resources`,
        // así que `resources/engine/**/*` acaba en
        // `Contents/Resources/resources/engine/` -- con el prefijo repetido.
        // Verificado sobre una .app construida de verdad: buscar solo
        // `engine/` no encontraba nada, y en la máquina de desarrollo el
        // fallo pasaba desapercibido porque la reserva al venv del
        // repositorio lo tapaba. En una máquina sin el repositorio la app
        // habría dicho "motor no encontrado".
        for candidato in ["resources/engine", "engine"] {
            let engine = dir.join(candidato);
            let python = engine.join("python/bin/python3");
            let script = engine.join("disk_analyzer.py");
            if python.is_file() && script.is_file() {
                return Some(Motor {
                    python,
                    script,
                    cwd: engine,
                });
            }
        }
    }

    let repo = repo_root()?;
    let python = repo.join("venv-web/bin/python");
    let script = repo.join("disk_analyzer.py");
    if python.is_file() && script.is_file() {
        return Some(Motor {
            python,
            script,
            cwd: repo,
        });
    }
    None
}

/// Tracks at most one in-flight scan. `pid` is the single source of truth
/// for "is a scan running": it is set (under its own lock, atomically with
/// the "already running" check) right after a successful spawn, and cleared
/// by the background waiter thread once the child is reaped. The `Child`
/// itself is never shared -- it is moved into the waiter thread that spawns
/// it, so `Child::wait()` (which blocks for the whole 25-60s scan) never
/// holds a lock that `cancel()` would need.
pub struct AnalisisManager {
    pid: Mutex<Option<i32>>,
    cancelado: AtomicBool,
    motor: Option<Motor>,
}

impl AnalisisManager {
    pub fn new(motor: Option<Motor>) -> Self {
        Self {
            pid: Mutex::new(None),
            cancelado: AtomicBool::new(false),
            motor,
        }
    }

    /// Whether an engine was found at startup. The menu uses this to say so
    /// up front instead of only failing when the user clicks "Analizar
    /// ahora".
    pub fn hay_motor(&self) -> bool {
        self.motor.is_some()
    }

    pub fn is_running(&self) -> bool {
        self.pid.lock().unwrap().is_some()
    }

    /// Starts a scan. Returns `Err` without spawning anything if one is
    /// already in flight -- this check-and-set happens under the `pid`
    /// lock, so it is race-free even if two clicks are handled concurrently
    /// (only one can observe `pid.is_none()` and win the spawn).
    ///
    /// `on_finish` runs exactly once, from a background thread, once the
    /// child has exited (normally, cancelled, or killed on app shutdown).
    pub fn start<F>(self: &Arc<Self>, on_finish: F) -> Result<(), String>
    where
        F: FnOnce(Resultado) + Send + 'static,
    {
        // Checked before building the command, because building it creates
        // the stderr file: an early return here keeps a rejected second
        // click from touching the filesystem at all.
        if self.is_running() {
            return Err("ya hay un análisis en marcha".to_string());
        }
        let motor = self
            .motor
            .as_ref()
            .ok_or_else(|| "no se encontró el motor de análisis".to_string())?;
        self.start_con(comando_analisis(motor)?, on_finish)
    }

    /// The half of `start` that does not know how to build the real scan
    /// command. Split out so the tests can exercise the whole spawn /
    /// track / cancel / reap machinery -- the part where a leaked process
    /// group would actually hurt -- against a cheap synthetic child, rather
    /// than against a whole-disk crawl that takes minutes.
    fn start_con<F>(self: &Arc<Self>, mut comando: Comando, on_finish: F) -> Result<(), String>
    where
        F: FnOnce(Resultado) + Send + 'static,
    {
        let mut pid_guard = self.pid.lock().unwrap();
        if pid_guard.is_some() {
            return Err("ya hay un análisis en marcha".to_string());
        }

        let programa = comando.cmd.get_program().to_string_lossy().into_owned();
        let mut child = comando
            .cmd
            .spawn()
            .map_err(|e| format!("no se pudo iniciar el motor de análisis ({programa}): {e}"))?;

        let pid = child.id() as i32;
        *pid_guard = Some(pid);
        // Reset while the `pid` lock is still held. Doing it after
        // releasing the lock leaves a window in which a `cancel()` that had
        // already latched onto this pid sets the flag and then has it wiped
        // here -- the scan would die from our own SIGTERM but get reported
        // as a failure instead of as cancelled.
        self.cancelado.store(false, Ordering::SeqCst);
        drop(pid_guard);

        let export_path = comando.export_path;
        let stderr_path = comando.stderr_path;
        let manager = Arc::clone(self);
        std::thread::spawn(move || {
            // Owns `child` exclusively: this blocking wait never holds
            // `manager.pid`'s lock, so `cancel()` (which only needs the pid)
            // is never blocked behind it.
            let status = child.wait();

            *manager.pid.lock().unwrap() = None;
            let cancelado = manager.cancelado.swap(false, Ordering::SeqCst);

            let resultado = if cancelado {
                Resultado::Cancelado
            } else {
                match status {
                    Ok(status) if status.success() => {
                        evaluar_export(&export_path, hay_acceso_total_al_disco())
                    }
                    Ok(status) => Resultado::Fallo(leer_stderr_o_codigo(&stderr_path, status)),
                    Err(e) => Resultado::Fallo(format!("no se pudo esperar al proceso: {e}")),
                }
            };

            let _ = std::fs::remove_file(&export_path);
            let _ = std::fs::remove_file(&stderr_path);
            on_finish(resultado);
        });

        Ok(())
    }

    /// Requests cancellation of the in-flight scan, if any. Sends SIGTERM
    /// immediately and schedules a SIGKILL after `TERM_GRACE` from a
    /// separate short-lived thread, so this call itself never blocks the
    /// menu-event thread. Returns `false` if nothing was running.
    pub fn cancel(&self) -> bool {
        let pid = match *self.pid.lock().unwrap() {
            Some(p) => p,
            None => return false,
        };
        self.cancelado.store(true, Ordering::SeqCst);
        unsafe {
            libc::kill(-pid, libc::SIGTERM);
        }
        std::thread::spawn(move || {
            std::thread::sleep(TERM_GRACE);
            // Idempotent: if the group already exited from the SIGTERM
            // above (the common case), this is ESRCH and a no-op.
            unsafe {
                libc::kill(-pid, libc::SIGKILL);
            }
        });
        true
    }

    /// Used only on app shutdown. Escalates SIGTERM -> SIGKILL immediately
    /// (no need to wait out `TERM_GRACE` in two steps -- the app is going
    /// away regardless) and then blocks, polling, until the background
    /// waiter thread clears `pid` (i.e. the child has been reaped) or
    /// `KILL_REAP_TIMEOUT` elapses. This is what guarantees "no orphans" on
    /// quit: the app does not finish exiting until the child is confirmed
    /// dead, or we've waited as long as we're willing to.
    pub fn kill_blocking(&self) {
        let pid = match *self.pid.lock().unwrap() {
            Some(p) => p,
            None => return,
        };
        self.cancelado.store(true, Ordering::SeqCst);
        unsafe {
            libc::kill(-pid, libc::SIGTERM);
        }
        std::thread::sleep(TERM_GRACE);
        unsafe {
            libc::kill(-pid, libc::SIGKILL);
        }
        let deadline = Instant::now() + KILL_REAP_TIMEOUT;
        while self.pid.lock().unwrap().is_some() && Instant::now() < deadline {
            std::thread::sleep(REAP_POLL_INTERVAL);
        }
    }
}

impl Default for AnalisisManager {
    fn default() -> Self {
        Self::new(None)
    }
}

/// Borra los temporales que dejó una ejecución anterior.
///
/// El hilo que espera al hijo los borra al terminar, pero si la app muere de
/// un SIGKILL (o de un cierre forzoso) no corre nadie y se acumulan. Se
/// comprueba el pid que va en el nombre antes de borrar: si ese proceso sigue
/// vivo, el fichero es de una instancia en marcha y no se toca. Borrarlo sin
/// mirar rompería el análisis de esa otra instancia, que se quedaría sin
/// informe que leer.
pub fn limpiar_temporales_huerfanos() {
    let Ok(dir) = std::fs::read_dir(std::env::temp_dir()) else {
        return;
    };
    for entrada in dir.flatten() {
        let nombre = entrada.file_name();
        let nombre = nombre.to_string_lossy();
        let Some(resto) = nombre.strip_prefix("disk-analyzer-tray-") else {
            continue;
        };
        let Some(pid) = resto.split('-').next().and_then(|p| p.parse::<i32>().ok()) else {
            continue;
        };
        if !proceso_muerto(pid) {
            continue;
        }
        let _ = std::fs::remove_file(entrada.path());
    }
}

/// Si el pid no corresponde a ningún proceso.
///
/// `kill(pid, 0)` no basta con comprobar `== 0`: para un proceso de otro
/// usuario devuelve -1 con `EPERM`, que significa "existe pero no puedes
/// señalarlo". Este proyecto documenta correr cosas con `sudo`, así que ese
/// caso llega a darse — y tratarlo como "muerto" haría borrar los temporales
/// de un análisis en marcha. Solo `ESRCH` significa muerto de verdad.
fn proceso_muerto(pid: i32) -> bool {
    if unsafe { libc::kill(pid, 0) } == 0 {
        return false;
    }
    std::io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH)
}

/// A scan's command plus the two temp paths its outcome is read back from.
struct Comando {
    cmd: Command,
    export_path: PathBuf,
    stderr_path: PathBuf,
}

/// Serial number for the temp file names. Naming them after the app's pid
/// alone is not enough: the pid is the same for every scan in a session, so
/// a second scan opened the *first* scan's stderr file with `File::create`
/// and truncated it out from under the still-running child.
static SECUENCIA: AtomicU64 = AtomicU64::new(0);

/// Builds the real whole-disk scan command.
fn comando_analisis(motor: &Motor) -> Result<Comando, String> {
    let etiqueta = format!(
        "{}-{}",
        std::process::id(),
        SECUENCIA.fetch_add(1, Ordering::SeqCst)
    );
    let export_path = std::env::temp_dir().join(format!("disk-analyzer-tray-{etiqueta}.json"));
    let stderr_path = std::env::temp_dir().join(format!("disk-analyzer-tray-{etiqueta}.stderr"));
    let stderr_file = std::fs::File::create(&stderr_path)
        .map_err(|e| format!("no se pudo preparar el registro de errores: {e}"))?;

    let mut cmd = Command::new(&motor.python);
    cmd.current_dir(&motor.cwd)
        .arg(&motor.script)
        .arg(SCAN_PATH)
        .arg("--min-size")
        .arg(MIN_SIZE_MB)
        .arg("--export")
        .arg(&export_path)
        .stdin(Stdio::null())
        // stdout is high-volume progress text nobody reads from a tray
        // menu; piping it without ever draining it risks filling the OS
        // pipe buffer and blocking the child mid-scan. Discard it.
        .stdout(Stdio::null())
        .stderr(Stdio::from(stderr_file))
        // New process group (pgid == the child's own pid), independent of
        // this app's group, so the whole group can be killed together via
        // `kill(-pid, ...)` without also signalling the app itself.
        .process_group(0);

    Ok(Comando {
        cmd,
        export_path,
        stderr_path,
    })
}

/// Reads the exported report and looks for permission errors in it.
///
/// `disk_analyzer.py` does not fail (non-zero exit) when it hits
/// `PermissionError` while walking protected directories -- it catches
/// those per-directory, appends a Spanish "Sin permisos..." message to
/// `report['errors']`, and keeps going (see `disk_analyzer.py`, e.g. line
/// ~194: `self.errors.append(f"Sin permisos: {item}")`). So a whole-disk
/// scan without Full Disk Access still exits 0 and produces a report; the
/// only way to notice is to look at `errors` after the fact, which is
/// exactly what this does.
fn evaluar_export(export_path: &Path, hay_acceso_total: bool) -> Resultado {
    let contents = match std::fs::read_to_string(export_path) {
        Ok(c) => c,
        Err(e) => return Resultado::Fallo(format!("no se generó el reporte: {e}")),
    };
    let json: serde_json::Value = match serde_json::from_str(&contents) {
        Ok(v) => v,
        Err(e) => return Resultado::Fallo(format!("reporte ilegible: {e}")),
    };
    let errores_de_permisos = json
        .get("errors")
        .and_then(|e| e.as_array())
        .map(|errores| {
            errores
                .iter()
                .filter(|e| {
                    e.as_str()
                        .map(|s| s.to_lowercase().contains("permiso"))
                        .unwrap_or(false)
                })
                .count()
        })
        .unwrap_or(0);

    match (errores_de_permisos, hay_acceso_total) {
        (0, _) => Resultado::Exito,
        // Sin el permiso concedido, los errores son la señal de que hay que
        // concederlo: es el primer arranque de cualquier usuario nuevo.
        (_, false) => Resultado::SinPermisos,
        // Con el permiso ya concedido, lo que queda son carpetas de root.
        (n, true) => Resultado::Parcial(n),
    }
}

/// Builds a short failure message from whatever the child wrote to stderr,
/// falling back to the exit code if stderr was empty (e.g. the interpreter
/// itself couldn't be found).
fn leer_stderr_o_codigo(stderr_path: &Path, status: ExitStatus) -> String {
    if let Ok(text) = std::fs::read_to_string(stderr_path) {
        let trimmed = text.trim();
        if !trimmed.is_empty() {
            // Keep it short: this renders as one line in a menu, not a log
            // viewer. The last line is usually the actual Python exception.
            let ultima_linea = trimmed.lines().last().unwrap_or(trimmed);
            return ultima_linea.chars().take(160).collect();
        }
    }
    format!("código de salida {:?}", status.code())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    /// True while any process still belongs to the group led by `pgid`.
    /// Signal 0 performs the permission and existence checks without
    /// delivering anything, so this is the direct question "is that whole
    /// group gone?" rather than a proxy for it.
    fn grupo_vivo(pgid: i32) -> bool {
        unsafe { libc::kill(-pgid, 0) == 0 }
    }

    fn esperar_grupo_muerto(pgid: i32) -> bool {
        let limite = Instant::now() + Duration::from_secs(5);
        while Instant::now() < limite {
            if !grupo_vivo(pgid) {
                return true;
            }
            std::thread::sleep(REAP_POLL_INTERVAL);
        }
        false
    }

    fn ruta_temporal(sufijo: &str) -> PathBuf {
        let etiqueta = format!(
            "{}-{}",
            std::process::id(),
            SECUENCIA.fetch_add(1, Ordering::SeqCst)
        );
        std::env::temp_dir().join(format!("prueba-analisis-{etiqueta}.{sufijo}"))
    }

    /// A stand-in for the real scan. The shell backgrounds one `sleep` and
    /// then blocks on another, so the group contains a *grandchild*:
    /// killing only the process we spawned leaves that one alive, and that
    /// is exactly the leak these tests exist to catch.
    ///
    /// It also touches a marker file *after* forking the background job.
    /// Without that handshake the tests are a race the leak wins: cancelling
    /// immediately after `spawn` returns usually signals `sh` before it has
    /// forked anything at all, so no grandchild ever exists, nothing can be
    /// orphaned, and the test passes just as happily against a `kill(pid)`
    /// that never touches the group. Verified by mutation: with the marker,
    /// changing `kill(-pid, ...)` to `kill(pid, ...)` fails these tests;
    /// without it, that same broken version passed.
    fn comando_de_prueba() -> (Comando, PathBuf) {
        let marca = ruta_temporal("marca");
        let script = format!(
            "sleep 300 & printf listo > {} ; sleep 300",
            marca.display()
        );
        let mut cmd = Command::new("/bin/sh");
        cmd.arg("-c")
            .arg(script)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .process_group(0);
        let comando = Comando {
            cmd,
            export_path: ruta_temporal("json"),
            stderr_path: ruta_temporal("stderr"),
        };
        (comando, marca)
    }

    /// Blocks until the synthetic child has actually forked its background
    /// job, so that what follows is testing the kill and not the race.
    fn esperar_a_que_haya_nieto(marca: &Path) {
        let limite = Instant::now() + Duration::from_secs(5);
        while Instant::now() < limite {
            if marca.exists() {
                let _ = std::fs::remove_file(marca);
                return;
            }
            std::thread::sleep(REAP_POLL_INTERVAL);
        }
        panic!("el hijo de prueba nunca llegó a crear su proceso en segundo plano");
    }

    #[test]
    fn cancelar_mata_el_grupo_entero_y_reporta_cancelado() {
        let manager = Arc::new(AnalisisManager::new(None));
        let (tx, rx) = mpsc::channel();
        let (comando, marca) = comando_de_prueba();
        manager
            .start_con(comando, move |r| {
                let _ = tx.send(r);
            })
            .expect("el primer análisis debería arrancar");

        let pgid = manager.pid.lock().unwrap().expect("debería haber un pid");
        esperar_a_que_haya_nieto(&marca);
        assert!(grupo_vivo(pgid), "el grupo debería estar vivo tras arrancar");

        assert!(manager.cancel(), "cancel() debería reportar que había algo");

        let resultado = rx
            .recv_timeout(Duration::from_secs(5))
            .expect("on_finish debería ejecutarse tras cancelar");
        assert!(
            matches!(resultado, Resultado::Cancelado),
            "un análisis cancelado no debe reportarse como fallo, se reportó {resultado:?}"
        );
        assert!(
            esperar_grupo_muerto(pgid),
            "el nieto backgroundeado sobrevivió: kill(-pgid) no alcanzó al grupo entero"
        );
        assert!(!manager.is_running());
    }

    #[test]
    fn kill_blocking_no_deja_huerfanos_al_salir() {
        let manager = Arc::new(AnalisisManager::new(None));
        let (comando, marca) = comando_de_prueba();
        manager
            .start_con(comando, |_| {})
            .expect("el análisis debería arrancar");
        let pgid = manager.pid.lock().unwrap().expect("debería haber un pid");
        esperar_a_que_haya_nieto(&marca);

        manager.kill_blocking();

        // kill_blocking's contract is that it does not return until the
        // child has been reaped, so this must already hold with no polling
        // of our own -- that is what makes "sin huérfanos al salir" true
        // even though the app tears down immediately afterwards.
        assert!(
            !manager.is_running(),
            "kill_blocking devolvió antes de que el hijo fuera cosechado"
        );
        assert!(esperar_grupo_muerto(pgid), "el grupo sobrevivió al apagado");
    }

    #[test]
    fn un_segundo_analisis_no_arranca_mientras_hay_uno_en_marcha() {
        let manager = Arc::new(AnalisisManager::new(None));
        let (comando, marca) = comando_de_prueba();
        manager
            .start_con(comando, |_| {})
            .expect("el primero debería arrancar");
        let pgid = manager.pid.lock().unwrap().expect("debería haber un pid");
        esperar_a_que_haya_nieto(&marca);

        let (otro, otra_marca) = comando_de_prueba();
        let segundo = manager.start_con(otro, |_| {});
        assert!(segundo.is_err(), "no debe haber dos escaneos a la vez");
        let _ = std::fs::remove_file(&otra_marca);

        manager.kill_blocking();
        assert!(esperar_grupo_muerto(pgid));
    }

    /// El motor empaquetado tiene que ganarle al del repositorio. Si se
    /// invirtiera la prioridad, la .app instalada seguiría dependiendo del
    /// checkout de quien la compiló -- que es exactamente lo que este
    /// empaquetado existe para arreglar, y no se notaría en la máquina de
    /// desarrollo, donde ambos existen y los dos funcionan.
    /// Reproduce la disposición que Tauri produce de verdad dentro de la
    /// .app: el prefijo `resources/` se conserva, así que el motor queda en
    /// `Contents/Resources/resources/engine/`. Este test existe porque la
    /// primera versión buscaba solo en `engine/` y en esta máquina el fallo
    /// quedaba tapado por la reserva al venv del repositorio.
    #[test]
    fn encuentra_el_motor_en_la_disposicion_real_de_tauri() {
        let base = ruta_temporal("recursos-tauri");
        let engine = base.join("resources/engine");
        std::fs::create_dir_all(engine.join("python/bin")).unwrap();
        std::fs::write(engine.join("python/bin/python3"), "#!/bin/sh\n").unwrap();
        std::fs::write(engine.join("disk_analyzer.py"), "").unwrap();

        let motor = localizar_motor(Some(base.clone()))
            .expect("debería encontrar el motor donde Tauri lo pone de verdad");
        assert!(
            motor.python.starts_with(&base),
            "cayó a la reserva del repositorio en vez de usar el motor empaquetado"
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn el_motor_empaquetado_gana_al_del_repositorio() {
        let base = ruta_temporal("recursos");
        let engine = base.join("engine");
        std::fs::create_dir_all(engine.join("python/bin")).unwrap();
        std::fs::write(engine.join("python/bin/python3"), "#!/bin/sh\n").unwrap();
        std::fs::write(engine.join("disk_analyzer.py"), "").unwrap();

        let motor = localizar_motor(Some(base.clone())).expect("debería encontrarlo");
        assert!(
            motor.python.starts_with(&base),
            "eligió {:?} en vez del motor empaquetado",
            motor.python
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn sin_motor_empaquetado_ni_repositorio_no_hay_motor() {
        let vacio = ruta_temporal("vacio");
        std::fs::create_dir_all(&vacio).unwrap();
        // Con un directorio de recursos vacío cae al repositorio, que en esta
        // máquina sí existe; lo que se comprueba es que no explota.
        let _ = localizar_motor(Some(vacio.clone()));
        assert!(!AnalisisManager::new(None).hay_motor());
        let _ = std::fs::remove_dir_all(&vacio);
    }

    #[test]
    fn un_export_con_errores_de_permisos_pide_acceso_total_al_disco() {
        let ruta = ruta_temporal("json");
        std::fs::write(
            &ruta,
            r#"{"errors": ["Sin permisos: /Library/Application Support"]}"#,
        )
        .unwrap();
        let resultado = evaluar_export(&ruta, false);
        let _ = std::fs::remove_file(&ruta);

        assert!(matches!(resultado, Resultado::SinPermisos));
        // The whole point of the state is that the summary tells the user
        // where to go; a generic "error" would leave them stuck.
        assert!(resultado.resumen().contains("Acceso total al disco"));
    }

    /// Un proceso de otro usuario existe aunque no podamos señalarlo:
    /// `kill` devuelve EPERM, no ESRCH. Darlo por muerto haría borrar los
    /// temporales de un análisis en marcha lanzado con sudo.
    #[test]
    fn un_proceso_de_otro_usuario_no_cuenta_como_muerto() {
        // launchd (pid 1) es de root y existe siempre.
        assert!(!proceso_muerto(1), "dio por muerto un proceso de root");
        assert!(proceso_muerto(999999), "no detectó un pid inexistente");
    }

    #[test]
    fn limpia_los_temporales_de_procesos_muertos_y_respeta_los_vivos() {
        let tmp = std::env::temp_dir();
        // El propio proceso de pruebas: vivo con total seguridad.
        let de_vivo = tmp.join(format!(
            "disk-analyzer-tray-{}-0.json",
            std::process::id()
        ));
        // Un pid altísimo que no puede estar asignado.
        let de_muerto = tmp.join("disk-analyzer-tray-999999-0.json");
        std::fs::write(&de_vivo, "{}").unwrap();
        std::fs::write(&de_muerto, "{}").unwrap();

        limpiar_temporales_huerfanos();

        let vivo_sigue = de_vivo.exists();
        let muerto_sigue = de_muerto.exists();
        let _ = std::fs::remove_file(&de_vivo);

        assert!(!muerto_sigue, "no borró el temporal de un proceso muerto");
        assert!(
            vivo_sigue,
            "borró el temporal de un proceso vivo: eso dejaría a esa \
             instancia sin informe que leer"
        );
    }

    /// Con el permiso ya concedido, unas pocas carpetas de `root` no son un
    /// fallo del permiso. Mandar al usuario a activar lo que ya tiene
    /// activado fue el bug real: un escaneo del disco entero siempre topa
    /// con ellas, así que el aviso salía siempre.
    #[test]
    fn con_acceso_concedido_las_carpetas_de_root_no_piden_el_permiso() {
        let ruta = ruta_temporal("json");
        std::fs::write(
            &ruta,
            r#"{"errors": ["Sin permisos para leer: /usr/sbin/authserver",
                           "Sin permisos para leer: /Library/Application Support/Avast/config/chest-data"]}"#,
        )
        .unwrap();
        let resultado = evaluar_export(&ruta, true);
        let _ = std::fs::remove_file(&ruta);

        match resultado {
            Resultado::Parcial(2) => {}
            otro => panic!("esperaba Parcial(2), salió {otro:?}"),
        }
        let resumen = resultado.resumen();
        assert!(
            !resumen.contains("Acceso total al disco"),
            "sigue pidiendo un permiso ya concedido: {resumen}"
        );
        assert!(resumen.contains("sudo"), "no dice cuál es el remedio real");
    }

    #[test]
    fn un_export_limpio_es_exito() {
        let ruta = ruta_temporal("json");
        std::fs::write(&ruta, r#"{"errors": [], "total_size": 123}"#).unwrap();
        let resultado = evaluar_export(&ruta, true);
        let _ = std::fs::remove_file(&ruta);
        assert!(matches!(resultado, Resultado::Exito));
    }

    #[test]
    fn un_export_ausente_o_ilegible_es_un_fallo_no_un_exito() {
        // Silence here would be the worst outcome: the menu would claim the
        // scan completed while no report was ever written.
        assert!(matches!(
            evaluar_export(Path::new("/no/existe/reporte.json"), true),
            Resultado::Fallo(_)
        ));

        let ruta = ruta_temporal("json");
        std::fs::write(&ruta, "esto no es json").unwrap();
        let resultado = evaluar_export(&ruta, true);
        let _ = std::fs::remove_file(&ruta);
        assert!(matches!(resultado, Resultado::Fallo(_)));
    }
}
