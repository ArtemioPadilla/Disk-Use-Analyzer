# Diseño — App de bandeja con Tauri

> **Revisión 3.** La v1 pasó por cinco revisiones adversariales y no sobrevivió
> intacta. La v2 corrigió el alcance. Esta v3 añade lo que faltaba de método:
> decisiones humanas que bloquean, mediciones reales en vez de adjetivos,
> etiquetado de lo que no está verificado, y un runbook con marcha atrás. El
> historial de cambios está al final.

---

## Decisiones bloqueantes (humanas, no delegables a un agente)

**Ninguna otra tarea empieza hasta que estas estén cerradas.** Son caras o
imposibles de revertir una vez que hay código encima, y ninguna debe decidirla un
subagente por su cuenta.

### D1 — El identificador del bundle

Propuesto: `dev.diskanalyzer.app`.

En macOS el identificador es la identidad del bundle a la que el sistema ata los
permisos concedidos (acceso a disco completo, entre otros). Cambiarlo después
significa que el usuario vuelve a conceder permisos y que las preferencias
guardadas quedan huérfanas. Requiere tu visto bueno explícito antes de escribirlo
en `tauri.conf.json`.

### D2 — Si el análisis de `/` entra en la versión 1

Analizar el disco completo exige **acceso a disco completo**, un permiso que el
usuario concede a mano en Ajustes del Sistema y que macOS ata a la identidad
firmada. Sin firma se pierde en cada recompilación.

- **Opción A — solo el directorio personal en la v1.** No requiere el permiso.
  La app funciona desde el primer arranque sin fricción. Es lo que recomiendo.
- **Opción B — disco completo desde el día uno.** Obliga a resolver firma y
  concesión de permisos antes de tener nada usable, y a diseñar cómo se le pide
  al usuario.

La elección determina si la firma es un requisito de la primera rebanada o puede
ir después.

### D3 — Qué hace "Analizar ahora" dado lo que cuesta de verdad

Medido en esta máquina (ver "Lo medido"): un análisis tarda **entre 25 y 60
segundos**, no los "~20" que afirmaba la v1. Un menú que se queda un minuto
pensando es un problema de diseño, no un detalle.

- **Opción A — con progreso y cancelable.** El menú muestra avance y permite
  abortar. Más trabajo, comportamiento honesto.
- **Opción B — abrir el analizador web y que el análisis ocurra allí**, donde ya
  existe barra de progreso por WebSocket. Menos código nuevo, pero rompe la
  premisa de "todo desde la barra".

---

## Lo medido

La v1 no medía nada; decía "barato" y "~20 segundos". Estas cifras son de esta
máquina, tomadas al escribir la v3. **Vuelve a medirlas si el hardware cambia.**

| Qué | Medido | Implicación |
|---|---|---|
| Leer el espacio de disco (`statvfs`) | **0,7 µs** por llamada (~1,4 M/s) | El pulso del icono es efectivamente gratis. Refrescar cada pocos segundos no necesita justificación |
| Análisis de `~/Downloads` (1.855 archivos) | **61 s** | Un análisis no es una acción de menú instantánea |
| Análisis del repositorio (399 archivos) | **25 s** | El coste no escala con el número de archivos: lo dominan el hashing de duplicados y el sondeo de cachés |

### La divergencia que obliga al test de consistencia

Esto es lo más importante que salió de medir. Sobre el mismo disco, ahora mismo:

| Fuente | Usado | Porcentaje | Libre |
|---|---|---|---|
| El motor (`total - available`) | 444,84 GB de 460,43 | **96,6 %** | 15,59 GB |
| La columna `used` de `df` | 11,71 GB | **43 %** | 15,59 GB |

No es un matiz: es la diferencia entre "va bien" y "crítico". Ocurre porque en
APFS `/` es el volumen de sistema de solo lectura, así que `df` cuenta solo ese
volumen mientras el espacio libre corresponde al contenedor compartido.

**Si `sysinfo` en Rust reporta como `df`, la bandeja dirá 43 % mientras el
informe dice 96,6 %.** El test de consistencia entre ambas lecturas deja de ser
una buena práctica y pasa a ser un requisito: sin él, el número que justifica la
app entera puede estar mal por 53 puntos.

De paso, la cifra real de esta máquina (15,59 GB libres) confirma por qué los
umbrales necesitan espacio absoluto y no solo proporción.

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


## Qué está verificado y qué no

La v1 presentaba con la misma confianza lo comprobado y lo supuesto. Esta tabla
separa las tres cosas. **Lo no verificado lleva plan B**, para que descubrirlo
falso no bloquee.

