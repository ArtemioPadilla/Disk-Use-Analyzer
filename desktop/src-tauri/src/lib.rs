use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;

use tauri::image::Image;
use tauri::menu::{CheckMenuItem, IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::Manager;
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};

pub mod ajustes;
pub mod analisis;
pub mod anillo;
pub mod avisos;
pub mod categorias;
pub mod desglose;
pub mod disk;
pub mod estado;
pub mod liberar;
pub mod memoria;
pub mod menu_nativo;
pub mod notificar;
pub mod progreso;
pub mod servidor;

use ajustes::{Ajustes, Etiqueta, PaletaId};
use analisis::AnalisisManager;
use categorias::{Categoria, Reparto};
use disk::DiskUsage;
use liberar::Liberador;
use servidor::Servidor;

/// Disk usage costs 0.7 µs to read (measured) -- 5s is plenty responsive
/// without needing any justification for the cost.
const POLL_INTERVAL: Duration = Duration::from_secs(5);

/// How often, in poller ticks, the swap culprit is re-measured. Finding it
/// runs `top`, which samples for about a second, so it is not done on every
/// 5-second tick — once a minute is plenty for something that changes slowly.
const TICKS_POR_CULPABLE: u32 = 12;

/// How often the category split is re-measured. It runs `du` over the cache
/// folders (and, with Full Disk Access, the user's folders), which takes
/// seconds and spins the disk; the split changes slowly, the free gap is the
/// part that has to be live, and that one is redrawn on every tick anyway.
const INTERVALO_CATEGORIAS: Duration = Duration::from_secs(30 * 60);

/// Time between frames of the "working" sweep: a turn every ~1.4 s.
const FOTOGRAMA: Duration = Duration::from_millis(120);

/// Whether this process is running from a packaged `.app` bundle.
///
/// Launch-at-login registers the path of the running executable. From
/// `cargo run` or a test, that path is a `target/debug` binary, and
/// registering it would leave a login item pointing at a build artefact.
fn es_app_empaquetada(ejecutable: &std::path::Path) -> bool {
    ejecutable
        .to_string_lossy()
        .contains(".app/Contents/MacOS/")
}

/// Turns launch-at-login on the first time the packaged app runs, and from
/// then on respects whatever the user chose in the menu. Returns whether it is
/// on.
///
/// The user asked for the app to start with the computer: it didn't after a
/// reboot, so they never saw the disk filling up. On by default for that
/// reason — but only once, via a marker file, so switching it off sticks.
fn configurar_arranque(app: &tauri::App) -> bool {
    let auto = app.autolaunch();
    let Some(dir) = app.path().app_config_dir().ok() else {
        return auto.is_enabled().unwrap_or(false);
    };
    let marcador = dir.join("arranque-configurado");
    if !marcador.exists() {
        let _ = auto.enable();
        let _ = std::fs::create_dir_all(&dir);
        let _ = std::fs::write(&marcador, "");
    } else if auto.is_enabled().unwrap_or(false) {
        // Re-register every launch so the login item follows the app if it
        // was moved or replaced by an update.
        let _ = auto.enable();
    }
    auto.is_enabled().unwrap_or(false)
}

fn gb(bytes: u64) -> f64 {
    bytes as f64 / (1024.0 * 1024.0 * 1024.0)
}

fn cifra(bytes: u64) -> String {
    format!("{:.1}", gb(bytes)).replace('.', ",")
}

/// The free figure leads: it's the number that actually drives
/// `estado::classify`'s thresholds (25 GB / 75 GB), so it's the one that
/// explains *why* the icon is the color it is.
fn texto_libre(u: &DiskUsage) -> String {
    let base = format!("{} GB libres de {} GB", cifra(u.available), cifra(u.total));
    // Purgeable space is shown apart, never added to the free figure: like
    // swap, it is disk the user can neither see in Finder nor delete, and
    // macOS gives it back only when it decides to.
    if gb(u.purgeable) >= 1.0 {
        format!("{base} (+{} GB purgables)", cifra(u.purgeable))
    } else {
        base
    }
}

fn color_de(c: Categoria, colores: &ajustes::Colores) -> ajustes::Rgb {
    match c {
        Categoria::Docker => colores.docker,
        Categoria::Caches => colores.caches,
        Categoria::Tuyo => colores.tuyo,
        Categoria::Resto => colores.resto,
    }
}

fn icono_punto(c: Categoria, colores: &ajustes::Colores) -> Option<Image<'static>> {
    Image::from_bytes(&anillo::png_punto(color_de(c, colores))?).ok()
}

/// One menu row per category, in the ring's order.
type FilasCategorias = Vec<(Categoria, Submenu<tauri::Wry>)>;

fn poner_puntos(filas: &FilasCategorias, colores: &ajustes::Colores) {
    for (c, item) in filas {
        let _ = item.set_icon(icono_punto(*c, colores));
    }
}

/// Adds or removes a row below the scan status. There is no hidden state for
/// a menu item, and an empty line would look like a glitch.
fn poner_fila(
    menu: &Menu<tauri::Wry>,
    item: &MenuItem<tauri::Wry>,
    puesta: &AtomicBool,
    texto: Option<&str>,
) {
    match texto {
        Some(t) => {
            let _ = item.set_text(t);
            if !puesta.swap(true, Ordering::SeqCst) {
                let estado = menu
                    .items()
                    .ok()
                    .and_then(|v| v.iter().position(|i| i.id().as_ref() == ID_ESTADO));
                if let Some(pos) = estado {
                    let _ = menu.insert(item, pos + 1);
                }
            }
        }
        None => {
            if puesta.swap(false, Ordering::SeqCst) {
                let _ = menu.remove(item);
            }
        }
    }
}

