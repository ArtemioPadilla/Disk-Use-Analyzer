# App de bandeja — Rebanada A: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una `.app` de macOS anclada en la barra de menú que muestra el llenado del disco con el mismo número que el resto del proyecto, permite lanzar un análisis, y está empaquetada y firmada.

**Architecture:** Caparazón Tauri 2 en Rust que hace solo lo barato y siempre encendido (leer el espacio de disco, pintar el icono, el menú). Python se invoca como sidecar únicamente para analizar. En esta rebanada **no hay servidor web ni ventana**: "Abrir analizador" abre el navegador contra el flujo existente.

**Tech Stack:** Tauri 2, Rust (a instalar), `sysinfo`, PyInstaller para el sidecar, `codesign` + `notarytool`.

**Spec:** `docs/superpowers/specs/2026-08-19-app-bandeja-tauri-design.md` — léelo antes de empezar. Este plan implementa su rebanada A y da por sentadas sus decisiones.

## Global Constraints

- **Tauri 2**, no patrones de v1.
- **Rust no está instalado en esta máquina** (verificado: `cargo`, `rustc` y `rustup` ausentes). El Task 2 lo instala.
- **No hay ninguna identidad de firma en el llavero** (verificado: `security find-identity -v -p codesigning` → 0). Firmar y notarizar exige cuenta de desarrollador de Apple (99 $/año) — es la decisión D4 del Task 1.
- macOS de esta máquina: **26.5.1**. Node 26.7.0, npm 11.19.0.
- **El icono nunca muere:** ningún fallo de una capa inferior puede tumbar el indicador.
- **Un solo análisis a la vez.**
- La suite existente (151 backend + 69 frontend) debe seguir en verde. Este trabajo no toca `disk_analyzer.py`, `disk_analyzer_core.py`, `analyzer/` ni `web/`.
- Mensajes de cara al usuario en español; comentarios de código en inglés.
- Un commit por task.

## Decisiones del Task 1 (cerradas el 20 de agosto de 2026)

| # | Decisión | Elegido |
|---|---|---|
| D1 | Identificador del bundle | **`dev.diskanalyzer.app`** |
| D2 | Alcance del análisis en la v1 | **Disco completo desde el día uno** |
| D3 | "Analizar ahora" | **Con progreso y cancelable** desde el menú |
| D4 | Cuenta de desarrollador de Apple | **Sin cuenta por ahora** |

### La tensión entre D2 y D4, y cómo se resuelve

D2 exige **acceso a disco completo**, un permiso que macOS ata a la identidad
firmada del bundle. D4 significa que no hay Developer ID, así que Tauri firma
*ad-hoc* y el hash cambia en cada recompilación: el permiso se rompería en cada
build, y el sistema mostraría la app como autorizada mientras el binario nuevo no
lo está.

**Resolución: un certificado autofirmado**, creado localmente desde Acceso a
Llaveros. No sirve para notarizar ni distribuir —eso sigue esperando a D4—, pero
da una **identidad estable**, de modo que la concesión de disco completo persiste
entre compilaciones. Cubre además la mitad del pipeline de firma que era objetivo
de aprendizaje: `codesign`, hardened runtime y entitlements; solo queda fuera la
notarización.

Consecuencias en el plan:

- El **Task 6 se adelanta parcialmente**: crear el certificado autofirmado y
  firmar con él pasa a ser prerequisito del Task 5, porque sin identidad estable
  no se puede probar el análisis de `/`.
- El Task 5 necesita además **detectar que falta el permiso y decirlo en el
  menú**, en vez de fallar en silencio: es el primer arranque de cualquier
  usuario nuevo.
- La notarización queda documentada en el runbook como pendiente de D4.


---

### Task 1: Cerrar las decisiones bloqueantes (humano, no delegable a un agente)

Ninguna otra tarea empieza hasta que estén cerradas. **Un subagente no debe decidir ninguna de estas por su cuenta**: son caras o imposibles de revertir.

