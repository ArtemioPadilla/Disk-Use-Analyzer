# E7 · Exhaustividad: plan de implementación

Épica: [#47](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/47). Última actualización: 3 de noviembre de 2026.

**Objetivo:** recuperar más espacio sin perder nada irrecuperable, y que todo el disco
tenga explicación.

**Cómo usar este plan:** cada historia es un issue y un PR. Al abrir el PR, escribe su
número en la línea **PR**; al mergearlo, marca la historia y sus tareas. El PR lleva
`Closes #N`.

## Por qué

Hoy la app solo ofrece cachés. Lo que más ocupa en un disco de desarrollo suele estar en
otro lado, y la app apenas lo muestra:

| Grupo | Dónde está hoy en la app |
|---|---|
| Artefactos de proyectos (`node_modules`, entornos, compilados) | Solo `node_modules` huérfanos, en el CLI |
| `~/.cache` | Se cuenta en Cachés, no se ofrece |
| Worktrees de git | En ningún lado |
| Docker | Dos totales, solo con el daemon encendido |
| Apps y sus datos | En ningún lado |
| Lo que no se puede medir sin permisos | Dentro de «Sistema y otros» |

## Reglas para todo el plan

- La verja `analyzer/protection.py::puede_borrarse` sigue siendo la única puerta. La app
  nunca construye un comando de borrado.
- El nombre de una carpeta no basta para borrarla: hace falta evidencia al lado. Es una
  decisión de producto tomada en E7.3 que amplía el segundo eje de la verja.
- Todo lo que borra pide confirmación nativa, nombra lo que se va y mide lo liberado.
- Solo Cachés tiene «limpiar todo». Lo que hay que volver a descargar nunca entra ahí.
- Lo que es del usuario se elige uno por uno y va a la papelera.
- Repo público: nada medido en una máquina concreta en issues, PR, commits ni documentos.
- Esperar a CI antes de mergear. Decir qué se probó de verdad y qué no.

## Orden

1. [ ] [E7.12](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/35) (#35): CI con versiones fijas
2. [ ] [E7.1](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/36) (#36): El motor promete borrar de npm lo que su comando no borra
3. [ ] [E7.2](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/37) (#37): Desglosar ~/.cache por herramienta
4. [ ] [E7.3](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/38) (#38): Motor: inventario de artefactos de proyectos (node_modules, .venv, target, .next)
5. [ ] [E7.4](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/39) (#39): Menú: sección Proyectos
6. [ ] [E7.5](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/40) (#40): Inventario y limpieza de worktrees de git
7. [ ] [E7.6](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/41) (#41): Inventario de ambientes: conda, Python, Node y venvs
8. [ ] [E7.7](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/42) (#42): Desglosar «Sistema y otros» y decir qué no se pudo medir
9. [ ] [E7.8](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/43) (#43): Docker a fondo: imágenes y volúmenes por nombre
10. [ ] [E7.9](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/44) (#44): Apps pesadas y lo que dejan en Library
11. [ ] [E7.10](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/45) (#45): Archivos grandes en el menú, agrupados
12. [ ] [E7.11](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/46) (#46): Limpiezas que piden permiso de administrador

E7.12 va primero porque cada PR siguiente depende de un CI estable. E7.1 y E7.2 son los
más baratos; E7.3 a E7.5 son los que más espacio recuperan.

## E7.12: CI con versiones fijas

- [ ] **Issue:** [#35](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/35)
- **PR:** [#48](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/pull/48)

CI usa `rust-toolchain@stable` y `requirements-web.txt` sin tope. Rust 1.99 y Starlette 1.x ya pusieron `main` en rojo sin cambios de código, y local y CI prueban versiones distintas.

**Archivos:** `rust-toolchain.toml (nuevo)`, `.github/workflows/ci.yml`, `requirements-web.lock (nuevo)`

**Tareas**

- [x] Fijar Rust y actualizar el toolchain local
- [x] Fijar Python, resolviendo avisos de obsolescencia
- [x] Documentar cómo subir versiones

**Hecho cuando**

- [x] Local y CI usan las mismas versiones.
- [x] Una versión nueva de una dependencia no rompe `main` por sí sola.

**Seguridad**

- El paquete de la app usa las mismas versiones que se prueban.

## E7.1: El motor promete borrar de npm lo que su comando no borra

- [ ] **Issue:** [#36](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/36)
- **PR:** [#49](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/pull/49)

La regla `npm` mide todo `~/.npm`, pero `npm cache clean --force` solo vacía `_cacache`. `~/.npm/_npx` no se toca: el menú vuelve a ofrecerlo para siempre, y parece que la limpieza falló.

**Archivos:** `disk_analyzer_core.py`, `analyzer/constants.py`, `analyzer/protection.py`, `tests/test_limpieza_rapida.py`, `tests/test_puede_borrarse.py`

**Tareas**

- [x] Prueba que falla: con `_cacache` y `_npx` falsos, `npm` solo mide `_cacache`
- [x] Separar la medición de `npm` y crear la regla `npx`
- [x] Ampliar la verja a `~/.npm/_npx` con su prueba
- [x] Probar en la máquina real: limpiar y confirmar que no se vuelve a ofrecer

**Hecho cuando**

- [x] Tras limpiar `npm`, la regla deja de ofrecer espacio que no puede liberar.
- [x] `_npx` aparece aparte, con su tamaño, y se puede limpiar.
- [x] Lo liberado medido coincide con lo estimado salvo ruido de APFS.

**Seguridad**

- Una prueba fija que ninguna regla mida una carpeta más amplia que la que vacía su comando, para `npm` y `npx`.

## E7.2: Desglosar ~/.cache por herramienta

- [ ] **Issue:** [#37](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/37)
- **PR:** [#50](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/pull/50)
- **Depende de:** E7.1 (#36)

`~/.cache` cuenta en la fila Cachés del menú, pero la regla `cache_general` es `solo_lista`, así que no se ofrece nada. Puede ser la mayor parte de lo que muestra esa fila.

**Archivos:** `disk_analyzer_core.py`, `analyzer/constants.py`, `analyzer/cache_types.py`, `analyzer/protection.py`, `desktop/src-tauri/src/liberar.rs`, `tests/test_limpieza_rapida.py`

**Tareas**

- [x] Pruebas de cada regla con carpetas falsas
- [x] Reglas y rutas permitidas
- [x] `Limpiar todas` excluye `redescarga`
- [x] Revisar en el menú real

**Hecho cuando**

- [x] El submenú Cachés lista cada herramienta con su tamaño.
- [x] Lo que hay que volver a descargar va bajo su encabezado y no entra en «Limpiar todas» ni en «Liberar lo seguro».
- [x] La suma de la fila Cachés y lo ofrecido se pueden explicar: lo no ofrecido se nombra.

**Seguridad**

- Una caché de modelos nunca se ofrece como `regenera`: bajarla de nuevo cuesta tiempo y datos.
- La herramienta ausente no rompe la medición.

## E7.3: Motor: inventario de artefactos de proyectos (node_modules, .venv, target, .next)

- [ ] **Issue:** [#38](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/38)
- **PR:** [#51](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/pull/51)

Lo regenerable más grande no son las cachés sino los artefactos de cada proyecto: `node_modules`, entornos virtuales y compilados. El motor solo detecta `node_modules` huérfanos, en el CLI y durante un escaneo completo.

**Archivos:** `analyzer/proyectos.py (nuevo)`, `analyzer/protection.py`, `disk_analyzer.py`, `tests/test_proyectos.py`, `tests/test_puede_borrarse.py`

**Tareas**

- [x] Decidir raíces por defecto y umbral de antigüedad
- [x] Pruebas de la verja: cada artefacto con y sin evidencia, incluidos nombres engañosos
- [x] Detector con carpetas falsas
- [x] Modo `--proyectos` y prueba de punta a punta
- [x] Medir el tiempo en la máquina real

**Hecho cuando**

- [x] `--proyectos` devuelve el inventario sin duplicar los artefactos dentro de worktrees.
- [x] Cada artefacto lleva un comando generado por `analyzer/comandos.py`.
- [x] No hay artefacto que pase la verja sin su evidencia.

**Seguridad**

- **Decisión de producto:** el nombre no basta. `target` solo con `Cargo.toml` al lado, `.next` con `package.json`, `.venv`/`venv` con `pyvenv.cfg` dentro.
- Una carpeta llamada `target` o `dist` con datos del usuario no se ofrece nunca. `dist` y `build` quedan fuera.
- No seguir symlinks. No entrar en `node_modules`.
- Un `.venv` sin archivo de dependencias en el proyecto se marca como no reproducible y no se preselecciona.

## E7.4: Menú: sección Proyectos

- [ ] **Issue:** [#39](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/39)
- **PR:** pendiente
- **Depende de:** E7.3 (#38)

El inventario de E7.3 no sirve si solo se ve en JSON. Hace falta una fila en el menú con lo que se puede recuperar por proyecto.

**Archivos:** `desktop/src-tauri/src/liberar.rs`, `desktop/src-tauri/src/lib.rs`, `web/src/components/`, `docs/runbooks/app-bandeja.md`

**Tareas**

- [ ] Pruebas de filas y de la selección por antigüedad
- [ ] Medir en segundo plano sin bloquear el menú
- [ ] Fila y submenú
- [ ] Revisar en pantalla con datos reales

**Hecho cuando**

- [ ] Se ve cuánto ocupa cada proyecto y desde cuándo no se toca.
- [ ] La confirmación nombra cada proyecto y avisa que hay que reinstalar.
- [ ] Lo liberado se mide, igual que el resto de limpiezas, con progreso.

**Seguridad**

- La app no construye comandos: todos vienen del motor.
- Un proyecto con actividad reciente no entra en la acción por antigüedad.

## E7.5: Inventario y limpieza de worktrees de git

- [ ] **Issue:** [#40](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/40)
- **PR:** pendiente
- **Depende de:** E7.3 (#38)

Los worktrees se acumulan sin que se note: muchos los crean herramientas automáticas, y algunos pueden quedar rotos.

**Archivos:** `analyzer/worktrees.py (nuevo)`, `disk_analyzer.py`, `desktop/src-tauri/src/liberar.rs`, `tests/test_worktrees.py`

**Tareas**

- [ ] Pruebas con repos git temporales: limpio, sucio, sin mergear, squash, roto
- [ ] Inventario
- [ ] Comando de limpieza con revalidación
- [ ] Menú y confirmación
- [ ] Revisar en repos reales sin quitar nada, y luego uno

**Hecho cuando**

- [ ] Se ve qué worktrees existen en cada repo y su estado.
- [ ] Solo se ofrece quitar los que no pierden nada, y se explica por qué los demás no.
- [ ] Los worktrees rotos se pueden limpiar.

**Seguridad**

- Nunca `--force`, nunca borrar ramas, nunca `rm -rf` de un worktree.
- Se comprueba el estado justo antes de quitar: pudo cambiar desde la medición.
- Comprobar «mergeada» contra la rama por defecto, incluso con squash: si no se puede saber, se trata como no mergeada.
- El worktree desde el que corre una sesión activa no se ofrece.

## E7.6: Inventario de ambientes: conda, Python, Node y venvs

- [ ] **Issue:** [#41](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/41)
- **PR:** pendiente
- **Depende de:** E7.3 (#38)

Coexisten varias instalaciones de Python y Node, y entornos que nadie usa. La app no los muestra. El CLI detecta entornos conda obsoletos, pero solo en algunas rutas y no llega al menú.

**Archivos:** `analyzer/ambientes.py (nuevo)`, `disk_analyzer.py`, `desktop/src-tauri/src/liberar.rs`, `tests/test_ambientes.py`

**Tareas**

- [ ] Pruebas de detección con árboles falsos
- [ ] Inventario
- [ ] Limpiezas con comando propio
- [ ] Menú
- [ ] Probar con las instalaciones reales sin borrar

**Hecho cuando**

- [ ] Una vista dice qué ambientes hay, de dónde vienen y cuánto ocupan.
- [ ] Se ofrece limpiar solo lo regenerable, como `conda clean`.
- [ ] Quitar un entorno pide confirmación y lo nombra.

**Seguridad**

- Nunca se ofrece desinstalar el Python o Node que usan otras fórmulas de Homebrew; solo se informa.
- Nunca tocar el Python del sistema.

## E7.7: Desglosar «Sistema y otros» y decir qué no se pudo medir

- [ ] **Issue:** [#42](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/42)
- **PR:** pendiente

«Sistema y otros» es lo que sobra, sin explicación. Además hay una parte que un escaneo sin permisos no ve, como la biblioteca de Fotos, Mail y Mensajes.

**Archivos:** `desktop/src-tauri/src/categorias.rs`, `desktop/src-tauri/src/anillo.rs`, `desktop/src-tauri/src/liberar.rs`, `analyzer/measurement.py`

**Tareas**

- [ ] Pruebas del reparto y de que la suma cuadra
- [ ] Medir volúmenes APFS
- [ ] Medir carpetas protegidas solo con permiso
- [ ] Submenú
- [ ] Confirmar qué hay en el hueco en la máquina real

**Hecho cuando**

- [ ] El submenú suma lo mismo que la fila, y «sin medir» es una cifra explícita.
- [ ] Sin Acceso total, dice qué falta y cómo darlo.
- [ ] Las cifras cuadran con el contenedor APFS con un margen documentado.

**Seguridad**

- Solo lectura: nada de esto se ofrece borrar.
- Nunca pedir permisos de macOS carpeta por carpeta: se comprueba el acceso antes de leer.

## E7.8: Docker a fondo: imágenes y volúmenes por nombre

- [ ] **Issue:** [#43](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/43)
- **PR:** pendiente

Con el daemon apagado la app no sabe qué hay en `Docker.raw`, y con él encendido solo da dos totales. Tampoco se ha probado ninguna limpieza contra un Docker real.

**Archivos:** `disk_analyzer_core.py`, `desktop/src-tauri/src/liberar.rs`, `tests/test_limpieza_rapida.py`, `docs/runbooks/app-bandeja.md`

**Tareas**

- [ ] Pruebas con el `docker` falso
- [ ] Inventario por nombre
- [ ] Encender desde el menú
- [ ] Probar de verdad y medir `Docker.raw`

**Hecho cuando**

- [ ] Se ve qué ocupa Docker por nombre.
- [ ] Las limpiezas de E4 están probadas contra un daemon real.
- [ ] El aviso final sobre el espacio refleja lo que realmente pasa.

**Seguridad**

- Ningún comando del menú toca volúmenes.
- Encender Docker requiere un clic explícito: nunca automático.

## E7.9: Apps pesadas y lo que dejan en Library

- [ ] **Issue:** [#44](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/44)
- **PR:** pendiente
- **Depende de:** E7.7 (#42)

Las apps pueden ocupar mucho, y algunas guardan muchos datos en `~/Library/Containers` que no se ven desde ningún lado.

**Archivos:** `analyzer/apps.py (nuevo)`, `disk_analyzer.py`, `desktop/src-tauri/src/liberar.rs`, `tests/test_apps.py`

**Tareas**

- [ ] Investigar la fuente de último uso
- [ ] Pruebas de asociación con bundles falsos
- [ ] Inventario
- [ ] Menú

**Hecho cuando**

- [ ] Se ve el tamaño real de cada app con sus datos.
- [ ] La fecha de último uso se muestra solo si es fiable.
- [ ] Nada se desinstala ni se borra desde la app.

**Seguridad**

- Solo informa. Los datos de una app pueden ser irrecuperables.
- Asociar datos a una app por identificador de bundle, nunca por parecido del nombre.

## E7.10: Archivos grandes en el menú, agrupados

- [ ] **Issue:** [#45](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/45)
- **PR:** pendiente
- **Depende de:** E7.3 (#38)

El motor detecta archivos grandes y descargas antiguas, pero el menú solo enlaza al analizador, que necesita un análisis previo cargado en la web. Los análisis del menú no pasan por el servidor web.

**Archivos:** `disk_analyzer_web.py`, `web/src/components/FileTable.tsx`, `desktop/src-tauri/src/liberar.rs`, `tests/`

**Tareas**

- [ ] Importar análisis del menú a las sesiones web
- [ ] Clasificación por grupos con pruebas
- [ ] Menú y enlaces con filtro
- [ ] Probar el recorrido completo

**Hecho cuando**

- [ ] El menú dice cuánto ocupa cada grupo.
- [ ] Desde ahí se llega a la lista y se elige uno por uno.
- [ ] Un análisis del menú se ve en el analizador.

**Seguridad**

- Son datos del usuario: nunca «borrar todo». Solo papelera, vía `/api/files/delete`.
- Sin borrado permanente desde el menú.

## E7.11: Limpiezas que piden permiso de administrador

- [ ] **Issue:** [#46](https://github.com/ArtemioPadilla/Disk-Use-Analyzer/issues/46)
- **PR:** pendiente
- **Depende de:** E7.2 (#37)

Hay cachés fuera del alcance del usuario, como `/Library/Developer/CoreSimulator/Caches`. La app ni las mide ni las ofrece.

**Archivos:** `disk_analyzer_core.py`, `analyzer/protection.py`, `desktop/src-tauri/src/liberar.rs`

**Tareas**

- [ ] Decidir si compensa
- [ ] Comprobar qué es seguro con `simctl`
- [ ] Pruebas de la lista cerrada
- [ ] Ejecución con privilegios y menú

**Hecho cuando**

- [ ] Se ofrecen con su tamaño y avisando que pedirán contraseña.
- [ ] Cancelar el diálogo no cuenta como fallo.

**Seguridad**

- La contraseña la pide macOS: la app nunca la ve.
- Lista cerrada de comandos fijos, sin rutas interpoladas.
- Preferir `xcrun simctl` sobre `rm` cuando exista. Decidir si este riesgo compensa antes de implementarlo.

## Fuera de este plan

- Duplicados en el menú: el motor ya los busca, pero nada indica que valga la pena aquí.
- Reiniciar el Mac desde el menú: se descartó por el riesgo de pulsarlo sin querer.
