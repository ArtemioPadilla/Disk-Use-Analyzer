# Roadmap

Última revisión: 22 de septiembre de 2026 · `main` en `e617adf` · v0.2.2 publicada ·
352 tests (247 backend, 85 frontend, 20 Rust), CI en verde.

Este es el mapa de **qué hay, qué falta, en qué orden y por qué**. No sustituye a
los planes de implementación: los enlaza. Si vas a ejecutar algo, el plan
enlazado es la fuente de verdad; si quieres saber qué hacer después, empieza
aquí.

## Cómo leerlo

- **Épica**: un área del producto con un objetivo propio.
- **Historia**: algo que cambia lo que el usuario puede hacer o lo que el
  código garantiza. Cada una lleva un criterio de aceptación: **"hecho cuando…"**.
- **Plan**: el documento con los tasks. Cuando una historia no tiene plan, es
  que todavía no se ha diseñado.

Estados: ✅ hecho · 🔶 en parte · ⬜ pendiente · ❓ pendiente de una decisión tuya.

## De un vistazo

| Épica | Hecho | Abierto | Lo más urgente |
|---|---|---|---|
| [E1 · Motor de análisis](#e1--motor-de-análisis-y-cli) | Motor compartido, niveles unificados, `id` y `efecto` | Reglas muertas, cifras infladas, escapadores del informe HTML | La cifra de cabecera miente 4× |
| [E2 · Seguridad de la limpieza](#e2--seguridad-de-la-limpieza) | Verja instalada en los tres caminos que borran, sin inyección | `caches_de_apps` borra y luego informa de fallo; tests vacuos | `caches_de_apps` |
| [E3 · Interfaz web](#e3--interfaz-web) | 7 páginas, terminal, asistentes, ahorro medido | `efecto` sin usar, `nivelDe` en 1 de 4 botones | Que lo que solo lista deje de tener botón |
| [E4 · App de barra de menús](#e4--app-de-barra-de-menús) | Rebanada A, analizador completo, puerto efímero | "Liberar lo seguro", rebanadas B y C | "Liberar lo seguro", **después** de E2 |
| [E5 · Distribución](#e5--distribución) | App autocontenida, releases firmados ad hoc | Certificado, notarización, Intel | Certificado autofirmado |
| [E6 · Salud del repo](#e6--salud-del-repo-y-del-proceso) | CI en tres suites, Fase 0 | `main` sin proteger, Dependabot apagado | Proteger `main` |

## Orden recomendado

1. ~~**E6.1 — Fase 0.**~~ Hecha el 22 de septiembre. Queda **E6.3**, proteger `main`: es una decisión tuya.
2. **E2.1 y el resto de E2/E3 abierto — cerrar el saneamiento.** Un plan de unos
   cinco tasks. Empieza por E2.1, el bug más visible.
3. **E4.1 — "Liberar lo seguro" en el menú.** Lo que originó el saneamiento.
   Depende de 2: sin él, el botón heredaría defectos conocidos.
4. **E4.2 — rebanada B, vigilancia de carpetas.**
5. **E5.1 — certificado autofirmado**, cuando la actualización que rompe el
   permiso de disco empiece a molestar. Es un paso manual tuyo.
6. **E4.3 — rebanada C**, solo tras decidir E4.3a.

---

## E1 · Motor de análisis y CLI

Objetivo: que lo que el motor recomienda sea cierto — que cada regla dispare
cuando debe, borre lo que dice y prometa el espacio que puede liberar.

| | Historia | Hecho cuando… | Plan |
|---|---|---|---|
| ✅ | Un solo motor para CLI, web y bandeja | `disk_analyzer.py` delega en el core; un test compara las dos interfaces | [Saneamiento T6](superpowers/plans/2026-08-21-saneamiento-limpieza.md) |
| ✅ | Cada recomendación declara `id` estable y `efecto` | Las 18 reglas traen ambos campos | Saneamiento T4, T6 |
| ✅ | Reglas para cachés de apps, papelera y Docker sin escaneo completo | Salen sobre un estado sintético | Saneamiento T7 |
| ⬜ | **E1.1** Las reglas muertas vuelven a funcionar o desaparecen | `node_modules_huerfano` y `git_pack_files` disparan sobre un disco real, o se borran junto con el caso de patrón `node_modules` de la verja | — |
| ⬜ | **E1.2** La cifra de cabecera suma solo lo que se ofrece | `cache_size` deja de contar `~/Downloads`, datos de Docker, `/private/var/folders` y simuladores instalados | — |
| ⬜ | **E1.3** `simuladores` promete lo que puede liberar | Su `space` sale de lo que borra su comando (1 GB medido), no de todo `CoreSimulator` (41 GB) | — |
| ⬜ | **E1.4** Los comandos del informe HTML pasan por el mismo camino | `delete_cmd` usa `comandos.py` y la verja; el script de duplicados funciona con apóstrofos en el nombre | — |

**Por qué E1.1 importa más de lo que parece:** `node_modules` y `.git/objects`
están en `IGNORE_PATTERNS`, así que el escáner nunca los ve y esas dos reglas no
pueden dispararse. Para una de ellas se abrió un hueco por nombre en la verja
(`puede_borrarse('/Volumes/Ext/x/node_modules') == True`) que hoy protege algo
que no existe.

Deuda menor: `_get_cleanup_command_for_downloads` es código muerto que genera un
`find ... -delete` (bórralo antes de que alguien lo llame); `sudo tmutil
deletelocalsnapshots {d}` interpola sin escapar (no es explotable: la fuente es
la salida de `tmutil`).

## E2 · Seguridad de la limpieza

Objetivo: que ninguna limpieza pueda borrar datos del usuario, y que cuando
diga que liberó espacio sea verdad.

| | Historia | Hecho cuando… | Plan |
|---|---|---|---|
| ✅ | El nombre de una carpeta no puede ejecutar comandos | Todo comando de borrado pasa por `analyzer/comandos.py` con `shlex.quote` | Saneamiento T1 |
| ✅ | Existe una verja de lo que se puede borrar, y la consultan todos los caminos | `comandos.py`, `clean_cache` y `_perform_cleanup_deletes` llaman a `puede_borrarse` | Saneamiento T2, T7 y ola final |
| ✅ | El clasificador no ve el nombre de usuario | Un usuario `logan` no tiene sus Descargas clasificadas como logs | Ola final |
| ✅ | Ninguna regla filtra solo por tipo de caché | Toda regla que filtra por `type` acota además por ruta | Ola final |
| ⬜ | **E2.1** Una subcarpeta sin permiso no convierte una limpieza en "fallo" | `caches_de_apps` sale con 0 en un Mac real; `borrar_contenido` no aborta el resto tras la primera ruta fallida | — |
| ⬜ | **E2.2** "Vaciar el contenido" incluye los ficheros ocultos | `rm -rf dir/*` deja hoy `.env` y similares; la papelera es donde más se nota | — |
| ⬜ | **E2.3** Los tests de seguridad fallan si se quita lo que protegen | Los nueve tests que la revisión final encontró vacuos o tautológicos fallan por mutación (lista abajo) | — |
| ❓ | **E2.4** Papelera para los ficheros del propio usuario | Decisión tomada: no para cachés regenerables; sí cuando se borren ficheros tuyos (Descargas, carpetas propias) | — |

**E2.1 es el bug más visible que queda.** `rm -rf ~/Library/Caches/*` se
encuentra con subcarpetas del sistema que el usuario no puede recorrer, borra
unos 21 GB, sale con código 1, y la interfaz no acredita nada, muestra un error
y vuelve a ofrecer la recomendación en el siguiente escaneo.

Tests que la revisión final encontró sin dientes (para E2.3):
`test_caches_de_apps_no_arrastra_coresimulator_ni_var_folders` (sobrevive a
quitar el filtro de ruta), `test_un_enlace_simbolico_no_permite_escapar_de_una_cache`
(se salta si falta `~/Documents`, así que en CI puede no cubrir `realpath`),
`test_las_dos_interfaces_recomiendan_lo_mismo` (tautológico desde la fusión), el
fixture de paridad (no dispara `caches_de_apps` ni `papelera`: salen 14, no 12),
`test_du_sh_otros_escapa_la_ruta_...`, `test_una_ruta_vacia_no_produce_comando`,
`test_la_raiz_nunca_genera_comando`, `test_los_temporales_del_sistema_los_gestiona_macos`
y los de `servidor.rs` que pasan con un `puerto_libre()` constante.

Deuda menor: la verja aprueba `/Network`, `/cores` y `/nix` por el `return True`
final; una ruta con `~` sin expandir la aprueba la verja pero el shell no la
expande entre comillas.

## E3 · Interfaz web

Objetivo: que la interfaz distinga lo que borra de lo que solo informa, y que
todos los botones por lotes apliquen la misma regla.

| | Historia | Hecho cuando… | Plan |
|---|---|---|---|
| ✅ | Web alojada: 7 páginas, terminal flotante, historial, exportación | Existe y está en producción | [Web alojada](superpowers/plans/2026-04-06-hosted-web-ui.md) |
| ✅ | Todos los flujos de limpieza pasan por un único runner | `useCleanupRunner` es lo único que lanza comandos | [Fase 4](superpowers/plans/2026-08-10-mejoras-fase4-frontend.md) |
| ✅ | El ahorro se mide del disco, no del código de salida | Delta de espacio libre, acotado a 3 s | Saneamiento T5 |
| ✅ | La web avisa cuando el servidor no responde | Banner distinto del de sesión caducada | PR #20 |
| ⬜ | **E3.1** Lo que solo lista deja de ser un botón | Los componentes leen `efecto`; `solo_lista` abre el navegador de ficheros filtrado en vez de ejecutar | — |
| ⬜ | **E3.2** Los cuatro botones por lotes usan `nivelDe` | `ReverseView`, `WhatIfSandbox` y `GuidedDeclutter` dejan de leer `tier` en crudo | — |
| ⬜ | **E3.3** El total "recuperable" excluye lo que no se ejecuta | `CleanupWizard` no suma `space` de recomendaciones `solo_lista` | — |
| ⬜ | **E3.4** Un pase de idioma | Etiquetas en español (hoy "Clean Safe Items", "Cleaned:", "freed") | — |

**E3.1 es lo que cierra el bug original.** Hoy `descargas_antiguas` ejecuta un
`find -ls` que sale con 0; si la medición de disco falla o tarda más de 3 s, se
acreditan los 18 GB estimados. Es exactamente el fallo que empezó todo esto,
alcanzable por el camino de reserva.

Deuda menor: `request()` no tiene timeout global (la medición sí está acotada);
`cleanup/execute` con `dry_run=true` devuelve la forma de `preview`;
`Docker.raw` en `lib/categories.ts` es código muerto; el campo `estimado` viaja
en el evento y nadie lo lee.

## E4 · App de barra de menús

Objetivo: enterarte de que algo se come el disco mientras pasa, y poder
liberarlo sin abrir nada más.
Spec: [app de bandeja](superpowers/specs/2026-08-19-app-bandeja-tauri-design.md) ·
Runbook: [app-bandeja](runbooks/app-bandeja.md)

| | Historia | Hecho cuando… | Plan |
|---|---|---|---|
| ✅ | Rebanada A: indicador en vivo y análisis cancelable | Icono de estado, menú vivo, sin huérfanos al salir | [Rebanada A](superpowers/plans/2026-08-20-app-bandeja-rebanada-a.md) |
| ✅ | La app no depende del repositorio | Lleva su CPython y su motor dentro | PR #12 |
| ✅ | "Abrir analizador completo" arranca el servidor de verdad | Puerto efímero, atado a 127.0.0.1, reaping del hijo | PR #19, #21 |
| ✅ | El aviso de permisos distingue "falta acceso total" de "pide sudo" | Sonda directa sobre `com.apple.TCC` | PR #18 |
| ⬜ | **E4.1** "Liberar lo seguro" en el menú | Un clic muestra qué se borra y cuánto; ejecuta solo nivel 1 tras confirmar; el resultado es el espacio medido | — |
| ⬜ | **E4.2** Rebanada B: vigilancia de carpetas | Te avisa cuando una carpeta crece de golpe, sin que la abras | — |
| ❓ | **E4.3** Rebanada C: ventana del panel | Pendiente de E4.3a | — |
| ❓ | **E4.3a** ¿Ventana nativa con gráficas propias, o ventana sobre la web que ya lleva dentro? | Decisión tuya. Elegiste nativa; dos revisiones adversariales lo desaconsejaron por duplicar la visualización | — |
| ❓ | **E4.4** ¿El servidor que lanza la bandeja lleva la terminal desactivada? | Decisión pendiente desde el spec. Hoy va **activada** (atada a loopback) | — |
| ✅ | **E4.5** Arranque al iniciar sesión | La app vuelve tras reiniciar el Mac | v0.3.0 |
| ✅ | Avisos de poco espacio y del swap | Notificación al cruzar 20 y 5 GB libres; el menú nombra la app que retiene el swap | v0.3.0 |
| ✅ | Anillo en vivo por categorías | El icono de la barra reparte lo usado por categorías; texto y paleta elegibles desde el menú | v0.3.0 |
| ⬜ | **E4.6** La configuración de qué es "seguro" | Casillas por categoría en el diálogo de confirmación; nada de pantalla de ajustes (los otros tres ejes se descartaron) | — |

Deuda conocida del servidor que lanza la bandeja: los shells del PTY hacen
`os.setsid()` y escapan del grupo de procesos, así que sobreviven al cerrar la
app; un `SIGKILL` de la app deja el servidor vivo con el token válido; el bucle
de arranque no detecta que el hijo murió y espera 45 s en silencio; el
comentario de `puerto_libre` promete un reintento que nadie hace.

## E5 · Distribución

| | Historia | Hecho cuando… | Plan |
|---|---|---|---|
| ✅ | App autocontenida y descargable | Releases v0.1.0 → v0.2.2 con `.zip` y sha256 | PR #12, #13 |
| ⬜ | **E5.1** El permiso de disco sobrevive a las actualizaciones | Certificado autofirmado en el llavero y la firma lo usa (paso manual: [runbook](runbooks/app-bandeja.md)) | — |
| ❓ | **E5.2** Firma con Developer ID y notarización | Decisión D4: cuenta de Apple, 99 $/año | — |
| ⬜ | **E5.3** Build para Intel o universal | Un `.zip` que abre en un Mac Intel | — |
| ⬜ | **E5.4** Linux y Windows | Documentado en el spec con sus obstáculos; `analisis.rs` solo compila en Unix | — |

## E6 · Salud del repo y del proceso

| | Historia | Hecho cuando… | Plan |
|---|---|---|---|
| ✅ | CI en las tres suites | Backend, frontend y Rust en cada PR | [Fase 5](superpowers/plans/2026-08-01-mejoras-fase5-tests-y-ci.md) |
| ✅ | **E6.1** Fase 0: higiene | 0 ficheros de `root` en el repo y 0 `.pyc` versionados. No hizo falta `sudo`: los 20 de root eran informes sin versionar en un directorio propio | [Roadmap de mejoras](superpowers/plans/2026-07-15-roadmap-mejoras.md#fase-0--higiene-del-repo-15-min-sin-plan-tdd) |
| ✅ | **E6.2** `CLAUDE.md` dice la verdad | El párrafo de estado ya no dice "Phase 4 pending merge, 66 tests" ni que el ahorro se acredita por el código de salida | Este roadmap |
| ❓ | **E6.3** `main` protegida | El CI bloquea el merge en rojo. Ya se mergeó una vez con el backend en rojo (PR #16) | — |
| ⬜ | **E6.4** Dependabot activo | Alertas de dependencias encendidas (hoy desactivadas) | — |
| ❓ | **E6.5** Convención de idioma | `CLAUDE.md` pide comentarios en inglés; varios módulos nuevos están en español. Actualizar la regla o traducir | — |

Deuda menor: `/docs` y `/openapi.json` quedan sin autenticación.

---

## Decisiones abiertas

Todas son tuyas; ninguna bloquea el paso siguiente del orden recomendado.

| | Decisión | Qué depende de ella |
|---|---|---|
| E4.3a | Ventana nativa con gráficas propias o sobre la web que ya va dentro | La rebanada C |
| E4.4 | Terminal activada o desactivada en el servidor que lanza la bandeja | La rebanada C; la postura de seguridad de un clic |
| E5.2 | Cuenta de desarrollador de Apple | Notarización y distribución sin "clic derecho → Abrir" |
| E6.3 | Proteger `main` | Que el CI deje de ser solo informativo |
| E6.5 | Idioma de los comentarios de código | Consistencia de los módulos nuevos |

## Historial: planes cerrados

Todos terminados. Se listan para que nadie los tome por trabajo pendiente.

| Plan | Resultado | Evidencia |
|---|---|---|
| [Informe HTML interactivo](superpowers/plans/2026-04-06-interactive-ux-overhaul.md) (abril) | ✅ Sus 10 tasks de funcionalidad. **Las casillas nunca se marcaron** | `36c28dc`, `7837fb5`, `b53b0d0`, `7908b68` |
| [Web alojada](superpowers/plans/2026-04-06-hosted-web-ui.md) (abril) | ✅ Sus 14 tasks, y bastante más. **Casillas sin marcar** | `e6fea81` → `fa88a8d` |
| [Mejoras UX](superpowers/specs/2026-04-06-ux-improvements.md) (abril, spec) | ✅ Sus ideas de alto impacto | `0b8ad49`, `0a77074`, `19122dc`… |
| [Plan de mejoras, fases 1–5](superpowers/plans/README.md) | ✅ Mergeadas (PR #5–#10). La Fase 0 sigue abierta como E6.1 | [Registro](superpowers/plans/2026-07-15-registro-ejecucion.md) |
| [Rebanada A de la bandeja](superpowers/plans/2026-08-20-app-bandeja-rebanada-a.md) | ✅ Publicada y ampliada hasta v0.2.1 | PR #11–#20 |
| [Saneamiento de la limpieza](superpowers/plans/2026-08-21-saneamiento-limpieza.md) | ✅ 8 tasks más una ola de arreglos. Lo que quedó fuera está repartido arriba | PR #21, v0.2.2 |
