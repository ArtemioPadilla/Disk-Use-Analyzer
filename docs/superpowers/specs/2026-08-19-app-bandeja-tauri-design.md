# Diseño — App de bandeja con Tauri (subsistema 1)

## Qué construimos

Una app de escritorio anclada en la barra de menú de macOS (y en la bandeja de
Windows y Linux) que muestra el llenado del disco de un vistazo y da acceso
inmediato al analizador que ya existe.

Este documento cubre **solo el primer subsistema de tres**. El objetivo completo
que planteó el usuario —app nativa, analítica en tiempo real, distribuible en
tres plataformas— son tres proyectos independientes:

| # | Subsistema | Estado |
|---|---|---|
| 1 | App de bandeja con pulso de disco en vivo | **este documento** |
| 2 | Vigilancia de carpetas en tiempo real (FSEvents / inotify / ReadDirectoryChangesW) | pendiente de diseñar |
| 3 | Empaquetado y distribución firmada en tres plataformas | pendiente de diseñar |

Se hacen en ese orden porque el primero ya entrega una app usable, y mezclarlos
multiplicaría el tamaño sin adelantar la fecha en que tienes algo anclado y
funcionando.

## Por qué Tauri

Se descartó SwiftUI (`MenuBarExtra`), que sería la mejor opción **solo** para
macOS, porque el requisito incluye Linux y Windows. Entre las alternativas
multiplataforma:

- **Tauri** reutiliza la interfaz Astro que ya está construida y probada,
  produce `.app`, `.msi`, `.deb` y `.AppImage` desde el mismo código, y genera
  binarios de unos 10 MB porque usa el webview del sistema en lugar de empaquetar
  un navegador. Su documentación de firma y notarización es sólida, lo que
  importa porque uno de los objetivos declarados es aprender ese pipeline.
- **PySide6 / Qt** mantendría todo en Python y evitaría el IPC, pero obligaría a
  rehacer la interfaz en widgets y produce bundles de 100-150 MB, algo que se
  nota en una app residente permanente.

El coste asumido de Tauri es Rust como tercer lenguaje del repositorio. Se
mitiga manteniendo el caparazón deliberadamente pequeño: la API de bandeja de
Tauri 2 está expuesta también a JavaScript, así que la lógica de presentación
puede vivir en TypeScript y el Rust queda reducido a lo que necesita acceso al
sistema.

## Arquitectura

Tres piezas con responsabilidades separadas y una regla que las ordena: **cada
capa cuesta lo que vale**.

### El caparazón Rust (`desktop/src-tauri/`)

Hace únicamente lo barato y siempre encendido:

- Sondea el espacio de disco con la crate `sysinfo`. Es una llamada al sistema
  de microsegundos, así que puede refrescarse cada pocos segundos indefinidamente
  sin coste apreciable.
- Redibuja el icono de la bandeja cuando el porcentaje cambia lo suficiente para
  verse.
- Gestiona el ciclo de vida del proceso Python.

**No mantiene Python residente.** Ese es el punto de la separación: una app
anclada permanentemente no puede arrastrar un intérprete encendido a todas horas.

### El motor Python (sin cambios)

Se invoca como *sidecar* solo cuando hay trabajo real. Tauri lo declara en
`externalBin` y lo lanza mediante el plugin `shell`, que permite leer su stdout
en streaming. Dos usos:

- **Escaneo bajo demanda:** el CLI ya sabe exportar JSON con `--export`.
- **Servidor del panel:** `disk_analyzer_web.py`, arrancado solo al abrir el
  panel completo.

### La interfaz Astro (sin cambios)

Se reutiliza tal cual como contenido de la ventana de detalle. Los 69 tests de
frontend y 151 de backend siguen aplicando sin tocarse.

## El icono como indicador

El icono **es** el dato, no un adorno junto al dato. Se genera en tiempo de
ejecución como píxeles RGBA y se pasa a la bandeja como imagen construida en
memoria.

Forma: un rectángulo redondeado con el contorno siempre visible y relleno
proporcional al uso del disco. El contorno importa porque garantiza que la pieza
se distinga sobre cualquier fondo de barra.

Escala de color, pensada para lo que de verdad importa en un analizador de disco:

| Uso | Color |
|---|---|
| < 70 % | verde |
| 70-85 % | ámbar |
| > 85 % | rojo |

El rojo debe significar "esto ya es un problema". Si aparece demasiado pronto,
dejas de mirarlo.

