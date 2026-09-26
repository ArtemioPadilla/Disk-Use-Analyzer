//! Desktop notifications through `UNUserNotificationCenter`.
//!
//! `tauri-plugin-notification` 2.4 posts through `NSUserNotification`, which
//! Apple deprecated in macOS 11. On macOS 27 its notifications never arrived
//! and it reported no error — the one failure mode a low-disk warning cannot
//! afford, since the user only finds out when the disk is already full. This
//! uses the replacement API directly.
//!
//! `UNUserNotificationCenter` raises an Objective-C exception when the process
//! is not inside an app bundle, so both entry points take `empaquetada` and do
//! nothing from `cargo run` or a test.

use block2::RcBlock;
use objc2::runtime::Bool;
use objc2_foundation::{NSError, NSString};
use objc2_user_notifications::{
    UNAuthorizationOptions, UNMutableNotificationContent, UNNotificationRequest,
    UNUserNotificationCenter,
};

/// Asks macOS for permission to show alerts. The first call shows the system
/// prompt; later calls return the stored answer without asking again.
pub fn pedir_permiso(empaquetada: bool) {
    if !empaquetada {
        return;
    }
    let centro = UNUserNotificationCenter::currentNotificationCenter();
    let al_responder = RcBlock::new(|_concedido: Bool, _error: *mut NSError| {});
    centro.requestAuthorizationWithOptions_completionHandler(
        UNAuthorizationOptions::Alert | UNAuthorizationOptions::Sound,
        &al_responder,
    );
}

/// Posts a notification. Fire and forget: if the user denied permission,
/// macOS drops it, which is the user's call to make.
pub fn enviar(empaquetada: bool, titulo: &str, cuerpo: &str) {
    if !empaquetada {
        return;
    }
    let centro = UNUserNotificationCenter::currentNotificationCenter();
    let contenido = UNMutableNotificationContent::new();
    contenido.setTitle(&NSString::from_str(titulo));
    contenido.setBody(&NSString::from_str(cuerpo));
    // A fresh identifier per notification: reusing one would make macOS
    // replace the previous alert instead of showing the new one.
    let id = NSString::from_str(&format!(
        "disco-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    ));
    let peticion =
        UNNotificationRequest::requestWithIdentifier_content_trigger(&id, &contenido, None);
    centro.addNotificationRequest_withCompletionHandler(&peticion, None);
}
