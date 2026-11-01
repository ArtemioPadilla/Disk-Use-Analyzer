//! "Liberar espacio": quick cleanups straight from the menu.
//!
//! The list comes from the engine (`disk_analyzer.py --limpieza-rapida`), so
//! every command was built by `analyzer/comandos.py` and passed the deletion
//! gate. Nothing here builds a deletion command: this module only shows what
//! the engine offers, asks, runs it, and measures what it actually freed.
//!
//! Only two consequences ever reach the menu: what comes back by itself
//! (caches, logs, build products) and the Trash, which goes in its own
//! section and is never part of "free everything".

use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::Deserialize;
use tauri::menu::{IsMenuItem, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Wry};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};

use crate::analisis::Motor;
use crate::disk;

/// Prefix of every menu id this module owns.
pub const PREFIJO: &str = "liberar:";
/// Menu id suffix of "free everything that comes back by itself".
pub const TODO: &str = "todo";
/// Menu id suffix of "review everything in the full analyzer".
pub const REVISAR: &str = "revisar";

const REGENERA: &str = "regenera";
const PERMANENTE: &str = "permanente";

/// One cleanup the engine offers.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Limpieza {
    pub id: String,
    pub titulo: String,
    pub descripcion: String,
    pub space: u64,
    pub consecuencia: String,
    pub command: String,
}

impl Limpieza {
    fn es_permanente(&self) -> bool {
        self.consecuencia == PERMANENTE
    }
}

/// Parses the engine's output. Anything that is not one of the two
/// consequences the menu may offer is dropped here too: the engine already
/// filters, but this is the last place a Docker prune could slip into a
/// one-click menu, so it checks again rather than trust the other side.
pub fn leer(json: &str) -> Result<Vec<Limpieza>, String> {
    let todas: Vec<Limpieza> =
        serde_json::from_str(json).map_err(|e| format!("respuesta del motor ilegible: {e}"))?;
    Ok(todas
        .into_iter()
        .filter(|l| {
            (l.consecuencia == REGENERA || l.consecuencia == PERMANENTE)
                && !l.command.trim().is_empty()
        })
        .collect())
}

/// Asks the engine what can be freed. Takes about ten seconds: it measures
/// the known cache folders, not the whole disk.
pub fn medir(motor: &Motor) -> Result<Vec<Limpieza>, String> {
    let salida = Command::new(motor.python())
        .current_dir(motor.cwd())
        .arg(motor.script())
        .arg("--limpieza-rapida")
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("no se pudo lanzar el motor: {e}"))?;
    if !salida.status.success() {
        return Err(ultima_linea(&salida.stderr).unwrap_or_else(|| "el motor falló".into()));
    }
    leer(&String::from_utf8_lossy(&salida.stdout))
}

fn gb(bytes: u64) -> f64 {
    bytes as f64 / (1024.0 * 1024.0 * 1024.0)
}

fn tamano(bytes: u64) -> String {
    if bytes >= 1024 * 1024 * 1024 {
        format!("{:.1} GB", gb(bytes))
    } else {
        format!("{} MB", bytes / (1024 * 1024))
    }
}

/// One row of the submenu.
#[derive(Debug, Clone, PartialEq)]
pub enum Fila {
    /// A greyed-out line: a section title or a state ("Midiendo…").
    Texto(String),
    /// A clickable line; `id` goes after `PREFIJO`.
    Accion {
        id: String,
        texto: String,
    },
    Separador,
}

/// The submenu for a list: what comes back by itself first, then the Trash
/// under its own heading, then the way out to the full review.
pub fn filas(lista: &[Limpieza]) -> Vec<Fila> {
    let mut out = Vec::new();
    let (regenera, permanente): (Vec<&Limpieza>, Vec<&Limpieza>) =
        lista.iter().partition(|l| !l.es_permanente());
    let accion = |l: &Limpieza| Fila::Accion {
        id: l.id.clone(),
        texto: format!("{} — {}", l.titulo, tamano(l.space)),
    };
    if lista.is_empty() {
        out.push(Fila::Texto("Nada que liberar ahora mismo".into()));
    }
    if !regenera.is_empty() {
        out.push(Fila::Texto("Vuelve solo, sin perder nada tuyo".into()));
        out.extend(regenera.iter().map(|l| accion(l)));
        if regenera.len() > 1 {
            let total: u64 = regenera.iter().map(|l| l.space).sum();
            out.push(Fila::Accion {
                id: TODO.into(),
                texto: format!("Liberar todo lo anterior — {}", tamano(total)),
            });
        }
    }
    if !permanente.is_empty() {
        out.push(Fila::Separador);
        out.push(Fila::Texto("No se puede deshacer".into()));
        out.extend(permanente.iter().map(|l| accion(l)));
    }
    out.push(Fila::Separador);
    out.push(Fila::Accion {
        id: REVISAR.into(),
        texto: "Revisar todo en el analizador completo…".into(),
    });
    out
}