**Files:** ninguno. La salida es que este archivo queda editado con las respuestas.

**Interfaces:**
- Produces: el identificador definitivo, el alcance del análisis en la v1, el comportamiento de "Analizar ahora", y si hay cuenta de Apple. Todos los tasks posteriores dependen de esto.

- [ ] **Step 1: Confirmar el identificador del bundle**

Propuesto: `dev.diskanalyzer.app`. macOS ata a esta identidad los permisos concedidos; cambiarlo después obliga al usuario a reconceder acceso a disco completo y deja preferencias huérfanas. Pide visto bueno explícito de la cadena exacta.

- [ ] **Step 2: Decidir el alcance del análisis en la v1 (D2)**

- **Opción A (recomendada): solo el directorio personal.** No requiere acceso a disco completo, así que la app funciona desde el primer arranque sin fricción y sin depender de la firma.
- **Opción B: disco completo desde el día uno.** Exige resolver firma y concesión de permisos antes de tener nada usable.

Si se elige A, el Task 6 (firma) puede posponerse sin bloquear nada. Si se elige B, el Task 6 pasa a ser prerequisito del Task 5.

- [ ] **Step 3: Decidir qué hace "Analizar ahora" (D3)**

Medido: un análisis tarda **25-60 segundos** (61 s para 1.855 archivos en `~/Downloads`, 25 s para 399 en el repo — lo dominan el hashing de duplicados y el sondeo de cachés, no el número de archivos).

- **Opción A (recomendada): con progreso y cancelable** desde el menú.
- **Opción B: delegar al analizador web**, que ya tiene progreso por WebSocket.

- [ ] **Step 4: Decidir si hay cuenta de desarrollador de Apple (D4)**

No hay identidades de firma en el llavero. Firmar y notarizar —que es el objetivo de aprendizaje declarado— requiere cuenta de pago (99 $/año).

- **Con cuenta:** el Task 6 se ejecuta completo.
- **Sin cuenta:** el Task 6 se limita a construir la `.app` sin firmar, que funciona en tu máquina con un clic derecho → Abrir, pero no es distribuible. Se documenta y se pospone.

- [ ] **Step 5: Registrar las respuestas**

Edita las Global Constraints de este archivo sustituyendo cada decisión abierta por la elegida, y commitea:

```bash
git add docs/superpowers/plans/2026-08-20-app-bandeja-rebanada-a.md
git commit -m "docs: cerrar las decisiones bloqueantes de la rebanada A"
```

---

### Task 2: Instalar Rust y crear el andamiaje Tauri

**Files:**
- Create: `desktop/` (proyecto Tauri completo), `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/src/main.rs`, `desktop/src-tauri/capabilities/default.json`
- Modify: `.gitignore`

**Interfaces:**
- Produces: una app Tauri que arranca, no aparece en el Dock ni en Cmd+Tab, y muestra un icono de bandeja estático con un menú de un solo ítem (Salir).

- [ ] **Step 1: Instalar Rust**

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
cargo --version && rustc --version
```
Expected: ambas versiones se imprimen. Si `cargo` no se encuentra en shells nuevas, añade `source "$HOME/.cargo/env"` a tu perfil.

- [ ] **Step 2: Crear el proyecto**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer
npm create tauri-app@latest desktop -- --template vanilla --manager npm --yes
```

Nota: la plantilla trae un frontend de ejemplo que no usaremos (esta rebanada no tiene ventana). No lo borres todavía: Tauri exige un `frontendDist` válido aunque no se abra ninguna ventana.

- [ ] **Step 3: Configurar la app como accesorio (sin icono en el Dock)**

Sin esto la app rebota en el Dock, se queda ahí y sale en Cmd+Tab — no se comporta como app de barra. En `desktop/src-tauri/src/main.rs`:

