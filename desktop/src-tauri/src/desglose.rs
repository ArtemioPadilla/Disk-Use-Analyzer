//! What "Sistema y otros" is made of.
//!
//! That row is whatever is left once the rest is measured, and on its own it
//! explains nothing. This names the parts it can measure and states what it
//! could not, as a figure of its own, instead of letting it pass for "system".
//!
//! Read-only: nothing here is ever offered for deletion. And without Full Disk
//! Access it does not read `~/Library`, which would make macOS ask folder by
//! folder (see `categorias.rs`).

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::categorias::{du, tamano};

/// A measured part, and the folders it adds up.
#[derive(Debug, Clone, PartialEq)]
pub struct Parte {
    pub nombre: &'static str,
    pub bytes: u64,
}

/// What to read, given the permissions the app has.
#[derive(Debug, PartialEq)]
pub struct Plan {
    pub aplicaciones: Vec<PathBuf>,
    pub herramientas: Vec<PathBuf>,
    pub sistema: Vec<PathBuf>,
    /// `~/Library`, its parts counted elsewhere, and Mail and Messages. Empty
    /// when reading them would prompt.
    pub biblioteca: Option<Biblioteca>,
}

#[derive(Debug, PartialEq)]
pub struct Biblioteca {
    pub todo: PathBuf,
    pub ya_contado: Vec<PathBuf>,
    pub correo: Vec<PathBuf>,
}

pub fn plan(casa: &Path, acceso_total: bool) -> Plan {
    Plan {
        aplicaciones: vec![PathBuf::from("/Applications"), casa.join("Applications")],
        herramientas: ["/opt", "/usr/local"]
            .map(PathBuf::from)
            .into_iter()
            .chain([".local", ".cargo", ".rustup", ".vscode", ".cursor"].map(|d| casa.join(d)))
            .collect(),
        // Not all of /private/var: `vm` is a volume of its own, counted as swap.
        sistema: [
            "/Library",
            "/private/var/db",
            "/private/var/folders",
            "/private/var/log",
        ]
        .map(PathBuf::from)
        .to_vec(),
        biblioteca: acceso_total.then(|| Biblioteca {
            todo: casa.join("Library"),
            ya_contado: [
                "Library/Caches",
                "Library/Logs",
                "Library/Containers/com.docker.docker/Data",
            ]
            .map(|d| casa.join(d))
            .to_vec(),
            correo: ["Library/Mail", "Library/Messages"]
                .map(|d| casa.join(d))
                .to_vec(),
        }),
    }
}

/// The APFS volumes from `diskutil apfs list`, as (name, bytes consumed).
pub fn parsear_apfs(salida: &str) -> Vec<(String, u64)> {
    let mut volumenes = Vec::new();
    let mut nombre: Option<String> = None;
    for linea in salida.lines() {
        let linea = linea.trim_start_matches([' ', '|', '+', '-', '>']).trim();
        if let Some(n) = linea.strip_prefix("Name:") {
            let n = n.trim();
            let n = n.split(" (").next().unwrap_or(n);
            nombre = Some(n.to_string());
        } else if let Some(c) = linea.strip_prefix("Capacity Consumed:") {
            let bytes = c.split_whitespace().next().and_then(|b| b.parse().ok());
            if let (Some(n), Some(b)) = (nombre.take(), bytes) {
                volumenes.push((n, b));
            }
        }
    }
    volumenes
}

/// macOS itself and swap, out of the volumes. Everything but the user's data
/// volume is the system's, whatever Apple calls them this year.
pub fn de_volumenes(volumenes: &[(String, u64)]) -> Vec<Parte> {
    let swap: u64 = volumenes
        .iter()
        .filter(|(n, _)| n == "VM")
        .map(|(_, b)| b)
        .sum();
    let macos: u64 = volumenes
        .iter()
        .filter(|(n, _)| n != "VM" && n != "Data")
        .map(|(_, b)| b)
        .sum();
    vec![
        Parte {
            nombre: "macOS",
            bytes: macos,
        },
        Parte {
            nombre: "Swap",
            bytes: swap,
        },
    ]
}

