#!/usr/bin/env bash
# Genera el icono de la app: el anillo del disco repartido por categorías, con
# el porcentaje usado en el centro, en la paleta «Sistema» (la misma que usa por
# defecto el anillo en vivo de la barra de menús, en el mismo orden de trozos).
#
#   ./desktop/tools/gen_icono_app.sh
#
# Necesita Google Chrome (lo usa en modo headless para rasterizar el SVG) y
# node (para `tauri icon`). Los ficheros de desktop/src-tauri/icons/ son la
# salida de este script: se versionan para que compilar no dependa de Chrome.
#
# Por tamaño, no escalando uno solo: a 16 px la cifra es ilegible y ensucia,
# así que esa versión va sin cifra y con el anillo más grueso.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ICONOS="$REPO_ROOT/desktop/src-tauri/icons"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# svg <con_cifra:0|1>
svg() {
  python3 - "$1" <<'PY'
import sys
cifra = sys.argv[1] == "1"
# Orden y colores de ajustes.rs (PaletaId::Sistema) y categorias.rs.
trozos = [("#0a84ff", 20), ("#ff9f0a", 16), ("#bf5af2", 18), ("#8e8e93", 28)]
libre, usado = "#30d158", 82
r, ancho = 30, (11 if cifra else 17)
arcos, off = "", 0.0
comun = f'cx="50" cy="50" r="{r}" fill="none" stroke-width="{ancho}" pathLength="100" transform="rotate(-90 50 50)"'
for color, pct in trozos:
    arcos += f'<circle {comun} stroke="{color}" stroke-dasharray="{max(pct - 1.2, 0.5)} 100" stroke-dashoffset="{-off}"/>'
    off += pct
arcos += f'<circle {comun} stroke="{libre}" stroke-dasharray="{max(100 - usado - 1.2, 0.5)} 100" stroke-dashoffset="{-off}"/>'
texto = (
    '<text x="50" y="58.5" text-anchor="middle" font-family="-apple-system,SF Pro Display,system-ui" '
    f'font-weight="700" font-size="25" fill="#fff">{usado}<tspan font-size="11" font-weight="600" dx="1" opacity=".7">%</tspan></text>'
    if cifra else ""
)
# Rejilla de iconos de macOS: la placa ocupa 824 de 1024 px, centrada.
print(f'''<!doctype html><html><body style="margin:0;background:transparent">
<svg width="1024" height="1024" viewBox="-12.14 -12.14 124.28 124.28"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#3a3f4b"/><stop offset="1" stop-color="#15171c"/></linearGradient></defs>
<rect width="100" height="100" rx="22.5" fill="url(#g)"/>
<circle cx="50" cy="50" r="{r}" fill="none" stroke="#2c3039" stroke-width="{ancho}"/>{arcos}{texto}</svg></body></html>''')
PY
}

pintar() { # <con_cifra> <salida.png>
  svg "$1" > "$TMP/icono.html"
  "$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --default-background-color=00000000 --window-size=1024,1024 \
    --screenshot="$2" "file://$TMP/icono.html" >/dev/null 2>&1
}

pintar 1 "$TMP/con.png"
pintar 0 "$TMP/sin.png"

# Todos los formatos (png, ico, Store…) a partir del de 1024 con cifra.
(cd "$REPO_ROOT/desktop" && npx tauri icon "$TMP/con.png" -o src-tauri/icons >/dev/null 2>&1)
rm -rf "$ICONOS/android" "$ICONOS/ios" "$ICONOS/64x64.png"

# El .icns, con la versión sin cifra a 16 px.
SET="$TMP/icono.iconset"; mkdir "$SET"
reducir() { sips -z "$2" "$2" "$1" --out "$SET/$3" >/dev/null; }
reducir "$TMP/sin.png" 16   icon_16x16.png
reducir "$TMP/con.png" 32   icon_16x16@2x.png
reducir "$TMP/con.png" 32   icon_32x32.png
reducir "$TMP/con.png" 64   icon_32x32@2x.png
reducir "$TMP/con.png" 128  icon_128x128.png
reducir "$TMP/con.png" 256  icon_128x128@2x.png
reducir "$TMP/con.png" 256  icon_256x256.png
reducir "$TMP/con.png" 512  icon_256x256@2x.png
reducir "$TMP/con.png" 512  icon_512x512.png
cp "$TMP/con.png" "$SET/icon_512x512@2x.png"
iconutil -c icns "$SET" -o "$ICONOS/icon.icns"
echo "Icono generado en $ICONOS"
