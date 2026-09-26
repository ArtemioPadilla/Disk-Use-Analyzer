//! Draws the live ring for the menu bar.
//!
//! Replaces the three fixed PNGs (ok / warning / critical) with a ring drawn
//! from the current numbers: one arc per category and the free gap in the
//! colour of the warning state. Drawn at 36 px because `tray-icon` scales the
//! image to 18 points tall, so 36 px stays sharp on Retina screens.

use tiny_skia::{LineCap, Paint, PathBuilder, Pixmap, Stroke, Transform};

use crate::ajustes::{Colores, Rgb};
use crate::categorias::{self, Categoria, Reparto};
use crate::disk::DiskUsage;
use crate::estado::Estado;

/// One arc: its share of the full circle and its colour.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Trozo {
    pub fraccion: f64,
    pub color: Rgb,
}

pub const TAM: u32 = 36;

/// The ring for a disk reading: the used slices in the palette's category
/// colours, then the free gap in the colour of the warning state, so the
/// icon turns orange or red exactly when the old fixed icons did.
///
/// Fractions are rounded to half a percent: the ring is 36 px, a finer
/// change is invisible, and rounding lets the caller skip redrawing when
/// nothing visible changed.
pub fn trozos(uso: &DiskUsage, reparto: &Reparto, estado: Estado, c: &Colores) -> Vec<Trozo> {
    let redondear = |f: f64| (f * 200.0).round() / 200.0;
    let mut out: Vec<Trozo> = categorias::porciones(uso, reparto)
        .into_iter()
        .map(|p| Trozo {
            fraccion: redondear(p.fraccion),
            color: match p.categoria {
                Categoria::Docker => c.docker,
                Categoria::Caches => c.caches,
                Categoria::Tuyo => c.tuyo,
                Categoria::Resto => c.resto,
            },
        })
        .collect();
    let usado: f64 = out.iter().map(|t| t.fraccion).sum();
    out.push(Trozo {
        fraccion: (1.0 - usado).max(0.0),
        color: match estado {
            Estado::Ok => c.libre,
            Estado::Aviso => c.aviso,
            Estado::Critico => c.critico,
        },
    });
    out
}

/// Gap between neighbouring arcs, as a share of the circle, so adjacent
/// categories read as separate slices instead of a smear.
const HUECO: f32 = 0.018;
/// The shortest an arc is ever drawn. Without it a nearly full disk — 3 %
/// free — would draw its free gap thinner than the separation between arcs,
/// i.e. not at all, which is the one reading the icon must never lose.
const MINIMO: f32 = 0.022;

/// Point on the circle at `a` radians, measured clockwise from twelve o'clock.
fn punto(cx: f32, cy: f32, r: f32, a: f32) -> (f32, f32) {
    (cx + r * a.sin(), cy - r * a.cos())
}

/// Appends a clockwise arc as cubic Béziers of at most a quarter turn each.
fn arco(pb: &mut PathBuilder, cx: f32, cy: f32, r: f32, desde: f32, barrido: f32) {
    let partes = (barrido / std::f32::consts::FRAC_PI_2).ceil().max(1.0) as usize;
    let paso = barrido / partes as f32;
    let k = 4.0 / 3.0 * (paso / 4.0).tan();
    let (x0, y0) = punto(cx, cy, r, desde);
    pb.move_to(x0, y0);
    for i in 0..partes {
        let a0 = desde + paso * i as f32;
        let a1 = a0 + paso;
        let (p0x, p0y) = punto(cx, cy, r, a0);
        let (p3x, p3y) = punto(cx, cy, r, a1);
        // Tangent of a clockwise circle at angle a is (cos a, sin a).
        let c1 = (p0x + k * r * a0.cos(), p0y + k * r * a0.sin());
        let c2 = (p3x - k * r * a1.cos(), p3y - k * r * a1.sin());
        pb.cubic_to(c1.0, c1.1, c2.0, c2.1, p3x, p3y);
    }
}

