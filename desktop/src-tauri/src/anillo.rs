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

/// One arc: its share of the full circle and its colour.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Trozo {
    pub fraccion: f64,
    pub color: Rgb,
    /// Opacity. Everything is opaque except the part of the disk that could
    /// not be broken down (no Full Disk Access), drawn translucent so it
    /// does not pass for a measured "system and the rest".
    pub alfa: u8,
}

pub const TAM: u32 = 36;

/// Opacity of the used space that could not be broken down into categories.
pub const ALFA_SIN_DESGLOSAR: u8 = 110;

/// Colour of the free gap, whatever the palette: like the battery icon, what
/// is left is white and it is the rest of the ring that changes colour.
pub const BLANCO: Rgb = [255, 255, 255];

/// The smallest the free gap is ever drawn, as a share of the circle (about
/// 30°). Proportional, 9 GB free on a 460 GB disk is a 7° sliver nobody sees
/// — at exactly the moment it matters most. The exact figure is in the text
/// beside the icon, so the ring only has to make "little left" obvious.
pub const LIBRE_MINIMO: f64 = 0.08;

/// The ring for a disk reading: the used slices, then the free gap in white.
///
/// Each category keeps its palette colour whatever the state: the split is
/// what the ring is for. The state reads from the white gap shrinking, the
/// number beside the icon and the notifications.
///
/// Used fractions are rounded down to half a percent: the ring is 36 px, a
/// finer change is invisible, and rounding lets the caller skip redrawing
/// when nothing visible changed. Down, so the free gap that takes up the
/// remainder can never come out under its minimum.
pub fn trozos(uso: &DiskUsage, reparto: &Reparto, c: &Colores) -> Vec<Trozo> {
    let redondear = |f: f64| (f * 200.0 + 1e-9).floor() / 200.0;
    let porciones = categorias::porciones(uso, reparto);
    let usado: f64 = porciones.iter().map(|p| p.fraccion).sum();
    let libre = (1.0 - usado).max(0.0);
    // Anything free at all gets at least the minimum; what is used shrinks in
    // proportion to make room, so the slices keep their relative sizes.
    let libre_dibujado = if uso.available > 0 {
        libre.max(LIBRE_MINIMO)
    } else {
        0.0
    };
    let escala = if usado > 0.0 {
        (1.0 - libre_dibujado).min(usado) / usado
    } else {
        0.0
    };
    let mut out: Vec<Trozo> = porciones
        .into_iter()
        .map(|p| Trozo {
            fraccion: redondear(p.fraccion * escala),
            alfa: if p.categoria == Categoria::Resto && reparto.tuyo.is_none() {
                ALFA_SIN_DESGLOSAR
            } else {
                255
            },
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
        fraccion: if libre_dibujado > 0.0 {
            (1.0 - usado).max(0.0)
        } else {
            0.0
        },
        alfa: 255,
        color: BLANCO,
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
    lienzo(trozos)?.encode_png().ok()
}

/// How many frames make one turn of the "working" sweep.
pub const FOTOGRAMAS: u32 = 12;

/// Length of the sweep's tail, as a share of the circle.
const ESTELA: f32 = 0.22;
/// Pieces the tail is drawn in, each fainter than the one ahead of it.
const PIEZAS_ESTELA: u32 = 6;

/// The ring with a white sweep running over it, frame `n` of `FOTOGRAMAS`:
/// what the icon shows while a scan or a cleanup is running, so the menu bar
/// says "working" without opening the menu. The colours stay visible under
/// it; the head is at `n / FOTOGRAMAS` of a turn and the tail fades behind
/// it, so successive frames read as clockwise motion.
pub fn png_barrido(trozos: &[Trozo], n: u32) -> Option<Vec<u8>> {
    let mut lienzo = lienzo(trozos)?;
    let (c, r, trazo) = geometria();
    let vuelta = std::f32::consts::TAU;
    let cabeza = (n % FOTOGRAMAS) as f32 / FOTOGRAMAS as f32;
    let pieza = ESTELA / PIEZAS_ESTELA as f32;
    for i in 0..PIEZAS_ESTELA {
        // i = 0 is the piece right behind the head, the brightest.
        let desde = cabeza - pieza * (i + 1) as f32;
        let mut pb = PathBuilder::new();
        arco(&mut pb, c, c, r, desde * vuelta, pieza * vuelta);
        if let Some(camino) = pb.finish() {
            let mut blanco = Paint::default();
            let alfa = 230 - (i * 190 / PIEZAS_ESTELA) as u8;
            blanco.set_color_rgba8(255, 255, 255, alfa);
            blanco.anti_alias = true;
            lienzo.stroke_path(&camino, &blanco, &trazo, Transform::identity(), None);
        }
    }
    lienzo.encode_png().ok()
}

/// Centre, radius and stroke shared by the ring and the sweep.
fn geometria() -> (f32, f32, Stroke) {
    let c = TAM as f32 / 2.0;
    let grosor = 7.0;
    let r = c - grosor / 2.0 - 1.0;
    let trazo = Stroke {
        width: grosor,
        line_cap: LineCap::Butt,
        ..Stroke::default()
    };
    (c, r, trazo)
}

fn lienzo(trozos: &[Trozo]) -> Option<Pixmap> {
    let mut lienzo = Pixmap::new(TAM, TAM)?;
    let (c, r, trazo) = geometria();

    // A faint full track underneath, so any rounding remainder reads as
    // "ring" rather than as a hole.
    let mut pista = PathBuilder::new();
    pista.push_circle(c, c, r);
    let mut gris = Paint::default();
    gris.set_color_rgba8(128, 128, 128, 35);
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
            pintura.set_color_rgba8(rr, gg, bb, t.alfa);
            pintura.anti_alias = true;
            lienzo.stroke_path(&camino, &pintura, &trazo, Transform::identity(), None);
        }
        inicio += f;
    }
    Some(lienzo)
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

    fn todo_rojo() -> [Trozo; 1] {
        [Trozo {
            fraccion: 1.0,
            color: ROJO,
            alfa: 255,
        }]
    }

    #[test]
    fn el_barrido_aclara_justo_detras_de_la_cabeza_y_deja_el_resto_en_su_color() {
        // Head at 4/12 of a turn (four o'clock); three o'clock is 1/12 behind
        // it, inside the tail. Nine o'clock is far from it.
        let png = png_barrido(&todo_rojo(), 4).unwrap();
        let tres = pixel(&png, 31, 18);
        assert!(
            tres[1] > 120 && tres[2] > 120,
            "sin estela a las tres: {tres:?}"
        );
        let nueve = pixel(&png, 4, 18);
        assert!(
            nueve[0] > 200 && nueve[1] < 40,
            "la estela tapa el anillo: {nueve:?}"
        );
        // Ahead of the head (six o'clock) the ring is untouched: the sweep
        // trails behind, so successive frames read as clockwise.
        let seis = pixel(&png, 18, 31);
        assert!(
            seis[1] < 40,
            "la estela va por delante de la cabeza: {seis:?}"
        );
    }

    #[test]
    fn el_barrido_avanza_con_el_fotograma_y_da_la_vuelta() {
        let lejos = pixel(&png_barrido(&todo_rojo(), 10).unwrap(), 31, 18);
        assert!(
            lejos[1] < 40,
            "fotograma 10 no debería tocar las tres: {lejos:?}"
        );
        assert_eq!(
            png_barrido(&todo_rojo(), 4),
            png_barrido(&todo_rojo(), 4 + FOTOGRAMAS)
        );
    }

    #[test]
    fn cada_trozo_ocupa_su_parte_del_circulo_en_orden_horario() {
        let png = png(&[
            Trozo {
                fraccion: 0.5,
                color: ROJO,
                alfa: 255,
            },
            Trozo {
                fraccion: 0.5,
                color: AZUL,
                alfa: 255,
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
                alfa: 255,
            },
            Trozo {
                fraccion: 0.75,
                color: AZUL,
                alfa: 255,
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
            alfa: 255,
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
                alfa: 255,
            },
            Trozo {
                fraccion: 0.015,
                color: ROJO,
                alfa: 255,
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

    fn disco(libre_pct: u64) -> DiskUsage {
        let gb = 1u64 << 30;
        DiskUsage {
            total: 100 * gb,
            used: (100 - libre_pct) * gb,
            available: libre_pct * gb,
            purgeable: 0,
            percent: (100 - libre_pct) as f64,
        }
    }

    fn reparto_ejemplo() -> Reparto {
        let gb = 1u64 << 30;
        Reparto {
            docker: Some(20 * gb),
            caches: 10 * gb,
            tuyo: None,
        }
    }

    fn suma(t: &[Trozo]) -> f64 {
        t.iter().map(|t| t.fraccion).sum()
    }

    #[test]
    fn con_espacio_de_sobra_cada_categoria_lleva_su_color_y_lo_libre_va_en_blanco() {
        let c = PaletaId::Sistema.colores();
        let t = trozos(&disco(30), &reparto_ejemplo(), &c);
        let colores: Vec<Rgb> = t.iter().map(|t| t.color).collect();
        assert_eq!(colores, vec![c.docker, c.caches, c.resto, BLANCO]);
        assert!((suma(&t) - 1.0).abs() < 1e-9, "los trozos suman {}", suma(&t));
        assert!((t[3].fraccion - 0.30).abs() < 0.006, "lo libre no es proporcional");
    }

    #[test]
    fn con_poco_espacio_cada_categoria_conserva_su_color() {
        let c = PaletaId::Sistema.colores();
        let t = trozos(&disco(2), &reparto_ejemplo(), &c);
        let colores: Vec<Rgb> = t.iter().map(|t| t.color).collect();
        assert_eq!(colores, vec![c.docker, c.caches, c.resto, BLANCO]);
    }

    #[test]
    fn lo_libre_nunca_baja_de_un_minimo_visible_y_el_circulo_sigue_cerrando() {
        let c = PaletaId::Sistema.colores();
        let t = trozos(&disco(2), &reparto_ejemplo(), &c);
        let libre = t.last().unwrap().fraccion;
        assert!((LIBRE_MINIMO..LIBRE_MINIMO + 0.02).contains(&libre), "libre: {libre}");
        assert!((suma(&t) - 1.0).abs() < 1e-9, "los trozos suman {}", suma(&t));
        // Lo usado se encoge en proporción: docker sigue siendo el doble que cachés.
        assert!((t[0].fraccion / t[1].fraccion - 2.0).abs() < 0.1);
    }

    #[test]
    fn un_disco_lleno_del_todo_no_inventa_hueco_libre() {
        let c = PaletaId::Sistema.colores();
        let t = trozos(&disco(0), &reparto_ejemplo(), &c);
        assert_eq!(t.last().unwrap().fraccion, 0.0);
    }

    #[test]
    fn lo_que_no_se_pudo_desglosar_se_ve_translucido() {
        let gb = 1u64 << 30;
        let uso = DiskUsage {
            total: 100 * gb,
            used: 90 * gb,
            available: 10 * gb,
            purgeable: 0,
            percent: 90.0,
        };
        let c = PaletaId::Sistema.colores();
        let alfa_resto = |tuyo| {
            let r = Reparto {
                docker: None,
                caches: 10 * gb,
                tuyo,
            };
            let t = trozos(&uso, &r, &c);
            let resto = t.iter().find(|t| t.color == c.resto).unwrap();
            assert!(t
                .iter()
                .filter(|x| x.color != c.resto)
                .all(|x| x.alfa == 255));
            resto.alfa
        };
        assert_eq!(alfa_resto(None), ALFA_SIN_DESGLOSAR);
        assert_eq!(alfa_resto(Some(30 * gb)), 255);
    }
}
