use std::sync::Arc;
use std::time::Duration;

use tauri::image::Image;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::Manager;
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

pub mod analisis;
pub mod avisos;
pub mod disk;
pub mod estado;
pub mod memoria;
pub mod notificar;
pub mod servidor;

use analisis::AnalisisManager;
use disk::DiskUsage;
use estado::Estado;
use servidor::Servidor;

/// Disk usage costs 0.7 µs to read (measured) -- 5s is plenty responsive
/// without needing any justification for the cost.
const POLL_INTERVAL: Duration = Duration::from_secs(5);

/// How often, in poller ticks, the swap culprit is re-measured. Finding it
/// runs `top`, which samples for about a second, so it is not done on every
/// 5-second tick — once a minute is plenty for something that changes slowly.
const TICKS_POR_CULPABLE: u32 = 12;

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

fn texto_uso(u: &DiskUsage) -> String {
    format!(
        "Uso: {:.1} GB / {:.1} GB ({:.0}%)",
        gb(u.used),
        gb(u.total),
        u.percent
    )
}

/// The absolute free-space figure gets its own menu line, not just a
/// percentage: it's the number that actually drives `estado::classify`'s
/// thresholds (25 GB / 75 GB), so it's the one that explains *why* the icon
/// is the color it is.
fn texto_libre(u: &DiskUsage) -> String {
    // Purgeable space is shown apart, never added to the free figure: like
    // swap, it is disk the user can neither see in Finder nor delete, and
    // macOS gives it back only when it decides to.
    if gb(u.purgeable) >= 1.0 {
        format!(
            "Libre: {:.1} GB (+{:.1} GB purgables)",
            gb(u.available),
            gb(u.purgeable)
        )
    } else {
        format!("Libre: {:.1} GB", gb(u.available))
    }
}

