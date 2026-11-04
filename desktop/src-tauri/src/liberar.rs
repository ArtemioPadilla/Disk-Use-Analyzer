//! The cleanups in the menu: each category's submenu and "Liberar lo seguro".
//!
//! The list comes from the engine (`disk_analyzer.py --limpieza-rapida`), so
//! every command was built by `analyzer/comandos.py` and passed the deletion
//! gate. Nothing here builds a deletion command: this module only shows what
//! the engine offers, asks, runs it, and measures what it actually freed.
//!
//! Three consequences reach the menu: what comes back by itself (caches, logs,
//! build products), Docker images, which have to be downloaded again, and the
//! Trash. The last two go under their own heading and are never part of "free
//! everything".

use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::menu::{IsMenuItem, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Wry};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};

use crate::analisis::Motor;
use crate::categorias::{tamano, Categoria};
use crate::disk;
use crate::menu_nativo;

/// Prefix of the menu ids that run a cleanup.
pub const PREFIJO: &str = "liberar:";
/// Prefix of the menu ids that open a page of the full analyzer.
pub const PREFIJO_ANALIZADOR: &str = "ir:";
/// Prefix of the menu ids that open something outside the app.
pub const PREFIJO_EXTERNO: &str = "externo:";
/// Menu id suffix of "everything safe", from any category.
pub const TODO: &str = "todo";
/// Menu id suffix of "the projects nobody has touched for a while".
const PROYECTOS_OLVIDADOS: &str = "proyectos_olvidados";
const CATEGORIA_PROYECTOS: &str = "proyectos";
/// Menu id suffix of "the worktrees that lose nothing".
const WORKTREES_LIMPIOS: &str = "worktrees_limpios";
const CATEGORIA_WORKTREES: &str = "worktrees";
const CATEGORIA_AMBIENTES: &str = "ambientes";
const CATEGORIA_DOCKER_DETALLE: &str = "docker_detalle";
/// How many images and volumes the submenu names; the rest are small.
const DOCKER_EN_MENU: usize = 8;
/// Menu id suffix of "all the caches".
const TODAS_CACHES: &str = "caches";

const EXTERNO_CACHES: &str = "caches";
const EXTERNO_DESCARGAS: &str = "descargas";
const EXTERNO_ALMACENAMIENTO: &str = "almacenamiento";
const EXTERNO_MONITOR: &str = "monitor";
const EXTERNO_DOCKER: &str = "docker";

/// Prefix of the menu ids that ask an app to quit.
pub const PREFIJO_CERRAR: &str = "cerrar:";

const TITULO_DESCARGA: &str = "Hay que volver a descargar";
const TITULO_DESGLOSE: &str = "De qué está hecho";

const REGENERA: &str = "regenera";
const REDESCARGA: &str = "redescarga";
const PERMANENTE: &str = "permanente";

/// One cleanup the engine offers.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Limpieza {
    pub id: String,
    pub titulo: String,
    pub descripcion: String,
    pub space: u64,
    pub consecuencia: String,
    pub categoria: String,
    pub command: String,
    /// Days since the project was touched, for what comes from a project.
    #[serde(default)]
    pub dias: Option<u64>,
    /// Why it is not offered, when it has no command.
    #[serde(default)]
    pub motivo: String,
}

impl Limpieza {
    fn es_permanente(&self) -> bool {
        self.consecuencia == PERMANENTE
    }

    fn esta_en(&self, c: Categoria) -> bool {
        self.categoria == clave(c)
    }

    fn esta_en_proyectos(&self) -> bool {
        self.categoria == CATEGORIA_PROYECTOS
    }

    fn esta_en_worktrees(&self) -> bool {
        self.categoria == CATEGORIA_WORKTREES
    }
}

/// Parses the engine's output. Anything the menu may not offer is dropped here
/// too: the engine already filters, but this is the last place a list of files
/// or a command touching Docker's volumes could slip into the menu, so it
/// checks again rather than trust the other side.
pub fn leer(json: &str) -> Result<Vec<Limpieza>, String> {
    let todas: Vec<Limpieza> =
        serde_json::from_str(json).map_err(|e| format!("respuesta del motor ilegible: {e}"))?;
    Ok(todas
        .into_iter()
        .filter(|l| {
            [REGENERA, REDESCARGA, PERMANENTE].contains(&l.consecuencia.as_str())
                && !l.command.trim().is_empty()
                && !(l.categoria == "docker" && l.command.contains("volume"))
        })
        .collect())
}

/// Asks the engine about projects or worktrees (`--proyectos`, `--worktrees`).
/// It walks the usual project folders and measures what it finds, so it takes a
/// while: call it off the main thread. Rows without a command stay in the list,
/// to say they exist.
pub fn medir_desarrollo(motor: &Motor, modo: &str) -> Result<Vec<Limpieza>, String> {
    let salida = Command::new(motor.python())
        .current_dir(motor.cwd())
        .arg(motor.script())
        .arg(modo)
        .env("PATH", path_con_herramientas())
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("no se pudo lanzar el motor: {e}"))?;
    if !salida.status.success() {
        return Err(ultima_linea(&salida.stderr).unwrap_or_else(|| "el motor falló".into()));
    }
    serde_json::from_slice(&salida.stdout).map_err(|e| format!("respuesta ilegible: {e}"))
}

/// Asks the engine what can be freed. Takes about ten seconds: it measures
/// the known cache folders, not the whole disk.
pub fn medir(motor: &Motor) -> Result<Vec<Limpieza>, String> {
    let salida = Command::new(motor.python())
        .current_dir(motor.cwd())
        .arg(motor.script())
        .arg("--limpieza-rapida")
        .env("PATH", path_con_herramientas())
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("no se pudo lanzar el motor: {e}"))?;
    if !salida.status.success() {
        return Err(ultima_linea(&salida.stderr).unwrap_or_else(|| "el motor falló".into()));
    }
    leer(&String::from_utf8_lossy(&salida.stdout))
}

/// How the engine names a category.
fn clave(c: Categoria) -> &'static str {
    match c {
        Categoria::Docker => "docker",
        Categoria::Caches => "caches",
        Categoria::Tuyo => "tuyo",
        Categoria::Resto => "resto",
    }
}

/// One row of a submenu.
#[derive(Debug, Clone, PartialEq)]
pub enum Fila {
    /// Not clickable: a section title or a note.
    Texto(String),
    /// A clickable line; `id` is the whole menu id.
    Accion {
        id: String,
        texto: String,
    },
    Separador,
}

fn accion(id: String, texto: impl Into<String>) -> Fila {
    Fila::Accion {
        id,
        texto: texto.into(),
    }
}

fn limpieza(l: &Limpieza) -> Fila {
    accion(
        format!("{PREFIJO}{}", l.id),
        format!("{}…\t{}", l.titulo, tamano(l.space)),
    )
}

