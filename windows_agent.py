#!/usr/bin/env python3
"""
RemoteLaunch Windows Agent v2
- Scans all installed apps (registry + Start Menu + UWP)
- Serves app list as JSON API
- Accepts file uploads from Mac (for "Open With" functionality)
- Returns file type associations for each app
Run: python windows_agent.py
"""

import http.server
import json
import subprocess
import os
import sys
import threading
import time
import hashlib
import winreg
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
try:
    import cgi
except ImportError:
    cgi = None  # Removed in Python 3.13+

AGENT_PORT = 7891
UPLOAD_DIR = Path.home() / ".remote-launch" / "uploads"
CACHE_FILE = Path.home() / ".remote-launch" / "app_cache.json"

# ─── File extension to app mapping ───────────────────────────────────
# Maps file extensions to the Windows apps that handle them
FILE_TYPE_MAP = {
    # Office
    "docx": ["WINWORD.EXE"], "doc": ["WINWORD.EXE"], "rtf": ["WINWORD.EXE"],
    "xlsx": ["EXCEL.EXE"], "xls": ["EXCEL.EXE"], "csv": ["EXCEL.EXE"],
    "pptx": ["POWERPNT.EXE"], "ppt": ["POWERPNT.EXE"],
    "pdf": ["Acrobat.exe", "AcroRd32.exe", "msedge.exe"],
    # Code
    "py": ["Code.exe", "notepad++.exe"], "js": ["Code.exe", "notepad++.exe"],
    "ts": ["Code.exe"], "jsx": ["Code.exe"], "tsx": ["Code.exe"],
    "html": ["Code.exe", "msedge.exe"], "css": ["Code.exe"],
    "json": ["Code.exe", "notepad++.exe"], "xml": ["Code.exe"],
    "yaml": ["Code.exe"], "yml": ["Code.exe"], "md": ["Code.exe"],
    "c": ["Code.exe"], "cpp": ["Code.exe"], "h": ["Code.exe"],
    "rs": ["Code.exe"], "go": ["Code.exe"], "java": ["Code.exe"],
    "sh": ["Code.exe"], "bat": ["Code.exe", "notepad.exe"],
    "ps1": ["Code.exe", "powershell_ise.exe"],
    "txt": ["Code.exe", "notepad++.exe", "notepad.exe"],
    "log": ["Code.exe", "notepad++.exe", "notepad.exe"],
    "ini": ["notepad++.exe", "notepad.exe"],
    "cfg": ["notepad++.exe", "notepad.exe"],
    # Engineering
    "sldprt": ["SLDWORKS.exe"], "sldasm": ["SLDWORKS.exe"], "slddrw": ["SLDWORKS.exe"],
    "step": ["SLDWORKS.exe", "FreeCAD.exe"], "stp": ["SLDWORKS.exe"],
    "iges": ["SLDWORKS.exe"], "igs": ["SLDWORKS.exe"],
    "stl": ["SLDWORKS.exe", "FreeCAD.exe"],
    "dwg": ["acad.exe", "SLDWORKS.exe"], "dxf": ["acad.exe", "SLDWORKS.exe"],
    "wbpj": ["RunWB2.exe"],  # ANSYS Workbench
    # Images
    "png": ["mspaint.exe", "Photoshop.exe"], "jpg": ["mspaint.exe"],
    "jpeg": ["mspaint.exe"], "bmp": ["mspaint.exe"], "gif": ["mspaint.exe"],
    "svg": ["Code.exe", "inkscape.exe"], "psd": ["Photoshop.exe"],
    "ai": ["Illustrator.exe"],
    # Media
    "mp4": ["wmplayer.exe", "vlc.exe"], "mkv": ["vlc.exe"],
    "avi": ["vlc.exe"], "mp3": ["vlc.exe", "wmplayer.exe"],
    "wav": ["vlc.exe"], "flac": ["vlc.exe"],
    # Archives
    "zip": ["explorer.exe", "7zFM.exe"], "rar": ["7zFM.exe"],
    "7z": ["7zFM.exe"], "tar": ["7zFM.exe"], "gz": ["7zFM.exe"],
}

