//! Decides when the tray app should send a low-disk notification.
//!
//! The tray icon already changes colour, but a colour nobody looks at warns
//! nobody. This module turns the free-space reading into at most one
//! notification per threshold crossed, never one per poll: the poller runs
//! every 5 seconds, and a disk hovering at 19.9 / 20.1 GB would otherwise fire
//! a notification on every lap. Hence the hysteresis — going back up to a
//! better level requires clearing the threshold by `HISTERESIS_GB`.

/// Below this, the user should start freeing space.
pub const UMBRAL_BAJO_GB: f64 = 20.0;
/// Below this, macOS itself starts failing to save files and to update.
pub const UMBRAL_CRITICO_GB: f64 = 5.0;
/// How far above a threshold the disk must climb before that level re-arms.
pub const HISTERESIS_GB: f64 = 2.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Nivel {
    Normal,
    Bajo,
    Critico,
}

fn nivel_de(libre_gb: f64) -> Nivel {
    if libre_gb < UMBRAL_CRITICO_GB {
        Nivel::Critico
    } else if libre_gb < UMBRAL_BAJO_GB {
        Nivel::Bajo
    } else {
        Nivel::Normal
    }
}

/// A notification to send: the level just entered and the free space then.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Aviso {
    pub nivel: Nivel,
    pub libre_gb: f64,
}

/// Remembers the last level reported, so each crossing notifies once.
pub struct Vigia {
    nivel: Nivel,
}

impl Vigia {
    /// Starts watching from the current reading.
    ///
    /// Silent unless the disk is already critical. The app starts at every
    /// login, and a user who routinely sits at 15 GB free would otherwise get
    /// a "running low" notification every single morning — which is how
    /// notifications get turned off for good. Critical is different: below
    /// 5 GB things are already breaking, so it is worth saying at login.
    pub fn al_arrancar(libre_gb: f64) -> (Self, Option<Aviso>) {
        let nivel = nivel_de(libre_gb);
        let aviso = (nivel == Nivel::Critico).then_some(Aviso { nivel, libre_gb });
        (Self { nivel }, aviso)
    }

    /// Feeds a new reading. Returns a notification only when the disk has
    /// just got worse; getting better is silent.
    pub fn observar(&mut self, libre_gb: f64) -> Option<Aviso> {
        let bruto = nivel_de(libre_gb);
        if bruto > self.nivel {
            self.nivel = bruto;
            return Some(Aviso {
                nivel: bruto,
                libre_gb,
            });
        }
        // Improving: only re-arm once the disk clears the threshold of the
        // current level by the hysteresis margin.
        if bruto < self.nivel {
            let umbral = match self.nivel {
                Nivel::Critico => UMBRAL_CRITICO_GB,
                Nivel::Bajo => UMBRAL_BAJO_GB,
                Nivel::Normal => return None,
            };
            if libre_gb >= umbral + HISTERESIS_GB {
                self.nivel = nivel_de(libre_gb - HISTERESIS_GB).max(bruto);
            }
        }
        None
    }
}

/// Title and body of the notification, in Spanish.
///
/// `swap` is the swap size in GB and the app holding most of it, when that is
/// large enough to matter. It is the one cause of a full disk that deleting
/// files cannot fix, so it is exactly the one worth naming.
pub fn texto(aviso: &Aviso, swap: Option<(f64, &str)>) -> (String, String) {
    let titulo = match aviso.nivel {
        Nivel::Critico => format!("Disco casi lleno: quedan {:.1} GB", aviso.libre_gb),
        _ => format!("Queda poco espacio: {:.1} GB libres", aviso.libre_gb),
    };
    let mut cuerpo = match aviso.nivel {
        Nivel::Critico => {
            "macOS empezará a fallar al guardar archivos y al actualizarse.".to_string()
        }
        _ => "Conviene liberar espacio antes de que se llene.".to_string(),
    };
    if let Some((gb, app)) = swap {
        cuerpo.push_str(&format!(
            " El swap ocupa {gb:.1} GB y lo retiene {app}: cerrar o reiniciar esa app lo libera."
        ));
    }
    (titulo, cuerpo)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn arrancar_con_poco_espacio_no_avisa_pero_critico_si() {
        assert_eq!(Vigia::al_arrancar(15.0).1, None);
        assert_eq!(Vigia::al_arrancar(80.0).1, None);
        let (_, aviso) = Vigia::al_arrancar(3.0);
        assert_eq!(aviso.map(|a| a.nivel), Some(Nivel::Critico));
    }

    #[test]
    fn cada_cruce_hacia_abajo_avisa_una_vez() {
        let (mut v, _) = Vigia::al_arrancar(40.0);
        assert_eq!(v.observar(30.0), None);
        assert_eq!(v.observar(19.0).map(|a| a.nivel), Some(Nivel::Bajo));
        assert_eq!(v.observar(18.0), None, "seguir bajo no vuelve a avisar");
        assert_eq!(v.observar(4.0).map(|a| a.nivel), Some(Nivel::Critico));
        assert_eq!(v.observar(3.0), None);
    }

    #[test]
    fn oscilar_en_el_umbral_no_dispara_una_tormenta_de_avisos() {
        let (mut v, _) = Vigia::al_arrancar(25.0);
        let mut avisos = 0;
        for i in 0..50 {
            let libre = if i % 2 == 0 { 19.9 } else { 20.1 };
            if v.observar(libre).is_some() {
                avisos += 1;
            }
        }
        assert_eq!(
            avisos, 1,
            "una oscilación de 0,2 GB solo puede avisar una vez"
        );
    }

    #[test]
    fn tras_recuperarse_de_verdad_vuelve_a_avisar() {
        let (mut v, _) = Vigia::al_arrancar(25.0);
        assert!(v.observar(19.0).is_some());
        assert_eq!(
            v.observar(21.0),
            None,
            "21 GB no supera el margen: no se rearma"
        );
        assert!(v.observar(19.0).is_none());
        assert_eq!(v.observar(23.0), None, "23 GB sí: se rearma en silencio");
        assert!(
            v.observar(19.0).is_some(),
            "y el siguiente cruce vuelve a avisar"
        );
    }

    #[test]
    fn desde_critico_recuperarse_a_bajo_rearma_solo_el_critico() {
        let (mut v, _) = Vigia::al_arrancar(3.0);
        assert_eq!(v.observar(8.0), None);
        assert_eq!(v.observar(4.0).map(|a| a.nivel), Some(Nivel::Critico));
        assert_eq!(v.observar(8.0), None);
        assert_eq!(
            v.observar(15.0),
            None,
            "sigue por debajo de 20: no avisa de 'bajo'"
        );
    }

    #[test]
    fn el_texto_nombra_el_swap_y_su_culpable_cuando_lo_hay() {
        let aviso = Aviso {
            nivel: Nivel::Critico,
            libre_gb: 3.2,
        };
        let (titulo, cuerpo) = texto(&aviso, Some((12.1, "Visual Studio Code")));
        assert!(titulo.contains("3.2 GB"));
        assert!(cuerpo.contains("12.1 GB") && cuerpo.contains("Visual Studio Code"));
        let (_, sin_swap) = texto(&aviso, None);
        assert!(!sin_swap.contains("swap"));
    }
}