const ID_ESTADO: &str = "estado_analisis";

/// How many apps the swap submenu offers to close.
const APPS_DE_SWAP: usize = 3;

/// Rebuilds the swap submenu, only when it says something new.
fn poner_swap(
    app: &tauri::AppHandle,
    submenu: &Submenu<tauri::Wry>,
    actuales: &mut Vec<liberar::Fila>,
    cerrables: &[(String, u64)],
) {
    let nuevas = liberar::filas_swap(cerrables);
    if nuevas != *actuales {
        liberar::poner_filas(app, submenu, &nuevas);
        *actuales = nuevas;
    }
}

/// The rows a scan touches.
#[derive(Clone)]
struct FilasAnalisis {
    menu: Menu<tauri::Wry>,
    analizar: Submenu<tauri::Wry>,
    estado: MenuItem<tauri::Wry>,
    detalle: MenuItem<tauri::Wry>,
    detalle_puesta: Arc<AtomicBool>,
    cancelar: MenuItem<tauri::Wry>,
    cancelar_puesta: Arc<AtomicBool>,
    informe: MenuItem<tauri::Wry>,
}

impl FilasAnalisis {
    fn empieza(&self) {
        let _ = self.analizar.set_enabled(false);
        let _ = self.cancelar.set_enabled(true);
        poner_fila(
            &self.menu,
            &self.cancelar,
            &self.cancelar_puesta,
            Some("Cancelar análisis"),
        );
    }

    fn termina(&self) {
        let _ = self.analizar.set_enabled(true);
        poner_fila(&self.menu, &self.detalle, &self.detalle_puesta, None);
        poner_fila(&self.menu, &self.cancelar, &self.cancelar_puesta, None);
        let _ = self.informe.set_enabled(analisis::ruta_informe().exists());
    }
}

/// Starts a scan of `ruta` and keeps the menu up to date until it ends.
fn iniciar_analisis(
    app: &tauri::AppHandle,
    manager: &Arc<AnalisisManager>,
    filas: &FilasAnalisis,
    liberador: &Arc<Liberador>,
    ruta: &std::path::Path,
    nombre: &str,
) {
    if manager.is_running() {
        return;
    }
    let pintor = app.try_state::<Arc<Pintor>>().map(|p| Arc::clone(&p));
    let pintor_fin = pintor.clone();
    let liberador_fin = Arc::clone(liberador);
    let filas_fin = filas.clone();
    let app_fin = app.clone();
    // Held while writing the status line, and set once the scan is over: the
    // progress thread and the start below must never overwrite the final
    // summary.
    let terminado = Arc::new(Mutex::new(false));
    let terminado_fin = Arc::clone(&terminado);
    // Before `start`, not after: a scan that ends at once would otherwise stop
    // the sweep before it began, and leave it spinning for good.
    if let Some(p) = pintor.as_ref() {
        p.animar();
    }
    filas.empieza();
    let inicio = manager.start(ruta, move |resultado| {
        let mut fin = terminado_fin.lock().unwrap();
        *fin = true;
        let _ = filas_fin.estado.set_text(resultado.resumen());
        filas_fin.termina();
        drop(fin);
        menu_nativo::aplicar(&app_fin);
        if let Some(p) = pintor_fin {
            p.parar();
        }
        liberador_fin.refrescar();
    });
    match inicio {
        Ok(()) => {
            let filas = filas.clone();
            let manager = Arc::clone(manager);
            let app = app.clone();
            let poner = move |estado: &str, cuentas: Option<&str>| {
                let fin = terminado.lock().unwrap();
                if !*fin {
                    let _ = filas.estado.set_text(estado);
                    poner_fila(&filas.menu, &filas.detalle, &filas.detalle_puesta, cuentas);
                    menu_nativo::aplicar(&app);
                }
                !*fin
            };
            poner(&format!("Analizando {nombre}…"), None);
            std::thread::spawn(move || loop {
                std::thread::sleep(Duration::from_secs(1));
                let Some(p) = manager.progreso() else {
                    if manager.is_running() {
                        continue;
                    }
                    break;
                };
                let (estado, cuentas) = p.lineas();
                if !poner(&estado, cuentas.as_deref()) {
                    break;
                }
            });
        }
        Err(e) => {
            if let Some(p) = pintor.as_ref() {
                p.parar();
            }
            filas.termina();
            let _ = filas.estado.set_text(format!("No se pudo iniciar: {e}"));
            menu_nativo::aplicar(app);
        }
    }
}

fn icono_anillo(uso: &DiskUsage, reparto: &Reparto, ajustes: &Ajustes) -> Option<Image<'static>> {
    let t = anillo::trozos(uso, reparto, &ajustes.paleta.colores());
    Image::from_bytes(&anillo::png(&t)?).ok()
}