# ─── Category / icon detection (same as before, condensed) ───────────
CATEGORY_KEYWORDS = {
    "Development": ["visual studio", "code", "python", "node", "git", "docker",
        "jetbrains", "intellij", "pycharm", "sublime", "notepad++", "eclipse",
        "android studio", "postman", "terminal", "cmake", "powershell"],
    "Engineering": ["ansys", "solidworks", "autocad", "catia", "inventor",
        "star-ccm", "comsol", "matlab", "simulink", "altium", "kicad",
        "fluent", "icepak", "mechanical", "spaceclaim", "meshing", "abaqus",
        "fusion 360", "creo", "rhino", "revit"],
    "Office": ["excel", "word", "powerpoint", "outlook", "onenote", "teams",
        "libreoffice", "notion", "obsidian"],
    "Web": ["chrome", "firefox", "edge", "brave", "opera", "vivaldi"],
    "Media": ["vlc", "spotify", "audacity", "obs ", "handbrake", "davinci",
        "premiere", "media player"],
    "Graphics": ["photoshop", "illustrator", "gimp", "inkscape", "paint",
        "blender", "3ds max", "figma", "affinity", "coreldraw"],
    "Communication": ["slack", "discord", "zoom", "skype", "telegram", "webex"],
    "System": ["task manager", "cmd", "command prompt", "powershell",
        "explorer", "file explorer", "registry", "control panel"],
    "Utilities": ["7-zip", "winrar", "everything", "calculator", "snipping",
        "sharex", "autohotkey", "virtualbox", "vmware"],
    "Database": ["sql server", "mysql", "postgresql", "mongodb", "dbeaver",
        "datagrip", "pgadmin", "ssms"],
}

SPECIFIC_ICONS = {
    "chrome": "🌐", "firefox": "🦊", "edge": "🔷", "brave": "🦁",
    "vs code": "💻", "visual studio code": "💻", "visual studio": "🟣",
    "excel": "📊", "word": "📄", "powerpoint": "📽️", "outlook": "📧",
    "teams": "👥", "slack": "💬", "discord": "🎮", "zoom": "📹",
    "spotify": "🎵", "vlc": "🎬", "obs": "📺",
    "photoshop": "🎨", "illustrator": "🖌️", "blender": "🧊",
    "docker": "🐳", "git": "📦", "postman": "📮",
    "ansys": "🔬", "solidworks": "⚙️", "matlab": "📐",
    "autocad": "📏", "altium": "🔌", "star-ccm": "🌊",
    "steam": "🎮", "notepad": "📓", "calculator": "🔢",
    "terminal": "🖥️", "cmd": "🖥️", "powershell": "🖥️",
    "file explorer": "📁", "explorer": "📁", "python": "🐍",
    "7-zip": "🗜️", "winrar": "🗜️", "task manager": "📈", "paint": "🎨",
}

CATEGORY_ICONS = {
    "Development": "💻", "Engineering": "🔬", "Office": "📝", "Web": "🌐",
    "Media": "🎬", "Graphics": "🎨", "Communication": "💬", "System": "⚙️",
    "Utilities": "🔧", "Database": "🗄️", "Security": "🔒", "Games": "🎮",
    "Other": "📦",
}

EXCLUDE_PATTERNS = [
    r"uninstall", r"update", r"helper", r"crash", r"telemetry",
    r"redistributable", r"runtime", r"\.net framework", r"visual c\+\+",
    r"microsoft visual c", r"windows sdk", r"driver", r"nvidia physx",
    r"vulkan", r"openal", r"directx", r"msxml", r"oobe", r"setup\b",
    r"\brepair\b", r"troubleshoot", r"compatibility", r"migration",
]


def categorize(name):
    nl = name.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in nl: return cat
    return "Other"


def get_icon(name):
    nl = name.lower()
    for k, v in SPECIFIC_ICONS.items():
        if k in nl: return v
    return CATEGORY_ICONS.get(categorize(name), "📦")


def should_exclude(name, path=""):
    combined = f"{name} {path}".lower()
    for p in EXCLUDE_PATTERNS:
        if re.search(p, combined, re.IGNORECASE): return True
    return False


def get_file_types_for_app(exe_path):
    """Determine which file extensions this app can open."""
    exe_name = os.path.basename(exe_path).upper()
    types = []
    for ext, handlers in FILE_TYPE_MAP.items():
        for h in handlers:
            if h.upper() == exe_name:
                types.append(ext)
    return types


