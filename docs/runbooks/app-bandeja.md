# Runbook: app de bandeja (Disk Use Analyzer)

Operación de la app de la barra de menús: firmarla, darle permisos,
desinstalarla del todo y volver atrás cuando algo sale mal.

- **Identificador del bundle:** `dev.diskanalyzer.app`
- **Nombre del producto:** `Disk Use Analyzer`
- **Dónde queda al compilar:**
  `desktop/src-tauri/target/release/bundle/macos/Disk Use Analyzer.app`
- **Código:** `desktop/src-tauri/src/` (`disk.rs`, `estado.rs`, `analisis.rs`, `lib.rs`)

## Lo que esta versión NO es todavía

**La app no es autocontenida y no se puede distribuir.** Al pulsar "Analizar
ahora" ejecuta el intérprete del repositorio por ruta absoluta:

```
<repo>/venv-web/bin/python <repo>/disk_analyzer.py / --min-size 50 --export <temporal>
```

Si mueves o borras el repositorio, o borras `venv-web/`, el análisis deja de
funcionar y el menú lo dice ("no se pudo iniciar el motor de análisis"). El
indicador de disco, en cambio, sigue funcionando: no depende de Python.

El motivo está documentado en el plan de la rebanada A: empaquetar el motor con
PyInstaller quedó descartado porque el antivirus de esta máquina puso en
cuarentena los tres binarios producidos. Los dos caminos abiertos para arreglarlo
—`python-build-standalone` y firmar con Developer ID— están en ese mismo
documento.

## Firma

### Por qué hay que firmar aunque no se distribuya

macOS ata el permiso de **Acceso a disco completo** a la identidad firmada del
bundle, no a su ruta. Sin certificado, Tauri firma *ad hoc* y el hash cambia en
cada compilación: el permiso se rompe en cada build y —lo peor— la lista de
Ajustes sigue mostrando la app como autorizada mientras el binario nuevo no lo
está. Un certificado autofirmado da una identidad **estable** y evita eso.

No sirve para distribuir ni para notarizar. Eso sigue esperando a una cuenta de
desarrollador de Apple (decisión D4, pospuesta).

### Crear el certificado autofirmado (una sola vez)

Necesita tu contraseña del llavero, así que hazlo tú desde la interfaz:

1. Abre **Acceso a Llaveros**.
2. Menú **Acceso a Llaveros → Asistente para certificados → Crear un
   certificado…**
3. Nombre: `Disk Analyzer Dev`. Tipo de identidad: **Root autofirmado**. Tipo de
   certificado: **Firma de código**. Marca *Permitirme sobrescribir estos
   valores* solo si quieres alargar la caducidad.
4. Comprueba que aparece:

```bash
security find-identity -v -p codesigning
```

### Firmar la app

```bash
codesign --force --timestamp=none \
  --sign "Disk Analyzer Dev" \
  "desktop/src-tauri/target/release/bundle/macos/Disk Use Analyzer.app"

# Verificar
codesign -dv --verbose=4 "desktop/src-tauri/target/release/bundle/macos/Disk Use Analyzer.app"
spctl -a -vvv "desktop/src-tauri/target/release/bundle/macos/Disk Use Analyzer.app"
```

Dos diferencias respecto a lo que suele encontrarse escrito por ahí:

- **Sin `--deep`.** Apple lo desaconseja desde hace años para firmar (solo para
  verificar): firma los componentes anidados con las mismas opciones que el
  contenedor, que casi nunca es lo que quieres. Esta app no tiene binarios
  anidados —el motor Python vive fuera del bundle—, así que no hace falta. Si
  algún día se empaqueta el motor dentro, hay que firmar **de dentro hacia
  fuera**: primero los binarios anidados, el bundle al final.
- **Sin `--options runtime`.** El *hardened runtime* solo es obligatorio para
  notarizar, y además restringe la ejecución de intérpretes no firmados, que es
  exactamente lo que esta versión hace. Se activará cuando se aborde la
  notarización, junto con los entitlements que la hagan compatible.

`spctl` va a **rechazar** la app: un certificado autofirmado no es una autoridad
en la que Gatekeeper confíe. Es lo esperado. Para abrirla la primera vez: clic
derecho sobre la `.app` → **Abrir** → **Abrir**.

## Acceso a disco completo

### Concederlo

Ajustes del Sistema → Privacidad y Seguridad → **Acceso total al disco** → `+` →
elige la `.app`. Después **cierra y vuelve a abrir la app**: macOS no reevalúa
el permiso de un proceso ya en marcha.

Sin este permiso el análisis **no falla**: el motor se salta los directorios
protegidos y termina con éxito, con un informe incompleto. Por eso el menú
detecta los errores de permisos en el informe y lo dice explícitamente en vez de
callarse.