| Afirmación | Estado | Si resulta falsa |
|---|---|---|
| Tauri acepta un icono construido desde píxeles RGBA en memoria | Verificado contra `docs.rs` en la revisión adversarial | Irrelevante: la v2 ya pasó a imágenes pre-generadas |
| `setTitle` funciona en macOS, no en Windows | Verificado contra `docs.rs` | El texto ya es opcional y apagado por defecto |
| La API de bandeja está expuesta a JavaScript | Verificado | Se escribe en Rust; más código, mismo resultado |
| Sidecars vía `externalBin` + plugin `shell` con streaming | Verificado | — |
| El plugin `autostart` cubre macOS | Verificado | Ya está fuera de la rebanada A |
| `ActivationPolicy::Accessory` evita el icono del Dock | **De la revisión, no probado por mí** | Alternativa: `LSUIElement` en el `Info.plist` del bundle |
| macOS 26 aplica su ajuste de estilo de iconos y el nuestro quedaría fuera | **No verificado** — no tengo esa versión a mano | Es cosmético; se comprueba al probar en esa versión |
| `sysinfo` coincide con el motor Python | **Refutado como riesgo real** (ver "Lo medido") | El test de consistencia es obligatorio, no opcional |
| Un análisis tarda "~20 s" | **Refutado por medición**: 25-60 s | Motivó la decisión D3 |

## Runbook y marcha atrás

Un entregable, no una nota. Va en `docs/runbooks/app-bandeja.md`.

### Instalar y desinstalar

Desinstalar no es solo borrar la `.app`: quedan el elemento de inicio de sesión si
se activó, las preferencias en `~/Library/Preferences/<identificador>.plist`, y la
concesión de acceso a disco completo. El runbook lista los tres y cómo quitarlos.

### Revocar el acceso a disco completo

Ajustes del Sistema → Privacidad y seguridad → Acceso a disco completo → quitar la
entrada. **Importante:** macOS ata la concesión a la identidad firmada, así que
tras recompilar con otra firma la entrada vieja queda huérfana y hay que
eliminarla a mano antes de volver a conceder; si no, el sistema muestra la app
como autorizada mientras el binario nuevo no lo está.

### Si la notarización rechaza el bundle

Apple devuelve un identificador de envío. `xcrun notarytool log <id>` da el motivo
real; el mensaje de rechazo por sí solo no basta. Los rechazos habituales de una
app que empaqueta un binario de Python son: falta de *hardened runtime*, binarios
anidados sin firmar (el intérprete y sus extensiones `.so` se firman por
separado), y falta de marca de tiempo segura. **Lee el log antes de reintentar**;
reenviar sin cambios devuelve el mismo rechazo.

### Secretos

El certificado de firma vive en el llavero, **nunca en el repositorio**. Si el
empaquetado pasa por CI, el certificado exportado y su contraseña van como
secretos del repositorio, y el `.gitignore` cubre `*.p12` y `*.cer` como defensa
en profundidad por si alguien deja una copia suelta.

### Volver atrás

- **Una versión mala ya instalada:** no hay actualizador en la rebanada A, así que
  volver atrás es reinstalar la anterior. Conserva la `.app` previa hasta validar
  la nueva.
- **La app no arranca tras firmar:** `spctl -a -vvv <ruta>.app` dice si Gatekeeper
  la rechaza y por qué.
- **Rendirse limpiamente:** desinstalar según arriba deja la máquina como estaba.
  El CLI y la interfaz web siguen funcionando: la app de bandeja no sustituye
  nada, solo añade.

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

### Cambios de la revisión 3

Provocados por comparar este documento con un plan de Tauri/Android de un
proyecto hermano, que resultó más maduro en método:

| Qué faltaba | Añadido |
|---|---|
| Las decisiones abiertas estaban en prosa, sin puerta | Sección de decisiones bloqueantes al principio, marcadas como no delegables |
| Cero mediciones; "barato" y "~20 s" eran adjetivos | Sección "Lo medido" con cifras reales — y una de ellas refutó el diseño |
| Lo verificado y lo supuesto se presentaban igual | Tabla de estado de cada afirmación, con plan B para lo no verificado |
| Sin runbook ni marcha atrás | Runbook con desinstalación, revocación de permisos, lectura del log de notarización y vuelta atrás |

La medición que más cambió el diseño: el motor y `df` difieren en **53 puntos
porcentuales** sobre el mismo disco. El test de consistencia pasó de buena
práctica a requisito.
