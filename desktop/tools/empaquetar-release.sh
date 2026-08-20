#!/usr/bin/env bash
# Construye el artefacto distribuible de la app de bandeja, de principio a fin.
#
#   ./desktop/tools/empaquetar-release.sh [version]
#
# Deja un .zip listo para subir en `desktop/dist/`.
set -euo pipefail

VERSION="${1:-v0.1.0}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
ARCH="$(uname -m)"
APP="desktop/src-tauri/target/release/bundle/macos/Disk Use Analyzer.app"
DESTINO="desktop/dist"
ZIP="$DESTINO/DiskUseAnalyzer-${VERSION}-macos-${ARCH}.zip"

# rustup instala cargo en ~/.cargo/bin, que no está en el PATH de un shell no
# interactivo. Sin esto, `tauri build` falla con un críptico "failed to run
# 'cargo metadata'".
if ! command -v cargo >/dev/null 2>&1; then
  export PATH="$HOME/.cargo/bin:$PATH"
fi
command -v cargo >/dev/null 2>&1 || { echo "No encuentro cargo. Instálalo: https://rustup.rs" >&2; exit 1; }

echo "▸ 1/4 Preparando el motor autocontenido"
./desktop/tools/preparar-motor.sh

echo "▸ 2/4 Compilando la .app"
(cd desktop && npm run tauri build -- --bundles app)

# Tauri deja el ejecutable con la firma del enlazador, pero NO firma el bundle:
# queda sin `_CodeSignature` y con "Sealed Resources=none", y `codesign
# --verify` lo rechaza con "code has no resources but signature indicates they
# must be present". macOS puede llegar a matar una app en ese estado por
# considerarla dañada, así que se firma ad hoc aquí.
#
# De dentro hacia fuera, no con `--deep`: `--deep` firma lo anidado con las
# mismas opciones que el contenedor, que casi nunca es lo que quieres, y Apple
# lo desaconseja para firmar (solo para verificar).
echo "▸ 3/4 Firmando ad hoc, de dentro hacia fuera"
find "$APP/Contents/Resources" -type f \
  \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) 2>/dev/null \
  | while read -r f; do
      if file -b "$f" | grep -q "Mach-O"; then
        codesign --force --timestamp=none -s - "$f" 2>/dev/null || true
      fi
    done
codesign --force --timestamp=none -s - "$APP"
codesign --verify --deep --strict "$APP"
echo "  ✓ firma ad hoc válida"

echo "▸ 4/4 Comprimiendo"
mkdir -p "$DESTINO"
rm -f "$ZIP"
# `ditto`, no `zip`: conserva los metadatos y permisos de macOS, sin los cuales
# la .app llega rota al otro lado.
ditto -c -k --keepParent --sequesterRsrc "$APP" "$ZIP"

echo
echo "▸ Listo: $ZIP ($(du -h "$ZIP" | cut -f1))"
echo "  Sin firmar con Developer ID y sin notarizar: Gatekeeper bloqueará el"
echo "  doble clic. Se abre con clic derecho → Abrir."
