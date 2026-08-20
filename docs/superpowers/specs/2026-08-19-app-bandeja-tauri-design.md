# Diseño — App de bandeja con Tauri

> **Revisión 2.** La primera versión fue sometida a cinco revisiones adversariales
> y no sobrevivió intacta. Los errores encontrados y las decisiones que provocaron
> están al final, en "Qué cambió y por qué". Vale la pena leerlo: varias
> afirmaciones de la v1 eran directamente falsas.

## Qué construimos

Una app de escritorio anclada en la barra de menú de macOS que muestra el llenado
del disco de un vistazo, permite lanzar un análisis desde el menú, y abre el
analizador completo que ya existe.

## Alcance honesto: macOS primero

**Esta revisión limita el objetivo a macOS.** La v1 prometía las tres
plataformas; la verificación demostró que era una promesa que el diseño no podía
cumplir:

- **GNOME —el escritorio Linux más común— no muestra bandeja del sistema** desde
  2017 sin que el usuario instale una extensión manualmente. La premisa de la app
  (un icono siempre visible) falla en silencio en un escritorio Linux de fábrica.
- **La bandeja de Linux no acepta píxeles en memoria.** Es DBus y toma una ruta de
  archivo; Tauri lo resuelve escribiendo un temporal en cada actualización. El
  modelo de coste de la v1 ("redibujado barato en memoria") era falso allí.
- **En Windows el servidor del panel no arranca.** `disk_analyzer_web.py:32`
  importa `PTYManager` a nivel de módulo, y `pty_manager.py` importa `pty`,
  `fcntl` y `termios` y llama a `os.fork()`. Ninguno existe en Windows: el
  servidor revienta al importar, no es que la terminal no funcione.
- **PyInstaller no compila cruzado.** El binario de cada plataforma debe
  construirse en esa plataforma. Sin runners por sistema, no hay forma de
  producir ni probar los sidecars de Linux y Windows desde un Mac.

Nada de esto hunde la idea, pero sí significa que "funciona en las tres" es un
proyecto aparte con su propio diseño, no una casilla que se marca al final. Se
deja anotado como trabajo futuro con estos obstáculos ya identificados, para que
quien lo retome no los redescubra.

## Las tres rebanadas, reordenadas

| # | Rebanada | Qué entrega | Estado |
|---|---|---|---|
| A | Icono en la barra + pulso de disco + análisis bajo demanda + **empaquetado firmado** | Una `.app` real, anclada, que ya sirve | **este documento** |
| B | Vigilancia de carpetas en tiempo real (FSEvents) | Lo que de verdad es "analítica en tiempo real" | pendiente |
| C | Panel completo como ventana Tauri | La interfaz web dentro de la app | pendiente |

La v1 ponía el panel en la primera rebanada. Estaba mal: el panel arrastra el
ciclo de vida del servidor, la exposición de la terminal, los procesos huérfanos
y el problema de CORS — es la parte **más difícil y más peligrosa**, y estaba
programada para construirse antes de haber aprendido la plataforma. Ahora va al
final.

El empaquetado sube a la rebanada A por tres razones concretas: es un objetivo de
aprendizaje declarado; condiciona la arquitectura (el sidecar de Tauri quiere un
binario ya compilado, no un script en un venv); y en macOS el **acceso a disco
completo se concede a la identidad firmada del bundle**, así que sin firma cada
recompilación pierde el permiso y el análisis de `/` falla de formas confusas.

### Sobre "analítica en tiempo real"

Conviene decirlo sin adornos: **la rebanada A no entrega analítica en tiempo
real**. Entrega un medidor de llenado que se actualiza solo, y análisis a
petición. Lo que pediste —enterarte de que algo se está comiendo el disco
*mientras pasa*— es la rebanada B, y es la que hace interesante tener la app
anclada en lugar de ejecutar `make analyze` a mano.

Se ordena así porque B necesita que exista una app donde vivir. Pero si tras la
rebanada A prefieres saltar a B antes que al panel, ese orden también es válido y
probablemente mejor.

## Arquitectura

Dos piezas, con una regla que las ordena: **cada capa cuesta lo que vale.**

**El caparazón Rust** hace lo barato y siempre encendido: lee el espacio de disco
con `sysinfo`, elige un icono y actualiza el menú. No mantiene Python residente.

**El motor Python** se invoca como sidecar solo cuando se pide un análisis. Se
empaqueta con PyInstaller en un binario por triple de destino, que es lo que el
mecanismo `externalBin` de Tauri espera.

En la rebanada A **no hay servidor web ni ventana**. "Abrir analizador completo"
abre el navegador contra el flujo que ya existe hoy. Es deliberado: evita de un
golpe el ciclo de vida del servidor, el CORS y la exposición de la terminal.

### Permisos de Tauri