# ─── App Scanning ────────────────────────────────────────────────────
def scan_registry():
    apps = {}
    paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in paths:
        try:
            key = winreg.OpenKey(hive, path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sk = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    try: name = winreg.QueryValueEx(sk, "DisplayName")[0]
                    except: continue
                    if not name or should_exclude(name): continue
                    exe = ""
                    for vn in ["DisplayIcon", "InstallLocation"]:
                        try:
                            val = winreg.QueryValueEx(sk, vn)[0]
                            if vn == "DisplayIcon":
                                exe = val.split(",")[0].strip().strip('"')
                            elif os.path.isdir(val):
                                for f in os.listdir(val):
                                    if f.lower().endswith(".exe") and not should_exclude(f):
                                        exe = os.path.join(val, f); break
                        except: continue
                    if exe and os.path.isfile(exe):
                        aid = hashlib.md5(exe.lower().encode()).hexdigest()[:8]
                        cat = categorize(name)
                        apps[aid] = {
                            "id": aid, "name": name.strip(), "path": exe,
                            "icon": get_icon(name), "category": cat,
                            "file_types": get_file_types_for_app(exe),
                            "source": "registry",
                        }
                    winreg.CloseKey(sk)
                except: continue
            winreg.CloseKey(key)
        except: continue
    return apps


def scan_start_menu():
    apps = {}
    for mp in [
        os.path.join(os.environ.get("ProgramData", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
    ]:
        if not os.path.isdir(mp): continue
        for root, dirs, files in os.walk(mp):
            for f in files:
                if not f.lower().endswith(".lnk"): continue
                name = os.path.splitext(f)[0]
                if should_exclude(name): continue
                try:
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         f"(New-Object -ComObject WScript.Shell).CreateShortcut('{os.path.join(root, f)}').TargetPath"],
                        capture_output=True, text=True, timeout=5)
                    target = r.stdout.strip().strip('"')
                    if target and os.path.isfile(target) and target.lower().endswith(".exe"):
                        if should_exclude(name, target): continue
                        aid = hashlib.md5(target.lower().encode()).hexdigest()[:8]
                        if aid not in apps:
                            cat = categorize(name)
                            rel = os.path.relpath(root, mp)
                            if rel != "." and cat == "Other": cat = rel.split(os.sep)[0]
                            apps[aid] = {
                                "id": aid, "name": name.strip(), "path": target,
                                "icon": get_icon(name), "category": cat,
                                "file_types": get_file_types_for_app(target),
                                "source": "start_menu",
                            }
                except: continue
    return apps


def discover_all():
    print("[Agent] Scanning installed applications...")
    all_apps = {}
    reg = scan_registry()
    all_apps.update(reg)
    print(f"  Registry: {len(reg)}")
    sm = scan_start_menu()
    for aid, app in sm.items():
        if aid not in all_apps: all_apps[aid] = app
        elif len(app["name"]) < len(all_apps[aid]["name"]): all_apps[aid]["name"] = app["name"]
    print(f"  Start Menu: {len(sm)}")
    print(f"  Total: {len(all_apps)} apps")
    return dict(sorted(all_apps.items(), key=lambda x: x[1]["name"].lower()))


# ─── Cache ───────────────────────────────────────────────────────────
class AppCache:
    def __init__(self):
        self.apps = {}
        self.last_scan = 0
        self.lock = threading.Lock()

    def get(self, refresh=False):
        with self.lock:
            if refresh or time.time() - self.last_scan > 300 or not self.apps:
                self.apps = discover_all()
                self.last_scan = time.time()
                CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_FILE, "w") as f:
                    json.dump(self.apps, f, indent=2)
        return self.apps

cache = AppCache()


