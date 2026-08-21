#!/usr/bin/env bash
# Prepara el motor de análisis autocontenido que se empaqueta dentro de la .app.
#
# Descarga un CPython de python-build-standalone, lo recorta y le copia al lado
# el motor de este repositorio. El resultado va a
# `desktop/src-tauri/resources/engine/`, que está en .gitignore: son ~46 MB de
# binarios que no tienen por qué vivir en el historial de git. Se regenera con
# este script y viaja dentro del artefacto del release.
#
# Por qué python-build-standalone y no PyInstaller: PyInstaller quedó descartado
# porque su bootloader autoextraíble dispara la heurística de los antivirus (ver
# el registro de ejecución). Esto es un CPython normal y sin modificar —el mismo
# que usa `uv`—, así que no tiene ese problema. Verificado en la máquina que lo
# sufrió.
set -euo pipefail

VERSION="20260814"
PY_VERSION="3.13.15"
ARCH="$(uname -m)"
case "$ARCH" in
  arm64)  TRIPLE="aarch64-apple-darwin" ;;
  x86_64) TRIPLE="x86_64-apple-darwin" ;;
  *) echo "Arquitectura no soportada: $ARCH" >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESTINO="$REPO_ROOT/desktop/src-tauri/resources/engine"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${VERSION}/cpython-${PY_VERSION}%2B${VERSION}-${TRIPLE}-install_only.tar.gz"

echo "▸ Preparando el motor para $TRIPLE (CPython $PY_VERSION)"
# El LEEME.md de este directorio SÍ está versionado: es el ancla que hace que
# el glob de `bundle.resources` encaje en un checkout limpio, sin la cual Tauri
# aborta la compilación. Un `rm -rf` a secas se lo llevaba por delante y dejaba
# el árbol de git sucio con un fichero borrado.
ANCLA=""
if [ -f "$DESTINO/LEEME.md" ]; then
  ANCLA="$(mktemp)"
  cp "$DESTINO/LEEME.md" "$ANCLA"
fi
rm -rf "$DESTINO"
mkdir -p "$DESTINO"
if [ -n "$ANCLA" ]; then
  mv "$ANCLA" "$DESTINO/LEEME.md"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "▸ Descargando CPython autocontenido (~25 MB)…"
curl -fsSL -o "$TMP/cpython.tar.gz" "$URL"
tar xzf "$TMP/cpython.tar.gz" -C "$TMP"
mv "$TMP/python" "$DESTINO/python"

# Recorte: nada de esto lo usa el motor, y son ~20 MB.
echo "▸ Recortando lo que el motor no usa…"
cd "$DESTINO/python"
rm -rf lib/tcl9.0 lib/tcl8 lib/*tcl* lib/*tk* \
       lib/python3.13/tkinter lib/python3.13/idlelib lib/python3.13/test \
       lib/python3.13/lib2to3 lib/python3.13/ensurepip \
       lib/python3.13/site-packages/pip* lib/python3.13/config-3.13-darwin \
       include share lib/pkgconfig
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find . -name "*.a" -delete
rm -f lib/python3.13/lib-dynload/_tkinter*.so

# El motor, junto al intérprete. `disk_analyzer.py` queda en la raíz de engine/,
# así que Python mete ese directorio en sys.path solo y encuentra `analyzer/`.
echo "▸ Copiando el motor…"
cd "$REPO_ROOT"
cp disk_analyzer.py disk_analyzer_core.py "$DESTINO/"
cp -R analyzer "$DESTINO/analyzer"

# El servidor web, para que "Abrir analizador completo" funcione sin depender
# de este repositorio. `disk_analyzer_web.py` resuelve sus rutas con
# `Path(__file__).parent`, así que `web/dist` y `static/` tienen que quedar
# exactamente donde están aquí, relativos a él.
echo "▸ Copiando el servidor web…"
if [ ! -d web/dist ]; then
  echo "  El frontend no está construido. Construyéndolo…"
  (cd web && npm run build >/dev/null)
fi
cp disk_analyzer_web.py pty_manager.py agents_manager.py persona_detector.py "$DESTINO/"
mkdir -p "$DESTINO/web"
cp -R web/dist "$DESTINO/web/dist"
cp -R static "$DESTINO/static"

# Las dependencias del servidor, instaladas al lado del código. Se usa el pip
# del venv del repositorio porque el intérprete empaquetado viene sin pip (lo
# quita el recorte de arriba); las ruedas valen igual, porque son de la misma
# versión de Python y la misma arquitectura.
echo "▸ Instalando las dependencias del servidor (~25 MB)…"
venv-web/bin/pip install -q --target "$DESTINO" -r requirements-web.txt

find "$DESTINO" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "▸ Comprobando que arranca…"
"$DESTINO/python/bin/python3" -c "
import sys; sys.path.insert(0, '$DESTINO')
from disk_analyzer_core import DiskAnalyzerCore
d = DiskAnalyzerCore('.').get_disk_usage()
assert d['total'] > 0
print('  ✓ motor operativo:', round(d['total']/1024**3, 1), 'GB totales')
import fastapi, uvicorn  # noqa: F401
print('  ✓ servidor web importable')
"
echo "▸ Listo: $DESTINO ($(du -sh "$DESTINO" | cut -f1))"
