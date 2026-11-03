# Menú de la barra: secciones y acciones por categoría

Aprobado el 2026-11-02 sobre simulaciones comparadas con el menú anterior.

## Objetivo

Que el menú se lea de un vistazo y que cada parte del disco ofrezca sus acciones
comunes al pasar el cursor, sin perder las garantías de borrado del proyecto.

## Estructura

```
Disco
  6,9 GB libres de 460,4 GB
  ● Docker            40 GB  ›
  ● Cachés            26 GB  ›
  ● Tus archivos     110 GB  ›
  ● Sistema y otros  278 GB  ›
Memoria
  Swap               11,0 GB  ›
Análisis
  Analizar                    ›
  (estado o progreso, en una o dos líneas)
Liberar lo seguro…   13,6 GB
Abrir analizador completo  ⌘O
Ajustes                       ›
Salir de Disk Use Analyzer ⌘Q
```

## Submenús

| Fila | Contenido |
|---|---|
| Docker | Caché de build (vuelve sola); imágenes sin usar y contenedores parados (hay que volver a descargar); abrir el analizador. Deshabilitado si el daemon no corre. |
| Cachés | Limpiar todas; cada caché por separado; abrir en Finder. |
| Tus archivos | Vaciar papelera; revisar archivos grandes y descargas más antiguas en el analizador; abrir Descargas en Finder. |
| Sistema y otros | No limpia nada. Desglose en el analizador y Almacenamiento de macOS. |
| Swap | Cerrar cada una de las tres apps que más retienen; Monitor de Actividad. |
| Analizar | Disco completo (⌘R), carpeta personal, elegir carpeta, ver último resultado. Durante un análisis, «Cancelar análisis». |

## Reglas

- Solo Cachés tiene «limpiar todo». Docker no, porque los volúmenes guardan datos
  que no vuelven; Tus archivos y Sistema y otros tampoco.
- Docker nunca recibe `--volumes`.
- Toda acción que borra o cierra una app pide confirmación nativa.
- Las acciones de borrado vienen del motor (`--limpieza-rapida`); la app no construye
  comandos. Lo liberado se mide, no se estima.
- Las apps se cierran de forma normal, sin forzar, y pueden preguntar si guardar. No hay
  botón de reiniciar ni se toca el archivo de swap.

## Lo que se comprobó en pantalla (macOS 27)

- Un título atribuido en un ítem deshabilitado sale gris igualmente. Por eso las filas que
  solo informan llevan una vista propia (`NSTextField`), que no se atenúa ni se resalta.
- La imagen de un ítem con submenú no se dibuja. Por eso el punto de color va dentro del
  texto como adjunto.
- Las cifras se alinean con un tope de tabulación a la derecha.

## Entrega

Cuatro PR: estructura; limpiezas por categoría; Docker; Swap y Analizar.