fn analizador(destino: &str, texto: &str) -> Fila {
    accion(format!("{PREFIJO_ANALIZADOR}{destino}"), texto)
}

fn externo(destino: &str, texto: &str) -> Fila {
    accion(format!("{PREFIJO_EXTERNO}{destino}"), texto)
}

/// A category's submenu. `aviso`, when there is one, takes the place of the
/// cleanups (still measuring, or the measure failed); the ways out stay.
pub fn filas(c: Categoria, lista: &[Limpieza], aviso: Option<&str>) -> Vec<Fila> {
    let propias: Vec<&Limpieza> = lista.iter().filter(|l| l.esta_en(c)).collect();
    let aviso = aviso.map(|a| Fila::Texto(a.to_string()));
    let mut out = Vec::new();
    match c {
        Categoria::Docker => {
            let (vuelve, descarga): (Vec<&&Limpieza>, Vec<&&Limpieza>) =
                propias.iter().partition(|l| l.consecuencia == REGENERA);
            if let Some(a) = aviso {
                out.push(a);
            } else if propias.is_empty() {
                out.push(Fila::Texto(
                    "Nada que limpiar, o Docker está apagado".into(),
                ));
            }
            let detalle: Vec<&Limpieza> = lista
                .iter()
                .filter(|l| l.categoria == CATEGORIA_DOCKER_DETALLE)
                .collect();
            if detalle.is_empty() {
                out.push(externo(EXTERNO_DOCKER, "Encender Docker"));
            }
            if !vuelve.is_empty() {
                out.push(Fila::Texto("Vuelve solo".into()));
                out.extend(vuelve.iter().map(|l| limpieza(l)));
            }
            if !descarga.is_empty() {
                if !vuelve.is_empty() {
                    out.push(Fila::Separador);
                }
                out.push(Fila::Texto(TITULO_DESCARGA.into()));
                out.extend(descarga.iter().map(|l| limpieza(l)));
                out.push(Fila::Texto("También borra contenedores parados".into()));
                out.push(Fila::Texto("Los volúmenes no se tocan".into()));
            }
            let (imagenes, volumenes): (Vec<&&Limpieza>, Vec<&&Limpieza>) =
                detalle.iter().partition(|l| l.consecuencia == REDESCARGA);
            if !imagenes.is_empty() {
                out.push(Fila::Separador);
                out.push(Fila::Texto("Imágenes".into()));
                for l in imagenes.iter().take(DOCKER_EN_MENU) {
                    if l.command.is_empty() {
                        out.push(Fila::Texto(format!("{}\t{}", l.titulo, tamano(l.space))));
                    } else {
                        out.push(limpieza(l));
                    }
                }
            }
            if !volumenes.is_empty() {
                out.push(Fila::Separador);
                out.push(Fila::Texto("Volúmenes: guardan datos, no se tocan".into()));
                out.extend(
                    volumenes
                        .iter()
                        .take(DOCKER_EN_MENU)
                        .map(|l| Fila::Texto(format!("{}\t{}", l.titulo, tamano(l.space)))),
                );
            }
            out.push(Fila::Separador);
            out.push(analizador("/", "Abrir analizador completo"));
        }
        Categoria::Caches => {
            let (vuelven, descarga): (Vec<&&Limpieza>, Vec<&&Limpieza>) =
                propias.iter().partition(|l| l.consecuencia == REGENERA);
            if let Some(a) = aviso {
                out.push(a);
            } else if propias.is_empty() {
                out.push(Fila::Texto("Nada que limpiar ahora mismo".into()));
            }
            if vuelven.len() > 1 {
                let total: u64 = vuelven.iter().map(|l| l.space).sum();
                out.push(accion(
                    format!("{PREFIJO}{TODAS_CACHES}"),
                    format!("Limpiar todas…\t{}", tamano(total)),
                ));
                out.push(Fila::Separador);
            }
            out.extend(vuelven.iter().map(|l| limpieza(l)));
            if !descarga.is_empty() {
                if !vuelven.is_empty() {
                    out.push(Fila::Separador);
                }
                out.push(Fila::Texto(TITULO_DESCARGA.into()));
                out.extend(descarga.iter().map(|l| limpieza(l)));
            }
            out.push(Fila::Separador);
            out.push(Fila::Texto("Lo demás no se limpia desde aquí".into()));
            out.push(externo(EXTERNO_CACHES, "Abrir en Finder"));
        }
        Categoria::Tuyo => {
            out.push(Fila::Texto("No vuelve".into()));
            if let Some(a) = aviso {
                out.push(a);
            } else if propias.is_empty() {
                out.push(Fila::Texto("La papelera está casi vacía".into()));
            } else {
                out.extend(propias.iter().map(|l| limpieza(l)));
            }
            out.push(Fila::Separador);
            out.push(Fila::Texto("Revisar antes de borrar".into()));
            out.push(analizador("/files", "Archivos más grandes"));
            out.push(analizador(
                "/files?path=/Downloads/&orden=antiguedad",
                "Descargas más antiguas",
            ));
            out.push(Fila::Texto("Se abren en el analizador".into()));
            out.push(Fila::Separador);
            out.push(externo(EXTERNO_DESCARGAS, "Abrir Descargas en Finder"));
        }
        Categoria::Resto => {
            if let Some(a) = aviso {
                out.push(a);
            } else if propias.is_empty() {
                out.push(Fila::Texto("Nada que limpiar desde aquí".into()));
            } else {
                out.extend(propias.iter().map(|l| limpieza(l)));
            }
            out.push(Fila::Separador);
            out.push(analizador("/", "Ver desglose en el analizador"));
            out.push(externo(
                EXTERNO_ALMACENAMIENTO,
                "Abrir Almacenamiento de macOS",
            ));
        }
    }
    out
}

/// Past this, a project counts as forgotten: long enough that reinstalling is
/// no bother, and short enough to catch what is really stale.
pub const DIAS_OLVIDADO: u64 = 30;
/// How many projects the submenu lists; the rest are one click away.
const PROYECTOS_EN_MENU: usize = 12;

fn olvidados(lista: &[Limpieza]) -> impl Iterator<Item = &Limpieza> {
    lista.iter().filter(|l| {
        l.esta_en_proyectos() && !l.command.is_empty() && l.dias.is_some_and(|d| d >= DIAS_OLVIDADO)
    })
}

/// The top-level row for projects.
pub fn fila_proyectos(lista: &[Limpieza]) -> String {
    let total: u64 = lista
        .iter()
        .filter(|l| l.esta_en_proyectos())
        .map(|l| l.space)
        .sum();
    format!("Proyectos\t{}", tamano(total))
}