/// What a click on `id` would run. "Free everything" never includes the
/// Trash.
pub fn elegir(lista: &[Limpieza], id: &str) -> Vec<Limpieza> {
    if id == TODO {
        lista
            .iter()
            .filter(|l| !l.es_permanente())
            .cloned()
            .collect()
    } else {
        lista.iter().filter(|l| l.id == id).cloned().collect()
    }
}

/// Texts of the confirmation dialog.
#[derive(Debug, Clone, PartialEq)]
pub struct Confirmacion {
    pub titulo: String,
    pub mensaje: String,
    pub boton: String,
    pub permanente: bool,
}

pub fn confirmacion(elegidas: &[Limpieza]) -> Confirmacion {
    let total: u64 = elegidas.iter().map(|l| l.space).sum();
    let permanente = elegidas.iter().any(Limpieza::es_permanente);
    let lineas: Vec<String> = elegidas
        .iter()
        .map(|l| format!("• {} — {}", l.titulo, tamano(l.space)))
        .collect();
    let despues = if permanente {
        "Lo que hay en la papelera se borra para siempre. Esto no se puede deshacer."
    } else {
        "Son datos que las apps vuelven a crear solas cuando los necesitan: \
         como mucho, la próxima vez que abras una app o compiles irá un poco más lento."
    };
    Confirmacion {
        titulo: if permanente {
            format!("¿Vaciar la papelera ({})?", tamano(total))
        } else {
            format!("¿Liberar unos {}?", tamano(total))
        },
        mensaje: format!(
            "{}\n\n{}\n\nLa cifra es una estimación; al terminar verás lo que se liberó de verdad.",
            lineas.join("\n"),
            despues
        ),
        boton: if permanente {
            "Vaciar la papelera".into()
        } else {
            "Liberar".into()
        },
        permanente,
    }
}

/// What a run achieved: free space measured before and after, and the
/// commands that failed with their last error line.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Hecho {
    pub liberado: u64,
    pub fallos: Vec<(String, String)>,
}

/// The notification after a run. The figure is always the measured one: a
/// `rm` that deleted nothing exits 0 just the same.
pub fn aviso_final(h: &Hecho) -> (String, String) {
    let titulo = if h.liberado >= 1024 * 1024 {
        format!("Liberados {}", tamano(h.liberado))
    } else {
        "No se liberó espacio".to_string()
    };
    let cuerpo = match h.fallos.as_slice() {
        [] if h.liberado >= 1024 * 1024 => "Medido en el disco antes y después.".to_string(),
        [] => "Puede que una app lo estuviera usando, o que ya estuviera vacío.".to_string(),
        fallos => fallos
            .iter()
            .map(|(t, e)| format!("{t}: {e}"))
            .collect::<Vec<_>>()
            .join("\n"),
    };
    (titulo, cuerpo)
}

fn ultima_linea(bytes: &[u8]) -> Option<String> {
    String::from_utf8_lossy(bytes)
        .lines()
        .rev()
        .map(str::trim)
        .find(|l| !l.is_empty())
        .map(str::to_string)
}

/// An app launched from Finder gets a bare PATH (/usr/bin:/bin:…), where
/// `brew` and `npm` from Homebrew are not found.
fn path_con_homebrew() -> String {
    let actual = std::env::var("PATH").unwrap_or_default();
    format!("/opt/homebrew/bin:/usr/local/bin:{actual}")
}