/// Draws the tray: the ring and the text beside it. Shared by the poller,
/// the category measurer and the menu, so a change of palette or label shows
/// at once instead of on the next tick.
struct Pintor {
    tray: TrayIcon,
    ajustes: Arc<Mutex<Ajustes>>,
    reparto: Arc<Mutex<Reparto>>,
    /// What is on screen now. Redrawing only on change: swapping the tray
    /// image every 5 s makes it flicker on some macOS versions.
    ultimo: Mutex<(Vec<anillo::Trozo>, String)>,
    /// How many things (a scan, a cleanup) want the sweep running now.
    animando: AtomicUsize,
    /// Whether the thread that draws the sweep is alive, so a quick
    /// stop-start never ends up with two of them.
    hilo_animacion: AtomicBool,
    /// How full the ring is while a cleanup runs. `None` means the length of
    /// the work is unknown, which is what the sweep says.
    llenado: Mutex<Option<f64>>,
    /// Asks for the category split to be measured again now. Holds one request:
    /// several while a measure runs come to the same new measure.
    remedir: mpsc::SyncSender<()>,
}

/// Waits for the next pass over the categories. True when it is the periodic one,
/// which also lists what can be freed; a cleanup that asks for a pass has its own
/// way of doing that, and listing it twice would run the slow measures for nothing.
fn esperar_repaso(pedidos: &mpsc::Receiver<()>, tope: Duration) -> bool {
    !matches!(pedidos.recv_timeout(tope), Ok(()))
}

impl Pintor {
    fn pintar(&self, uso: &DiskUsage) {
        let ajustes = *self.ajustes.lock().unwrap();
        let reparto = *self.reparto.lock().unwrap();
        let trozos = anillo::trozos(uso, &reparto, &ajustes.paleta.colores());
        let titulo = ajustes.texto(gb(uso.available), uso.percent);
        let mut ultimo = self.ultimo.lock().unwrap();
        if ultimo.0 != trozos {
            // While the sweep runs it draws every frame from `ultimo`, so it
            // picks this change up on its own.
            if self.animando.load(Ordering::SeqCst) == 0 {
                self.poner_icono(anillo::png(&trozos));
            }
            ultimo.0 = trozos;
        }
        if ultimo.1 != titulo {
            // The percentage stays while a cleanup runs; `llenar` puts this back.
            if self.llenado.lock().unwrap().is_none() {
                let _ = self.tray.set_title(Some(&titulo));
            }
            ultimo.1 = titulo;
        }
    }
}

impl Pintor {
    fn poner_icono(&self, png: Option<Vec<u8>>) {
        if let Some(img) = png.and_then(|b| Image::from_bytes(&b).ok()) {
            let _ = self.tray.set_icon(Some(img));
        }
    }

    /// Starts the sweep over the ring. Every call needs one `parar`.
    fn animar(self: &Arc<Self>) {
        self.animando.fetch_add(1, Ordering::SeqCst);
        if self.hilo_animacion.swap(true, Ordering::SeqCst) {
            return;
        }
        let yo = Arc::clone(self);
        std::thread::spawn(move || loop {
            let mut n = 0;
            while yo.animando.load(Ordering::SeqCst) > 0 {
                let trozos = yo.ultimo.lock().unwrap().0.clone();
                let llenado = *yo.llenado.lock().unwrap();
                yo.poner_icono(match llenado {
                    Some(f) => anillo::png_llenado(&trozos, f, n),
                    None => anillo::png_barrido(&trozos, n),
                });
                n = (n + 1) % anillo::FOTOGRAMAS;
                std::thread::sleep(FOTOGRAMA);
            }
            let trozos = yo.ultimo.lock().unwrap().0.clone();
            yo.poner_icono(anillo::png(&trozos));
            yo.hilo_animacion.store(false, Ordering::SeqCst);
            // Someone may have started it again between the loop seeing zero
            // and the flag going down; if so, keep going in this thread.
            if yo.animando.load(Ordering::SeqCst) == 0
                || yo.hilo_animacion.swap(true, Ordering::SeqCst)
            {
                break;
            }
        });
    }

    /// Fills the ring and says the percentage beside it, or with `None` goes back
    /// to the sweep and the usual text. Drawn by the thread `animar` started.
    fn llenar(&self, fraccion: Option<f64>) {
        *self.llenado.lock().unwrap() = fraccion;
        let titulo = match fraccion {
            Some(f) => format!("{} %", (f * 100.0).floor() as u32),
            None => self.ultimo.lock().unwrap().1.clone(),
        };
        let _ = self.tray.set_title(Some(&titulo));
    }

    fn parar(&self) {
        let _ = self
            .animando
            .try_update(Ordering::SeqCst, Ordering::SeqCst, |n| n.checked_sub(1));
    }
}

fn como_menu(items: &[CheckMenuItem<tauri::Wry>]) -> Vec<&dyn IsMenuItem<tauri::Wry>> {
    items
        .iter()
        .map(|i| i as &dyn IsMenuItem<tauri::Wry>)
        .collect()
}