Tauri 2 bloquea por defecto todo lo que este diseño necesita. Hay que declarar
explícitamente en las capabilities: `core:tray:default` para la bandeja, y
`shell:allow-execute` con la entrada `{"name": ..., "sidecar": true}` por cada
binario. Los argumentos dinámicos (ruta a analizar, `--export`) necesitan además
una lista blanca o un validador — no se pueden pasar libremente.

## El icono

**Imágenes pre-generadas por umbral, no un rasterizador en tiempo de ejecución.**
La v1 proponía dibujar un medidor con relleno proporcional en cada refresco. Es
sobreingeniería: nadie pidió un dial animado, tres estados discretos no necesitan
antialiasing, y la variante pre-generada elimina el problema del archivo temporal
cuando llegue Linux.

Se generan como *assets* en `@1x/@2x` y se intercambian según el estado.

### Umbrales por espacio libre, no solo por porcentaje

La v1 usaba 70/85% a secas. Está mal en los dos extremos: un disco de 4 TB al 85%
tiene 600 GB libres y no es urgente; uno de 128 GB al 60% tiene 51 GB y ya aprieta
con Xcode y Docker. Los umbrales combinan proporción **y** espacio absoluto, y el
rojo debe significar "esto ya es un problema" — si aparece pronto, dejas de
mirarlo.

### Contabilidad consistente con el motor

El icono debe mostrar **el mismo número que el resto de la app**. Este proyecto ya
invirtió esfuerzo en que esa cifra sea correcta en APFS: usar `total - available`
en vez de la columna `used` de `df`, saltar los firmlinks que duplicaban el total,
y contabilizar los volúmenes del sistema con `diskutil apfs list`. Si la bandeja
dice 90% y el informe dice 74%, se rompe la confianza en el único dato que
justifica la app.

La rebanada A usa `sysinfo` en Rust y **verifica contra el motor Python que
coinciden**, con un test que compara ambas lecturas. Si divergen, la bandeja se
alinea con el motor, no al revés.

### La contrapartida del color, completa

macOS espera iconos de barra en modo *template*: monocromos, que el sistema tiñe
según la apariencia. Un icono en color renuncia a más de lo que decía la v1:

- No se adapta solo a barra clara u oscura.
- **No recibe el estado resaltado** al pulsar el icono para abrir el menú.
- En macOS 26 no participa del ajuste de estilo de iconos del sistema, así que se
  verá ajeno junto a los demás.
- Un medidor de relleno en color es **el lenguaje visual del icono de batería**, y
  se leerá como indicador del sistema en vez de como app de terceros.

Se acepta igualmente, porque el color es justo lo que permite leer un disco al 92%
de un vistazo. Pero se verifica en tema claro, tema oscuro, con "Reducir
transparencia" activado, y sobre fondos de escritorio claros y oscuros.

### El texto del porcentaje: opcional y apagado por defecto

macOS **oculta elementos de la barra sin ningún aviso** cuando no caben, y el
notch reduce el espacio. Añadir texto ensancha el elemento y lo vuelve más
propenso a desaparecer — justo lo contrario del objetivo. Se implementa como
opción, apagada por defecto.

## El menú

- Uso de disco (usado / total, porcentaje y **espacio libre en GB**)
- Resultado del último análisis, si lo hay
- **Analizar ahora** — lanza el CLI como sidecar
- **Abrir analizador completo** — abre el navegador
- **Salir**

Se descarta de esta rebanada el conmutador de arranque al inicio de sesión: no lo
pediste, y el registro como login item es poco fiable en builds sin firmar, así
que llegaría antes de poder funcionar bien.

## macOS: lo que la v1 no consideró

**`LSUIElement`.** Una app Tauri es una app normal salvo que se declare lo
contrario. Sin esto rebota en el Dock, se queda ahí y aparece en Cmd+Tab — no se
comporta como app de barra. Se establece `ActivationPolicy::Accessory`.

**Acceso a disco completo.** Analizar `/` lo requiere. El permiso se concede a la
identidad firmada del bundle, así que sin firma se pierde en cada recompilación
(otra razón para adelantar el empaquetado). La app debe detectar que le falta y
decirlo en el menú, no fallar en silencio.

**Pantalla completa.** Con una app en pantalla completa la barra se oculta hasta
que llevas el puntero al borde. El "de un vistazo" no aplica ahí, y conviene
saberlo en vez de descubrirlo.

## Procesos: lo que la v1 afirmaba sin diseñar

La v1 decía "el hijo se mata al salir, incluido el cierre inesperado". Era falso
por tres motivos verificados en el código:

1. **`uvicorn` corre con `reload=True`** (`disk_analyzer_web.py:1458`), lo que
   lanza un supervisor y un worker. Matar "al hijo" mata al supervisor y deja al
   worker con el puerto ocupado. *(Afecta a la rebanada C; se anota aquí para que
   no se pierda: el sidecar debe invocarse con `reload=False`, y eso es un segundo
   cambio necesario en el backend además de `--host`.)*
2. **Los shells del PTY llaman a `os.setsid()`** (`pty_manager.py:83`), poniéndose
   deliberadamente fuera del grupo de procesos. Ningún `killpg` sobre el servidor
   los alcanza. *(También rebanada C.)*