/// Runs the chosen cleanups one after another and measures the result.
pub fn ejecutar(elegidas: &[Limpieza]) -> Hecho {
    let antes = disk::read().map(|u| u.available);
    let mut fallos = Vec::new();
    for l in elegidas {
        let r = Command::new("/bin/sh")
            .arg("-c")
            .arg(&l.command)
            .env("PATH", path_con_homebrew())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .output();
        match r {
            Ok(o) if o.status.success() => {}
            Ok(o) => fallos.push((
                l.titulo.clone(),
                ultima_linea(&o.stderr).unwrap_or_else(|| format!("salió con {}", o.status)),
            )),
            Err(e) => fallos.push((l.titulo.clone(), e.to_string())),
        }
    }
    // APFS frees blocks asynchronously; a moment's wait keeps the measured
    // figure from coming out short.
    std::thread::sleep(Duration::from_secs(1));
    let despues = disk::read().map(|u| u.available);
    let liberado = match (antes, despues) {
        (Some(a), Some(d)) => d.saturating_sub(a),
        _ => 0,
    };
    Hecho { liberado, fallos }
}

/// The submenu and its current list.
pub struct Liberador {
    app: AppHandle,
    submenu: Submenu<Wry>,
    motor: Option<Motor>,
    lista: Mutex<Vec<Limpieza>>,
    ocupado: AtomicBool,
}

impl Liberador {
    pub fn new(app: AppHandle, submenu: Submenu<Wry>, motor: Option<Motor>) -> Arc<Self> {
        let l = Arc::new(Liberador {
            app,
            submenu,
            motor,
            lista: Mutex::new(Vec::new()),
            ocupado: AtomicBool::new(false),
        });
        let texto = if l.motor.is_some() {
            "Midiendo lo que se puede liberar…"
        } else {
            "Motor de análisis no encontrado"
        };
        l.poner(&[Fila::Texto(texto.into())]);
        l
    }

    fn poner(&self, filas: &[Fila]) {
        if let Ok(viejos) = self.submenu.items() {
            for v in viejos {
                let _ = self.submenu.remove(&v as &dyn IsMenuItem<Wry>);
            }
        }
        for f in filas {
            let _ = match f {
                Fila::Texto(t) => MenuItem::new(&self.app, t, false, None::<&str>)
                    .and_then(|i| self.submenu.append(&i)),
                Fila::Accion { id, texto } => MenuItem::with_id(
                    &self.app,
                    format!("{PREFIJO}{id}"),
                    texto,
                    true,
                    None::<&str>,
                )
                .and_then(|i| self.submenu.append(&i)),
                Fila::Separador => {
                    PredefinedMenuItem::separator(&self.app).and_then(|i| self.submenu.append(&i))
                }
            };
        }
    }

    /// Re-measures and rebuilds the submenu. Blocking: call it off the main
    /// thread.
    pub fn refrescar(&self) {
        let Some(motor) = self.motor.as_ref() else {
            return;
        };
        if self.ocupado.load(Ordering::SeqCst) {
            return;
        }
        match medir(motor) {
            Ok(lista) => {
                self.poner(&filas(&lista));
                *self.lista.lock().unwrap() = lista;
            }
            Err(e) => self.poner(&[Fila::Texto(format!("No se pudo medir: {e}"))]),
        }
    }

