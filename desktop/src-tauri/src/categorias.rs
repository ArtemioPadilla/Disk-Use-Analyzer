//! How the used part of the disk splits into categories, for the tray ring.
//!
//! Measured without ever triggering a macOS permission prompt. Docker keeps
//! its data under `~/Library/Containers`, and Documents, Desktop and
//! Downloads are privacy-protected too: reading any of them without Full
//! Disk Access makes macOS ask the user, folder by folder. So:
//!
//! - caches are always measured (their folders are not protected);
//! - Docker, through its own CLI when the daemon is up, or through its data
//!   folder when the app has Full Disk Access;
//! - the user's files, only with Full Disk Access;
//! - whatever is left over is "system and the rest".
//!
//! Anything that could not be measured falls into the rest rather than being
//! guessed.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::disk::DiskUsage;

/// The measured parts. `None` means "could not measure", not zero.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Reparto {
    pub docker: Option<u64>,
    pub caches: u64,
    pub tuyo: Option<u64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Categoria {
    Docker,
    Caches,
    Tuyo,
    Resto,
}

/// One slice of the ring: a category and its share of the *whole disk*.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Porcion {
    pub categoria: Categoria,
    pub fraccion: f64,
}

/// Splits the used space into ring slices, in a fixed order, each as a share
/// of the whole disk, so the slices add up to exactly the used fraction.
///
/// The measurements come from a scan that can be half an hour old while the
/// used figure is live. If they add up to more than what is used now (files
/// deleted since the scan), they are scaled down together, so the ring never
/// claims more than is used and never eats into the free gap.
pub fn porciones(uso: &DiskUsage, reparto: &Reparto) -> Vec<Porcion> {
    if uso.total == 0 {
        return Vec::new();
    }
    let medidas = [
        (Categoria::Docker, reparto.docker.unwrap_or(0)),
        (Categoria::Caches, reparto.caches),
        (Categoria::Tuyo, reparto.tuyo.unwrap_or(0)),
    ];
    let suma: u64 = medidas.iter().map(|(_, b)| b).sum();
    let escala = if suma > uso.used {
        uso.used as f64 / suma as f64
    } else {
        1.0
    };
    let total = uso.total as f64;
    let mut out: Vec<Porcion> = medidas
        .iter()
        .filter(|(_, b)| *b > 0)
        .map(|(c, b)| Porcion {
            categoria: *c,
            fraccion: *b as f64 * escala / total,
        })
        .collect();
    let asignado: f64 = out.iter().map(|p| p.fraccion).sum();
    let resto = uso.used as f64 / total - asignado;
    if resto > 0.0 {
        out.push(Porcion {
            categoria: Categoria::Resto,
            fraccion: resto,
        });
    }
    out
}

/// Parses a size as `docker system df` prints it: `12.5GB`, `1.2kB`, `0B`.
/// Docker uses decimal units (1 GB = 10^9 bytes).
pub fn bytes_docker(texto: &str) -> Option<u64> {
    let t = texto.trim();
    let corte = t.find(|c: char| c.is_ascii_alphabetic())?;
    let (num, unidad) = t.split_at(corte);
    let n: f64 = num.trim().parse().ok()?;
    let mult = match unidad.to_ascii_uppercase().as_str() {
        "B" => 1.0,
        "KB" => 1e3,
        "MB" => 1e6,
        "GB" => 1e9,
        "TB" => 1e12,
        _ => return None,
    };
    Some((n * mult) as u64)
}

/// Where the Docker CLI may live. Apps launched by macOS get a bare PATH
/// (`/usr/bin:/bin:...`), so `docker` alone would not be found.
const DOCKER: &[&str] = &[
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
    "/Applications/Docker.app/Contents/Resources/bin/docker",
];

fn docker_por_cli() -> Option<u64> {
    let bin = DOCKER.iter().find(|p| Path::new(p).exists())?;
    let out = Command::new(bin)
        .args(["system", "df", "--format", "{{.Size}}"])
        .output()
        .ok()?;
    if !out.status.success() {
        return None; // daemon down
    }
    let texto = String::from_utf8_lossy(&out.stdout);
    Some(texto.lines().filter_map(bytes_docker).sum())
}

/// `du -sk` over several paths, summed. Missing paths are skipped. Runs at
/// low priority: it walks tens of GB and nobody is waiting on it.
fn du(rutas: &[PathBuf]) -> u64 {
    let existentes: Vec<&PathBuf> = rutas.iter().filter(|p| p.exists()).collect();
    if existentes.is_empty() {
        return 0;
    }
    let Ok(out) = Command::new("/usr/bin/nice")
        .arg("-n")
        .arg("15")
        .arg("/usr/bin/du")
        .arg("-sk")
        .args(&existentes)
        .output()
    else {
        return 0;
    };
    // `du` exits non-zero when it hits unreadable subfolders but still
    // prints totals for what it could read, which is what we want.
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .filter_map(|l| l.split_whitespace().next()?.parse::<u64>().ok())
        .sum::<u64>()
        * 1024
}

/// Which folders may be read, given the permissions the app has. Split out
/// from `medir` so the rule "nothing protected without Full Disk Access" can
/// be tested without walking the disk.
#[derive(Debug, PartialEq)]
pub struct Plan {
    pub caches: Vec<PathBuf>,
    /// Docker's data folder; `None` when reading it would prompt the user.
    pub docker_carpeta: Option<PathBuf>,
    /// The user's own folders; empty when reading them would prompt.
    pub tuyo: Vec<PathBuf>,
}