/// Makes a group of check items behave like radio buttons: macOS toggles the
/// clicked one on its own, so every item is set explicitly.
fn marcar_uno(items: &[CheckMenuItem<tauri::Wry>], elegido: usize) {
    for (i, item) in items.iter().enumerate() {
        let _ = item.set_checked(i == elegido);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .setup(|app| {
            // A menu bar app must not appear in the Dock or Cmd+Tab.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            // Read once, synchronously, before the tray exists, so the very
            // first frame already shows the real disk state instead of a
            // placeholder that only gets corrected 5s later by the poller.
            let lectura_inicial = disk::read();
            let dir_ajustes = app.path().app_config_dir().ok();
            let ajustes_iniciales = dir_ajustes
                .as_deref()
                .map(Ajustes::cargar)
                .unwrap_or_default();
            let ajustes = Arc::new(Mutex::new(ajustes_iniciales));
            let reparto = Arc::new(Mutex::new(Reparto::default()));

            let libre_item = MenuItem::with_id(
                app,
                "libre",
                lectura_inicial
                    .as_ref()
                    .map(texto_libre)
                    .unwrap_or_else(|| "Libre: no disponible".to_string()),
                false,
                None::<&str>,
            )?;
            let filas_categorias: FilasCategorias = Categoria::TODAS
                .iter()
                .map(|c| {
                    Submenu::with_id_and_icon(
                        app,
                        format!("categoria:{}", c.nombre()),
                        format!("{}\t…", c.nombre()),
                        true,
                        icono_punto(*c, &ajustes_iniciales.paleta.colores()),
                    )
                    .map(|m| (*c, m))
                })
                .collect::<tauri::Result<_>>()?;
            let titulo = |t: &str| MenuItem::new(app, t, false, None::<&str>);
            let titulo_disco = titulo("Disco")?;
            let titulo_memoria = titulo("Memoria")?;
            let titulo_analisis = titulo("Análisis")?;
            let detalle_item = MenuItem::new(app, "", false, None::<&str>)?;
            let cancelar_item =
                MenuItem::with_id(app, "cancelar", "Cancelar análisis", true, None::<&str>)?;
            let informe_item = MenuItem::with_id(
                app,
                "ultimo_informe",
                "Ver último resultado",
                analisis::ruta_informe().exists(),
                None::<&str>,
            )?;
            let analizar_menu = Submenu::with_items(
                app,
                "Analizar",
                true,
                &[
                    &MenuItem::with_id(
                        app,
                        "analizar:disco",
                        "Disco completo",
                        true,
                        Some("Cmd+R"),
                    )?,
                    &MenuItem::with_id(
                        app,
                        "analizar:personal",
                        "Carpeta personal",
                        true,
                        None::<&str>,
                    )?,
                    &MenuItem::with_id(
                        app,
                        "analizar:elegir",
                        "Elegir carpeta…",
                        true,
                        None::<&str>,
                    )?,
                    &PredefinedMenuItem::separator(app)?,
                    &informe_item,
                ],
            )?;
            let estado_analisis_item =
                MenuItem::with_id(app, ID_ESTADO, "Sin análisis reciente", false, None::<&str>)?;
            let abrir_item = MenuItem::with_id(
                app,
                "abrir",
                "Abrir analizador completo",
                true,
                Some("Cmd+O"),
            )?;
            let empaquetada = std::env::current_exe()
                .map(|e| es_app_empaquetada(&e))
                .unwrap_or(false);
            let arranque_activo = empaquetada && configurar_arranque(app);
            // Ask now, at startup, rather than on the first low-disk warning:
            // the system prompt would otherwise appear exactly when the user
            // is busiest, and the warning itself would be lost behind it.
            notificar::pedir_permiso(empaquetada);
            let arranque_item = CheckMenuItem::with_id(
                app,
                "arranque",
                "Abrir al iniciar sesión",
                empaquetada,
                arranque_activo,
                None::<&str>,
            )?;
            let swap_inicial = memoria::swap_usado().map(gb).unwrap_or(0.0);
            let swap_menu = Submenu::new(app, memoria::texto_swap(swap_inicial), true)?;
            liberar::poner_filas(app.handle(), &swap_menu, &liberar::filas_swap(&[]));
            let quit_item = MenuItem::with_id(
                app,
                "quit",
                "Salir de Disk Use Analyzer",
                true,
                Some("Cmd+Q"),
            )?;

            let etiqueta_items = Etiqueta::TODAS
                .iter()
                .enumerate()
                .map(|(i, e)| {
                    CheckMenuItem::with_id(
                        app,
                        format!("etiqueta:{i}"),
                        e.nombre(),
                        true,
                        *e == ajustes_iniciales.etiqueta,
                        None::<&str>,
                    )
                })
                .collect::<tauri::Result<Vec<_>>>()?;
            let paleta_items = PaletaId::TODAS
                .iter()
                .enumerate()
                .map(|(i, p)| {
                    CheckMenuItem::with_id(
                        app,
                        format!("paleta:{i}"),
                        p.nombre(),
                        true,
                        *p == ajustes_iniciales.paleta,
                        None::<&str>,
                    )
                })
                .collect::<tauri::Result<Vec<_>>>()?;
            let etiqueta_menu = Submenu::with_items(
                app,
                "Mostrar junto al icono",
                true,
                &como_menu(&etiqueta_items),
            )?;
            let paleta_menu = Submenu::with_items(app, "Colores", true, &como_menu(&paleta_items))?;
            let titulo_desarrollo = titulo("Desarrollo")?;
            let proyectos_menu = Submenu::new(app, "Proyectos\t…", true)?;
            let worktrees_menu = Submenu::new(app, "Worktrees\t…", true)?;
            let ambientes_menu = Submenu::new(app, "Ambientes\t…", true)?;
            let seguro_item = MenuItem::with_id(
                app,
                format!("{}{}", liberar::PREFIJO, liberar::TODO),
                "Midiendo lo que se puede liberar…",
                false,
                None::<&str>,
            )?;

            let ajustes_menu = Submenu::with_items(
                app,
                "Ajustes",
                true,
                &[&etiqueta_menu, &paleta_menu, &arranque_item],
            )?;

            let mut filas_menu: Vec<&dyn IsMenuItem<tauri::Wry>> = vec![&titulo_disco, &libre_item];
            filas_menu.extend(
                filas_categorias
                    .iter()
                    .map(|(_, i)| i as &dyn IsMenuItem<tauri::Wry>),
            );
            let separador = || PredefinedMenuItem::separator(app);
            let (sep1, sep2, sep3, sep4, sep5) = (
                separador()?,
                separador()?,
                separador()?,
                separador()?,
                separador()?,
            );
            filas_menu.extend([
                &sep1 as &dyn IsMenuItem<tauri::Wry>,
                &titulo_desarrollo,
                &proyectos_menu,
                &worktrees_menu,
                &ambientes_menu,
                &sep5,
                &titulo_memoria,
                &swap_menu,
                &sep2,
                &titulo_analisis,
                &analizar_menu,
                &estado_analisis_item,
                &sep3,
                &seguro_item,
                &abrir_item,
                &sep4,
                &ajustes_menu,
                &quit_item,
            ]);
            let menu = Menu::with_items(app, &filas_menu)?;

            // El motor empaquetado dentro de la .app es el que hace que la
            // app sea autocontenida; si no está (modo desarrollo), se cae al
            // venv del repositorio.
            // Barrer antes de nada lo que dejó un cierre forzoso anterior.
            analisis::limpiar_temporales_huerfanos();

            let motor = analisis::localizar_motor(app.path().resource_dir().ok());
            let hay_motor = motor.is_some();
            let manager = Arc::new(AnalisisManager::new(motor.clone()));
            let servidor = Arc::new(Servidor::new());
            // Managed state so the shutdown handler in `run()` below (which
            // runs outside `setup` and has no closure access to `manager`)
            // can still reach it to guarantee cleanup on any exit path, not
            // just the "quit" menu item.
            app.manage(Arc::clone(&manager));
            app.manage(Arc::clone(&servidor));
            let liberador = Liberador::new(
                app.handle().clone(),
                filas_categorias.clone(),
                seguro_item,
                proyectos_menu,
                worktrees_menu,
                ambientes_menu,
                motor.clone(),
            );

            // Decirlo desde el arranque, no solo al pulsar: sin motor, el
            // indicador de disco sigue siendo perfectamente útil, así que la
            // app no se rompe -- pero el usuario tiene que saber por qué esa
            // opción está apagada.
            if !hay_motor {
                let _ = analizar_menu.set_enabled(false);
                let _ = estado_analisis_item.set_text("Motor de análisis no encontrado");
            } else if !analisis::hay_acceso_total_al_disco() {
                // Decirlo al arrancar y no al terminar: el escaneo del disco
                // completo tarda un par de minutos, y hacer esperar todo eso
                // para anunciar un permiso que falta desde el principio es
                // gratuito.
                let _ = estado_analisis_item
                    .set_text("Sin acceso total al disco: el análisis saldrá incompleto");
            }

            let mut tray_builder = TrayIconBuilder::with_id(menu_nativo::ID_BANDEJA)
                .menu(&menu)
                .show_menu_on_left_click(true);
            let icono_inicial = lectura_inicial
                .as_ref()
                .and_then(|u| icono_anillo(u, &Reparto::default(), &ajustes_iniciales));
            match icono_inicial {
                Some(icon) => tray_builder = tray_builder.icon(icon),
                _ => {
                    // Disk read (or icon decode) failed at startup: fall
                    // back to the bundle icon rather than showing nothing.
                    if let Some(icon) = app.default_window_icon() {
                        tray_builder = tray_builder.icon(icon.clone());
                    }
                }
            }

            let tray = {
                let manager = Arc::clone(&manager);
                let servidor = Arc::clone(&servidor);
                let motor_web = motor.clone();
                let abrir_item = abrir_item.clone();
                let arranque_item = arranque_item.clone();
                let filas_analisis = FilasAnalisis {
                    menu: menu.clone(),
                    analizar: analizar_menu.clone(),
                    estado: estado_analisis_item.clone(),
                    detalle: detalle_item.clone(),
                    detalle_puesta: Arc::new(AtomicBool::new(false)),
                    cancelar: cancelar_item.clone(),
                    cancelar_puesta: Arc::new(AtomicBool::new(false)),
                    informe: informe_item.clone(),
                };
                let ajustes = Arc::clone(&ajustes);
                let dir_ajustes = dir_ajustes.clone();
                let liberador = Arc::clone(&liberador);
                let filas_categorias = filas_categorias.clone();
                tray_builder
                    .on_menu_event(move |app, event| {
                        let id = event.id().as_ref();
                        let eleccion = |prefijo: &str| {
                            id.strip_prefix(prefijo)
                                .and_then(|n| n.parse::<usize>().ok())
                        };
                        if let Some(i) =
                            eleccion("etiqueta:").filter(|i| *i < Etiqueta::TODAS.len())
                        {
                            marcar_uno(&etiqueta_items, i);
                            ajustes.lock().unwrap().etiqueta = Etiqueta::TODAS[i];
                        } else if let Some(i) =
                            eleccion("paleta:").filter(|i| *i < PaletaId::TODAS.len())
                        {
                            marcar_uno(&paleta_items, i);
                            ajustes.lock().unwrap().paleta = PaletaId::TODAS[i];
                        }
                        if id.starts_with("etiqueta:") || id.starts_with("paleta:") {
                            let actuales = *ajustes.lock().unwrap();
                            if let Some(dir) = dir_ajustes.as_deref() {
                                let _ = actuales.guardar(dir);
                            }
                            poner_puntos(&filas_categorias, &actuales.paleta.colores());
                            if let (Some(uso), Some(pintor)) =
                                (disk::read(), app.try_state::<Arc<Pintor>>())
                            {
                                pintor.pintar(&uso);
                            }
                            return;
                        }
                        if event.id() == "arranque" {
                            // macOS already flipped the tick; apply whatever
                            // it now shows, then re-read the real state so the
                            // tick never lies if the change failed.
                            let auto = app.autolaunch();
                            let quiere = arranque_item.is_checked().unwrap_or(false);
                            let _ = if quiere {
                                auto.enable()
                            } else {
                                auto.disable()
                            };
                            let _ = arranque_item.set_checked(auto.is_enabled().unwrap_or(false));
                        } else if event.id() == "quit" {
                            // El servidor web también: lo arrancamos nosotros,
                            // así que no debe sobrevivirnos ocupando su puerto.
                            servidor.kill_blocking();
                            // Block briefly (bounded by KILL_REAP_TIMEOUT)
                            // so the scan's process group is confirmed dead
                            // before the app actually tears down -- "no
                            // orphans on quit" has to hold regardless of
                            // whether RunEvent::ExitRequested also fires.
                            manager.kill_blocking();
                            app.exit(0);
                        } else if let Some(que) = id.strip_prefix(liberar::PREFIJO) {
                            let Some(pintor) = app.try_state::<Arc<Pintor>>() else {
                                return;
                            };
                            let (al_empezar, al_avanzar, al_terminar) = (
                                Arc::clone(&pintor),
                                Arc::clone(&pintor),
                                Arc::clone(&pintor),
                            );
                            liberador.pedir(
                                que,
                                move || al_empezar.animar(),
                                move |fraccion| {
                                    al_avanzar.llenar(fraccion);
                                    // The commands ended: what they freed is
                                    // known to Docker and to `du` right now.
                                    if fraccion.is_none() {
                                        let _ = al_avanzar.remedir.try_send(());
                                    }
                                },
                                move |hecho| {
                                    al_terminar.parar();
                                    // Docker's image has finished shrinking, and
                                    // what is not Docker comes out of its size.
                                    if hecho.docker {
                                        let _ = al_terminar.remedir.try_send(());
                                    }
                                    let (titulo, cuerpo) = liberar::aviso_final(hecho);
                                    notificar::enviar(empaquetada, &titulo, &cuerpo);
                                    if let Some(uso) = disk::read() {
                                        al_terminar.pintar(&uso);
                                    }
                                },
                            );
                        } else if let Some(que) = id.strip_prefix(liberar::PREFIJO_EXTERNO) {
                            let home = std::env::var("HOME").unwrap_or_default();
                            if let Some(destino) = liberar::externo_de(que, &home) {
                                let _ = if destino.starts_with('/') {
                                    tauri_plugin_opener::open_path(destino, None::<&str>)
                                } else {
                                    tauri_plugin_opener::open_url(destino, None::<&str>)
                                };
                            }
                        } else if event.id() == "abrir"
                            || id.starts_with(liberar::PREFIJO_ANALIZADOR)
                        {
                            let pagina = id
                                .strip_prefix(liberar::PREFIJO_ANALIZADOR)
                                .unwrap_or("/")
                                .to_string();
                            // Arrancar FastAPI lleva varios segundos, así que
                            // el ítem lo dice en vez de parecer que el clic no
                            // hizo nada.
                            let volver = abrir_item.clone();
                            let _ = abrir_item.set_text("Arrancando el analizador…");
                            let _ = abrir_item.set_enabled(false);
                            servidor.abrir(motor_web.as_ref(), move |resultado| {
                                let _ = volver.set_enabled(true);
                                match resultado {
                                    Ok(url) => {
                                        let _ = volver.set_text("Abrir analizador completo");
                                        let _ = tauri_plugin_opener::open_url(
                                            liberar::url_en(&url, &pagina),
                                            None::<&str>,
                                        );
                                    }
                                    Err(e) => {
                                        let _ = volver.set_text(format!("No se pudo abrir: {e}"));
                                    }
                                }
                            });
                        } else if let Some(que) = id.strip_prefix(liberar::PREFIJO_VER_APP) {
                            if let Some(ruta) = liberador.ruta_de_app(que) {
                                let _ = tauri_plugin_opener::reveal_item_in_dir(ruta);
                            }
                        } else if let Some(que) = id.strip_prefix(liberar::PREFIJO_CERRAR) {
                            let que = que.to_string();
                            app.dialog()
                                .message(
                                    "Se cierra como si eligieras Salir: te preguntará si quieres \
                                     guardar lo que tengas abierto.\n\nEl swap puede tardar en \
                                     bajar. Si no baja, solo se libera al reiniciar.",
                                )
                                .title(format!("¿Cerrar {que}?"))
                                .kind(MessageDialogKind::Warning)
                                .buttons(MessageDialogButtons::OkCancelCustom(
                                    "Cerrar".into(),
                                    "Cancelar".into(),
                                ))
                                .show(move |acepta| {
                                    if acepta && !memoria::cerrar(&que) {
                                        notificar::enviar(
                                            empaquetada,
                                            &format!("No se pudo cerrar {que}"),
                                            "Puede que ya estuviera cerrada.",
                                        );
                                    }
                                });
                        } else if event.id() == "cancelar" {
                            if manager.cancel() {
                                let _ = filas_analisis.cancelar.set_text("Cancelando…");
                                let _ = filas_analisis.cancelar.set_enabled(false);
                            }
                        } else if event.id() == "ultimo_informe" {
                            let _ = tauri_plugin_opener::open_path(
                                analisis::ruta_informe(),
                                None::<&str>,
                            );
                        } else if event.id() == "analizar:disco" {
                            iniciar_analisis(
                                app,
                                &manager,
                                &filas_analisis,
                                &liberador,
                                std::path::Path::new(analisis::RUTA_DISCO),
                                "disco completo",
                            );
                        } else if event.id() == "analizar:personal" {
                            let home = std::env::var("HOME").unwrap_or_default();
                            iniciar_analisis(
                                app,
                                &manager,
                                &filas_analisis,
                                &liberador,
                                std::path::Path::new(&home),
                                "carpeta personal",
                            );
                        } else if event.id() == "analizar:elegir" {
                            let (app, manager, filas, liberador) = (
                                app.clone(),
                                Arc::clone(&manager),
                                filas_analisis.clone(),
                                Arc::clone(&liberador),
                            );
                            app.clone().dialog().file().pick_folder(move |carpeta| {
                                let Some(ruta) = carpeta.and_then(|c| c.into_path().ok()) else {
                                    return;
                                };
                                let nombre = ruta
                                    .file_name()
                                    .map(|n| n.to_string_lossy().into_owned())
                                    .unwrap_or_else(|| ruta.to_string_lossy().into_owned());
                                iniciar_analisis(
                                    &app, &manager, &filas, &liberador, &ruta, &nombre,
                                );
                            });
                        }
                    })
                    .build(app)?
            };

            let (pide_remedir, pedidos_remedir) = mpsc::sync_channel(1);
            let pintor = Arc::new(Pintor {
                tray,
                ajustes: Arc::clone(&ajustes),
                reparto: Arc::clone(&reparto),
                ultimo: Mutex::new((Vec::new(), String::new())),
                animando: AtomicUsize::new(0),
                hilo_animacion: AtomicBool::new(false),
                llenado: Mutex::new(None),
                remedir: pide_remedir,
            });
            app.manage(Arc::clone(&pintor));
            if let Some(uso) = lectura_inicial.as_ref() {
                pintor.pintar(uso);
            }
            menu_nativo::aplicar(app.handle());

            // The category split, measured off the main thread: the first
            // pass runs `du` for a few seconds, and the tray must be up and
            // showing the free gap before that finishes.
            {
                let pintor = Arc::clone(&pintor);
                let liberador = Arc::clone(&liberador);
                let mut listar = true;
                std::thread::spawn(move || loop {
                    // Probed on every pass, not once: cheap, and it also
                    // notices the permission being revoked. Granting it
                    // still needs a relaunch; macOS does not re-evaluate a
                    // running process.
                    let medido = categorias::medir(analisis::hay_acceso_total_al_disco());
                    *pintor.reparto.lock().unwrap() = medido;
                    if let Some(uso) = disk::read() {
                        pintor.pintar(&uso);
                        // On its own thread: it reads a lot, and "Liberar lo
                        // seguro" must not wait for it.
                        let liberador = Arc::clone(&liberador);
                        std::thread::spawn(move || {
                            let acceso = analisis::hay_acceso_total_al_disco();
                            liberador.poner_desglose(desglose::filas(
                                &desglose::medir(acceso),
                                categorias::bytes_de(Categoria::Resto, &uso, &medido),
                                acceso,
                            ));
                        });
                    }
                    // After the split, not before: both run `du`, and the
                    // ring is what the user sees first.
                    if listar {
                        liberador.refrescar();
                    }
                    listar = esperar_repaso(&pedidos_remedir, INTERVALO_CATEGORIAS);
                });
            }

            // Background poller: refresh the texts and the ring every tick;
            // `Pintor` only touches the tray when something visible changed.
            {
                let pintor = Arc::clone(&pintor);
                let libre_item = libre_item.clone();
                let filas_categorias = filas_categorias.clone();
                let app_poller = app.handle().clone();
                let swap_menu = swap_menu.clone();
                let mut filas_swap = liberar::filas_swap(&[]);
                let libre_inicial = lectura_inicial.map(|u| gb(u.available)).unwrap_or(f64::MAX);
                let (mut vigia, aviso_inicial) = avisos::Vigia::al_arrancar(libre_inicial);
                let mut culpable: Option<String> = None;
                let mut tick: u32 = 0;
                std::thread::spawn(move || {
                    let notificar = |aviso: &avisos::Aviso, culpable: &Option<String>| {
                        let swap_gb = memoria::swap_usado().map(gb).unwrap_or(0.0);
                        let swap = culpable
                            .as_deref()
                            .filter(|_| swap_gb >= memoria::UMBRAL_SWAP_GB)
                            .map(|app| (swap_gb, app));
                        let (titulo, cuerpo) = avisos::texto(aviso, swap);
                        notificar::enviar(empaquetada, &titulo, &cuerpo);
                    };
                    if let Some(aviso) = aviso_inicial {
                        culpable = memoria::medir_culpables(0).and_then(|(app, _)| app);
                        notificar(&aviso, &culpable);
                    }
                    loop {
                        std::thread::sleep(POLL_INTERVAL);
                        tick = tick.wrapping_add(1);
                        let swap_gb = memoria::swap_usado().map(gb).unwrap_or(0.0);
                        if swap_gb >= memoria::UMBRAL_SWAP_GB {
                            if culpable.is_none() || tick.is_multiple_of(TICKS_POR_CULPABLE) {
                                let (app, cerrables) =
                                    memoria::medir_culpables(APPS_DE_SWAP).unwrap_or_default();
                                culpable = app;
                                poner_swap(&app_poller, &swap_menu, &mut filas_swap, &cerrables);
                            }
                        } else {
                            culpable = None;
                            poner_swap(&app_poller, &swap_menu, &mut filas_swap, &[]);
                        }
                        let _ = swap_menu.set_text(memoria::texto_swap(swap_gb));
                        match disk::read() {
                            Some(usage) => {
                                let _ = libre_item.set_text(texto_libre(&usage));
                                let reparto = *pintor.reparto.lock().unwrap();
                                if reparto != Reparto::default() {
                                    for (c, item) in &filas_categorias {
                                        let _ =
                                            item.set_text(categorias::fila(*c, &usage, &reparto));
                                    }
                                }
                                if let Some(aviso) = vigia.observar(gb(usage.available)) {
                                    notificar(&aviso, &culpable);
                                }
                                pintor.pintar(&usage);
                            }
                            None => {
                                let _ = libre_item.set_text("Libre: no disponible");
                            }
                        }
                        menu_nativo::aplicar(&app_poller);
                    }
                });
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Defensive backstop: if the app ever exits some other way than
            // the "quit" menu item (which already calls `kill_blocking`
            // itself), still make sure a running scan is killed before the
            // process actually goes away. `kill_blocking` is a no-op when
            // nothing is running, so this is safe to call unconditionally
            // on every exit.
            if let tauri::RunEvent::ExitRequested { .. } = event {
                if let Some(manager) = app_handle.try_state::<Arc<AnalisisManager>>() {
                    manager.kill_blocking();
                }
                if let Some(servidor) = app_handle.try_state::<Arc<Servidor>>() {
                    servidor.kill_blocking();
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::es_app_empaquetada;
    use std::path::Path;

    #[test]
    fn lo_purgable_se_muestra_aparte_y_nunca_suma_como_libre() {
        use super::{texto_libre, DiskUsage};
        let g = 1024 * 1024 * 1024;
        let u = |purgeable| DiskUsage {
            total: 460 * g,
            used: 446 * g,
            available: 14 * g,
            purgeable,
            percent: 97.0,
        };
        assert_eq!(texto_libre(&u(0)), "14,0 GB libres de 460,0 GB");
        assert_eq!(
            texto_libre(&u(g / 2)),
            "14,0 GB libres de 460,0 GB",
            "menos de 1 GB no merece ruido"
        );
        assert_eq!(
            texto_libre(&u(5 * g + g / 2)),
            "14,0 GB libres de 460,0 GB (+5,5 GB purgables)"
        );
    }

    #[test]
    fn solo_la_app_empaquetada_se_registra_para_arrancar() {
        assert!(es_app_empaquetada(Path::new(
            "/Applications/Disk Use Analyzer.app/Contents/MacOS/Disk Use Analyzer"
        )));
        assert!(!es_app_empaquetada(Path::new(
            "/Users/u/repo/desktop/src-tauri/target/debug/desktop"
        )));
    }
}

#[cfg(test)]
mod tests_repaso {
    use super::*;

    #[test]
    fn un_repaso_pedido_no_espera_al_periodico_ni_vuelve_a_listar() {
        let (pide, pedidos) = mpsc::sync_channel(1);
        pide.try_send(()).unwrap();
        // A long limit: if the request were not seen, the test would hang here.
        assert!(!esperar_repaso(&pedidos, Duration::from_secs(600)));
    }

    #[test]
    fn el_repaso_periodico_tambien_lista_lo_que_se_puede_liberar() {
        let (_pide, pedidos) = mpsc::sync_channel::<()>(1);
        assert!(esperar_repaso(&pedidos, Duration::from_millis(1)));
    }

    #[test]
    fn varios_pedidos_mientras_se_mide_acaban_en_un_solo_repaso() {
        let (pide, pedidos) = mpsc::sync_channel(1);
        pide.try_send(()).unwrap();
        assert!(pide.try_send(()).is_err());
        assert!(!esperar_repaso(&pedidos, Duration::from_millis(1)));
        assert!(esperar_repaso(&pedidos, Duration::from_millis(1)));
    }
}
