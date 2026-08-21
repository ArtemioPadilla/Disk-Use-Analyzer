//! Arranca el servidor web del propio proyecto, bajo demanda, desde el ítem
//! "Abrir analizador completo".
//!
//! Antes ese ítem se limitaba a abrir `http://localhost:8000/`, dando por
//! hecho que el servidor ya estaba corriendo. En la app empaquetada no podía
//! estarlo nunca: el bundle no llevaba el servidor. El resultado era un botón
//! que abría una pestaña con un error de conexión.
//!
//! Dos decisiones que no son obvias:
//!
//! - **Se ata a loopback, no a toda la red.** El servidor por defecto escucha
//!   en `0.0.0.0` porque el acceso desde otros dispositivos es una función
//!   documentada de `make web`. Pero aquí lo arranca un clic de menú, y la
//!   interfaz web incluye una terminal que corre con los privilegios del
//!   usuario: publicarla en la red sin que nadie lo haya pedido sería una
//!   sorpresa desagradable. Por eso se le pasa `--host 127.0.0.1`.
//! - **El token viaja por variable de entorno.** El servidor corre con
//!   `reload=True`, así que uvicorn reimporta el módulo en un subproceso y
//!   cualquier cosa definida solo en el bloque `__main__` no llega al worker
//!   que atiende las peticiones. `DISK_ANALYZER_TOKEN` sí llega.

use std::io::Read;
use std::net::{Shutdown, SocketAddr, TcpStream};
use std::os::unix::process::CommandExt;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::analisis::Motor;

const PUERTO: u16 = 8000;
const HOST: &str = "127.0.0.1";
/// Cuánto se espera a que el servidor acepte conexiones. Arrancar FastAPI y
/// uvicorn lleva varios segundos en frío; medido en esta máquina, entre 8 y
/// 10. El margen es generoso a propósito: quedarse corto se manifiesta como
/// "el botón no hace nada".
const ARRANQUE_MAXIMO: Duration = Duration::from_secs(45);
const SONDEO: Duration = Duration::from_millis(250);
const TERM_GRACE: Duration = Duration::from_millis(300);

fn direccion() -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], PUERTO))
}

/// Si algo acepta conexiones en el puerto. No distingue *qué* escucha: eso lo
/// resuelve `Servidor`, que sabe si la instancia es suya.
fn puerto_ocupado() -> bool {
    match TcpStream::connect_timeout(&direccion(), Duration::from_millis(400)) {
        Ok(s) => {
            let _ = s.shutdown(Shutdown::Both);
            true
        }
        Err(_) => false,
    }
}

/// Token de un solo uso para esta instancia del servidor.
///
/// Se lee de `/dev/urandom` en vez de tirar de una dependencia nueva: son 16
/// bytes y el proyecto no tiene ningún otro motivo para arrastrar un
/// generador criptográfico.
fn token_nuevo() -> Result<String, String> {
    let mut bytes = [0u8; 16];
    std::fs::File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut bytes))
        .map_err(|e| format!("no se pudo generar el token: {e}"))?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

struct Instancia {
    pid: i32,
    url: String,
}

pub struct Servidor {
    instancia: Mutex<Option<Instancia>>,
}

impl Servidor {
    pub fn new() -> Self {
        Self {
            instancia: Mutex::new(None),
        }
    }

    /// Deja listo el analizador web y entrega por `al_terminar` la URL que hay
    /// que abrir.
    ///
    /// No bloquea: arrancar el servidor lleva segundos y esto lo llama el hilo
    /// que atiende el menú. La espera ocurre en un hilo aparte.
    pub fn abrir<F>(self: &Arc<Self>, motor: Option<&Motor>, al_terminar: F)
    where
        F: FnOnce(Result<String, String>) + Send + 'static,
    {
        // Ya teníamos uno vivo: se reutiliza con su token, en vez de arrancar
        // un segundo que chocaría en el mismo puerto.
        {
            let guard = self.instancia.lock().unwrap();
            if let Some(inst) = guard.as_ref() {
                if puerto_ocupado() {
                    al_terminar(Ok(inst.url.clone()));
                    return;
                }
            }
        }

        // El puerto está ocupado por algo que no es nuestro: puede ser un
        // `make web` del propio usuario. No conocemos su token, así que se
        // abre la URL a secas y que la sesión del navegador haga el resto.
        if puerto_ocupado() {
            al_terminar(Ok(format!("http://{HOST}:{PUERTO}/")));
            return;
        }

        // Sin motor empaquetado no hay servidor que arrancar. No es
        // necesariamente un error: puede haber un `make web` del usuario que
        // ya se habría atendido arriba.
        let Some(motor) = motor else {
            al_terminar(Err(
                "no hay servidor que abrir: falta el motor empaquetado".to_string()
            ));
            return;
        };

        let token = match token_nuevo() {
            Ok(t) => t,
            Err(e) => {
                al_terminar(Err(e));
                return;
            }
        };
        let script = motor.cwd().join("disk_analyzer_web.py");
        if !script.is_file() {
            al_terminar(Err("el motor empaquetado no trae el servidor web".to_string()));
            return;
        }

        let mut cmd = Command::new(motor.python());
        cmd.current_dir(motor.cwd())
            .arg(&script)
            .arg("--host")
            .arg(HOST)
            .arg("--port")
            .arg(PUERTO.to_string())
            .env("DISK_ANALYZER_TOKEN", &token)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            // Grupo propio: uvicorn con recarga levanta un worker aparte, así
            // que matar solo al proceso que lanzamos dejaría ese worker vivo
            // ocupando el puerto.
            .process_group(0);

        let child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                al_terminar(Err(format!("no se pudo arrancar el servidor: {e}")));
                return;
            }
        };
        let pid = child.id() as i32;
        let url = format!("http://{HOST}:{PUERTO}/?token={token}");
        *self.instancia.lock().unwrap() = Some(Instancia {
            pid,
            url: url.clone(),
        });

        let servidor = Arc::clone(self);
        std::thread::spawn(move || {
            let limite = Instant::now() + ARRANQUE_MAXIMO;
            while Instant::now() < limite {
                if puerto_ocupado() {
                    al_terminar(Ok(url));
                    return;
                }
                std::thread::sleep(SONDEO);
            }
            // No llegó a escuchar: se recoge para no dejar un proceso a medias.
            servidor.matar(pid);
            *servidor.instancia.lock().unwrap() = None;
            al_terminar(Err("el servidor no llegó a arrancar".to_string()));
        });
    }

    fn matar(&self, pid: i32) {
        unsafe {
            libc::kill(-pid, libc::SIGTERM);
        }
        std::thread::sleep(TERM_GRACE);
        unsafe {
            libc::kill(-pid, libc::SIGKILL);
        }
    }

    /// Al salir de la app. Igual que con el análisis: lo que arrancamos
    /// nosotros no debe sobrevivirnos ocupando el puerto 8000.
    pub fn kill_blocking(&self) {
        let inst = self.instancia.lock().unwrap().take();
        if let Some(inst) = inst {
            self.matar(inst.pid);
        }
    }
}

impl Default for Servidor {
    fn default() -> Self {
        Self::new()
    }
}