/// The ring as a PNG, ready for `tauri::image::Image::from_bytes`.
pub fn png(trozos: &[Trozo]) -> Option<Vec<u8>> {
    let mut lienzo = Pixmap::new(TAM, TAM)?;
    let c = TAM as f32 / 2.0;
    let grosor = 7.0;
    let r = c - grosor / 2.0 - 1.0;
    let trazo = Stroke {
        width: grosor,
        line_cap: LineCap::Butt,
        ..Stroke::default()
    };

    // A faint full track underneath, so any rounding remainder reads as
    // "ring" rather than as a hole.
    let mut pista = PathBuilder::new();
    pista.push_circle(c, c, r);
    let mut gris = Paint::default();
    gris.set_color_rgba8(128, 128, 128, 70);
    gris.anti_alias = true;
    if let Some(p) = pista.finish() {
        lienzo.stroke_path(&p, &gris, &trazo, Transform::identity(), None);
    }

    let vuelta = std::f32::consts::TAU;
    let mut inicio = 0.0f32;
    for t in trozos {
        let f = t.fraccion.clamp(0.0, 1.0) as f32;
        if f <= 0.0 {
            continue;
        }
        let largo = (f - HUECO).max(MINIMO);
        let mut pb = PathBuilder::new();
        arco(
            &mut pb,
            c,
            c,
            r,
            (inicio + HUECO / 2.0) * vuelta,
            largo * vuelta,
        );
        if let Some(camino) = pb.finish() {
            let mut pintura = Paint::default();
            let [rr, gg, bb] = t.color;
            pintura.set_color_rgba8(rr, gg, bb, 255);
            pintura.anti_alias = true;
            lienzo.stroke_path(&camino, &pintura, &trazo, Transform::identity(), None);
        }
        inicio += f;
    }
    lienzo.encode_png().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    use crate::ajustes::PaletaId;

    const ROJO: Rgb = [255, 0, 0];
    const AZUL: Rgb = [0, 0, 255];

    /// Pixel at fixed coordinates. Deliberately not through `punto`, so a
    /// mistake there cannot cancel itself out in the test.
    fn pixel(png: &[u8], x: u32, y: u32) -> [u8; 4] {
        let img = Pixmap::decode_png(png).unwrap();
        let p = img.pixel(x, y).unwrap().demultiply();
        [p.red(), p.green(), p.blue(), p.alpha()]
    }

    #[test]
    fn cada_trozo_ocupa_su_parte_del_circulo_en_orden_horario() {
        let png = png(&[
            Trozo {
                fraccion: 0.5,
                color: ROJO,
            },
            Trozo {
                fraccion: 0.5,
                color: AZUL,
            },
        ])
        .unwrap();
        // The ring's centre line is 13.5 px from the centre (18, 18).
        let derecha = pixel(&png, 31, 18); // las tres
        let izquierda = pixel(&png, 4, 18); // las nueve
        assert!(
            derecha[0] > 200 && derecha[2] < 60,
            "a las tres debería ser rojo: {derecha:?}"
        );
        assert!(
            izquierda[2] > 200 && izquierda[0] < 60,
            "a las nueve, azul: {izquierda:?}"
        );

        // Empieza a las doce: un primer cuarto rojo queda arriba a la derecha.
        let cuarto = super::png(&[
            Trozo {
                fraccion: 0.25,
                color: ROJO,
            },
            Trozo {
                fraccion: 0.75,
                color: AZUL,
            },
        ])
        .unwrap();
        let arriba = pixel(&cuarto, 27, 8);
        let abajo = pixel(&cuarto, 27, 27);
        assert!(
            arriba[0] > 200 && arriba[2] < 60,
            "arriba a la derecha, rojo: {arriba:?}"
        );
        assert!(
            abajo[2] > 200 && abajo[0] < 60,
            "abajo a la derecha, azul: {abajo:?}"
        );
    }

    #[test]
    fn el_centro_es_transparente() {
        let png = png(&[Trozo {
            fraccion: 1.0,
            color: ROJO,
        }])
        .unwrap();
        let img = Pixmap::decode_png(&png).unwrap();
        assert_eq!(img.pixel(TAM / 2, TAM / 2).unwrap().alpha(), 0);
    }

    #[test]
    fn un_hueco_libre_minusculo_se_sigue_viendo() {
        // Disco al 98,5 %: lo libre es menos que el hueco entre trozos, y aun
        // así, en rojo, tiene que aparecer.
        let png = png(&[
            Trozo {
                fraccion: 0.985,
                color: AZUL,
            },
            Trozo {
                fraccion: 0.015,
                color: ROJO,
            },
        ])
        .unwrap();
        let img = Pixmap::decode_png(&png).unwrap();
        let rojos = img
            .pixels()
            .iter()
            .map(|p| p.demultiply())
            .filter(|p| p.alpha() > 128 && p.red() > 200 && p.blue() < 80)
            .count();
        assert!(
            rojos >= 6,
            "el hueco libre apenas se ve: {rojos} píxeles rojos"
        );
    }

    #[test]
    fn el_hueco_libre_toma_el_color_del_estado_y_cierra_el_circulo() {
        let gb = 1u64 << 30;
        let uso = DiskUsage {
            total: 100 * gb,
            used: 90 * gb,
            available: 10 * gb,
            purgeable: 0,
            percent: 90.0,
        };
        let reparto = Reparto {
            docker: Some(20 * gb),
            caches: 10 * gb,
            tuyo: None,
        };
        let c = PaletaId::Sistema.colores();
        let t = trozos(&uso, &reparto, Estado::Critico, &c);
        let colores: Vec<Rgb> = t.iter().map(|t| t.color).collect();
        assert_eq!(colores, vec![c.docker, c.caches, c.resto, c.critico]);
        let suma: f64 = t.iter().map(|t| t.fraccion).sum();
        assert!((suma - 1.0).abs() < 1e-9, "los trozos suman {suma}");
        assert!((t[3].fraccion - 0.10).abs() < 0.006);
        assert_eq!(trozos(&uso, &reparto, Estado::Ok, &c)[3].color, c.libre);
        assert_eq!(trozos(&uso, &reparto, Estado::Aviso, &c)[3].color, c.aviso);
    }
}