# ─── HTTP Server ─────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print(f"[HTTP] {args[0]}")

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _parse_multipart(self, content_type, content_length):
        """Parse multipart/form-data without the deprecated cgi module."""
        if cgi is not None:
            form = cgi.FieldStorage(
                fp=self.rfile, headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type})
            file_item = form["file"]
            if file_item.filename:
                return (file_item.filename, file_item.file.read())
            return None
        # Manual parsing for Python 3.13+
        body = self.rfile.read(content_length)
        boundary = content_type.split("boundary=")[-1].strip().encode()
        parts = body.split(b"--" + boundary)
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header_section = part[:header_end].decode(errors="replace")
            data = part[header_end + 4:]
            if data.endswith(b"\r\n"):
                data = data[:-2]
            if 'name="file"' in header_section or "filename=" in header_section:
                fn_match = re.search(r'filename="([^"]+)"', header_section)
                if fn_match:
                    return (fn_match.group(1), data)
        return None

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)

        if p.path == "/api/apps":
            apps = cache.get("refresh" in q)
            al = list(apps.values())
            cat = q.get("category", [None])[0]
            if cat: al = [a for a in al if a["category"] == cat]
            s = q.get("search", [None])[0]
            if s:
                sl = s.lower()
                al = [a for a in al if sl in a["name"].lower() or sl in a["category"].lower()]
            self._json({
                "status": "ok", "count": len(al), "apps": al,
                "hostname": os.environ.get("COMPUTERNAME", ""),
                "username": os.environ.get("USERNAME", ""),
            })

        elif p.path == "/api/status":
            self._json({
                "status": "ok",
                "hostname": os.environ.get("COMPUTERNAME", ""),
                "username": os.environ.get("USERNAME", ""),
                "app_count": len(cache.get()),
                "upload_dir": str(UPLOAD_DIR),
                "version": "2.0",
            })

        elif p.path == "/api/refresh":
            apps = cache.get(True)
            self._json({"status": "ok", "count": len(apps)})

        elif p.path == "/api/enable-remoteapp":
            ok = enable_remoteapp()
            self._json({"status": "ok" if ok else "error",
                         "message": "RemoteApp allowlist disabled" if ok else "Failed — run agent as Admin"})

        elif p.path.startswith("/api/download/"):
            # Download a file from upload dir
            fname = p.path.split("/api/download/", 1)[1]
            fpath = UPLOAD_DIR / fname
            if fpath.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(fpath.stat().st_size))
                self.end_headers()
                with open(fpath, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            else:
                self._json({"error": "File not found"}, 404)
        else:
            self._json({
                "service": "RemoteLaunch Agent v2",
                "endpoints": ["/api/apps", "/api/status", "/api/refresh",
                              "POST /api/upload", "POST /api/launch",
                              "/api/download/<filename>"]
            })

    def do_POST(self):
        if self.path == "/api/upload":
            # Accept file upload from Mac, return Windows path
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))

            if "multipart/form-data" in content_type:
                parsed = self._parse_multipart(content_type, content_length)
                if parsed:
                    filename, data = parsed
                    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                    safe_name = os.path.basename(filename)
                    dest = UPLOAD_DIR / safe_name
                    with open(dest, "wb") as f:
                        f.write(data)
                    self._json({
                        "status": "ok",
                        "filename": safe_name,
                        "windows_path": str(dest),
                        "size": dest.stat().st_size,
                    })
                    return
            elif content_length > 0:
                # Simple binary upload with filename in header
                filename = self.headers.get("X-Filename", "uploaded_file")
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                safe_name = os.path.basename(filename)
                dest = UPLOAD_DIR / safe_name
                with open(dest, "wb") as f:
                    remaining = content_length
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 65536))
                        if not chunk: break
                        f.write(chunk)
                        remaining -= len(chunk)
                self._json({
                    "status": "ok",
                    "filename": safe_name,
                    "windows_path": str(dest),
                    "size": dest.stat().st_size,
                })
                return

            self._json({"error": "No file provided"}, 400)

        elif self.path == "/api/launch":
            # Launch an app on Windows (called from Mac launcher)
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(body.decode())
            except:
                self._json({"error": "Invalid JSON"}, 400)
                return
            app_path = data.get("path", "")
            file_arg = data.get("file", "")
            if not app_path:
                self._json({"error": "Missing 'path'"}, 400)
                return
            if not os.path.isfile(app_path):
                self._json({"error": f"App not found: {app_path}"}, 404)
                return
            try:
                cmd = [app_path]
                if file_arg:
                    cmd.append(file_arg)
                subprocess.Popen(cmd, shell=False,
                                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
                self._json({"status": "ok", "launched": app_path, "file": file_arg})
            except Exception as e:
                self._json({"error": str(e)}, 500)

        else:
            self._json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


def enable_remoteapp():
    """Enable RemoteApp for all apps on Windows Pro by disabling the allowlist check."""
    try:
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList"
        key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        winreg.SetValueEx(key, "fDisabledAllowList", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[Agent] Warning: Could not enable RemoteApp allowlist: {e}")
        print(f"[Agent] Try running the agent as Administrator")
        return False


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[Agent] RemoteLaunch Agent v2.0")
    print(f"[Agent] Upload dir: {UPLOAD_DIR}")
    if enable_remoteapp():
        print(f"[Agent] RemoteApp allowlist disabled (all apps allowed)")
    cache.get(True)
    server = http.server.HTTPServer(("0.0.0.0", AGENT_PORT), Handler)
    print(f"[Agent] Listening on http://0.0.0.0:{AGENT_PORT}")
    print(f"[Agent] Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Agent] Stopped.")