```rust
fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // A menu bar app must not appear in the Dock or Cmd+Tab.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

Nota de verificación: `set_activation_policy` y `ActivationPolicy::Accessory` provienen de la revisión adversarial, no de una prueba propia. Si la firma difiere en la versión instalada, consulta `cargo doc --open -p tauri` y ajusta; la alternativa es `LSUIElement` en el `Info.plist` del bundle.

- [ ] **Step 4: Declarar permisos de bandeja**

Tauri 2 bloquea por defecto lo que este diseño necesita. En `desktop/src-tauri/capabilities/default.json`, añade a `permissions`:

```json
"core:tray:default"
```

- [ ] **Step 5: Icono de bandeja mínimo con menú**

En el `setup`, tras la política de activación:

```rust
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;

let quit = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
let menu = Menu::with_items(app, &[&quit])?;
let _tray = TrayIconBuilder::new()
    .menu(&menu)
    .on_menu_event(|app, event| {
        if event.id() == "quit" {
            app.exit(0);
        }
    })
    .build(app)?;
```

- [ ] **Step 6: Ignorar los artefactos de compilación**

Añade a `.gitignore` (`Cargo.lock` de un binario **sí** se commitea, no lo ignores):

```
desktop/src-tauri/target/
desktop/node_modules/
desktop/dist/
```

- [ ] **Step 7: Verificar y commitear**

```bash
cd desktop && npm run tauri dev
```
Expected: aparece un icono en la barra de menú; su menú tiene "Salir" y funciona; **no** aparece nada en el Dock ni en Cmd+Tab.

```bash
git add desktop .gitignore
git commit -m "feat(desktop): andamiaje Tauri con icono de bandeja y sin presencia en el Dock"
```

---

### Task 3: Lectura de disco consistente con el motor

El task más importante del plan. Sobre esta máquina, ahora mismo, el motor Python dice **96,6 %** de disco usado y la columna `used` de `df` dice **43 %** — 53 puntos de diferencia sobre el mismo disco, porque en APFS `/` es el volumen de sistema de solo lectura mientras el espacio libre corresponde al contenedor compartido. Si la lectura de Rust se parece a `df`, la bandeja mostrará verde tranquilizador con 15 GB libres.

**Files:**
- Create: `desktop/src-tauri/src/disk.rs`, `desktop/src-tauri/tests/consistency.rs`
- Modify: `desktop/src-tauri/src/main.rs`, `desktop/src-tauri/Cargo.toml`

**Interfaces:**
- Produces: `disk::read() -> DiskUsage { total: u64, used: u64, available: u64, percent: f64 }`, donde `used` se calcula como `total - available` para coincidir con el motor.

- [ ] **Step 1: Escribir el test de consistencia primero**

Crea `desktop/src-tauri/tests/consistency.rs`. Compara la lectura de Rust contra el motor Python real:

```rust
use std::process::Command;

/// The tray must show the same number as the rest of the project.
/// Measured on this machine while writing the plan: the engine reports
/// 96.6% used while `df`'s own "used" column reports 43% — a 53-point gap,
/// because on APFS `/` is the read-only system volume while free space
/// belongs to the shared container. Reading disk usage the way `df` does
/// would make the tray show a reassuring green on a nearly-full disk.
#[test]
fn rust_reading_matches_the_python_engine() {
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("repo root");

    let out = Command::new(repo.join("venv-web/bin/python"))
        .current_dir(&repo)
        .args([
            "-c",
            "import sys; sys.path.insert(0,'.'); \
             from disk_analyzer_core import DiskAnalyzerCore; \
             d=DiskAnalyzerCore('.').get_disk_usage(); \
             print(d['total'], d['used'], d['available'])",
        ])
        .output()
        .expect("the python engine must be runnable");

    let stdout = String::from_utf8(out.stdout).expect("utf8");
    let nums: Vec<u64> = stdout
        .split_whitespace()
        .map(|s| s.parse().expect("number"))
        .collect();
    let (py_total, py_used, py_available) = (nums[0], nums[1], nums[2]);

    let rust = disk_analyzer_tray::disk::read().expect("disk read");

    // Free space moves while the test runs, so compare with a tolerance
    // large enough for normal churn but far smaller than the 53-point gap
    // this test exists to catch.
    let tolerance = (py_total as f64 * 0.01) as u64; // 1% of the volume
    assert!(
        rust.total.abs_diff(py_total) <= tolerance,
        "el total diverge: rust {} vs python {}", rust.total, py_total
    );
    assert!(
        rust.used.abs_diff(py_used) <= tolerance,
        "used diverge: rust {} vs python {} — ¿estás usando la columna 'used' \
         en vez de total-available?", rust.used, py_used
    );
    assert!(
        rust.available.abs_diff(py_available) <= tolerance,
        "available diverge: rust {} vs python {}", rust.available, py_available
    );
}
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
cd desktop/src-tauri && cargo test --test consistency
```
Expected: FAIL — el módulo `disk` no existe todavía.

- [ ] **Step 3: Implementar la lectura**

Añade a `desktop/src-tauri/Cargo.toml`:

```toml
sysinfo = "0.32"
```

Crea `desktop/src-tauri/src/disk.rs`:

```rust
use sysinfo::Disks;