/// Measures everything. Takes a while: call it off the main thread.
pub fn medir(acceso_total: bool) -> Vec<Parte> {
    let casa = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
    let plan = plan(&casa, acceso_total);
    let mut partes = vec![
        Parte {
            nombre: "Aplicaciones",
            bytes: du(&plan.aplicaciones),
        },
        Parte {
            nombre: "Herramientas de desarrollo",
            bytes: du(&plan.herramientas),
        },
        Parte {
            nombre: "/Library y /private/var",
            bytes: du(&plan.sistema),
        },
    ];
    if let Some(b) = plan.biblioteca {
        let correo = du(&b.correo);
        let todo = du(std::slice::from_ref(&b.todo));
        let fuera = du(&b.ya_contado) + correo;
        partes.push(Parte {
            nombre: "Datos de apps",
            bytes: todo.saturating_sub(fuera),
        });
        partes.push(Parte {
            nombre: "Mail y Mensajes",
            bytes: correo,
        });
    }
    if let Ok(o) = Command::new("/usr/sbin/diskutil")
        .args(["apfs", "list"])
        .output()
    {
        partes.extend(de_volumenes(&parsear_apfs(&String::from_utf8_lossy(
            &o.stdout,
        ))));
    }
    partes
}

/// The rows of the submenu: largest first, and what is left stated as such, so
/// that they add up to `resto`, the figure on the row itself. Measures taken at
/// different moments, or files with clones, can add up to a little more; then
/// nothing is left and it does not pretend otherwise.
pub fn filas(partes: &[Parte], resto: u64, acceso_total: bool) -> Vec<String> {
    let mut ordenadas: Vec<&Parte> = partes.iter().filter(|p| p.bytes > 0).collect();
    ordenadas.sort_by_key(|p| std::cmp::Reverse(p.bytes));
    let medido: u64 = ordenadas.iter().map(|p| p.bytes).sum();
    let mut out: Vec<String> = ordenadas
        .iter()
        .map(|p| format!("{}\t{}", p.nombre, tamano(p.bytes)))
        .collect();
    let sin_medir = resto.saturating_sub(medido);
    if sin_medir > 0 {
        out.push(format!("Sin medir\t{}", tamano(sin_medir)));
    }
    if !acceso_total {
        out.push("Sin Acceso total al disco falta ~/Library".to_string());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const GB: u64 = 1 << 30;

    const APFS: &str = "\
    +-> Volume disk3s1 929E22E4
    |   Name:                      Macintosh HD (Case-insensitive)
    |   Capacity Consumed:         1000 B (1.0 KB)
    +-> Volume disk3s2 EBDFE772
    |   Name:                      Preboot (Case-insensitive)
    |   Capacity Consumed:         200 B (0.2 KB)
    +-> Volume disk3s5 B3505597
    |   Name:                      Data (Case-insensitive)
    |   Capacity Consumed:         9000 B (9.0 KB)
        Name:                      VM (Case-insensitive)
        Capacity Consumed:         300 B (0.3 KB)
";

    #[test]
    fn lee_los_volumenes_de_apfs() {
        let v = parsear_apfs(APFS);
        assert_eq!(v.len(), 4);
        assert_eq!(v[0], ("Macintosh HD".to_string(), 1000));
        assert_eq!(v[3], ("VM".to_string(), 300));
    }

    #[test]
    fn macos_es_todo_menos_los_datos_y_el_swap_aparte() {
        let p = de_volumenes(&parsear_apfs(APFS));
        assert_eq!(p[0].bytes, 1200);
        assert_eq!(p[1].bytes, 300);
    }

    #[test]
    fn sin_acceso_total_no_lee_library_para_no_disparar_avisos() {
        let casa = Path::new("/Users/u");
        let sin = plan(casa, false);
        assert_eq!(sin.biblioteca, None);
        let rutas: Vec<&PathBuf> = sin
            .aplicaciones
            .iter()
            .chain(&sin.herramientas)
            .chain(&sin.sistema)
            .collect();
        assert!(!rutas.iter().any(|r| r.starts_with("/Users/u/Library")));
        assert!(plan(casa, true).biblioteca.is_some());
    }

    #[test]
    fn las_filas_suman_lo_que_dice_la_fila_y_nombran_lo_no_medido() {
        let partes = vec![
            Parte {
                nombre: "macOS",
                bytes: 20 * GB,
            },
            Parte {
                nombre: "Aplicaciones",
                bytes: 70 * GB,
            },
            Parte {
                nombre: "Vacío",
                bytes: 0,
            },
        ];
        assert_eq!(
            filas(&partes, 100 * GB, true),
            vec!["Aplicaciones\t70 GB", "macOS\t20 GB", "Sin medir\t10 GB"]
        );
    }

    #[test]
    fn si_lo_medido_se_pasa_no_inventa_un_sin_medir() {
        let partes = vec![Parte {
            nombre: "macOS",
            bytes: 120 * GB,
        }];
        assert_eq!(filas(&partes, 100 * GB, true), vec!["macOS\t120 GB"]);
    }

    #[test]
    fn sin_acceso_total_dice_que_falta() {
        let f = filas(&[], GB, false);
        assert!(f.last().unwrap().contains("Acceso total"));
    }
}
