//! User preferences for the tray: what the text beside the ring shows, and
//! which colour palette the ring uses. Persisted as JSON in the app's config
//! directory.

use serde::{Deserialize, Serialize};
use std::path::Path;

/// What the menu bar shows to the right of the ring.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Etiqueta {
    /// Free space, "13 GB". The default: it is the figure that drives the
    /// low-disk warnings, and it says how much room is left, which a
    /// percentage does not.
    Gb,
    Porcentaje,
    Ambos,
}

/// The palettes offered in the menu.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PaletaId {
    Sistema,
    Pastel,
    /// Okabe-Ito: distinguishable with colour blindness. Matters here because
    /// the warning states are otherwise the classic green/orange/red.
    Accesible,
    Monocromo,
}

pub type Rgb = [u8; 3];

/// Colours for one palette: one per category, one for free space in each
/// warning state.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Colores {
    pub docker: Rgb,
    pub caches: Rgb,
    pub tuyo: Rgb,
    pub resto: Rgb,
    pub libre: Rgb,
    pub aviso: Rgb,
    pub critico: Rgb,
}

impl Etiqueta {
    pub const TODAS: [Etiqueta; 3] = [Etiqueta::Gb, Etiqueta::Porcentaje, Etiqueta::Ambos];

    pub fn nombre(self) -> &'static str {
        match self {
            Etiqueta::Gb => "GB libres",
            Etiqueta::Porcentaje => "Porcentaje usado",
            Etiqueta::Ambos => "Ambos",
        }
    }
}

impl PaletaId {
    pub const TODAS: [PaletaId; 4] = [
        PaletaId::Sistema,
        PaletaId::Pastel,
        PaletaId::Accesible,
        PaletaId::Monocromo,
    ];

    pub fn nombre(self) -> &'static str {
        match self {
            PaletaId::Sistema => "Sistema",
            PaletaId::Pastel => "Pastel",
            PaletaId::Accesible => "Accesible (daltonismo)",
            PaletaId::Monocromo => "Monocromo",
        }
    }

    pub fn colores(self) -> Colores {
        match self {
            PaletaId::Sistema => Colores {
                docker: [0x0a, 0x84, 0xff],
                caches: [0xff, 0x9f, 0x0a],
                tuyo: [0xbf, 0x5a, 0xf2],
                resto: [0x8e, 0x8e, 0x93],
                libre: [0x30, 0xd1, 0x58],
                aviso: [0xff, 0x9f, 0x0a],
                critico: [0xff, 0x45, 0x3a],
            },
            PaletaId::Pastel => Colores {
                docker: [0x8a, 0xb4, 0xf8],
                caches: [0xfb, 0xc6, 0x87],
                tuyo: [0xd7, 0xae, 0xfb],
                resto: [0xb4, 0xb7, 0xc0],
                libre: [0x9f, 0xe3, 0xb4],
                aviso: [0xfb, 0xc6, 0x87],
                critico: [0xff, 0x8a, 0x80],
            },
            PaletaId::Accesible => Colores {
                docker: [0x00, 0x72, 0xb2],
                caches: [0xe6, 0x9f, 0x00],
                tuyo: [0xcc, 0x79, 0xa7],
                resto: [0x99, 0x99, 0x99],
                libre: [0x56, 0xb4, 0xe9],
                aviso: [0xe6, 0x9f, 0x00],
                critico: [0xd5, 0x5e, 0x00],
            },
            PaletaId::Monocromo => Colores {
                docker: [0x5e, 0x65, 0x72],
                caches: [0x7c, 0x83, 0x91],
                tuyo: [0x9a, 0xa1, 0xae],
                resto: [0xb8, 0xbe, 0xcb],
                libre: [0x30, 0xd1, 0x58],
                aviso: [0xff, 0x9f, 0x0a],
                critico: [0xff, 0x45, 0x3a],
            },
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Ajustes {
    pub etiqueta: Etiqueta,
    pub paleta: PaletaId,
}

impl Default for Ajustes {
    fn default() -> Self {
        Self {
            etiqueta: Etiqueta::Gb,
            paleta: PaletaId::Sistema,
        }
    }
}

const FICHERO: &str = "ajustes.json";

impl Ajustes {
    /// Loads the preferences, falling back to the defaults if the file is
    /// missing or unreadable. A corrupt settings file must never stop the
    /// tray from starting: the indicator is the one thing that has to work.
    pub fn cargar(dir: &Path) -> Self {
        std::fs::read_to_string(dir.join(FICHERO))
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or_default()
    }

    /// Saves atomically: written to a temp file, then renamed over the old
    /// one, so a crash mid-write leaves the previous settings intact instead
    /// of a truncated file.
    pub fn guardar(&self, dir: &Path) -> std::io::Result<()> {
        std::fs::create_dir_all(dir)?;
        let tmp = dir.join(format!("{FICHERO}.tmp"));
        std::fs::write(&tmp, serde_json::to_vec_pretty(self)?)?;
        std::fs::rename(tmp, dir.join(FICHERO))
    }

    /// The text beside the ring.
    pub fn texto(&self, libre_gb: f64, porcentaje: f64) -> String {
        match self.etiqueta {
            Etiqueta::Gb => format!("{libre_gb:.0} GB"),
            Etiqueta::Porcentaje => format!("{porcentaje:.0} %"),
            Etiqueta::Ambos => format!("{libre_gb:.0} GB · {porcentaje:.0} %"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dir_temporal(nombre: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("ajustes-{}-{nombre}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        d
    }

    #[test]
    fn por_defecto_gb_y_paleta_sistema() {
        let a = Ajustes::default();
        assert_eq!(a.etiqueta, Etiqueta::Gb);
        assert_eq!(a.paleta, PaletaId::Sistema);
    }

    #[test]
    fn se_guarda_y_se_recupera() {
        let d = dir_temporal("ida-vuelta");
        let a = Ajustes {
            etiqueta: Etiqueta::Ambos,
            paleta: PaletaId::Accesible,
        };
        a.guardar(&d).unwrap();
        assert_eq!(Ajustes::cargar(&d), a);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn un_fichero_corrupto_o_ausente_da_los_valores_por_defecto() {
        let d = dir_temporal("corrupto");
        assert_eq!(Ajustes::cargar(&d), Ajustes::default(), "sin fichero");
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join(FICHERO), "{esto no es json").unwrap();
        assert_eq!(Ajustes::cargar(&d), Ajustes::default(), "fichero roto");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn el_texto_sigue_la_eleccion() {
        let mut a = Ajustes::default();
        assert_eq!(a.texto(13.2, 97.1), "13 GB");
        a.etiqueta = Etiqueta::Porcentaje;
        assert_eq!(a.texto(13.2, 97.1), "97 %");
        a.etiqueta = Etiqueta::Ambos;
        assert_eq!(a.texto(13.2, 97.1), "13 GB · 97 %");
    }

    #[test]
    fn la_paleta_accesible_no_usa_verde_y_rojo_como_estados() {
        // Okabe-Ito: libre en azul, aviso en naranja, crítico en bermellón.
        let c = PaletaId::Accesible.colores();
        let verdoso = |[r, g, b]: Rgb| g > r && g > b;
        assert!(
            !verdoso(c.libre),
            "lo libre no puede ser verde para un daltónico"
        );
    }
}