#[derive(Debug, Clone, Copy)]
pub struct DiskUsage {
    pub total: u64,
    pub used: u64,
    pub available: u64,
    pub percent: f64,
}

/// Read usage for the volume backing `/`.
///
/// `used` is deliberately computed as `total - available` rather than taken
/// from any per-volume "used" figure: on APFS the root volume is read-only
/// and its own used bytes say nothing about how full the disk is. The Python
/// engine made this same choice (`disk_analyzer_core.get_disk_usage`), and
/// tests/consistency.rs fails if the two ever drift apart.
pub fn read() -> Option<DiskUsage> {
    let disks = Disks::new_with_refreshed_list();
    let root = disks
        .list()
        .iter()
        .find(|d| d.mount_point() == std::path::Path::new("/"))?;

    let total = root.total_space();
    let available = root.available_space();
    if total == 0 {
        return None;
    }
    let used = total.saturating_sub(available);
    Some(DiskUsage {
        total,
        used,
        available,
        percent: used as f64 / total as f64 * 100.0,
    })
}
```

Expón el módulo desde una librería para que el test pueda importarlo: crea `desktop/src-tauri/src/lib.rs` con `pub mod disk;` y añade a `Cargo.toml`:

```toml
[lib]
name = "disk_analyzer_tray"
path = "src/lib.rs"
```

- [ ] **Step 4: Correr el test y verificar que pasa**

```bash
cd desktop/src-tauri && cargo test --test consistency
```
Expected: PASS.

Si falla por divergencia, **no ajustes la tolerancia**: es exactamente el fallo que el test existe para detectar. Investiga qué volumen está eligiendo `sysinfo`.

- [ ] **Step 5: Commit**

```bash
git add desktop/src-tauri
git commit -m "feat(desktop): lectura de disco verificada contra el motor Python"
```

---

### Task 4: Estado del icono por porcentaje y espacio absoluto

Los umbrales por porcentaje solos fallan en los dos extremos: 4 TB al 85 % deja 600 GB libres (no urgente); 128 GB al 60 % deja 51 GB (ya aprieta con Xcode y Docker).

**Files:**
- Create: `desktop/src-tauri/src/estado.rs`, `desktop/src-tauri/assets/tray/` (los PNG)
- Modify: `desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: `disk::DiskUsage` del Task 3.
- Produces: `estado::classify(u: DiskUsage) -> Estado` donde `Estado` es `Ok | Aviso | Critico`.

- [ ] **Step 1: Escribir los tests primero**

