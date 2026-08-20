use std::sync::Arc;
use std::time::Duration;

use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::Manager;

pub mod analisis;
pub mod disk;
pub mod estado;

use analisis::AnalisisManager;
use disk::DiskUsage;
use estado::Estado;

/// Disk usage costs 0.7 µs to read (measured) -- 5s is plenty responsive
/// without needing any justification for the cost.
const POLL_INTERVAL: Duration = Duration::from_secs(5);

const URL_ANALIZADOR_COMPLETO: &str = "http://localhost:8000/";

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
    format!("Libre: {:.1} GB", gb(u.available))
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
            let quit_item = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;

            let menu = Menu::with_items(
                app,
                &[
                    &uso_item,
                    &libre_item,
                    &PredefinedMenuItem::separator(app)?,
                    &analizar_item,
                    &estado_analisis_item,
                    &PredefinedMenuItem::separator(app)?,
                    &abrir_item,
                    &PredefinedMenuItem::separator(app)?,
                    &quit_item,
                ],
            )?;

            let manager = Arc::new(AnalisisManager::new());
            // Managed state so the shutdown handler in `run()` below (which
            // runs outside `setup` and has no closure access to `manager`)
            // can still reach it to guarantee cleanup on any exit path, not
            // just the "quit" menu item.
            app.manage(Arc::clone(&manager));

            let mut tray_builder = TrayIconBuilder::new().menu(&menu).show_menu_on_left_click(true);
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
                let analizar_item = analizar_item.clone();
                let estado_analisis_item = estado_analisis_item.clone();
                tray_builder
                    .on_menu_event(move |app, event| {
                        if event.id() == "quit" {
                            // Block briefly (bounded by KILL_REAP_TIMEOUT)
                            // so the scan's process group is confirmed dead
                            // before the app actually tears down -- "no
                            // orphans on quit" has to hold regardless of
                            // whether RunEvent::ExitRequested also fires.
                            manager.kill_blocking();
                            app.exit(0);
                        } else if event.id() == "abrir" {
                            let _ = tauri_plugin_opener::open_url(
                                URL_ANALIZADOR_COMPLETO,
                                None::<&str>,
                            );
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
                let mut ultimo_estado = estado_inicial;
                std::thread::spawn(move || loop {
                    std::thread::sleep(POLL_INTERVAL);
                    match disk::read() {
                        Some(usage) => {
                            let _ = uso_item.set_text(texto_uso(&usage));
                            let _ = libre_item.set_text(texto_libre(&usage));
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
            }
        });
}