### Revocarlo, y la trampa de la entrada huérfana

Ajustes del Sistema → Privacidad y Seguridad → Acceso total al disco →
selecciona la app → `−`.

**Cuidado con esto:** si recompilas la app con una firma distinta (o sin firma),
la entrada vieja de la lista se queda apuntando a una identidad que ya no
existe. La interfaz sigue mostrando "Disk Use Analyzer" con el interruptor
encendido, pero el binario nuevo **no** tiene el permiso. Los síntomas son
confusos: la lista dice que sí y los análisis siguen saliendo incompletos.

Cuando pase: quita la entrada con `−`, vuelve a añadirla con `+` apuntando a la
`.app` nueva, y reinicia la app. Si sigue sin funcionar, comprueba que la
identidad es la que crees:

```bash
codesign -dv --verbose=4 "/Applications/Disk Use Analyzer.app" 2>&1 | grep -E "Authority|Identifier"
```

Reiniciar el subsistema de permisos entero (`tccutil reset SystemPolicyAllFiles`)
revoca el acceso a **todas** las apps del sistema, no solo a esta. Para una sola:

```bash
tccutil reset SystemPolicyAllFiles dev.diskanalyzer.app
```

## Desinstalar del todo

```bash
# 1. Parar la app
pkill -f "Disk Use Analyzer" ; pkill -x desktop

# 2. Comprobar que no queda ningún análisis vivo
ps aux | grep -i disk_analyzer | grep -v grep

# 3. Borrar la app
rm -rf "/Applications/Disk Use Analyzer.app"
rm -rf "desktop/src-tauri/target/release/bundle/macos/Disk Use Analyzer.app"

# 4. Preferencias y estado
rm -f ~/Library/Preferences/dev.diskanalyzer.app.plist
rm -rf ~/Library/Application\ Support/dev.diskanalyzer.app
rm -rf ~/Library/Saved\ Application\ State/dev.diskanalyzer.app.savedState
rm -rf ~/Library/Caches/dev.diskanalyzer.app

# 5. Temporales de análisis que hayan quedado de un cierre brusco
rm -f "$TMPDIR"/disk-analyzer-tray-*
```

Falta un paso que **no es un comando**: quitar la entrada de Acceso total al
disco a mano (ver arriba). Borrar la `.app` no la borra; queda ahí, huérfana.

Esta versión **no instala ningún elemento de inicio de sesión**: no hay
`LaunchAgent`, no hay entrada en Ajustes → General → Elementos de inicio. Si
alguna vez se añade, este runbook tiene que crecer con ella. Para comprobarlo:

```bash
ls ~/Library/LaunchAgents | grep -i diskanalyzer   # debe salir vacío
```

## Volver atrás

1. Cierra la app (`pkill -x desktop`) y comprueba que no queda ningún análisis
   vivo (`ps aux | grep disk_analyzer`).
2. Vuelve al commit anterior y recompila:

```bash
git log --oneline -- desktop/
git checkout <commit-anterior> -- desktop/
cd desktop && npm run tauri build -- --bundles app
```

3. Vuelve a firmar (la firma no sobrevive a la recompilación) y **rehaz la
   entrada de Acceso total al disco**, por lo de la entrada huérfana.

Si Gatekeeper bloquea la app y no sabes por qué, la respuesta está en:

```bash
spctl -a -vvv "<ruta>.app"          # qué decide Gatekeeper y por qué
codesign --verify --deep --strict --verbose=4 "<ruta>.app"   # aquí --deep sí vale: es verificación
log show --last 5m --predicate 'subsystem == "com.apple.TCC"' --info   # denegaciones de permisos
```

## Notarización (pendiente de D4)

No se puede hacer todavía: requiere cuenta de desarrollador de Apple. Cuando la
haya, el proceso es firmar con Developer ID **con hardened runtime**, comprimir y
enviar:

```bash
codesign --force --options runtime --timestamp \
  --sign "Developer ID Application: TU NOMBRE (TEAMID)" "<ruta>.app"
ditto -c -k --keepParent "<ruta>.app" app.zip
xcrun notarytool submit app.zip --apple-id <tu-id> --team-id <TEAMID> --wait
xcrun stapler staple "<ruta>.app"
```

**Si rechaza, lee el log antes de reintentar.** Reenviar lo mismo devuelve el
mismo rechazo:

```bash
xcrun notarytool log <id-de-envío> --apple-id <tu-id> --team-id <TEAMID>
```

Causas habituales al empaquetar Python: falta de *hardened runtime*, extensiones
`.so` anidadas sin firmar, y falta de marca de tiempo segura (`--timestamp`, que
arriba desactivamos a propósito para el certificado autofirmado).
