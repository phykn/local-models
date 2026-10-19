#!/bin/zsh
# The project path is baked into Info.plist, so rebuild after moving the project.
set -euo pipefail
root="${0:A:h:h}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
app="$tmp/LOCAL-MODELS.app"   # built aside, then moved in whole, so Finder never caches a half-built bundle
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
swift "$root/app/icon.swift" "$tmp/icon.png"
mkdir "$tmp/icon.iconset"
for px in 16 32 128 256 512; do
  sips -z $px $px "$tmp/icon.png" --out "$tmp/icon.iconset/icon_${px}x${px}.png" >/dev/null
  sips -z $((px*2)) $((px*2)) "$tmp/icon.png" --out "$tmp/icon.iconset/icon_${px}x${px}@2x.png" >/dev/null
done
iconutil -c icns "$tmp/icon.iconset" -o "$app/Contents/Resources/LOCAL-MODELS.icns"
swiftc -O "$root"/app/Sources/*.swift -o "$app/Contents/MacOS/LOCAL-MODELS"
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>LOCAL-MODELS</string>
  <key>CFBundleIdentifier</key><string>local.models.app</string>
  <key>CFBundleExecutable</key><string>LOCAL-MODELS</string>
  <key>CFBundleIconFile</key><string>LOCAL-MODELS</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>ProjectRoot</key><string>$root</string>
</dict></plist>
PLIST
codesign --force --sign - "$app"
rm -rf "$root/LOCAL-MODELS.app"
mv "$app" "$root/LOCAL-MODELS.app"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$root/LOCAL-MODELS.app"
echo "built $root/LOCAL-MODELS.app"
