//! Swap usage, and which app is holding it.
//!
//! Swap lives in files on the same disk, so heavy memory pressure eats disk
//! space: on the development machine it reached 23 GB and left 205 MB free.
//! Nothing a cleanup deletes can recover that — only quitting the app that
//! holds the swapped memory, or rebooting. Naming that app is the point here.
//!
//! The attribution walks the process tree. `top` truncates names to 16
//! characters ("Code Helper (Plu") and a language server shows up as a bare
//! `java`, so neither name tells the user anything. Climbing parent processes
//! until one lives inside a `.app` bundle turns both into "Visual Studio Code".

use std::collections::HashMap;
use std::process::Command;

/// Swap in use, in bytes, read straight from the kernel (`vm.swapusage`).
pub fn swap_usado() -> Option<u64> {
    let mut uso: libc::xsw_usage = unsafe { std::mem::zeroed() };
    let mut tam = std::mem::size_of::<libc::xsw_usage>();
    let nombre = c"vm.swapusage";
    let r = unsafe {
        libc::sysctlbyname(
            nombre.as_ptr(),
            &mut uso as *mut _ as *mut libc::c_void,
            &mut tam,
            std::ptr::null_mut(),
            0,
        )
    };
    (r == 0).then_some(uso.xsu_used)
}

/// Parses a size as `top` prints it: `1946M`, `637M+`, `12K`, `1.2G`, `0B`.
fn bytes_de(texto: &str) -> Option<u64> {
    let t = texto.trim_end_matches(['+', '-']);
    let (num, unidad) = t.split_at(t.len().checked_sub(1)?);
    let n: f64 = num.parse().ok()?;
    let mult = match unidad {
        "B" => 1.0,
        "K" => 1024.0,
        "M" => 1024.0 * 1024.0,
        "G" => 1024.0 * 1024.0 * 1024.0,
        _ => return None,
    };
    Some((n * mult) as u64)
}

/// Rows of `top -l 1 -o cmprs -stats pid,cmprs`: (pid, compressed bytes).
///
/// "Compressed" in `top` covers memory that is compressed in RAM *or* already
/// swapped out to disk, which is the quantity that tracks swap growth.
pub fn parsear_top(salida: &str) -> Vec<(i32, u64)> {
    salida
        .lines()
        .skip_while(|l| !l.trim_start().starts_with("PID"))
        .skip(1)
        .filter_map(|l| {
            let mut campos = l.split_whitespace();
            let pid = campos.next()?.parse().ok()?;
            let bytes = bytes_de(campos.next()?)?;
            Some((pid, bytes))
        })
        .collect()
}

/// `ps -axo pid=,ppid=,comm=` into pid -> (ppid, executable path).
/// The path may contain spaces, so it is everything after the second field.
pub fn parsear_ps(salida: &str) -> HashMap<i32, (i32, String)> {
    salida
        .lines()
        .filter_map(|l| {
            let l = l.trim_start();
            let (pid, resto) = l.split_once(char::is_whitespace)?;
            let resto = resto.trim_start();
            let (ppid, ruta) = resto.split_once(char::is_whitespace)?;
            Some((
                pid.parse().ok()?,
                (ppid.parse().ok()?, ruta.trim().to_string()),
            ))
        })
        .collect()
}

/// The outermost `.app` bundle in a path, without the extension.
/// `/Applications/Visual Studio Code.app/.../Code Helper (Plugin).app/...`
/// gives "Visual Studio Code", not the helper.
fn app_en_ruta(ruta: &str) -> Option<String> {
    ruta.split('/')
        .find(|c| c.ends_with(".app"))
        .map(|c| c.trim_end_matches(".app").to_string())
}

/// The app a process belongs to: its own bundle, or the first ancestor's.
/// Falls back to the executable's name when no ancestor is inside a bundle.
pub fn app_de(pid: i32, tabla: &HashMap<i32, (i32, String)>) -> Option<String> {
    let mut actual = pid;
    // Bounded: a malformed table must not loop forever.
    for _ in 0..32 {
        let (ppid, ruta) = tabla.get(&actual)?;
        if let Some(app) = app_en_ruta(ruta) {
            return Some(app);
        }
        if *ppid <= 1 || *ppid == actual {
            break;
        }
        actual = *ppid;
    }
    let (_, ruta) = tabla.get(&pid)?;
    ruta.rsplit('/').next().map(str::to_string)
}

/// The app holding the most compressed/swapped memory, summed over all of its
/// processes (VS Code alone was 56 of them).
pub fn culpable(top: &[(i32, u64)], tabla: &HashMap<i32, (i32, String)>) -> Option<(String, u64)> {
    let mut por_app: HashMap<String, u64> = HashMap::new();
    for (pid, bytes) in top {
        if let Some(app) = app_de(*pid, tabla) {
            *por_app.entry(app).or_default() += bytes;
        }
    }
    por_app.into_iter().max_by_key(|(_, b)| *b)
}

/// Runs `top` and `ps` and names the app holding the most swapped memory.
/// Costs about a second of `top` sampling, so callers must not run it on
/// every 5-second poll.
pub fn medir_culpable() -> Option<(String, u64)> {
    let top = Command::new("/usr/bin/top")
        .args(["-l", "1", "-o", "cmprs", "-stats", "pid,cmprs", "-n", "40"])
        .output()
        .ok()?;
    let ps = Command::new("/bin/ps")
        .args(["-axo", "pid=,ppid=,comm="])
        .output()
        .ok()?;
    culpable(
        &parsear_top(&String::from_utf8_lossy(&top.stdout)),
        &parsear_ps(&String::from_utf8_lossy(&ps.stdout)),
    )
}

