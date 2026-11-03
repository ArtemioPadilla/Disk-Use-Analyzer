//! What Tauri's menu API cannot say, written straight on the native menu.
//!
//! Tauri only knows plain titles, and macOS paints a disabled item in a faint
//! grey: fine for an unavailable command, hard to read for the figures this
//! menu exists to show. An attributed title does not help, macOS 27 greys it
//! just the same (checked on screen). So a row that only informs carries its
//! own view, a label, which macOS neither dims nor highlights. Rows with a
//! figure are attributed titles, so that they still behave like menu items.
//!
//! `set_text` replaces an attributed title with a plain one and does not reach
//! a view, so `aplicar` has to run again after any text changes.

use objc2::rc::Retained;
use objc2::runtime::AnyObject;
use objc2::AnyThread;
use objc2_app_kit::{
    NSAttributedStringAttachmentConveniences, NSColor, NSFont, NSFontAttributeName,
    NSFontWeightRegular, NSForegroundColorAttributeName, NSMenu, NSMenuItem,
    NSMutableParagraphStyle, NSParagraphStyleAttributeName, NSTextAlignment, NSTextAttachment,
    NSTextField, NSTextTab, NSView,
};
use objc2_foundation::{
    MainThreadMarker, NSArray, NSAttributedString, NSAttributedStringKey, NSDictionary,
    NSMutableAttributedString, NSPoint, NSRect, NSSize, NSString,
};
use tauri::{AppHandle, Wry};

/// The id of the app's only tray icon.
pub const ID_BANDEJA: &str = "principal";

/// Section titles. Matched by their exact text, on disabled items only.
const TITULOS: [&str; 5] = [
    "Disco",
    "Memoria",
    "Análisis",
    "No vuelve",
    "Revisar antes de borrar",
];

/// Where a figure ends, in points from the start of the title. Also what
/// keeps the rows of a section the same width.
const FIN_CIFRAS: f64 = 230.0;
const TAM_FUENTE: f64 = 13.0;
/// A label row, matched by eye to the items macOS draws around it.
const MARGEN_FILA: f64 = 14.0;
const ALTO_FILA: f64 = 24.0;
const LADO_PUNTO: f64 = 16.0;
/// What a text attachment reads as in a plain title.
const ADJUNTO: char = '\u{fffc}';

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Estilo {
    /// A label in bold.
    Titulo,
    /// A label, as readable as the rest of the menu.
    Informativo,
    /// A menu item with a right-aligned figure, after a tab.
    ConCifra,
    /// Left to macOS.
    Normal,
}

/// How a row is drawn. Only the top level gets readable disabled rows: in a
/// submenu, grey still means what it means everywhere else, "not available".
pub fn clasificar(titulo: &str, habilitado: bool, raiz: bool) -> Estilo {
    if !habilitado && TITULOS.contains(&titulo) {
        Estilo::Titulo
    } else if !habilitado && raiz {
        Estilo::Informativo
    } else if titulo.contains('\t') {
        Estilo::ConCifra
    } else {
        Estilo::Normal
    }
}

fn atribuido(titulo: &str, estilo: Estilo) -> Option<Retained<NSAttributedString>> {
    let fuente = match estilo {
        Estilo::Normal => return None,
        Estilo::Titulo => NSFont::boldSystemFontOfSize(TAM_FUENTE),
        Estilo::Informativo => NSFont::menuFontOfSize(TAM_FUENTE),
        Estilo::ConCifra => unsafe {
            NSFont::monospacedDigitSystemFontOfSize_weight(TAM_FUENTE, NSFontWeightRegular)
        },
    };
    let mut claves: Vec<&NSAttributedStringKey> = vec![unsafe { NSFontAttributeName }];
    let mut valores: Vec<Retained<AnyObject>> = vec![fuente.into_super().into_super()];
    if estilo == Estilo::ConCifra {
        let parrafo = NSMutableParagraphStyle::new();
        let tope = unsafe {
            NSTextTab::initWithTextAlignment_location_options(
                NSTextTab::alloc(),
                NSTextAlignment::Right,
                FIN_CIFRAS,
                &NSDictionary::new(),
            )
        };
        parrafo.setTabStops(Some(&NSArray::from_retained_slice(&[tope])));
        claves.push(unsafe { NSParagraphStyleAttributeName });
        valores.push(parrafo.into_super().into_super().into());
    } else {
        claves.push(unsafe { NSForegroundColorAttributeName });
        valores.push(NSColor::labelColor().into_super().into());
    }
    let valores: Vec<&AnyObject> = valores.iter().map(|v| &**v).collect();
    let atributos = NSDictionary::from_slices(&claves, &valores);
    Some(unsafe {
        NSAttributedString::new_with_attributes(&NSString::from_str(titulo), &atributos)
    })
}

