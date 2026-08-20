# Motor de análisis empaquetado

Este directorio lo llena `desktop/tools/preparar-motor.sh`, que descarga un
CPython de [python-build-standalone](https://github.com/astral-sh/python-build-standalone),
lo recorta y le copia al lado el motor de análisis de este repositorio.

Son unos 47 MB de binarios, así que **no se versionan**: se regeneran. Este
`LEEME.md` es la excepción, y está versionado a propósito — Tauri aborta la
compilación si el glob de `bundle.resources` no encaja con ningún fichero, así
que sin él no se podría compilar la app en un checkout limpio (ni en el CI).

Para preparar el motor antes de compilar:

```bash
./desktop/tools/preparar-motor.sh
cd desktop && npm run tauri build -- --bundles app
```

Si te saltas ese paso, la `.app` se construye igual pero sin motor: el indicador
de disco funciona con normalidad y "Analizar ahora" sale apagado, con el texto
"Motor de análisis no encontrado" en el menú.