Crea el módulo con sus tests al final, en `desktop/src-tauri/src/estado.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use crate::disk::DiskUsage;

    fn uso(total_gb: u64, libre_gb: u64) -> DiskUsage {
        let gb = 1024u64 * 1024 * 1024;
        let total = total_gb * gb;
        let available = libre_gb * gb;
        let used = total - available;
        DiskUsage { total, used, available, percent: used as f64 / total as f64 * 100.0 }
    }

    #[test]
    fn disco_holgado_es_ok() {
        assert_eq!(classify(uso(500, 300)), Estado::Ok);
    }

    #[test]
    fn porcentaje_alto_pero_muchos_gb_libres_no_es_critico() {
        // 4 TB al 85%: 600 GB libres. No es urgente aunque el porcentaje asuste.
        assert_ne!(classify(uso(4000, 600)), Estado::Critico);
    }

    #[test]
    fn porcentaje_moderado_con_pocos_gb_si_avisa() {
        // 128 GB al 60%: 51 GB libres. Aprieta de verdad.
        assert_ne!(classify(uso(128, 51)), Estado::Ok);
    }

    #[test]
    fn el_caso_real_de_esta_maquina_es_critico() {
        // Medido al escribir el plan: 460 GB totales, 15.59 GB libres.
        assert_eq!(classify(uso(460, 15)), Estado::Critico);
    }
}
```

- [ ] **Step 2: Correr y verificar que fallan**

```bash
cd desktop/src-tauri && cargo test estado
```
Expected: FAIL — no compila, falta `classify`.

- [ ] **Step 3: Implementar**

En el mismo archivo, encima de los tests:

```rust
use crate::disk::DiskUsage;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Estado {
    Ok,
    Aviso,
    Critico,
}

const GB: u64 = 1024 * 1024 * 1024;

/// Classify disk pressure from both proportion and absolute free space.
///
/// Percentage alone is wrong at both ends of the drive-size range: 85% of a
/// 4 TB drive still leaves 600 GB, while 60% of a 128 GB drive leaves 51 GB,
/// which is already tight for Xcode and Docker. Red must mean "this is a
/// problem now" — if it shows up early, people stop looking at it.
pub fn classify(u: DiskUsage) -> Estado {
    let libre_gb = u.available / GB;
    if libre_gb < 25 || u.percent >= 95.0 {
        Estado::Critico
    } else if libre_gb < 75 || u.percent >= 85.0 {
        Estado::Aviso
    } else {
        Estado::Ok
    }
}
```

- [ ] **Step 4: Verificar que pasan**

```bash
cd desktop/src-tauri && cargo test estado
```
Expected: PASS los cuatro.

- [ ] **Step 5: Crear los iconos**

Tres PNG en `desktop/src-tauri/assets/tray/`, en `@1x` (22×22) y `@2x` (44×44): `ok.png`, `aviso.png`, `critico.png`. Un rectángulo redondeado con contorno siempre visible y relleno proporcional al estado, en verde, ámbar y rojo.

El contorno no es decoración: garantiza que la pieza se distinga sobre cualquier fondo de barra.

- [ ] **Step 6: Commit**

```bash
git add desktop/src-tauri
git commit -m "feat(desktop): estado del icono por porcentaje y espacio absoluto"
```

---

### Task 5: Menú vivo y análisis bajo demanda

**Files:**
- Modify: `desktop/src-tauri/src/main.rs`, `desktop/src-tauri/capabilities/default.json`
- Create: `desktop/src-tauri/src/analisis.rs`

**Interfaces:**
- Consumes: `disk::read()`, `estado::classify()`.
- Produces: un menú que se refresca solo y una acción de análisis con un único proceso a la vez.

- [ ] **Step 1: Refrescar el pulso**

Leer el disco cuesta **0,7 µs** (medido), así que refrescar cada 5 segundos no necesita justificación. En el `setup`, tras construir la bandeja, lanza una tarea que cada 5 s lea el disco, actualice el texto del ítem de uso y cambie el icono si el estado cambió.

Actualiza el icono **solo cuando cambia el estado**, no en cada lectura: cambiarlo sin necesidad provoca parpadeo en algunas versiones de macOS.

- [ ] **Step 2: Un solo análisis a la vez**

En `desktop/src-tauri/src/analisis.rs`, guarda el proceso hijo en un `Mutex<Option<Child>>`. Si ya hay uno vivo, el segundo clic no lanza otro: el menú indica que hay un análisis en marcha.

