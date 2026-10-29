#!/bin/bash
# Meet install (macOS 15+, Apple silicon). No sudo. Needs Homebrew (https://brew.sh), Git and Xcode Command Line Tools (xcode-select --install).
# Kurulum (macOS 15+, Apple işlemci). Sudo istemez; Homebrew, Git ve Xcode komut satırı araçları gerekir.
set -e
cd "$(dirname "$0")"
KOK="$(pwd)"

echo "1/6 Tools via Homebrew: ffmpeg, uv"
if ! command -v brew >/dev/null; then echo "Homebrew not found. Install it first: https://brew.sh"; exit 1; fi
for p in ffmpeg uv; do brew list "$p" >/dev/null 2>&1 || brew install "$p"; done

echo "2/6 Python environment (.venv) and packages"
[ -d .venv ] || uv venv .venv --python 3.12
uv pip install --python .venv/bin/python --only-binary :all: -r requirements.txt

echo "3/6 Settings and folders"
[ -f ayarlar.json ] || cp ayarlar.ornek.json ayarlar.json
mkdir -p kayitlar yuklemeler kareler profil misafir modeller .onbellek indirilenler

echo "4/6 Meeting recorder (Swift, ScreenCaptureKit)"
if ! command -v swiftc >/dev/null; then echo "swiftc not found. Run: xcode-select --install"; exit 1; fi
APP="kaydedici/Transkript Kaydedici.app"
mkdir -p "$APP/Contents/MacOS"
cp kaydedici/Info.plist "$APP/Contents/Info.plist"
swiftc -O -o "$APP/Contents/MacOS/kaydedici" kaydedici/kaydedici.swift -framework ScreenCaptureKit -framework AVFoundation \
  -framework CoreAudio -framework AppKit -framework UserNotifications \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker kaydedici/Info.plist 2>/dev/null
codesign -s - -f --deep "$APP" >/dev/null 2>&1 || true

echo "5/6 Start at login (LaunchAgents): the site and the recorder"
LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
cat > "$LA/com.yehso.transkript.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.yehso.transkript</string>
  <key>ProgramArguments</key><array><string>$KOK/.venv/bin/python</string><string>$KOK/site.py</string></array>
  <key>WorkingDirectory</key><string>$KOK</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$KOK/site.log</string><key>StandardErrorPath</key><string>$KOK/site.log</string>
</dict></plist>
PLIST
cat > "$LA/com.yehso.transkript.kaydedici.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.yehso.transkript.kaydedici</string>
  <key>ProgramArguments</key><array><string>$KOK/$APP/Contents/MacOS/kaydedici</string><string>--izle</string><string>$KOK/ayarlar.json</string><string>$KOK/kayitlar</string></array>
  <key>WorkingDirectory</key><string>$KOK</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$KOK/kaydedici/kaydedici.log</string><key>StandardErrorPath</key><string>$KOK/kaydedici/kaydedici.log</string>
</dict></plist>
PLIST
for e in com.yehso.transkript com.yehso.transkript.kaydedici; do
  launchctl bootout "gui/$(id -u)/$e" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$LA/$e.plist"
done

echo "6/6 Done."
echo "  • Open http://127.0.0.1:8766 (later: double-click Meet.command). The \"Getting started\" card lists what is left."
echo "  • Recording is off until you turn it on: Settings → Recording → Automatic meeting recording."
echo "    The first recording asks for Screen & System Audio Recording and Microphone permission (System Settings → Privacy)."
echo "  • Chrome extension (names, live captions, side panel): chrome://extensions → Developer mode → Load unpacked → the 'uzanti' folder."
echo "  • Notes and summaries need Claude Code signed in (claude auth login) or a local model:"
echo "      brew install ollama && brew services start ollama && ollama pull gemma3:4b"
echo "  • Tell the people in your meetings that you are recording; many countries require their consent."
