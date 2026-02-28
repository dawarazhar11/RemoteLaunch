#!/usr/bin/env python3
"""
RemoteLaunch App Generator
Fetches all Windows apps from the agent and creates individual .app bundles
in /Applications/Remote Apps/ so they appear in Spotlight, Launchpad, and Dock.

Each .app:
  - Appears in Spotlight search
  - Has file type associations (double-click .docx → remote Word)
  - Uploads local files to Windows before opening
  - Uses optimized FreeRDP for Parsec-like latency

Run: python3 generate_apps.py [--host NETBIRD_IP]
"""

import json
import os
import sys
import stat
import urllib.request
import subprocess
import shutil
from pathlib import Path

CONFIG_DIR = Path.home() / ".remote-launch"
CONFIG_FILE = CONFIG_DIR / "config.json"
APPS_DIR = Path("/Applications/Remote Apps")
AGENT_PORT = 7891

# ─── macOS UTI mappings for file type associations ───────────────────
# Maps file extension to (UTI, MIME type) for CFBundleDocumentTypes
FILE_TYPE_UTIS = {
    # Documents
    "docx": ("org.openxmlformats.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "doc": ("com.microsoft.word.doc", "application/msword"),
    "rtf": ("public.rtf", "text/rtf"),
    "xlsx": ("org.openxmlformats.spreadsheetml.sheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "xls": ("com.microsoft.excel.xls", "application/vnd.ms-excel"),
    "csv": ("public.comma-separated-values-text", "text/csv"),
    "pptx": ("org.openxmlformats.presentationml.presentation", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "ppt": ("com.microsoft.powerpoint.ppt", "application/vnd.ms-powerpoint"),
    "pdf": ("com.adobe.pdf", "application/pdf"),
    # Code
    "py": ("public.python-script", "text/x-python"),
    "js": ("com.netscape.javascript-source", "text/javascript"),
    "ts": ("com.microsoft.typescript", "text/typescript"),
    "html": ("public.html", "text/html"),
    "css": ("public.css", "text/css"),
    "json": ("public.json", "application/json"),
    "xml": ("public.xml", "text/xml"),
    "yaml": ("public.yaml", "text/yaml"),
    "md": ("net.daringfireball.markdown", "text/markdown"),
    "txt": ("public.plain-text", "text/plain"),
    "log": ("public.log", "text/plain"),
    "c": ("public.c-source", "text/x-c"),
    "cpp": ("public.c-plus-plus-source", "text/x-c++"),
    "h": ("public.c-header", "text/x-c"),
    "rs": ("public.rust-source", "text/x-rust"),
    "go": ("public.go-source", "text/x-go"),
    "java": ("com.sun.java-source", "text/x-java"),
    "sh": ("public.shell-script", "text/x-shellscript"),
    "bat": ("com.microsoft.batch-file", "text/plain"),
    "ps1": ("com.microsoft.powershell-script", "text/plain"),
    "ini": ("public.ini", "text/plain"),
    # Engineering
    "stl": ("public.standard-tesselated-geometry-format", "application/sla"),
    "step": ("public.step", "application/step"),
    "stp": ("public.step", "application/step"),
    "dxf": ("public.dxf", "application/dxf"),
    "dwg": ("com.autodesk.dwg", "application/acad"),
    # Images
    "png": ("public.png", "image/png"),
    "jpg": ("public.jpeg", "image/jpeg"),
    "jpeg": ("public.jpeg", "image/jpeg"),
    "gif": ("public.gif", "image/gif"),
    "bmp": ("com.microsoft.bmp", "image/bmp"),
    "svg": ("public.svg-image", "image/svg+xml"),
    # Media
    "mp4": ("public.mpeg-4", "video/mp4"),
    "mkv": ("public.matroska-video", "video/x-matroska"),
    "avi": ("public.avi", "video/avi"),
    "mp3": ("public.mp3", "audio/mpeg"),
    "wav": ("com.microsoft.waveform-audio", "audio/wav"),
    # Archives
    "zip": ("com.pkware.zip-archive", "application/zip"),
    "rar": ("com.rarlab.rar-archive", "application/x-rar-compressed"),
    "7z": ("org.7-zip.7-zip-archive", "application/x-7z-compressed"),
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"connection": {"host": "", "username": "", "password": "", "port": 3389},
            "settings": {"agent_port": AGENT_PORT, "extra_flags": "/cert:ignore"}}


def fetch_apps(host, port):
    """Fetch app list from Windows agent."""
    url = f"http://{host}:{port}/api/apps"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
            return data.get("apps", [])
    except Exception as e:
        print(f"❌ Cannot reach agent at {host}:{port} — {e}")
        return []


def safe_name(name):
    """Make a filesystem-safe name."""
    return "".join(c for c in name if c.isalnum() or c in " .-_()").strip()


def safe_id(name):
    """Make a bundle identifier component."""
    return "".join(c for c in name if c.isalnum()).lower()


def build_document_types_plist(file_types):
    """Generate CFBundleDocumentTypes XML for file type associations."""
    if not file_types:
        return ""

    entries = []
    for ext in file_types:
        uti_info = FILE_TYPE_UTIS.get(ext)
        if not uti_info:
            continue
        uti, mime = uti_info
        entries.append(f"""      <dict>
        <key>CFBundleTypeName</key>
        <string>{ext.upper()} Document</string>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>LSHandlerRank</key>
        <string>Alternate</string>
        <key>CFBundleTypeExtensions</key>
        <array>
          <string>{ext}</string>
        </array>
        <key>LSItemContentTypes</key>
        <array>
          <string>{uti}</string>
        </array>
      </dict>""")

    if not entries:
        return ""

    return f"""  <key>CFBundleDocumentTypes</key>
  <array>
{chr(10).join(entries)}
  </array>"""


def create_launcher_script(app, config):
    """Generate the bash launcher script for a .app bundle."""
    conn = config.get("connection", {})
    settings = config.get("settings", {})
    host = conn.get("host", "")
    port = conn.get("port", 3389)
    username = conn.get("username", "")
    password = conn.get("password", "")
    domain = conn.get("domain", "")
    agent_port = settings.get("agent_port", AGENT_PORT)
    extra = settings.get("extra_flags", "/cert:ignore")
    win_path = app.get("path", "")
    app_name = app.get("name", "App")

    return f'''#!/bin/bash
# RemoteLaunch — {app_name}
# Auto-generated launcher for remote Windows app

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

HOST="{host}"
PORT="{port}"
USER="{username}"
PASS="{password}"
DOMAIN="{domain}"
AGENT_PORT="{agent_port}"
WIN_APP_PATH="{win_path}"
APP_NAME="{app_name}"

# ── Find FreeRDP ──
FREERDP=""
for cmd in xfreerdp3 xfreerdp /opt/homebrew/bin/xfreerdp3 /opt/homebrew/bin/xfreerdp; do
    if command -v "$cmd" &>/dev/null; then
        FREERDP="$cmd"
        break
    fi
done

if [ -z "$FREERDP" ]; then
    osascript -e 'display dialog "FreeRDP not found!\\n\\nInstall with:\\nbrew install freerdp3" with title "RemoteLaunch" buttons {{"OK"}} with icon stop'
    exit 1
fi

IS_V3=0
if echo "$FREERDP" | grep -q "freerdp3"; then
    IS_V3=1
fi

# ── Handle file argument (Open With / drag & drop) ──
FILE_ARG=""
WIN_FILE_PATH=""

if [ -n "$1" ] && [ -f "$1" ]; then
    LOCAL_FILE="$1"
    FILENAME=$(basename "$LOCAL_FILE")

    # Upload file to Windows agent
    echo "Uploading $FILENAME to Windows..."
    UPLOAD_RESULT=$(curl -s -X POST \\
        -H "X-Filename: $FILENAME" \\
        -H "Content-Type: application/octet-stream" \\
        --data-binary "@$LOCAL_FILE" \\
        "http://$HOST:$AGENT_PORT/api/upload" 2>/dev/null)

    if echo "$UPLOAD_RESULT" | grep -q "windows_path"; then
        WIN_FILE_PATH=$(echo "$UPLOAD_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('windows_path',''))" 2>/dev/null)
    fi

    if [ -z "$WIN_FILE_PATH" ]; then
        osascript -e "display dialog \\"Could not upload file to Windows PC.\\nMake sure the agent is running on $HOST\\" with title \\"RemoteLaunch\\" buttons {{\\"OK\\"}} with icon caution"
        exit 1
    fi
fi

# ── Build FreeRDP command ──
CMD=("$FREERDP")
CMD+=("/v:$HOST:$PORT")
CMD+=("/u:$USER")
[ -n "$PASS" ] && CMD+=("/p:$PASS")
[ -n "$DOMAIN" ] && CMD+=("/d:$DOMAIN")

# RemoteApp mode
if [ -n "$WIN_FILE_PATH" ]; then
    # Launch app with file argument
    if [ "$IS_V3" -eq 1 ]; then
        CMD+=("/app:program:$WIN_APP_PATH" "/app:cmd:$WIN_FILE_PATH")
    else
        CMD+=("/app:$WIN_APP_PATH" "/app-cmd:$WIN_FILE_PATH")
    fi
else
    if [ "$IS_V3" -eq 1 ]; then
        CMD+=("/app:program:$WIN_APP_PATH")
    else
        CMD+=("/app:$WIN_APP_PATH")
    fi
fi

# ── Latency-optimized flags (Parsec-like) ──
CMD+=("/network:lan")
CMD+=("/gfx:RFX")
CMD+=("+gfx-progressive")
CMD+=("/dynamic-resolution")
CMD+=("+clipboard")
CMD+=("+home-drive")
CMD+=("/audio-mode:0")
CMD+=("/compression-level:2")

# Extra user flags
{extra}
for flag in {extra}; do
    CMD+=("$flag")
done

# ── Launch ──
exec "${{CMD[@]}}" 2>>"$HOME/.remote-launch/launch.log"
'''


def create_app_bundle(app, config):
    """Create a macOS .app bundle for a Windows app."""
    name = safe_name(app.get("name", "App"))
    if not name:
        return None

    app_path = APPS_DIR / f"{name}.app"
    contents = app_path / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"

    # Clean existing
    if app_path.exists():
        shutil.rmtree(app_path)

    macos.mkdir(parents=True)
    resources.mkdir(parents=True)

    bundle_id = f"com.remoteLaunch.{safe_id(name)}"
    file_types = app.get("file_types", [])
    doc_types_xml = build_document_types_plist(file_types)

    # ── Info.plist ──
    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundleIdentifier</key>
  <string>{bundle_id}</string>
  <key>CFBundleName</key>
  <string>{name}</string>
  <key>CFBundleDisplayName</key>
  <string>{name} (Remote)</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSUIElement</key>
  <false/>
{doc_types_xml}
</dict>
</plist>"""

    with open(contents / "Info.plist", "w") as f:
        f.write(info_plist)

    # ── Launcher script ──
    launcher = create_launcher_script(app, config)
    launcher_path = macos / "launch"
    with open(launcher_path, "w") as f:
        f.write(launcher)
    os.chmod(launcher_path, 0o755)

    # ── App metadata (for the control panel) ──
    meta = {
        "name": app.get("name", ""),
        "path": app.get("path", ""),
        "icon": app.get("icon", ""),
        "category": app.get("category", ""),
        "file_types": file_types,
        "id": app.get("id", ""),
    }
    with open(resources / "app_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    return app_path


def generate_all_apps(host=None, port=None):
    """Main entry: fetch apps from agent and generate .app bundles."""
    config = load_config()

    if host:
        config["connection"]["host"] = host
    if port:
        config["settings"]["agent_port"] = port

    h = config.get("connection", {}).get("host", "")
    p = config.get("settings", {}).get("agent_port", AGENT_PORT)

    if not h:
        print("❌ No host configured. Run with --host YOUR_NETBIRD_IP")
        print("   or set it in ~/.remote-launch/config.json")
        return

    print(f"🔄 Fetching apps from {h}:{p}...")
    apps = fetch_apps(h, p)

    if not apps:
        print("❌ No apps found. Make sure windows_agent.py is running.")
        return

    print(f"✅ Found {len(apps)} Windows apps")

    # Create /Applications/Remote Apps/
    APPS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old generated apps
    existing = set(p.name for p in APPS_DIR.glob("*.app"))

    created = 0
    skipped = 0
    total_file_types = 0

    for app in apps:
        # Skip UWP apps (don't work well with RemoteApp)
        if app.get("is_uwp"):
            skipped += 1
            continue

        result = create_app_bundle(app, config)
        if result:
            ft_count = len(app.get("file_types", []))
            total_file_types += ft_count
            ft_str = f" [{', '.join(app.get('file_types', [])[:5])}]" if ft_count else ""
            print(f"  ✅ {app['icon']}  {app['name']}{ft_str}")
            created += 1
        else:
            skipped += 1

    # Reset LaunchServices to pick up new apps
    print(f"\n🔄 Resetting LaunchServices database...")
    subprocess.run(
        ["/System/Library/Frameworks/CoreServices.framework/Frameworks/"
         "LaunchServices.framework/Support/lsregister",
         "-kill", "-r", "-domain", "local", "-domain", "system", "-domain", "user"],
        capture_output=True)

    # Also touch the apps dir to force Spotlight reindex
    subprocess.run(["touch", str(APPS_DIR)], capture_output=True)

    print(f"\n{'='*50}")
    print(f"✅ Generated {created} app bundles")
    print(f"📁 Location: {APPS_DIR}")
    print(f"📋 File type associations: {total_file_types} total")
    if skipped:
        print(f"⏭️  Skipped: {skipped}")
    print(f"\n🔍 Apps now searchable in Spotlight!")
    print(f"📌 Drag any app to your Dock for quick access")
    print(f"📄 Double-click .docx/.xlsx/.py files → opens with remote Windows app")
    print(f"\n💡 To set a remote app as default for a file type:")
    print(f"   Right-click any file → Get Info → Open With → choose the (Remote) app")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate macOS .app bundles for Windows apps")
    parser.add_argument("--host", help="Netbird IP of Windows PC")
    parser.add_argument("--port", type=int, help=f"Agent port (default {AGENT_PORT})")
    parser.add_argument("--clean", action="store_true", help="Remove all generated apps first")
    args = parser.parse_args()

    if args.clean and APPS_DIR.exists():
        print(f"🗑  Removing {APPS_DIR}...")
        shutil.rmtree(APPS_DIR)

    generate_all_apps(args.host, args.port)