/// The projects submenu: what has been forgotten for a while, the largest
/// ones, and how many are not offered and why.
pub fn filas_proyectos(lista: &[Limpieza], aviso: Option<&str>) -> Vec<Fila> {
    let mut out = Vec::new();
    if let Some(a) = aviso {
        out.push(Fila::Texto(a.to_string()));
    }
    let total_olvidado: u64 = olvidados(lista).map(|l| l.space).sum();
    if aviso.is_none() && total_olvidado > 0 {
        out.push(accion(
            format!("{PREFIJO}{PROYECTOS_OLVIDADOS}"),
            format!(
                "Limpiar sin tocar hace {DIAS_OLVIDADO} días…\t{}",
                tamano(total_olvidado)
            ),
        ));
        out.push(Fila::Separador);
    }
    let mut ofrecibles: Vec<&Limpieza> = lista
        .iter()
        .filter(|l| l.esta_en_proyectos() && !l.command.is_empty())
        .collect();
    ofrecibles.sort_by_key(|l| std::cmp::Reverse(l.space));
    let total = ofrecibles.len();
    for l in ofrecibles.into_iter().take(PROYECTOS_EN_MENU) {
        let hace = l.dias.map(|d| format!(" ({d} d)")).unwrap_or_default();
        out.push(accion(
            format!("{PREFIJO}{}", l.id),
            format!("{}{hace}…\t{}", l.titulo, tamano(l.space)),
        ));
    }
    if aviso.is_none() && total == 0 {
        out.push(Fila::Texto("Nada que limpiar en tus proyectos".into()));
    }
    let sin_ofrecer = lista
        .iter()
        .filter(|l| l.esta_en_proyectos() && l.command.is_empty())
        .count();
    if sin_ofrecer > 0 {
        out.push(Fila::Texto(format!(
            "{sin_ofrecer} sin ofrecer: podrían no reconstruirse"
        )));
    }
    out.push(Fila::Separador);
    out.push(analizador("/projects", "Ver todos en el analizador"));
    out
}

/// The top-level row for worktrees.
pub fn fila_worktrees(lista: &[Limpieza]) -> String {
    let (n, total) = lista
        .iter()
        .filter(|l| l.esta_en_worktrees())
        .fold((0, 0), |(n, t), l| (n + 1, t + l.space));
    format!("Worktrees ({n})\t{}", tamano(total))
}

/// The worktrees submenu: what can go because it loses nothing, and how many
/// stay and why.
pub fn filas_worktrees(lista: &[Limpieza], aviso: Option<&str>) -> Vec<Fila> {
    let mut out = Vec::new();
    if let Some(a) = aviso {
        out.push(Fila::Texto(a.to_string()));
    }
    let mut limpios: Vec<&Limpieza> = lista
        .iter()
        .filter(|l| l.esta_en_worktrees() && !l.command.is_empty())
        .collect();
    limpios.sort_by_key(|l| std::cmp::Reverse(l.space));
    if aviso.is_none() && limpios.len() > 1 {
        let total: u64 = limpios.iter().map(|l| l.space).sum();
        out.push(accion(
            format!("{PREFIJO}{WORKTREES_LIMPIOS}"),
            format!(
                "Quitar los {} que no pierden nada…\t{}",
                limpios.len(),
                tamano(total)
            ),
        ));
        out.push(Fila::Separador);
    }
    if aviso.is_none() && limpios.is_empty() {
        out.push(Fila::Texto(
            "Ninguno se puede quitar sin perder algo".into(),
        ));
    }
    out.extend(limpios.iter().map(|l| limpieza(l)));
    let mut motivos: Vec<(String, usize)> = Vec::new();
    for l in lista
        .iter()
        .filter(|l| l.esta_en_worktrees() && l.command.is_empty())
    {
        match motivos.iter_mut().find(|(m, _)| *m == l.motivo) {
            Some((_, n)) => *n += 1,
            None => motivos.push((l.motivo.clone(), 1)),
        }
    }
    motivos.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    if !motivos.is_empty() {
        out.push(Fila::Separador);
        out.extend(
            motivos
                .into_iter()
                .map(|(m, n)| Fila::Texto(format!("{n}: {m}"))),
        );
    }
    out
}

/// The top-level row for environments.
pub fn fila_ambientes(lista: &[Limpieza]) -> String {
    let total: u64 = lista
        .iter()
        .filter(|l| l.categoria == CATEGORIA_AMBIENTES)
        .map(|l| l.space)
        .sum();
    format!("Ambientes\t{}", tamano(total))
}

/// The environments submenu: what conda can clean, then the rest to inform.
pub fn filas_ambientes(lista: &[Limpieza], aviso: Option<&str>) -> Vec<Fila> {
    let propias: Vec<&Limpieza> = lista
        .iter()
        .filter(|l| l.categoria == CATEGORIA_AMBIENTES)
        .collect();
    let (limpiables, informan): (Vec<&Limpieza>, Vec<&Limpieza>) =
        propias.iter().partition(|l| !l.command.is_empty());
    let mut out = Vec::new();
    if let Some(a) = aviso {
        out.push(Fila::Texto(a.to_string()));
    } else if propias.is_empty() {
        out.push(Fila::Texto("No se encontró ninguno".into()));
    }
    out.extend(limpiables.iter().map(|l| limpieza(l)));
    if !informan.is_empty() {
        if !limpiables.is_empty() {
            out.push(Fila::Separador);
        }
        out.push(Fila::Texto("Instalados".into()));
        out.extend(
            informan
                .iter()
                .map(|l| Fila::Texto(format!("{}\t{}", l.titulo, tamano(l.space)))),
        );
    }
    out
}

/// The swap submenu. Nothing can delete swap: it only shrinks when the app
/// holding it quits, or with a restart, and the last lines say so.
pub fn filas_swap(cerrables: &[(String, u64)]) -> Vec<Fila> {
    let mut out = vec![Fila::Texto("Lo retiene".into())];
    if cerrables.is_empty() {
        out.push(Fila::Texto("Ninguna app en especial".into()));
    }
    out.extend(cerrables.iter().map(|(app, bytes)| {
        accion(
            format!("{PREFIJO_CERRAR}{app}"),
            format!("Cerrar {app}…\t{}", tamano(*bytes)),
        )
    }));
    out.push(Fila::Separador);
    out.push(externo(EXTERNO_MONITOR, "Abrir Monitor de Actividad"));
    out.push(Fila::Texto(
        "Si no baja al cerrar, solo se libera al reiniciar".into(),
    ));
    out
}

/// Replaces what a submenu shows.
pub fn poner_filas(app: &AppHandle, submenu: &Submenu<Wry>, filas: &[Fila]) {
    if let Ok(viejos) = submenu.items() {
        for v in viejos {
            let _ = submenu.remove(&v as &dyn IsMenuItem<Wry>);
        }
    }
    for f in filas {
        let _ = match f {
            Fila::Texto(t) => {
                MenuItem::new(app, t, false, None::<&str>).and_then(|i| submenu.append(&i))
            }
            Fila::Accion { id, texto } => MenuItem::with_id(app, id, texto, true, None::<&str>)
                .and_then(|i| submenu.append(&i)),
            Fila::Separador => PredefinedMenuItem::separator(app).and_then(|i| submenu.append(&i)),
        };
    }
}

