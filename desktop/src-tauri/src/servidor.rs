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

const HOST: &str = "127.0.0.1";
/// Cuánto se espera a que el servidor acepte conexiones. Arrancar FastAPI y
/// uvicorn lleva varios segundos en frío; medido en esta máquina, entre 8 y
/// 10. El margen es generoso a propósito: quedarse corto se manifiesta como
/// "el botón no hace nada".
const ARRANQUE_MAXIMO: Duration = Duration::from_secs(45);
const SONDEO: Duration = Duration::from_millis(250);
const TERM_GRACE: Duration = Duration::from_millis(300);

fn direccion(puerto: u16) -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], puerto))
}

/// Si algo acepta conexiones en el puerto. No distingue *qué* escucha: eso lo
/// resuelve `Servidor::es_nuestra_instancia`, que sabe si la instancia es
/// suya.
fn acepta(puerto: u16) -> bool {
    match TcpStream::connect_timeout(&direccion(puerto), Duration::from_millis(400)) {
        Ok(s) => {
            let _ = s.shutdown(Shutdown::Both);
            true
        }
        Err(_) => false,
    }
}

/// Pide al sistema un puerto libre.
///
/// Atar el 0 hace que el kernel asigne uno sin usar; se suelta acto seguido y
/// se le pasa al servidor. Queda una ventana mínima en la que otro proceso
/// podría cogerlo, y por eso quien llama reintenta.
///
/// El 8000 fijo que había antes es un puerto muy disputado (Django, Rails,
/// http.server). Y como la app abre el navegador ella misma, el número nunca
/// lo ve el usuario: fijarlo solo servía para chocar.
fn puerto_libre() -> Result<u16, String> {
    let l = std::net::TcpListener::bind(("127.0.0.1", 0))
        .map_err(|e| format!("no se pudo pedir un puerto libre: {e}"))?;
    let p = l
        .local_addr()
        .map_err(|e| format!("no se pudo leer el puerto asignado: {e}"))?
        .port();
    drop(l);
    Ok(p)
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
    puerto: u16,
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

    /// Si el puerto lo ocupa el servidor que arrancamos nosotros.
    ///
    /// La versión anterior solo comprobaba que *algo* aceptara TCP en el
    /// 8000, así que un Django del usuario se abría en el navegador como si
    /// fuera el analizador. Ahora se exige que sea nuestra instancia
    /// registrada, que su proceso siga vivo y que el puerto siga aceptando.
    pub fn es_nuestra_instancia(&self, puerto: u16) -> bool {
        let guard = self.instancia.lock().unwrap();
        match guard.as_ref() {
            Some(inst) => {
                inst.puerto == puerto
                    && unsafe { libc::kill(inst.pid, 0) } == 0
                    && acepta(puerto)
            }
            None => false,
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
        // Ya teníamos uno vivo y sigue siendo el nuestro: se reutiliza con su
        // token, en vez de arrancar un segundo servidor. Si el puerto lo
        // ocupa ahora otra cosa (o nuestro proceso ya murió), no se reutiliza
        // nada: se arranca uno nuevo más abajo, en un puerto libre.
        {
            let existente = {
                let guard = self.instancia.lock().unwrap();
                guard.as_ref().map(|inst| (inst.puerto, inst.url.clone()))
            };
            if let Some((puerto, url)) = existente {
                if self.es_nuestra_instancia(puerto) {
                    al_terminar(Ok(url));
                    return;
                }
            }
        }

        // Sin motor empaquetado no hay servidor que arrancar.
        let Some(motor) = motor else {
            al_terminar(Err(
                "no hay servidor que abrir: falta el motor empaquetado".to_string()
            ));
            return;
        };

        let puerto = match puerto_libre() {
            Ok(p) => p,
            Err(e) => {
                al_terminar(Err(e));
                return;
            }
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
            .arg(puerto.to_string())
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
        let url = format!("http://{HOST}:{puerto}/?token={token}");
        *self.instancia.lock().unwrap() = Some(Instancia {
            pid,
            puerto,
            url: url.clone(),
        });

        let servidor = Arc::clone(self);
        std::thread::spawn(move || {
            let limite = Instant::now() + ARRANQUE_MAXIMO;
            while Instant::now() < limite {
                if acepta(puerto) {
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
    /// nosotros no debe sobrevivirnos ocupando el puerto que tomó.
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn pide_un_puerto_libre_distinto_del_8000() {
        let p = puerto_libre().expect("debería conseguir un puerto");
        assert_ne!(p, 8000, "el 8000 está muy disputado: Django, Rails, etc.");
        assert!(p >= 1024, "no se piden puertos privilegiados");
    }

    #[test]
    fn dos_llamadas_no_devuelven_el_mismo_puerto_ocupado() {
        let a = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let ocupado = a.local_addr().unwrap().port();
        // Mientras `a` siga vivo, nadie debe proponer ese puerto.
        for _ in 0..20 {
            assert_ne!(puerto_libre().unwrap(), ocupado);
        }
    }

    #[test]
    fn no_reutiliza_un_servidor_ajeno() {
        // Alguien ocupa un puerto sin ser nuestro servidor.
        let ajeno = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let puerto = ajeno.local_addr().unwrap().port();
        let servidor = Servidor::new();
        assert!(
            !servidor.es_nuestra_instancia(puerto),
            "abrir el navegador en un servidor ajeno lo presenta como nuestro"
        );
    }
}