**Contrapartida asumida:** macOS prefiere iconos de barra en modo *template*
—monocromos, que se adaptan solos a barra clara u oscura—. Un indicador en color
renuncia a eso, así que el contraste en ambos temas es responsabilidad nuestra y
hay que verificarlo explícitamente. Se acepta el compromiso porque el color es
precisamente lo que permite leer un disco al 92 % de un vistazo.

**Diferencia por plataforma:** en macOS y Linux se añade el porcentaje como texto
junto al icono (`setTitle`). En Windows esa API no existe, así que el icono y el
tooltip son toda la información. Por eso el icono carga con el significado en vez
de delegarlo en el texto.

## El menú

Al desplegar:

- Uso de disco actual (usado / total y porcentaje)
- Resumen del último análisis: espacio recuperable y mayores consumidores
- **Analizar ahora** — lanza el CLI como sidecar y actualiza el menú al terminar
- **Abrir panel** — abre la ventana Tauri con la interfaz completa
- **Arrancar al iniciar sesión** — conmutador, vía el plugin `autostart`
- **Salir**

## Ciclo de vida del servidor

Es la parte con más aristas, así que se especifica en detalle.

El servidor arranca **de forma perezosa**, solo al abrir el panel por primera
vez. Una app residente no debe tener un servidor encendido sin que nadie lo mire.
El precio es un arranque de dos o tres segundos la primera vez, que se cubre con
un indicador de carga en la ventana.

Reglas:

1. **Puerto dinámico.** Se pide al sistema un puerto libre en lugar de asumir el
   8000, que puede estar ocupado por otra cosa (o por un `make web` del propio
   usuario).
2. **Solo localhost.** Se enlaza a `127.0.0.1`, no a `0.0.0.0`. Una app de
   escritorio no tiene por qué exponer nada a la red local.
3. **Con autenticación.** Se genera un token y se pasa por la variable de entorno
   `DISK_ANALYZER_TOKEN`, que es exactamente el mecanismo que ya existe. **No** se
   usa `--no-auth`: aunque escuche solo en localhost, cualquier proceso de la
   máquina podría hablarle.
4. **Sin procesos huérfanos.** El hijo se mata al salir la app, incluido el
   camino de cierre inesperado. Un servidor Python huérfano tras cerrar la app
   sería un fallo real y visible.

### Dependencia en el backend

`disk_analyzer_web.py` hoy fija `host="0.0.0.0"` en código y no acepta un
argumento para cambiarlo. Este subsistema necesita añadir un flag `--host` (con
el valor actual por defecto, para no alterar el comportamiento de `make web`).
Es un cambio pequeño pero es una dependencia real y se implementa como parte de
este trabajo.

## Manejo de errores

La regla que ordena esta sección: **el icono nunca muere**. Es lo que separa una
app que la gente ancla de una que desinstala.

| Fallo | Comportamiento |
|---|---|
| El servidor no arranca | El menú lo indica; el pulso de disco sigue funcionando |
| El escaneo falla o se cuelga | Se refleja en el menú; no bloquea la app |
| La lectura de disco falla | El icono muestra estado desconocido y el texto `—`, nunca un número antiguo que mentiría |
| El puerto elegido queda ocupado | Se reintenta con otro |

Ningún fallo de una capa puede tumbar la de arriba.

## Pruebas

- **Rust:** tests unitarios de la lógica sin dependencias del sistema — el mapeo
  de porcentaje a color, el umbral de redibujado, el formateo de tamaños.
- **Existentes:** los 69 de frontend y 151 de backend siguen pasando sin cambios.
  El flag `--host` nuevo lleva su propio test.
- **Manual, lo que solo se ve mirando:** que el icono aparezca en la barra; que
  el relleno se mueva al cambiar el espacio libre; que se lea en tema claro y
  oscuro; que el panel abra y muestre datos; que al salir no quede ningún proceso
  Python vivo.

## Fuera de alcance

Explícitamente no entra aquí, para que nadie lo dé por supuesto:

- **Firma, notarización e instaladores.** Subsistema 3. En desarrollo se apunta
  al `venv` existente y no se empaqueta Python todavía.
- **Vigilancia de carpetas en tiempo real.** Subsistema 2. El "tiempo real" de
  este subsistema es el pulso del disco, no la detección de cambios.
- **Reescribir la interfaz web.** Se reutiliza como está.