Lanza el hijo en su **propio grupo de procesos** para poder matar el grupo entero, y al salir escala de `SIGTERM` a `SIGKILL` con un plazo — el mismo patrón que `pty_manager.py` ya tiene probado en `KILL_REAP_TIMEOUT`.

- [ ] **Step 3: Permisos del sidecar**

Añade a `capabilities/default.json`:

```json
{
  "identifier": "shell:allow-execute",
  "allow": [{ "name": "binaries/disk-analyzer", "sidecar": true }]
}
```

Los argumentos dinámicos (la ruta a analizar) necesitan lista blanca o validador: Tauri no los permite libres.

- [ ] **Step 4: Verificar a mano**

```bash
cd desktop && npm run tauri dev
```
Comprueba: el porcentaje del menú coincide con `venv-web/bin/python -c "..."` del Task 3; el icono cambia de estado al liberar o llenar espacio; dos clics seguidos en "Analizar ahora" no lanzan dos procesos (`ps aux | grep disk_analyzer`); al salir no queda ninguno vivo.

- [ ] **Step 5: Commit**

```bash
git add desktop/src-tauri
git commit -m "feat(desktop): menú vivo y análisis con un solo proceso a la vez"
```

---

### Task 6: Empaquetado, firma y notarización

**Condicional a la decisión D4 del Task 1.** Sin cuenta de desarrollador de Apple, ejecuta solo los pasos 1 y 2 y documenta el resto como pendiente.

**Files:**
- Create: `docs/runbooks/app-bandeja.md`
- Modify: `desktop/src-tauri/tauri.conf.json`, `.gitignore`

- [ ] **Step 1: Empaquetar el motor Python como sidecar**

PyInstaller produce un binario por plataforma y **no compila cruzado**. Tauri espera el nombre con el triple de destino:

```bash
venv-web/bin/pip install pyinstaller
venv-web/bin/pyinstaller --onefile --name disk-analyzer disk_analyzer.py
mkdir -p desktop/src-tauri/binaries
cp dist/disk-analyzer "desktop/src-tauri/binaries/disk-analyzer-$(rustc -vV | sed -n 's/host: //p')"
```

Declara en `tauri.conf.json`: `"bundle": { "externalBin": ["binaries/disk-analyzer"] }`.

- [ ] **Step 2: Construir la `.app` sin firmar y probarla**

```bash
cd desktop && npm run tauri build
```
Expected: una `.app` en `desktop/src-tauri/target/release/bundle/macos/`. Ábrela con clic derecho → Abrir (Gatekeeper la bloqueará con doble clic, que es lo esperado sin firma).

- [ ] **Step 3: Firmar (requiere D4 afirmativa)**

Ignora los secretos antes de nada — añade a `.gitignore`:

```
*.p12
*.cer
```

El certificado vive en el llavero, **nunca en el repositorio**. Firma con *hardened runtime*, que la notarización exige:

```bash
codesign --deep --force --options runtime \
  --sign "Developer ID Application: TU NOMBRE (TEAMID)" \
  desktop/src-tauri/target/release/bundle/macos/*.app
```

El binario de Python empaquetado se firma también: los binarios anidados sin firmar son una causa habitual de rechazo.

- [ ] **Step 4: Notarizar**

```bash
xcrun notarytool submit <ruta>.zip --apple-id <tu-id> --team-id <TEAMID> --wait
```

**Si rechaza, lee el log antes de reintentar** — reenviar sin cambios devuelve el mismo rechazo:

```bash
xcrun notarytool log <id-de-envío>
```

Causas habituales al empaquetar Python: falta de *hardened runtime*, extensiones `.so` anidadas sin firmar, y falta de marca de tiempo segura.

- [ ] **Step 5: Escribir el runbook**

