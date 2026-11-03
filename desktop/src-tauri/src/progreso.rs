//! What the menu says while a scan runs.
//!
//! The engine writes `{fase, archivos, bytes, objetivo, segundos}` to a file
//! about once a second (`disk_analyzer.py --progreso`). `objetivo` is its
//! estimate of how many bytes the scan will count in total, from the previous
//! scan of the same path; without one there is no percentage and no time
//! left, only what has been counted so far — never a made-up figure.

use std::path::Path;

use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Progreso {
    pub fase: String,
    pub archivos: u64,
    pub bytes: u64,
    pub objetivo: Option<u64>,
    pub segundos: f64,
}

/// Reads the engine's progress file. `None` while it does not exist yet or
/// cannot be parsed: the menu keeps whatever it was showing.
pub fn leer(ruta: &Path) -> Option<Progreso> {
    serde_json::from_str(&std::fs::read_to_string(ruta).ok()?).ok()
}

/// The first seconds of a scan go through small folders at a pace that has
/// nothing to do with the rest; an estimate from them swings wildly.
const SEGUNDOS_ANTES_DE_ESTIMAR: f64 = 20.0;

fn gb(bytes: u64) -> f64 {
    bytes as f64 / (1024.0 * 1024.0 * 1024.0)
}

fn archivos(n: u64) -> String {
    if n >= 1_000_000 {
        format!("{:.1} M archivos", n as f64 / 1e6).replace('.', ",")
    } else if n >= 1_000 {
        format!("{} mil archivos", n / 1_000)
    } else {
        format!("{n} archivos")
    }
}

fn falta(segundos: f64) -> String {
    let minutos = (segundos / 60.0).round() as u64;
    if minutos < 1 {
        "falta menos de 1 min".into()
    } else {
        format!("faltan ~{minutos} min")
    }
}

impl Progreso {
    /// What the menu says: the state, and for the scan a second line with the
    /// counts. Two lines because a single one made the whole menu wider.
    pub fn lineas(&self) -> (String, Option<String>) {
        match self.fase.as_str() {
            "escaneo" => self.lineas_escaneo(),
            "duplicados" => ("Buscando archivos duplicados…".into(), None),
            "caches" => ("Midiendo cachés…".into(), None),
            "docker" => ("Revisando Docker…".into(), None),
            _ => ("Preparando el informe…".into(), None),
        }
    }

    fn lineas_escaneo(&self) -> (String, Option<String>) {
        let Some(objetivo) = self.objetivo.filter(|o| *o > 0) else {
            return (
                "Analizando…".into(),
                Some(format!(
                    "{:.0} GB · {}",
                    gb(self.bytes),
                    archivos(self.archivos)
                )),
            );
        };
        // Capped: the estimate can fall short of what the scan finds, and
        // "100 %" with more to go, or "104 %", would be worse than vague.
        let fraccion = (self.bytes as f64 / objetivo as f64).min(0.99);
        let mut estado = format!("Analizando… {:.0} %", fraccion * 100.0);
        if self.segundos >= SEGUNDOS_ANTES_DE_ESTIMAR && fraccion > 0.02 {
            let restante = self.segundos * (1.0 - fraccion) / fraccion;
            estado.push_str(" · ");
            estado.push_str(&falta(restante));
        }
        let cuentas = format!(
            "{:.0} de {:.0} GB · {}",
            gb(self.bytes),
            gb(objetivo),
            archivos(self.archivos)
        );
        (estado, Some(cuentas))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const GB: u64 = 1024 * 1024 * 1024;

    fn p(bytes: u64, objetivo: Option<u64>, segundos: f64, archivos: u64) -> Progreso {
        Progreso {
            fase: "escaneo".into(),
            archivos,
            bytes,
            objetivo,
            segundos,
        }
    }

    fn par(a: &str, b: &str) -> (String, Option<String>) {
        (a.to_string(), Some(b.to_string()))
    }

    #[test]
    fn con_objetivo_dice_porcentaje_total_y_lo_que_falta() {
        // 100 of 300 GB in 60 s: a third done, twice as long to go.
        let t = p(100 * GB, Some(300 * GB), 60.0, 1_234_567).lineas();
        assert_eq!(
            t,
            par(
                "Analizando… 33 % · faltan ~2 min",
                "100 de 300 GB · 1,2 M archivos"
            )
        );
    }

    #[test]
    fn sin_objetivo_solo_dice_lo_contado() {
        let t = p(95 * GB, None, 60.0, 850_400).lineas();
        assert_eq!(t, par("Analizando…", "95 GB · 850 mil archivos"));
    }

    #[test]
    fn al_principio_no_se_atreve_a_estimar_el_tiempo() {
        let t = p(10 * GB, Some(300 * GB), 5.0, 900).lineas();
        assert_eq!(t, par("Analizando… 3 %", "10 de 300 GB · 900 archivos"));
    }

    #[test]
    fn nunca_pasa_del_99_aunque_cuente_mas_de_lo_estimado() {
        let (estado, _) = p(320 * GB, Some(300 * GB), 200.0, 2_000_000).lineas();
        assert_eq!(estado, "Analizando… 99 % · falta menos de 1 min");
    }

    #[test]
    fn las_fases_tras_el_escaneo_se_nombran() {
        let mut x = p(0, None, 0.0, 0);
        x.fase = "duplicados".into();
        assert_eq!(x.lineas(), ("Buscando archivos duplicados…".into(), None));
        x.fase = "informe".into();
        assert_eq!(x.lineas(), ("Preparando el informe…".into(), None));
    }

    #[test]
    fn lee_el_fichero_del_motor_y_tolera_que_aun_no_exista() {
        let dir = std::env::temp_dir().join(format!("progreso-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("p.json");
        assert_eq!(leer(&ruta), None);
        std::fs::write(
            &ruta,
            r#"{"fase":"escaneo","archivos":3,"bytes":15000,"objetivo":null,"segundos":1.5}"#,
        )
        .unwrap();
        assert_eq!(leer(&ruta), Some(p(15000, None, 1.5, 3)));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