    /// Handles a click on `id` (without the prefix): confirm, run, report.
    /// `al_empezar` and `al_terminar` let the caller animate the icon and
    /// notify; both run on a worker thread.
    pub fn pedir<E, T>(self: &Arc<Self>, id: &str, al_empezar: E, al_terminar: T)
    where
        E: FnOnce() + Send + 'static,
        T: FnOnce(&Hecho) + Send + 'static,
    {
        let elegidas = elegir(&self.lista.lock().unwrap(), id);
        if elegidas.is_empty() || self.ocupado.load(Ordering::SeqCst) {
            return;
        }
        let c = confirmacion(&elegidas);
        let yo = Arc::clone(self);
        self.app
            .dialog()
            .message(c.mensaje)
            .title(c.titulo)
            .kind(if c.permanente {
                MessageDialogKind::Warning
            } else {
                MessageDialogKind::Info
            })
            .buttons(MessageDialogButtons::OkCancelCustom(
                c.boton,
                "Cancelar".into(),
            ))
            .show(move |acepta| {
                if !acepta || yo.ocupado.swap(true, Ordering::SeqCst) {
                    return;
                }
                yo.poner(&[Fila::Texto("Liberando espacio…".into())]);
                std::thread::spawn(move || {
                    al_empezar();
                    let hecho = ejecutar(&elegidas);
                    yo.ocupado.store(false, Ordering::SeqCst);
                    yo.refrescar();
                    al_terminar(&hecho);
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const GB: u64 = 1024 * 1024 * 1024;

    fn l(id: &str, consecuencia: &str, space: u64) -> Limpieza {
        Limpieza {
            id: id.into(),
            titulo: format!("T-{id}"),
            descripcion: String::new(),
            space,
            consecuencia: consecuencia.into(),
            command: format!("echo {id}"),
        }
    }

    #[test]
    fn solo_entra_lo_que_vuelve_solo_y_la_papelera() {
        let json = r#"[
            {"id":"logs","titulo":"Logs","descripcion":"","space":1,"consecuencia":"regenera","command":"x"},
            {"id":"docker","titulo":"Docker","descripcion":"","space":1,"consecuencia":"redescarga","command":"docker system prune -a -f"},
            {"id":"lista","titulo":"L","descripcion":"","space":1,"consecuencia":"solo_lista","command":"du"},
            {"id":"vacio","titulo":"V","descripcion":"","space":1,"consecuencia":"regenera","command":"  "},
            {"id":"papelera","titulo":"Papelera","descripcion":"","space":1,"consecuencia":"permanente","command":"y"}
        ]"#;
        let ids: Vec<String> = leer(json).unwrap().into_iter().map(|l| l.id).collect();
        assert_eq!(ids, vec!["logs", "papelera"]);
    }

    #[test]
    fn la_papelera_va_aparte_y_nunca_entra_en_liberar_todo() {
        let lista = vec![
            l("caches", REGENERA, 6 * GB),
            l("logs", REGENERA, GB / 2),
            l("papelera", PERMANENTE, 2 * GB),
        ];
        let f = filas(&lista);
        let pos = |id: &str| {
            f.iter()
                .position(|x| matches!(x, Fila::Accion { id: i, .. } if i == id))
                .unwrap()
        };
        let aviso = f
            .iter()
            .position(|x| *x == Fila::Texto("No se puede deshacer".into()))
            .unwrap();
        assert!(pos(TODO) < aviso && aviso < pos("papelera"));
        assert!(matches!(&f[pos(TODO)], Fila::Accion { texto, .. } if texto.ends_with("6.5 GB")));

        let todo: Vec<String> = elegir(&lista, TODO).into_iter().map(|l| l.id).collect();
        assert_eq!(todo, vec!["caches", "logs"]);
    }

    #[test]
    fn liberar_todo_solo_aparece_con_mas_de_una_cosa() {
        let f = filas(&[l("logs", REGENERA, GB)]);
        assert!(!f
            .iter()
            .any(|x| matches!(x, Fila::Accion { id, .. } if id == TODO)));
    }

    #[test]
    fn sin_nada_que_liberar_lo_dice_y_deja_ir_al_analizador() {
        let f = filas(&[]);
        assert_eq!(f[0], Fila::Texto("Nada que liberar ahora mismo".into()));
        assert!(matches!(f.last(), Some(Fila::Accion { id, .. }) if id == REVISAR));
    }

    #[test]
    fn la_confirmacion_de_la_papelera_dice_que_no_se_puede_deshacer() {
        let c = confirmacion(&[l("papelera", PERMANENTE, 2 * GB)]);
        assert!(c.permanente);
        assert_eq!(c.boton, "Vaciar la papelera");
        assert!(c.mensaje.contains("no se puede deshacer"));

        let c = confirmacion(&[l("logs", REGENERA, GB)]);
        assert!(!c.permanente);
        assert!(!c.mensaje.contains("no se puede deshacer"));
        assert!(c.mensaje.contains("T-logs — 1.0 GB"));
    }

    #[test]
    fn el_aviso_final_da_la_cifra_medida_y_los_fallos() {
        let (t, _) = aviso_final(&Hecho {
            liberado: 3 * GB,
            fallos: vec![],
        });
        assert_eq!(t, "Liberados 3.0 GB");
        let (t, c) = aviso_final(&Hecho {
            liberado: 0,
            fallos: vec![("Caché de npm".into(), "npm: command not found".into())],
        });
        assert_eq!(t, "No se liberó espacio");
        assert!(c.contains("Caché de npm: npm: command not found"));
    }

    #[test]
    fn ejecutar_informa_del_error_de_un_comando_que_falla() {
        let mut malo = l("x", REGENERA, 1);
        malo.command = "echo 'algo salió mal' >&2; exit 3".into();
        let h = ejecutar(&[malo]);
        assert_eq!(h.fallos, vec![("T-x".into(), "algo salió mal".into())]);
    }
}
