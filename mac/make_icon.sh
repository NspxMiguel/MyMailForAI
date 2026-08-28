#!/bin/bash
# Gera Resources/icon-1024.png (do vetor em Tools/makeicon.swift) e o .icns.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p Resources

if [ ! -f Resources/icon-1024.png ] || [ Tools/makeicon.swift -nt Resources/icon-1024.png ]; then
  swift Tools/makeicon.swift >/dev/null
fi
[ -f Resources/icon-1024.png ] || { echo "sem icon-1024.png — nada a fazer"; exit 0; }

ICONSET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z $size $size Resources/icon-1024.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  sips -z $((size*2)) $((size*2)) Resources/icon-1024.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o Resources/AppIcon.icns
echo "==> Resources/AppIcon.icns"