pub fn plan(casa: &Path, acceso_total: bool) -> Plan {
    Plan {
        caches: ["Library/Caches", "Library/Logs", ".cache", ".npm"]
            .map(|d| casa.join(d))
            .to_vec(),
        docker_carpeta: acceso_total
            .then(|| casa.join("Library/Containers/com.docker.docker/Data")),
        tuyo: if acceso_total {
            [
                "Documents",
                "Desktop",
                "Downloads",
                "Pictures",
                "Movies",
                "Music",
            ]
            .map(|d| casa.join(d))
            .to_vec()
        } else {
            Vec::new()
        },
    }
}

/// Measures the categories. Takes seconds to a minute; call it from a
/// background thread, never from the poller.
pub fn medir(acceso_total: bool) -> Reparto {
    let casa = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
    let plan = plan(&casa, acceso_total);
    Reparto {
        caches: du(&plan.caches),
        docker: docker_por_cli().or_else(|| plan.docker_carpeta.map(|c| du(&[c]))),
        tuyo: (!plan.tuyo.is_empty()).then(|| du(&plan.tuyo)),
    }
}

/// The menu line that says what the ring's colours are, in the ring's
/// order. Without Full Disk Access it says so, so a mostly grey ring reads
/// as "missing permission" rather than "your disk is all system".
pub fn texto_reparto(r: &Reparto) -> String {
    let gb = |b: u64| format!("{:.0} GB", b as f64 / (1u64 << 30) as f64);
    let mut partes = Vec::new();
    if let Some(d) = r.docker.filter(|d| *d > 0) {
        partes.push(format!("Docker {}", gb(d)));
    }
    partes.push(format!("Cachés {}", gb(r.caches)));
    match r.tuyo {
        Some(t) => partes.push(format!("Tus archivos {}", gb(t))),
        None => partes.push("sin Acceso total al disco, el resto no se desglosa".into()),
    }
    partes.join(" · ")
}

#[cfg(test)]
mod tests {
    use super::*;

    const GB: u64 = 1_000_000_000;

    fn uso(total: u64, used: u64) -> DiskUsage {
        DiskUsage {
            total,
            used,
            available: total - used,
            purgeable: 0,
            percent: used as f64 / total as f64 * 100.0,
        }
    }

    #[test]
    fn las_porciones_suman_exactamente_lo_usado() {
        let p = porciones(
            &uso(400 * GB, 300 * GB),
            &Reparto {
                docker: Some(40 * GB),
                caches: 20 * GB,
                tuyo: Some(60 * GB),
            },
        );
        let suma: f64 = p.iter().map(|x| x.fraccion).sum();
        assert!((suma - 0.75).abs() < 1e-9, "suma {suma}, esperado 0.75");
        assert_eq!(p.last().unwrap().categoria, Categoria::Resto);
    }

    #[test]
    fn lo_que_no_se_pudo_medir_cae_en_el_resto_sin_inventar() {
        let p = porciones(
            &uso(400 * GB, 300 * GB),
            &Reparto {
                docker: None,
                caches: 20 * GB,
                tuyo: None,
            },
        );
        let cats: Vec<_> = p.iter().map(|x| x.categoria).collect();
        assert_eq!(cats, vec![Categoria::Caches, Categoria::Resto]);
    }

    #[test]
    fn una_medicion_vieja_mayor_que_lo_usado_se_escala_y_no_invade_lo_libre() {
        // Se borraron cosas desde el último escaneo: las medidas suman más
        // que lo usado ahora. El anillo nunca puede comerse el hueco libre.
        let p = porciones(
            &uso(400 * GB, 100 * GB),
            &Reparto {
                docker: Some(80 * GB),
                caches: 40 * GB,
                tuyo: Some(80 * GB),
            },
        );
        let suma: f64 = p.iter().map(|x| x.fraccion).sum();
        assert!(
            suma <= 0.25 + 1e-9,
            "el anillo ocupa {suma}, más que lo usado"
        );
    }

    #[test]
    fn lee_los_tamanos_de_docker() {
        assert_eq!(bytes_docker("12.5GB"), Some(12_500_000_000));
        assert_eq!(bytes_docker("1.2kB"), Some(1_200));
        assert_eq!(bytes_docker("0B"), Some(0));
        assert_eq!(bytes_docker("basura"), None);
    }

    #[test]
    fn sin_acceso_total_no_se_toca_nada_protegido() {
        // Sin Acceso total al disco, leer Documentos o la carpeta de Docker
        // haría que macOS pidiera permiso, carpeta por carpeta.
        let p = plan(Path::new("/Users/u"), false);
        assert_eq!(p.docker_carpeta, None);
        assert!(p.tuyo.is_empty());
        for ruta in &p.caches {
            let r = ruta.to_string_lossy();
            assert!(
                !r.contains("Containers") && !r.contains("Documents") && !r.contains("Downloads"),
                "{r} está protegida"
            );
        }
    }

    #[test]
    fn con_acceso_total_se_miden_tambien_tus_archivos_y_docker() {
        let p = plan(Path::new("/Users/u"), true);
        assert!(p.docker_carpeta.is_some());
        assert!(p.tuyo.iter().any(|r| r.ends_with("Downloads")));
    }

    #[test]
    fn el_texto_del_reparto_sigue_el_orden_del_anillo_y_dice_si_falta_permiso() {
        let g = 1u64 << 30;
        let completo = Reparto {
            docker: Some(20 * g),
            caches: 21 * g,
            tuyo: Some(180 * g),
        };
        assert_eq!(
            texto_reparto(&completo),
            "Docker 20 GB · Cachés 21 GB · Tus archivos 180 GB"
        );
        let sin_permiso = Reparto {
            docker: None,
            caches: 21 * g,
            tuyo: None,
        };
        assert_eq!(
            texto_reparto(&sin_permiso),
            "Cachés 21 GB · sin Acceso total al disco, el resto no se desglosa"
        );
    }
}