3. **Ante `SIGKILL` no corre ningún manejador.** "Cierre inesperado" no se resuelve
   con código en la app: requiere grupos de procesos, o que el hijo se autotermine
   al detectar que su padre murió (EOF en stdin sirve).

En la rebanada A el problema se reduce mucho, porque el único hijo es el CLI del
análisis y no engendra nietos. Aun así:

- Se lanza en su propio grupo de procesos y se mata el grupo, escalando de
  `SIGTERM` a `SIGKILL` con un plazo — el mismo patrón que `pty_manager.py` ya
  tiene probado en `KILL_REAP_TIMEOUT`.
- **Un análisis a la vez.** El segundo clic no lanza otro proceso; el menú indica
  que ya hay uno en marcha.
- Si la app sale a mitad de un análisis, el hijo muere con ella y el archivo de
  exportación a medias se descarta (escritura a temporal y renombrado atómico).

## Manejo de errores

La regla: **el icono nunca muere.**

| Fallo | Comportamiento |
|---|---|
| La lectura de disco falla | Icono en estado desconocido y `—`, nunca un número viejo que mentiría |
| El análisis falla o expira | Se refleja en el menú; el pulso sigue |
| Falta acceso a disco completo | El menú lo dice y explica cómo concederlo |
| El sidecar no existe para esta plataforma | El menú lo dice; la app sigue mostrando el pulso |

## Pruebas

- **Rust:** lógica sin dependencias del sistema — el mapeo de estado a icono, los
  umbrales combinados de porcentaje y GB, el formateo.
- **Consistencia:** un test que compara la lectura de `sysinfo` con la del motor
  Python y falla si divergen más de un margen pequeño.
- **CI:** `cargo test` y `cargo clippy` en el workflow existente. Este proyecto
  tiene 151 tests de backend y 69 de frontend, ambos en CI; un lenguaje nuevo no
  entra sin la misma disciplina.
- **Manual, lo que solo se ve mirando:** icono legible en tema claro y oscuro, con
  "Reducir transparencia", y sobre fondos claros y oscuros; que el estado cambie al
  liberar espacio; que no aparezca en el Dock ni en Cmd+Tab; que al salir no quede
  ningún proceso vivo.

## Fuera de alcance

- **Linux y Windows.** Documentados arriba con sus obstáculos concretos.
- **Vigilancia de carpetas.** Rebanada B.
- **El panel como ventana Tauri**, y con él el ciclo de vida del servidor, el CORS
  y la decisión sobre exponer la terminal. Rebanada C.
- **Reescribir la interfaz web.**

Cuando llegue la rebanada C hay una decisión pendiente que conviene no olvidar:
**si el servidor que lanza la app debe llevar la terminal desactivada.** Un clic
que expone un shell interactivo es muy distinto de escribir `make web` a
conciencia, y `CLAUDE.md` ya advierte de que ese terminal con `sudo` da acceso
root.

## Qué cambió y por qué

Cinco revisiones adversariales sobre la v1. Lo que encontraron:

| Hallazgo | Efecto en el diseño |
|---|---|
| GNOME no tiene bandeja; Linux no acepta píxeles en memoria | Alcance reducido a macOS, con los obstáculos documentados |
| El servidor no importa en Windows por el PTY | Idem, y desmiente el "motor sin cambios" de la v1 |
| PyInstaller no compila cruzado | El empaquetado deja de ser aplazable |
| El panel arrastra los problemas más difíciles | Se mueve a la última rebanada |
| `reload=True` y `os.setsid()` rompen la promesa de "sin huérfanos" | Anotado para la rebanada C; grupos de procesos en la A |
| Umbrales por porcentaje mal en discos grandes y pequeños | Umbrales combinados con espacio absoluto |
| Dos contabilidades de disco distintas divergirán | Test de consistencia contra el motor |
| El icono en color pierde más de lo dicho | Contrapartida completa y verificación explícita |
| `LSUIElement`, acceso a disco completo y pantalla completa sin considerar | Secciones propias |
| El rasterizador es sobreingeniería | Imágenes pre-generadas |
| Autoarranque no pedido y poco fiable sin firma | Fuera de la rebanada A |
| Sin permisos de Tauri declarados | Sección propia |
| Sin CI para Rust | Añadido |
| La rebanada A no entrega "tiempo real" | Dicho explícitamente en vez de implícito |

Una crítica se descartó: un reviewer señaló colisión con la rama de la Fase 4 sin
mergear. Ya está mergeada (PR #9).

Las afirmaciones sobre la API de Tauri **sí resistieron**: el icono desde RGBA, el
reparto de `setTitle` por plataforma, la API de bandeja en JavaScript, los
sidecars con streaming y el plugin de autoarranque se verificaron todos correctos
contra la documentación. El diseño no se equivocaba sobre Tauri; se equivocaba en
todo lo que lo rodea.