/// The row's icon inside its title. macOS 27 does not draw the image of a menu
/// item that has a submenu (checked on screen, with and without an attributed
/// title); inside the text it does, and it still follows `set_icon`.
fn con_punto(item: &NSMenuItem, texto: &NSAttributedString) -> Retained<NSAttributedString> {
    let Some(imagen) = item.image() else {
        return unsafe { Retained::retain(texto as *const _ as *mut NSAttributedString) }
            .expect("a reference is never null");
    };
    let adjunto = NSTextAttachment::new();
    adjunto.setImage(Some(&imagen));
    adjunto.setBounds(NSRect::new(
        NSPoint::new(0.0, -LADO_PUNTO / 4.0),
        NSSize::new(LADO_PUNTO, LADO_PUNTO),
    ));
    let linea = NSMutableAttributedString::new();
    linea.appendAttributedString(&NSAttributedString::attributedStringWithAttachment(
        &adjunto,
    ));
    linea.appendAttributedString(&NSAttributedString::from_nsstring(&NSString::from_str(" ")));
    linea.appendAttributedString(texto);
    linea.into_super()
}

/// The label a row already carries, if it still says `titulo`.
fn ya_dice(item: &NSMenuItem, titulo: &str) -> bool {
    item.view()
        .and_then(|v| v.subviews().firstObject())
        .and_then(|e| e.downcast::<NSTextField>().ok())
        .is_some_and(|l| l.stringValue().to_string() == titulo)
}

fn poner_etiqueta(item: &NSMenuItem, texto: &NSAttributedString, mtm: MainThreadMarker) {
    let etiqueta = NSTextField::labelWithAttributedString(texto, mtm);
    etiqueta.sizeToFit();
    let tam = etiqueta.frame().size;
    etiqueta.setFrameOrigin(NSPoint::new(MARGEN_FILA, (ALTO_FILA - tam.height) / 2.0));
    let marco = NSRect::new(
        NSPoint::new(0.0, 0.0),
        NSSize::new(tam.width + 2.0 * MARGEN_FILA, ALTO_FILA),
    );
    let fila = NSView::initWithFrame(mtm.alloc(), marco);
    fila.addSubview(&etiqueta);
    item.setView(Some(&fila));
}

fn recorrer(menu: &NSMenu, raiz: bool, mtm: MainThreadMarker) {
    for item in menu.itemArray().iter() {
        let item: &NSMenuItem = &item;
        if item.isSeparatorItem() {
            continue;
        }
        if let Some(sub) = item.submenu() {
            recorrer(&sub, false, mtm);
        }
        let titulo = item.title().to_string();
        // Already formatted: the attachment shows up in the plain title, and
        // formatting it again would add a second dot. `set_text` clears it.
        if titulo.starts_with(ADJUNTO) {
            continue;
        }
        let estilo = clasificar(&titulo, item.isEnabled(), raiz);
        let Some(texto) = atribuido(&titulo, estilo) else {
            continue;
        };
        if estilo == Estilo::ConCifra {
            item.setAttributedTitle(Some(&con_punto(item, &texto)));
        } else if !ya_dice(item, &titulo) {
            poner_etiqueta(item, &texto, mtm);
        }
    }
}

/// Formats the whole tray menu. Call it after changing any text; safe from
/// any thread, it hops to the main one.
pub fn aplicar(app: &AppHandle<Wry>) {
    let Some(bandeja) = app.tray_by_id(ID_BANDEJA) else {
        return;
    };
    let _ = bandeja.with_inner_tray_icon(|t| {
        let (Some(mtm), Some(item)) = (MainThreadMarker::new(), t.ns_status_item()) else {
            return;
        };
        if let Some(menu) = item.menu(mtm) {
            recorrer(&menu, true, mtm);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn los_titulos_de_seccion_solo_cuentan_si_no_son_clicables() {
        assert_eq!(clasificar("Disco", false, true), Estilo::Titulo);
        assert_eq!(clasificar("Disco", true, true), Estilo::Normal);
    }

    #[test]
    fn lo_informativo_se_lee_arriba_pero_en_un_submenu_gris_sigue_siendo_gris() {
        assert_eq!(
            clasificar("6,9 GB libres", false, true),
            Estilo::Informativo
        );
        assert_eq!(
            clasificar("Motor no encontrado", false, false),
            Estilo::Normal
        );
        assert_eq!(clasificar("Analizar ahora", true, true), Estilo::Normal);
    }

    #[test]
    fn una_cifra_se_alinea_en_cualquier_fila_que_se_pueda_pulsar() {
        assert_eq!(clasificar("Docker\t40 GB", true, true), Estilo::ConCifra);
        assert_eq!(
            clasificar("Cache de npm…\t6,6 GB", true, false),
            Estilo::ConCifra
        );
    }
}