Crea `docs/runbooks/app-bandeja.md` con: cómo desinstalar del todo (la `.app`, el elemento de inicio si existe, `~/Library/Preferences/<identificador>.plist` y la entrada de acceso a disco completo); cómo revocar ese permiso, advirtiendo de que tras recompilar con otra firma la entrada vieja queda huérfana y macOS muestra la app como autorizada aunque el binario nuevo no lo esté; cómo leer el log de notarización; y cómo volver atrás (reinstalar la versión anterior, `spctl -a -vvv` para diagnosticar Gatekeeper).

- [ ] **Step 6: Commit**

```bash
git add desktop/src-tauri/tauri.conf.json .gitignore docs/runbooks/app-bandeja.md
git commit -m "feat(desktop): empaquetado del sidecar y runbook de firma y notarización"
```

---

### Task 7: CI y verificación integral

**Files:**
- Modify: `.github/workflows/ci.yml`, `Makefile`

- [ ] **Step 1: Añadir Rust al CI**

Un lenguaje nuevo no entra sin la misma disciplina que el resto: el proyecto tiene 151 tests de backend y 69 de frontend, ambos en CI. Añade un job `desktop` que corra en `macos-latest`:

```yaml
  desktop:
    name: Desktop (Rust)
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: clippy
      - name: Clippy
        run: cargo clippy --manifest-path desktop/src-tauri/Cargo.toml -- -D warnings
      - name: Test
        run: cargo test --manifest-path desktop/src-tauri/Cargo.toml
```

Nota: el test de consistencia necesita el venv de Python. Si en CI no existe, márcalo con `#[ignore]` y córrelo en local, documentándolo — mejor un test honestamente saltado en CI que uno que pasa sin comprobar nada.

- [ ] **Step 2: Añadir el objetivo al Makefile**

Añade `cargo test` al target `test` existente, para que `make test` y el CI corran lo mismo.

- [ ] **Step 3: Verificación manual**

Lo que solo se ve mirando. Anota el resultado de cada punto:

1. El icono se lee en **tema claro** y en **tema oscuro**.
2. Se lee con **"Reducir transparencia"** activado (Ajustes → Accesibilidad → Pantalla).
3. Se lee sobre un fondo de escritorio claro y sobre uno oscuro.
4. En **macOS 26** (esta máquina), comprueba si el ajuste de estilo de iconos del sistema hace que el nuestro desentone junto a los demás.
5. El estado cambia al liberar o llenar espacio de verdad.
6. **No** aparece en el Dock ni en Cmd+Tab.
7. Al salir no queda ningún proceso vivo: `ps aux | grep -i disk_analyzer`.

- [ ] **Step 4: Actualizar la documentación**

Añade la rebanada A al registro de ejecución y actualiza el punto de entrada de los planes con el estado y la siguiente acción.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml Makefile docs/
git commit -m "ci: tests de Rust, y cerrar el registro de la rebanada A"
```

---

## Self-Review

**1. Cobertura del spec:** las decisiones bloqueantes son el Task 1; la lectura consistente el 3 (con el test que la medición hizo obligatoria); los umbrales combinados el 4; el proceso único con grupo de procesos el 5; el empaquetado y el runbook el 6; el CI el 7. La política de accesorio y los permisos de Tauri están en el 2. Queda fuera lo que el spec declara fuera: vigilancia de carpetas, ventana del panel, Linux y Windows.

**2. Marcadores:** ninguno. Las notas de "verifica la firma contra la versión instalada" son deliberadas y llevan alternativa concreta, no son huecos.

**3. Consistencia de tipos:** `disk::read() -> Option<DiskUsage>` se define en el Task 3 y se consume en el 4 y el 5; `estado::classify(DiskUsage) -> Estado` se define en el 4 y se consume en el 5; el nombre de la librería `disk_analyzer_tray` es el mismo en el test del 3 y en el `Cargo.toml`.

**4. Riesgo principal:** que `sysinfo` elija un volumen distinto al que mira el motor. Por eso el Task 3 va antes que cualquier trabajo de interfaz y su test compara contra el motor real en vez de contra una constante.