/// Icons are embedded at compile time (`include_bytes!`) rather than read
/// from disk at runtime: that way the tray works the same in dev mode and
/// in a future bundled `.app`, independent of the process's working
/// directory.
fn icono_para(estado: Estado) -> tauri::Result<Image<'static>> {
    let bytes: &[u8] = match estado {
        Estado::Ok => include_bytes!("../assets/tray/ok.png"),
        Estado::Aviso => include_bytes!("../assets/tray/aviso.png"),
        Estado::Critico => include_bytes!("../assets/tray/critico.png"),
    };
    Image::from_bytes(bytes)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
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
            let estado_inicial = lectura_inicial.map(estado::classify);

            let uso_item = MenuItem::with_id(
                app,
                "uso",
                lectura_inicial
                    .as_ref()
                    .map(texto_uso)
                    .unwrap_or_else(|| "Uso: no disponible".to_string()),
                false,
                None::<&str>,
            )?;
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
            let analizar_item =
                MenuItem::with_id(app, "analizar", "Analizar ahora", true, None::<&str>)?;
            let estado_analisis_item = MenuItem::with_id(
                app,
                "estado_analisis",
                "Sin análisis reciente",
                false,
                None::<&str>,
            )?;
            let abrir_item = MenuItem::with_id(
                app,
                "abrir",
                "Abrir analizador completo",
                true,
                None::<&str>,
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
            let swap_item = MenuItem::with_id(
                app,
                "swap",
                memoria::texto_swap(swap_inicial, None),
                false,
                None::<&str>,
            )?;
            let quit_item = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;

            let menu = Menu::with_items(
                app,
                &[
                    &uso_item,
                    &libre_item,
                    &swap_item,
                    &PredefinedMenuItem::separator(app)?,
                    &analizar_item,
                    &estado_analisis_item,
                    &PredefinedMenuItem::separator(app)?,
                    &abrir_item,
                    &PredefinedMenuItem::separator(app)?,
                    &arranque_item,
                    &quit_item,
                ],
            )?;

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

            // Decirlo desde el arranque, no solo al pulsar: sin motor, el
            // indicador de disco sigue siendo perfectamente útil, así que la
            // app no se rompe -- pero el usuario tiene que saber por qué esa
            // opción está apagada.
            if !hay_motor {
                let _ = analizar_item.set_enabled(false);
                let _ = estado_analisis_item.set_text("Motor de análisis no encontrado");
            } else if !analisis::hay_acceso_total_al_disco() {
                // Decirlo al arrancar y no al terminar: el escaneo del disco
                // completo tarda un par de minutos, y hacer esperar todo eso
                // para anunciar un permiso que falta desde el principio es
                // gratuito.
                let _ = estado_analisis_item
                    .set_text("Sin acceso total al disco: el análisis saldrá incompleto");
            }

            let mut tray_builder = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(true);
            match estado_inicial.map(icono_para) {
                Some(Ok(icon)) => tray_builder = tray_builder.icon(icon),
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
                let analizar_item = analizar_item.clone();
                let estado_analisis_item = estado_analisis_item.clone();
                tray_builder
                    .on_menu_event(move |app, event| {
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
                        } else if event.id() == "abrir" {
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
                                        let _ = tauri_plugin_opener::open_url(url, None::<&str>);
                                    }
                                    Err(e) => {
                                        let _ = volver.set_text(format!("No se pudo abrir: {e}"));
                                    }
                                }
                            });
                        } else if event.id() == "analizar" {
                            if manager.is_running() {
                                if manager.cancel() {
                                    let _ = analizar_item.set_text("Cancelando…");
                                    let _ = analizar_item.set_enabled(false);
                                }
                            } else {
                                let analizar_item_fin = analizar_item.clone();
                                let estado_analisis_item_fin = estado_analisis_item.clone();
                                let inicio = manager.start(move |resultado| {
                                    let _ = analizar_item_fin.set_text("Analizar ahora");
                                    let _ = analizar_item_fin.set_enabled(true);
                                    let _ = estado_analisis_item_fin.set_text(resultado.resumen());
                                });
                                match inicio {
                                    Ok(()) => {
                                        let _ = analizar_item.set_text("Cancelar análisis");
                                        let _ = estado_analisis_item
                                            .set_text("Analizando disco completo…");
                                    }
                                    Err(e) => {
                                        let _ = estado_analisis_item
                                            .set_text(format!("No se pudo iniciar: {e}"));
                                    }
                                }
                            }
                        }
                    })
                    .build(app)?
            };

            // Background poller: refresh the usage text every tick, but
            // only touch the icon when the classified state actually
            // changes -- swapping it on every poll causes flicker on some
            // macOS versions.
            {
                let tray = tray.clone();
                let uso_item = uso_item.clone();
                let libre_item = libre_item.clone();
                let swap_item = swap_item.clone();
                let mut ultimo_estado = estado_inicial;
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
                        culpable = memoria::medir_culpable().map(|(app, _)| app);
                        notificar(&aviso, &culpable);
                    }
                    loop {
                        std::thread::sleep(POLL_INTERVAL);
                        tick = tick.wrapping_add(1);
                        let swap_gb = memoria::swap_usado().map(gb).unwrap_or(0.0);
                        if swap_gb >= memoria::UMBRAL_SWAP_GB {
                            if culpable.is_none() || tick.is_multiple_of(TICKS_POR_CULPABLE) {
                                culpable = memoria::medir_culpable().map(|(app, _)| app);
                            }
                        } else {
                            culpable = None;
                        }
                        let _ =
                            swap_item.set_text(memoria::texto_swap(swap_gb, culpable.as_deref()));
                        match disk::read() {
                            Some(usage) => {
                                let _ = uso_item.set_text(texto_uso(&usage));
                                let _ = libre_item.set_text(texto_libre(&usage));
                                if let Some(aviso) = vigia.observar(gb(usage.available)) {
                                    notificar(&aviso, &culpable);
                                }
                                let nuevo_estado = estado::classify(usage);
                                if ultimo_estado != Some(nuevo_estado) {
                                    if let Ok(icon) = icono_para(nuevo_estado) {
                                        let _ = tray.set_icon(Some(icon));
                                    }
                                    ultimo_estado = Some(nuevo_estado);
                                }
                            }
                            None => {
                                let _ = uso_item.set_text("Uso: no disponible");
                                let _ = libre_item.set_text("Libre: no disponible");
                            }
                        }
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
        assert_eq!(texto_libre(&u(0)), "Libre: 14.0 GB");
        assert_eq!(texto_libre(&u(g / 2)), "Libre: 14.0 GB", "menos de 1 GB no merece ruido");
        assert_eq!(texto_libre(&u(5 * g + g / 2)), "Libre: 14.0 GB (+5.5 GB purgables)");
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