/// "Liberar lo seguro" and what it adds up to. It runs what comes back by
/// itself, without a download behind it: never the Trash, never Docker.
fn seguras(lista: &[Limpieza]) -> impl Iterator<Item = &Limpieza> {
    lista.iter().filter(|l| {
        l.consecuencia == REGENERA
            && (l.esta_en(Categoria::Caches)
                || l.esta_en(Categoria::Resto)
                || l.esta_en(Categoria::Tuyo))
    })
}

/// The text of the top-level "Liberar lo seguro" row, and whether it can be
/// clicked.
pub fn fila_seguro(lista: &[Limpieza]) -> (String, bool) {
    let total: u64 = seguras(lista).map(|l| l.space).sum();
    if total == 0 {
        ("Nada que liberar ahora mismo".into(), false)
    } else {
        (format!("Liberar lo seguro…\t{}", tamano(total)), true)
    }
}

/// The analyzer's address for a page of it: `destino` replaces the path of the
/// server's address, and keeps its token.
pub fn url_en(url: &str, destino: &str) -> String {
    let Some((base, token)) = url.split_once("/?") else {
        return url.to_string();
    };
    let union = if destino.contains('?') { '&' } else { '?' };
    format!("{base}{destino}{union}{token}")
}

/// What an external menu id opens. A fixed list: an id is never a path.
pub fn externo_de(id: &str, home: &str) -> Option<String> {
    match id {
        EXTERNO_CACHES => Some(format!("{home}/Library/Caches")),
        EXTERNO_DESCARGAS => Some(format!("{home}/Downloads")),
        EXTERNO_DOCKER => Some("/Applications/Docker.app".to_string()),
        EXTERNO_MONITOR => Some("/System/Applications/Utilities/Activity Monitor.app".to_string()),
        EXTERNO_ALMACENAMIENTO => {
            Some("x-apple.systempreferences:com.apple.settings.Storage".to_string())
        }
        _ => None,
    }
}

