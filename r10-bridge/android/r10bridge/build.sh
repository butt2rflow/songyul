#!/usr/bin/env bash
# Build R10 Bridge without Gradle: javac + d8 + aapt2 + zipalign + apksigner from the Android SDK.
# Needs (Ubuntu): sudo apt install google-android-platform-34-installer \
#   google-android-build-tools-34.0.0-installer google-android-platform-tools-installer
# Output: build/r10bridge.apk  (install: adb install -r build/r10bridge.apk)
set -euo pipefail
cd "$(dirname "$0")"

SDK=${ANDROID_HOME:-/usr/lib/android-sdk}
BT=$SDK/build-tools/34.0.0
JAR=$SDK/platforms/android-34/android.jar
for f in "$JAR" "$BT/aapt2" "$BT/d8" "$BT/zipalign" "$BT/apksigner"; do
  [ -e "$f" ] || { echo "missing $f (see the apt line at the top)"; exit 1; }
done

# The glove page is bundled and served by the app at http://127.0.0.1:8765/ (see WsServer.java).
PAGE=${PAGE:-../../../phone}
[ -f "$PAGE/index.html" ] || { echo "glove page not found at $PAGE (set PAGE=...)"; exit 1; }
classes=build/classes
dex=build/dex
assets=build/assets
rm -r -- "$classes" "$dex" "$assets" 2>/dev/null || true
mkdir -p "$classes" "$dex" "$assets/web"
cp "$PAGE"/*.html "$PAGE"/*.js "$PAGE"/*.json build/assets/web/
"$BT/aapt2" compile --dir res -o build/resources.zip
"$BT/aapt2" link -o build/base.apk -I "$JAR" --manifest AndroidManifest.xml -A build/assets --java build build/resources.zip
javac -source 8 -target 8 -XDstringConcat=inline -Xlint:-options -encoding UTF-8 -classpath "$JAR" -d build/classes \
  build/org/songyul/r10bridge/R.java $(find src -name '*.java')
"$BT/d8" --min-api 26 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
cp build/base.apk build/unsigned.apk
(cd build/dex && zip -q ../unsigned.apk classes.dex)
"$BT/zipalign" -f 4 build/unsigned.apk build/aligned.apk

KS=${R10_DEBUG_KEYSTORE:-build/debug.keystore}   # local debug key, excluded by .gitignore
if [ ! -f "$KS" ]; then
  mkdir -p "$(dirname "$KS")"
  keytool -genkeypair -keystore "$KS" -storepass android -keypass android -alias r10bridge \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=R10 Bridge debug" >/dev/null
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
  --out build/r10bridge.apk build/aligned.apk
echo "built $(pwd)/build/r10bridge.apk"
