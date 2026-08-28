#!/bin/bash
# Monta MyMailForAI.app. O CLI em Python viaja dentro do bundle: o app não faz
# nada sozinho, ele conversa com o mesmo mymailforai que roda no terminal.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="MyMailForAI"
BUILD_DIR=".build/release"
APP_BUNDLE="${APP_NAME}.app"
REPO_DIR=".."
VERSION="$(python3 -c "import re,pathlib; print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('${REPO_DIR}/mymailforai/__init__.py').read_text()).group(1))")"

echo "==> Compilando (release)…"
swift build -c release

./make_icon.sh >/dev/null

echo "==> Montando ${APP_BUNDLE} (versão ${VERSION})…"
rm -rf "${APP_BUNDLE}"
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources/mymailforai"

cp "${BUILD_DIR}/${APP_NAME}" "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
cp Resources/AppIcon.icns "${APP_BUNDLE}/Contents/Resources/AppIcon.icns"

# O que o CLI precisa para rodar de dentro do bundle. Uma instalação só: o
# terminal e o app sempre falam com a mesma versão.
for item in bin mymailforai; do
  cp -R "${REPO_DIR}/${item}" "${APP_BUNDLE}/Contents/Resources/mymailforai/${item}"
done
find "${APP_BUNDLE}/Contents/Resources/mymailforai" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cat > "${APP_BUNDLE}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>dev.nspx.mymailforai</string>
    <key>CFBundleName</key>
    <string>MyMailForAI</string>
    <key>CFBundleDisplayName</key>
    <string>MyMailForAI</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <!-- só barra de menus: sem ícone no Dock e sem janela. É o pedido. -->
    <key>LSUIElement</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>MIT</string>
</dict>
</plist>
PLIST

# Assinatura ad-hoc: sem ela o macOS mata o app na primeira execução em
# máquinas com Gatekeeper mais rígido.
codesign --force --deep --sign - "${APP_BUNDLE}" >/dev/null 2>&1 || true

echo "==> Pronto: $(pwd)/${APP_BUNDLE}"