/// What a click on `id` would run. Neither "everything" includes the Trash.
pub fn elegir(lista: &[Limpieza], id: &str) -> Vec<Limpieza> {
    match id {
        TODO => seguras(lista).cloned().collect(),
        PROYECTOS_OLVIDADOS => olvidados(lista).cloned().collect(),
        WORKTREES_LIMPIOS => lista
            .iter()
            .filter(|l| l.esta_en_worktrees() && !l.command.is_empty())
            .cloned()
            .collect(),
        TODAS_CACHES => lista
            .iter()
            .filter(|l| l.esta_en(Categoria::Caches) && l.consecuencia == REGENERA)
            .cloned()
            .collect(),
        _ => lista
            .iter()
            .filter(|l| l.id == id && !l.command.is_empty())
            .cloned()
            .collect(),
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

/// A dialog taller than the screen hides its own buttons.
const LINEAS_EN_CONFIRMACION: usize = 10;

pub fn confirmacion(elegidas: &[Limpieza]) -> Confirmacion {
    let total: u64 = elegidas.iter().map(|l| l.space).sum();
    let permanente = elegidas.iter().any(Limpieza::es_permanente);
    let mut lineas: Vec<String> = elegidas
        .iter()
        .take(LINEAS_EN_CONFIRMACION)
        .map(|l| format!("• {} — {}", l.titulo, tamano(l.space)))
        .collect();
    if elegidas.len() > LINEAS_EN_CONFIRMACION {
        lineas.push(format!(
            "• y {} más",
            elegidas.len() - LINEAS_EN_CONFIRMACION
        ));
    }
    let proyectos = elegidas.iter().any(Limpieza::esta_en_proyectos);
    let worktrees = elegidas.iter().any(Limpieza::esta_en_worktrees);
    let descarga = elegidas.iter().any(|l| l.consecuencia == REDESCARGA);
    let docker = elegidas.iter().any(|l| l.esta_en(Categoria::Docker));
    let despues = if permanente {
        "Lo que hay en la papelera se borra para siempre. Esto no se puede deshacer."
    } else if worktrees {
        "Solo se quita la copia de trabajo: la rama y sus commits siguen en el repo. Si algo \
         cambió desde la última medición, git se niega y no se quita."
    } else if proyectos {
        "Tu código no se toca. Cuando vuelvas a esos proyectos habrá que reinstalar las \
         dependencias o volver a compilar."
    } else if descarga && !docker {
        "Habrá que volver a descargarlo cuando lo necesites, y según lo que sea puede tardar \
         y gastar datos."
    } else if descarga {
        "Las imágenes habrá que volver a descargarlas cuando las necesites, y los \
         contenedores parados se pierden. Lo que esté corriendo y los volúmenes no se tocan."
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
        } else if worktrees {
            "Quitar".into()
        } else if descarga && docker {
            "Borrar imágenes".into()
        } else if descarga {
            "Borrar".into()
        } else {
            "Liberar".into()
        },
        permanente: permanente || descarga,
    }
}

/// What a run achieved: free space measured before and after, and the
/// commands that failed with their last error line.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Hecho {
    pub liberado: u64,
    pub fallos: Vec<(String, String)>,
    /// Docker keeps everything in one disk image, which may not shrink at once.
    pub docker: bool,
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
        [] if h.docker => "Docker puede tardar en devolver el espacio al disco.".to_string(),
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
/// `brew`, `npm` and `docker` are not found.
fn path_con_herramientas() -> String {
    let actual = std::env::var("PATH").unwrap_or_default();
    format!(
        "/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:{actual}"
    )
}

/// How far a run has got. `liberado` is measured on the disk, like the final
/// figure; `objetivo` is the engine's estimate.
#[derive(Debug, Clone, PartialEq)]
pub struct Avance {
    pub paso: usize,
    pub pasos: usize,
    pub titulo: String,
    pub liberado: u64,
    pub objetivo: u64,
}

impl Avance {
    /// One line for the menu. The estimate can fall short, so once the
    /// measured figure passes it only the measured figure is shown.
    pub fn texto(&self) -> String {
        let cuenta = if self.pasos > 1 {
            format!("{} de {}: ", self.paso, self.pasos)
        } else {
            String::new()
        };
        let cifras = if self.liberado > self.objetivo {
            format!("{} liberados", tamano(self.liberado))
        } else {
            format!("{} de {}", tamano(self.liberado), tamano(self.objetivo))
        };
        format!("Liberando {cuenta}{} · {cifras}", self.titulo)
    }
}

/// How often the free space is measured during a run. Reading it costs next to
/// nothing (see `POLL_INTERVAL` in `lib.rs`).
const INTERVALO_AVANCE: Duration = Duration::from_secs(1);

/// Runs the chosen cleanups one after another and measures the result, telling
/// `al_avanzar` how it goes: when each one starts, and every second while it
/// runs, since a single `rm -rf` of a big cache can take minutes.
pub fn ejecutar<A>(elegidas: &[Limpieza], al_avanzar: A) -> Hecho
where
    A: Fn(&Avance) + Sync,
{
    let antes = disk::read().map(|u| u.available);
    let objetivo: u64 = elegidas.iter().map(|l| l.space).sum();
    let medido = || match (antes, disk::read().map(|u| u.available)) {
        (Some(a), Some(d)) => d.saturating_sub(a),
        _ => 0,
    };
    let mut fallos = Vec::new();
    for (i, l) in elegidas.iter().enumerate() {
        let avisar = || {
            al_avanzar(&Avance {
                paso: i + 1,
                pasos: elegidas.len(),
                titulo: l.titulo.clone(),
                liberado: medido(),
                objetivo,
            })
        };
        avisar();
        let termino = AtomicBool::new(false);
        let r = std::thread::scope(|hilos| {
            hilos.spawn(|| {
                let mut ultimo = Instant::now();
                while !termino.load(Ordering::SeqCst) {
                    std::thread::sleep(Duration::from_millis(50));
                    if ultimo.elapsed() >= INTERVALO_AVANCE {
                        ultimo = Instant::now();
                        avisar();
                    }
                }
            });
            let r = Command::new("/bin/sh")
                .arg("-c")
                .arg(&l.command)
                .env("PATH", path_con_herramientas())
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .output();
            termino.store(true, Ordering::SeqCst);
            r
        });
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
    Hecho {
        liberado: medido(),
        fallos,
        docker: elegidas
            .iter()
            .any(|l| l.esta_en(Categoria::Docker) || l.categoria == CATEGORIA_DOCKER_DETALLE),
    }
}

/// What the engine lists about development, slower than the caches.
const MODOS_DESARROLLO: [&str; 4] = [
    "--proyectos",
    "--worktrees",
    "--ambientes",
    "--docker-detalle",
];

/// The cleanups' place in the menu and their current list.
pub struct Liberador {
    app: AppHandle,
    categorias: Vec<(Categoria, Submenu<Wry>)>,
    fila_seguro: MenuItem<Wry>,
    proyectos: Submenu<Wry>,
    worktrees: Submenu<Wry>,
    ambientes: Submenu<Wry>,
    motor: Option<Motor>,
    lista: Mutex<Vec<Limpieza>>,
    /// What comes from the slower measures: projects and the like.
    desarrollo: Mutex<Vec<Limpieza>>,
    /// The rows that explain "Sistema y otros". Read-only.
    desglose: Mutex<Vec<String>>,
    ocupado: AtomicBool,
}

impl Liberador {
    pub fn new(
        app: AppHandle,
        categorias: Vec<(Categoria, Submenu<Wry>)>,
        fila_seguro: MenuItem<Wry>,
        proyectos: Submenu<Wry>,
        worktrees: Submenu<Wry>,
        ambientes: Submenu<Wry>,
        motor: Option<Motor>,
    ) -> Arc<Self> {
        let l = Arc::new(Liberador {
            app,
            categorias,
            fila_seguro,
            proyectos,
            worktrees,
            ambientes,
            motor,
            lista: Mutex::new(Vec::new()),
            desarrollo: Mutex::new(Vec::new()),
            desglose: Mutex::new(Vec::new()),
            ocupado: AtomicBool::new(false),
        });
        let texto = if l.motor.is_some() {
            "Midiendo lo que se puede liberar…"
        } else {
            "Motor de análisis no encontrado"
        };
        l.poner(&[], Some(texto));
        l
    }

    /// Rebuilds every submenu and the top-level row.
    fn poner(&self, lista: &[Limpieza], aviso: Option<&str>) {
        let mut con_desarrollo = lista.to_vec();
        con_desarrollo.extend(self.desarrollo.lock().unwrap().iter().cloned());
        for (c, submenu) in &self.categorias {
            let mut todas = filas(*c, &con_desarrollo, aviso);
            if *c == Categoria::Resto {
                let desglose = self.desglose.lock().unwrap();
                if !desglose.is_empty() {
                    let mut primero = vec![Fila::Texto(TITULO_DESGLOSE.into())];
                    primero.extend(desglose.iter().cloned().map(Fila::Texto));
                    primero.push(Fila::Separador);
                    primero.append(&mut todas);
                    todas = primero;
                }
            }
            poner_filas(&self.app, submenu, &todas);
        }
        let (texto, activa) = match aviso {
            Some(a) => (a.to_string(), false),
            None => fila_seguro(lista),
        };
        let _ = self.fila_seguro.set_text(texto);
        let _ = self.fila_seguro.set_enabled(activa);
        self.poner_desarrollo(aviso);
        menu_nativo::aplicar(&self.app);
    }

    /// Keeps what "Sistema y otros" is made of. It shows with the next
    /// `refrescar`, which the same thread runs right after.
    pub fn poner_desglose(&self, filas: Vec<String>) {
        *self.desglose.lock().unwrap() = filas;
    }

    fn poner_desarrollo(&self, aviso: Option<&str>) {
        let lista = self.desarrollo.lock().unwrap().clone();
        let _ = self.proyectos.set_text(fila_proyectos(&lista));
        poner_filas(&self.app, &self.proyectos, &filas_proyectos(&lista, aviso));
        let _ = self.worktrees.set_text(fila_worktrees(&lista));
        poner_filas(&self.app, &self.worktrees, &filas_worktrees(&lista, aviso));
        let _ = self.ambientes.set_text(fila_ambientes(&lista));
        poner_filas(&self.app, &self.ambientes, &filas_ambientes(&lista, aviso));
    }

    /// Re-measures and rebuilds the menu. Blocking: call it off the main
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
                self.poner(&lista, None);
                *self.lista.lock().unwrap() = lista;
            }
            // The reason goes to the log: a long line would widen the whole menu.
            Err(e) => {
                eprintln!("No se pudo medir lo que se puede liberar: {e}");
                self.poner(&[], Some("No se pudo medir"));
            }
        }
        // Last, because it is the slowest: the rest of the menu is ready.
        let mut desarrollo = Vec::new();
        for modo in MODOS_DESARROLLO {
            match medir_desarrollo(motor, modo) {
                Ok(lista) => desarrollo.extend(lista),
                Err(e) => eprintln!("No se pudo medir {modo}: {e}"),
            }
        }
        if self.ocupado.load(Ordering::SeqCst) {
            return;
        }
        *self.desarrollo.lock().unwrap() = desarrollo;
        let lista = self.lista.lock().unwrap().clone();
        self.poner(&lista, None);
    }

    /// Handles a click on `id` (without the prefix): confirm, run, report.
    /// `al_empezar` and `al_terminar` let the caller animate the icon and
    /// notify; both run on a worker thread.
    pub fn pedir<E, T>(self: &Arc<Self>, id: &str, al_empezar: E, al_terminar: T)
    where
        E: FnOnce() + Send + 'static,
        T: FnOnce(&Hecho) + Send + 'static,
    {
        let mut todas = self.lista.lock().unwrap().clone();
        todas.extend(self.desarrollo.lock().unwrap().iter().cloned());
        let elegidas = elegir(&todas, id);
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
                yo.poner(&[], Some("Liberando espacio…"));
                std::thread::spawn(move || {
                    al_empezar();
                    let hecho = ejecutar(&elegidas, |avance| {
                        let _ = yo.fila_seguro.set_text(avance.texto());
                        menu_nativo::aplicar(&yo.app);
                    });
                    // Before measuring again, which takes about ten seconds:
                    // the result is already known.
                    al_terminar(&hecho);
                    yo.poner(&[], Some("Midiendo lo que se puede liberar…"));
                    yo.ocupado.store(false, Ordering::SeqCst);
                    yo.refrescar();
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
            categoria: if consecuencia == PERMANENTE {
                "tuyo".into()
            } else {
                "caches".into()
            },
            command: format!("echo {id}"),
            dias: None,
            motivo: String::new(),
        }
    }

    #[test]
    fn solo_entra_lo_que_el_menu_puede_ofrecer() {
        let json = r#"[
            {"id":"logs","titulo":"Logs","descripcion":"","space":1,"consecuencia":"regenera","categoria":"caches","command":"x"},
            {"id":"docker_imagenes","titulo":"I","descripcion":"","space":1,"consecuencia":"redescarga","categoria":"docker","command":"docker image prune -a -f"},
            {"id":"malo","titulo":"M","descripcion":"","space":1,"consecuencia":"redescarga","categoria":"docker","command":"docker system prune -a --volumes -f"},
            {"id":"lista","titulo":"L","descripcion":"","space":1,"consecuencia":"solo_lista","categoria":"caches","command":"du"},
            {"id":"vacio","titulo":"V","descripcion":"","space":1,"consecuencia":"regenera","categoria":"caches","command":"  "},
            {"id":"papelera","titulo":"Papelera","descripcion":"","space":1,"consecuencia":"permanente","categoria":"tuyo","command":"y"}
        ]"#;
        let ids: Vec<String> = leer(json).unwrap().into_iter().map(|l| l.id).collect();
        assert_eq!(ids, vec!["logs", "docker_imagenes", "papelera"]);
    }

    fn ids(f: &[Fila]) -> Vec<String> {
        f.iter()
            .filter_map(|x| match x {
                Fila::Accion { id, .. } => Some(id.clone()),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn la_papelera_va_en_tus_archivos_y_nunca_entra_en_liberar_lo_seguro() {
        let lista = vec![
            l("caches_de_apps", REGENERA, 6 * GB),
            l("logs", REGENERA, GB / 2),
            l("papelera", PERMANENTE, 2 * GB),
        ];
        assert!(!ids(&filas(Categoria::Caches, &lista, None)).contains(&"liberar:papelera".into()));
        assert!(ids(&filas(Categoria::Tuyo, &lista, None)).contains(&"liberar:papelera".into()));

        assert_eq!(
            fila_seguro(&lista),
            ("Liberar lo seguro…\t6,5 GB".to_string(), true)
        );
        let todo: Vec<String> = elegir(&lista, TODO).into_iter().map(|l| l.id).collect();
        assert_eq!(todo, vec!["caches_de_apps", "logs"]);
    }

    #[test]
    fn liberar_lo_seguro_no_entra_en_docker() {
        let mut build = l("docker_build", REGENERA, 8 * GB);
        build.categoria = "docker".into();
        let lista = vec![build, l("logs", REGENERA, GB)];
        assert_eq!(elegir(&lista, TODO).len(), 1);
        assert!(fila_seguro(&lista).0.ends_with("1,0 GB"));
    }

    fn de_docker(id: &str, consecuencia: &str) -> Limpieza {
        let mut d = l(id, consecuencia, 4 * GB);
        d.categoria = "docker".into();
        d
    }

    #[test]
    fn docker_separa_lo_que_vuelve_solo_de_lo_que_hay_que_descargar() {
        let lista = vec![
            de_docker("docker_build", REGENERA),
            de_docker("docker_imagenes", REDESCARGA),
        ];
        let f = filas(Categoria::Docker, &lista, None);
        let pos = |t: &str| f.iter().position(|x| *x == Fila::Texto(t.into())).unwrap();
        let fila = |i: &str| {
            f.iter()
                .position(|x| matches!(x, Fila::Accion { id, .. } if id == i))
                .unwrap()
        };
        assert!(fila("liberar:docker_build") < pos("Hay que volver a descargar"));
        assert!(pos("Hay que volver a descargar") < fila("liberar:docker_imagenes"));
        assert!(!ids(&f).iter().any(|i| i == "liberar:todo"));
    }

    #[test]
    fn docker_apagado_lo_dice_y_no_ofrece_limpiar() {
        let f = filas(Categoria::Docker, &[], None);
        assert!(matches!(&f[0], Fila::Texto(t) if t.contains("apagado")));
        assert!(!ids(&f).iter().any(|i| i.starts_with(PREFIJO)));
    }

    #[test]
    fn docker_nombra_imagenes_y_deja_los_volumenes_sin_accion() {
        let detalle = |id: &str, cons: &str, cmd: &str| {
            let mut d = l(id, cons, GB);
            d.categoria = CATEGORIA_DOCKER_DETALLE.into();
            d.command = cmd.into();
            d
        };
        let lista = vec![
            detalle("libre", REDESCARGA, "docker image rm x"),
            detalle("usada", REDESCARGA, ""),
            detalle("vol", "solo_lista", ""),
        ];
        let f = filas(Categoria::Docker, &lista, None);
        let acciones = ids(&f);
        assert!(acciones.contains(&"liberar:libre".to_string()));
        assert!(!acciones
            .iter()
            .any(|i| i.contains("usada") || i.contains("vol")));
        assert!(f.contains(&Fila::Texto("T-vol\t1,0 GB".into())));
        assert!(!acciones.contains(&"externo:docker".to_string()));
        assert!(elegir(&lista, "vol").is_empty());
    }

    #[test]
    fn con_docker_apagado_ofrece_encenderlo_solo_con_un_clic() {
        let f = filas(Categoria::Docker, &[], None);
        assert!(ids(&f).contains(&"externo:docker".to_string()));
    }

    #[test]
    fn la_confirmacion_de_una_imagen_no_habla_de_contenedores() {
        let mut d = l("img", REDESCARGA, GB);
        d.categoria = CATEGORIA_DOCKER_DETALLE.into();
        let c = confirmacion(&[d]);
        assert_eq!(c.boton, "Borrar");
        assert!(!c.mensaje.contains("contenedores"));
    }

    #[test]
    fn la_confirmacion_de_docker_avisa_de_la_descarga_y_de_los_contenedores() {
        let c = confirmacion(&[de_docker("docker_imagenes", REDESCARGA)]);
        assert!(c.permanente, "se avisa con el diálogo de advertencia");
        assert_eq!(c.boton, "Borrar imágenes");
        assert!(c.mensaje.contains("volver a descargarlas"));
        assert!(c.mensaje.contains("contenedores parados"));
    }

    #[test]
    fn el_aviso_final_explica_que_docker_puede_tardar_en_devolver_el_espacio() {
        let (t, c) = aviso_final(&Hecho {
            liberado: 0,
            fallos: vec![],
            docker: true,
        });
        assert_eq!(t, "No se liberó espacio");
        assert!(c.contains("Docker puede tardar"));
    }

    #[test]
    fn limpiar_todas_solo_aparece_en_cachés_con_mas_de_una() {
        let una = filas(Categoria::Caches, &[l("logs", REGENERA, GB)], None);
        assert!(!ids(&una).contains(&"liberar:caches".to_string()));

        let lista = vec![l("logs", REGENERA, GB), l("npm", REGENERA, GB)];
        let dos = filas(Categoria::Caches, &lista, None);
        assert_eq!(ids(&dos)[0], "liberar:caches");
        assert_eq!(elegir(&lista, TODAS_CACHES).len(), 2);
    }

    #[test]
    fn lo_que_hay_que_descargar_no_entra_en_limpiar_todas_ni_en_lo_seguro() {
        let lista = vec![
            l("uv", REGENERA, GB),
            l("act", REGENERA, GB),
            l("modelos", REDESCARGA, 8 * GB),
        ];
        let f = filas(Categoria::Caches, &lista, None);
        assert!(f.contains(&Fila::Texto(TITULO_DESCARGA.into())));
        assert!(ids(&f).contains(&"liberar:modelos".to_string()));
        assert!(!elegir(&lista, TODAS_CACHES)
            .iter()
            .any(|x| x.id == "modelos"));
        assert!(!elegir(&lista, TODO).iter().any(|x| x.id == "modelos"));
        assert_eq!(fila_seguro(&lista).0, "Liberar lo seguro…\t2,0 GB");
    }

    #[test]
    fn la_confirmacion_de_una_cache_a_descargar_no_habla_de_imagenes() {
        let c = confirmacion(&[l("modelos", REDESCARGA, GB)]);
        assert_eq!(c.boton, "Borrar");
        assert!(c.mensaje.contains("volver a descargarlo"));
        assert!(!c.mensaje.contains("contenedores"));
    }

    fn proyecto(id: &str, dias: Option<u64>, space: u64) -> Limpieza {
        let mut p = l(id, REGENERA, space);
        p.categoria = CATEGORIA_PROYECTOS.into();
        p.dias = dias;
        p
    }

    #[test]
    fn limpiar_olvidados_no_toca_lo_reciente_ni_lo_que_no_se_ofrece() {
        let mut sin_comando = proyecto("c", Some(90), GB);
        sin_comando.command = String::new();
        let lista = vec![
            proyecto("viejo", Some(40), GB),
            proyecto("nuevo", Some(2), GB),
            proyecto("sin_fecha", None, GB),
            sin_comando,
        ];
        let ids_elegidos: Vec<String> = elegir(&lista, PROYECTOS_OLVIDADOS)
            .into_iter()
            .map(|x| x.id)
            .collect();
        assert_eq!(ids_elegidos, vec!["viejo"]);
    }

    #[test]
    fn un_proyecto_sin_comando_no_se_puede_elegir_ni_por_id() {
        let mut p = proyecto("c", Some(90), GB);
        p.command = String::new();
        assert!(elegir(&[p], "c").is_empty());
    }

    #[test]
    fn los_proyectos_no_entran_en_liberar_lo_seguro() {
        let lista = vec![proyecto("p", Some(90), 4 * GB), l("logs", REGENERA, GB)];
        assert_eq!(elegir(&lista, TODO).len(), 1);
        assert_eq!(fila_seguro(&lista).0, "Liberar lo seguro…\t1,0 GB");
    }

    #[test]
    fn el_submenu_de_proyectos_lista_y_dice_lo_que_no_ofrece() {
        let mut sin_comando = proyecto("c", Some(90), GB);
        sin_comando.command = String::new();
        let lista = vec![
            proyecto("a", Some(40), 2 * GB),
            proyecto("b", Some(1), 3 * GB),
            sin_comando,
        ];
        let f = filas_proyectos(&lista, None);
        let i = ids(&f);
        assert_eq!(i[0], "liberar:proyectos_olvidados");
        assert_eq!(i[1], "liberar:b", "el mayor primero");
        assert_eq!(i.last().unwrap(), "ir:/projects");
        assert!(f.contains(&Fila::Texto(
            "1 sin ofrecer: podrían no reconstruirse".into()
        )));
        assert_eq!(fila_proyectos(&lista), "Proyectos\t6,0 GB");
    }

    fn worktree(id: &str, motivo: &str, space: u64) -> Limpieza {
        let mut w = l(id, REGENERA, space);
        w.categoria = CATEGORIA_WORKTREES.into();
        w.motivo = motivo.into();
        if !motivo.is_empty() {
            w.command = String::new();
        }
        w
    }

    #[test]
    fn solo_se_quitan_los_worktrees_que_no_pierden_nada() {
        let lista = vec![
            worktree("a", "", GB),
            worktree("b", "", 2 * GB),
            worktree("c", "tiene cambios sin commit", 9 * GB),
            worktree("d", "la rama no está mergeada", GB),
            worktree("e", "la rama no está mergeada", GB),
        ];
        let f = filas_worktrees(&lista, None);
        assert_eq!(
            ids(&f),
            vec!["liberar:worktrees_limpios", "liberar:b", "liberar:a"]
        );
        assert!(f.contains(&Fila::Texto("2: la rama no está mergeada".into())));
        assert!(f.contains(&Fila::Texto("1: tiene cambios sin commit".into())));

        let elegidos: Vec<String> = elegir(&lista, WORKTREES_LIMPIOS)
            .into_iter()
            .map(|x| x.id)
            .collect();
        assert_eq!(elegidos, vec!["a", "b"]);
        assert_eq!(fila_worktrees(&lista), "Worktrees (5)\t14 GB");
    }

    #[test]
    fn los_worktrees_no_entran_en_liberar_lo_seguro() {
        assert!(elegir(&[worktree("a", "", GB)], TODO).is_empty());
    }

    #[test]
    fn la_confirmacion_de_un_worktree_dice_que_la_rama_sigue() {
        let c = confirmacion(&[worktree("a", "", GB)]);
        assert_eq!(c.boton, "Quitar");
        assert!(c.mensaje.contains("la rama y sus commits siguen"));
    }

    #[test]
    fn los_ambientes_solo_ofrecen_lo_que_tiene_comando() {
        let mut cache = l("pkgs", REDESCARGA, GB);
        cache.categoria = CATEGORIA_AMBIENTES.into();
        let mut brew = l("brew", REGENERA, 2 * GB);
        brew.categoria = CATEGORIA_AMBIENTES.into();
        brew.command = String::new();
        let lista = vec![cache, brew];

        let f = filas_ambientes(&lista, None);

        assert_eq!(ids(&f), vec!["liberar:pkgs"]);
        assert!(f.contains(&Fila::Texto("T-brew\t2,0 GB".into())));
        assert_eq!(fila_ambientes(&lista), "Ambientes\t3,0 GB");
        assert!(elegir(&lista, TODO).is_empty());
    }

    #[test]
    fn la_confirmacion_no_crece_sin_limite_y_dice_que_el_codigo_no_se_toca() {
        let lista: Vec<Limpieza> = (0..15)
            .map(|i| proyecto(&format!("p{i}"), Some(90), GB))
            .collect();
        let c = confirmacion(&lista);
        assert!(c.mensaje.contains("y 5 más"));
        assert!(c.mensaje.contains("Tu código no se toca"));
        assert_eq!(c.boton, "Liberar");
    }

    #[test]
    fn solo_cachés_ofrece_limpiar_todo() {
        let lista = vec![l("logs", REGENERA, GB), l("papelera", PERMANENTE, GB)];
        for c in [Categoria::Docker, Categoria::Tuyo, Categoria::Resto] {
            assert!(!ids(&filas(c, &lista, None))
                .iter()
                .any(|i| i == "liberar:todo" || i == "liberar:caches"));
        }
    }

    #[test]
    fn sistema_y_otros_no_ofrece_borrar_nada_si_el_motor_no_lo_propone() {
        let f = filas(Categoria::Resto, &[l("logs", REGENERA, GB)], None);
        assert!(!ids(&f).iter().any(|i| i.starts_with(PREFIJO)));
        assert_eq!(f[0], Fila::Texto("Nada que limpiar desde aquí".into()));
    }

    #[test]
    fn un_aviso_sustituye_las_limpiezas_pero_deja_las_salidas() {
        let f = filas(Categoria::Caches, &[], Some("Midiendo…"));
        assert_eq!(f[0], Fila::Texto("Midiendo…".into()));
        assert_eq!(ids(&f), vec!["externo:caches"]);
        assert!(!fila_seguro(&[]).1);
    }

    #[test]
    fn el_swap_ofrece_cerrar_apps_y_no_promete_nada_mas() {
        let f = filas_swap(&[("Slack".to_string(), 4 * GB)]);
        assert_eq!(ids(&f), vec!["cerrar:Slack", "externo:monitor"]);
        assert!(matches!(&f[1], Fila::Accion { texto, .. } if texto == "Cerrar Slack…\t4,0 GB"));
        assert_eq!(
            f.last(),
            Some(&Fila::Texto(
                "Si no baja al cerrar, solo se libera al reiniciar".into()
            ))
        );
        assert_eq!(ids(&filas_swap(&[])), vec!["externo:monitor"]);
    }

    #[test]
    fn la_url_del_analizador_conserva_el_token_en_cualquier_pagina() {
        let u = "http://127.0.0.1:8123/?token=abc";
        assert_eq!(url_en(u, "/"), u);
        assert_eq!(url_en(u, "/files"), "http://127.0.0.1:8123/files?token=abc");
        assert_eq!(
            url_en(u, "/files?path=/Downloads/&orden=antiguedad"),
            "http://127.0.0.1:8123/files?path=/Downloads/&orden=antiguedad&token=abc"
        );
    }

    #[test]
    fn un_id_externo_nunca_es_una_ruta_cualquiera() {
        assert_eq!(
            externo_de(EXTERNO_DESCARGAS, "/Users/u").as_deref(),
            Some("/Users/u/Downloads")
        );
        assert_eq!(externo_de("/etc/passwd", "/Users/u"), None);
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
        assert!(c.mensaje.contains("T-logs — 1,0 GB"));
    }

    #[test]
    fn el_aviso_final_da_la_cifra_medida_y_los_fallos() {
        let (t, _) = aviso_final(&Hecho {
            liberado: 3 * GB,
            ..Hecho::default()
        });
        assert_eq!(t, "Liberados 3,0 GB");
        let (t, c) = aviso_final(&Hecho {
            liberado: 0,
            fallos: vec![("Caché de npm".into(), "npm: command not found".into())],
            docker: false,
        });
        assert_eq!(t, "No se liberó espacio");
        assert!(c.contains("Caché de npm: npm: command not found"));
    }

    fn avance(paso: usize, pasos: usize, liberado: u64, objetivo: u64) -> Avance {
        Avance {
            paso,
            pasos,
            titulo: "Cache de npm".into(),
            liberado,
            objetivo,
        }
    }

    #[test]
    fn el_avance_dice_el_paso_y_lo_liberado_de_lo_estimado() {
        assert_eq!(
            avance(2, 4, 5 * GB, 12 * GB).texto(),
            "Liberando 2 de 4: Cache de npm · 5,0 GB de 12 GB"
        );
        assert_eq!(
            avance(1, 1, GB / 2, GB).texto(),
            "Liberando Cache de npm · 512 MB de 1,0 GB"
        );
    }

    #[test]
    fn si_se_libera_mas_de_lo_estimado_solo_da_lo_medido() {
        assert_eq!(
            avance(1, 1, 3 * GB, GB).texto(),
            "Liberando Cache de npm · 3,0 GB liberados"
        );
    }

    #[test]
    fn ejecutar_avisa_al_empezar_cada_paso_y_mientras_dura() {
        let mut lenta = l("lenta", REGENERA, GB);
        lenta.command = "sleep 3.5".into();
        let mut rapida = l("rapida", REGENERA, GB);
        rapida.command = "true".into();
        let vistos = Mutex::new(Vec::new());

        ejecutar(&[lenta, rapida], |a| {
            vistos.lock().unwrap().push((a.paso, a.pasos, a.objetivo));
        });

        let vistos = vistos.into_inner().unwrap();
        let del_primero = vistos.iter().filter(|v| v.0 == 1).count();
        assert!(del_primero >= 3, "al empezar y cada segundo: {vistos:?}");
        assert_eq!(vistos.last(), Some(&(2, 2, 2 * GB)));
    }

    #[test]
    fn ejecutar_informa_del_error_de_un_comando_que_falla() {
        let mut malo = l("x", REGENERA, 1);
        malo.command = "echo 'algo salió mal' >&2; exit 3".into();
        let h = ejecutar(&[malo], |_| {});
        assert_eq!(h.fallos, vec![("T-x".into(), "algo salió mal".into())]);
    }
}