/// Swap worth mentioning in the menu and in notifications. Below this it is
/// ordinary macOS housekeeping, not a cause of a full disk.
pub const UMBRAL_SWAP_GB: f64 = 4.0;

/// The menu line for swap. Names the app only once swap is big enough to
/// matter, so the line does not point fingers at normal usage.
pub fn texto_swap(swap_gb: f64, culpable: Option<&str>) -> String {
    match culpable {
        Some(app) if swap_gb >= UMBRAL_SWAP_GB => {
            format!("Swap: {swap_gb:.1} GB · lo retiene {app}")
        }
        _ => format!("Swap: {swap_gb:.1} GB"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TOP: &str = "Processes: 612 total\nLoad Avg: 2.1\n\nPID    CMPRS\n5773   1946M\n3228   1625M+\n3222   1474M\n956    400M\n77     12K\n";

    const PS: &str = "    1     0 /sbin/launchd
  900     1 /Applications/Visual Studio Code.app/Contents/MacOS/Code
 3228   900 /Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper (Plugin).app/Contents/MacOS/Code Helper (Plugin)
 3222   900 /Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper (Plugin).app/Contents/MacOS/Code Helper (Plugin)
 5773  3228 /Users/u/.vscode/extensions/sonarsource.sonarlint-vscode/jre/bin/java
  950     1 /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
  956   950 /Applications/Brave Browser.app/Contents/Frameworks/Brave Browser Framework.framework/Helpers/Brave Browser Helper.app/Contents/MacOS/Brave Browser Helper
   77     1 /usr/libexec/logd
";

    #[test]
    fn lee_los_tamanos_como_los_imprime_top() {
        assert_eq!(bytes_de("1946M"), Some(1946 * 1024 * 1024));
        assert_eq!(bytes_de("637M+"), Some(637 * 1024 * 1024));
        assert_eq!(bytes_de("12K"), Some(12 * 1024));
        assert_eq!(bytes_de("0B"), Some(0));
        assert_eq!(bytes_de("basura"), None);
    }

    #[test]
    fn parsea_top_saltando_la_cabecera() {
        let filas = parsear_top(TOP);
        assert_eq!(filas.len(), 5);
        assert_eq!(filas[0], (5773, 1946 * 1024 * 1024));
    }

    #[test]
    fn ps_conserva_las_rutas_con_espacios() {
        let t = parsear_ps(PS);
        assert_eq!(t[&900].0, 1);
        assert!(t[&3228].1.ends_with("Code Helper (Plugin)"));
    }

    #[test]
    fn el_java_de_una_extension_se_atribuye_a_vs_code() {
        // El caso real: SonarLint aparece en `top` como `java` a secas.
        let t = parsear_ps(PS);
        assert_eq!(app_de(5773, &t).as_deref(), Some("Visual Studio Code"));
    }

    #[test]
    fn un_helper_anidado_cuenta_para_la_app_de_fuera() {
        let t = parsear_ps(PS);
        assert_eq!(app_de(956, &t).as_deref(), Some("Brave Browser"));
        assert_eq!(app_de(3228, &t).as_deref(), Some("Visual Studio Code"));
    }

    #[test]
    fn fuera_de_un_bundle_usa_el_nombre_del_ejecutable() {
        let t = parsear_ps(PS);
        assert_eq!(app_de(77, &t).as_deref(), Some("logd"));
    }

    #[test]
    fn el_culpable_suma_todos_los_procesos_de_una_app() {
        // VS Code: 1946 + 1625 + 1474 = 5045 MB, contra 400 MB de Brave.
        let (app, bytes) = culpable(&parsear_top(TOP), &parsear_ps(PS)).unwrap();
        assert_eq!(app, "Visual Studio Code");
        assert_eq!(bytes, (1946 + 1625 + 1474) * 1024 * 1024);
    }

    #[test]
    fn una_tabla_con_ciclo_no_se_queda_colgada() {
        let mut t = HashMap::new();
        t.insert(10, (11, "/bin/a".to_string()));
        t.insert(11, (10, "/bin/b".to_string()));
        assert_eq!(app_de(10, &t).as_deref(), Some("a"));
    }

    /// Diagnóstico contra la máquina real: `cargo test --lib en_vivo -- --ignored --nocapture`.
    /// Ignorado por defecto porque su resultado depende de lo que esté abierto.
    #[test]
    #[ignore]
    fn en_vivo() {
        let gb = |b: u64| b as f64 / (1024.0 * 1024.0 * 1024.0);
        println!("swap usado: {:.1} GB", gb(swap_usado().unwrap()));
        let (app, bytes) = medir_culpable().expect("debería encontrar un culpable");
        println!("culpable: {app} con {:.1} GB", gb(bytes));
    }

    #[test]
    fn la_linea_de_swap_solo_senala_culpable_si_el_swap_importa() {
        assert_eq!(texto_swap(0.4, Some("Visual Studio Code")), "Swap: 0.4 GB");
        assert_eq!(
            texto_swap(11.7, Some("Visual Studio Code")),
            "Swap: 11.7 GB · lo retiene Visual Studio Code"
        );
        assert_eq!(texto_swap(11.7, None), "Swap: 11.7 GB");
    }

    #[test]
    fn el_swap_se_lee_del_kernel() {
        // En cualquier Mac la llamada debe responder, aunque el swap sea 0.
        assert!(swap_usado().is_some());
    }
}
