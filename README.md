# 🚀 RemoteLaunch v2

**Every Windows app becomes a real macOS app.** Spotlight, Launchpad, Dock, file associations — all native.

Double-click a `.docx` on your Mac → file uploads to Windows → opens in remote Word as its own window. Your MacBook stays a lightweight streaming terminal.

## How It Works

```
┌─ MacBook Air M2 (thin client) ────────────────────────────────────────┐
│                                                                        │
│  /Applications/Remote Apps/                                            │
│    ├── Microsoft Word.app        ← appears in Spotlight, Launchpad    │
│    ├── Microsoft Excel.app       ← drag to Dock                       │
│    ├── VS Code.app               ← double-click .py → opens here      │
│    ├── ANSYS Workbench.app       ← double-click .wbpj → opens here   │
│    ├── SolidWorks.app                                                  │
│    └── ... (every installed Windows app)                               │
│                                                                        │
│  User double-clicks report.docx on Mac:                                │
│    1. Launcher uploads report.docx to Windows via HTTP                 │
│    2. FreeRDP opens Word in RemoteApp mode (seamless window)           │
│    3. Word opens with the uploaded file                                │
│    4. Mac just streams the display — zero CPU/RAM used                 │
│                                                                        │
└──── Netbird VPN ───────────────────────────────────────────────────────┘
                           │
┌─ Windows PC (64GB RAM) ──┘─────────────────────────────────────────────┐
│                                                                        │
│  windows_agent.py (port 7891)                                          │
│    - Scans Registry + Start Menu → finds all installed apps            │
│    - Serves app list as JSON API                                       │
│    - Accepts file uploads from Mac                                     │
│    - Returns Windows path for uploaded files                           │
│                                                                        │
│  RDP Server (port 3389)                                                │
│    - Runs each app in RemoteApp mode (seamless window, no desktop)     │
│    - Streams via AVC444/RFX with progressive encoding                  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Windows PC — one-line deploy (PowerShell Admin)

Paste this into an **elevated PowerShell** window:

```powershell
irm https://raw.githubusercontent.com/dawarazhar11/RemoteLaunch/main/windows_setup.ps1 -OutFile $env:TEMP\ws.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\ws.ps1; irm https://raw.githubusercontent.com/dawarazhar11/RemoteLaunch/main/windows_agent.py -OutFile $env:USERPROFILE\windows_agent.py; python $env:USERPROFILE\windows_agent.py
```

Or step by step:

```powershell
# 1. Enable RDP + open firewall (run as Admin)
powershell -ExecutionPolicy Bypass -File windows_setup.ps1

# 2. Start the agent (keep running)
python windows_agent.py
```

Output:
```
[Agent] Registry: 52
[Agent] Start Menu: 71
[Agent] Total: 87 apps
[Agent] Listening on http://0.0.0.0:7891
```

### Mac — one-line deploy (Terminal)

Paste this into **Terminal**:

```bash
curl -fsSL https://raw.githubusercontent.com/dawarazhar11/RemoteLaunch/main/setup_mac.sh | bash
```

Or step by step:

```bash
git clone https://github.com/dawarazhar11/RemoteLaunch.git && cd RemoteLaunch
chmod +x setup_mac.sh
./setup_mac.sh
```

This will:
1. Install FreeRDP via Homebrew
2. Ask for your Netbird IP + Windows credentials
3. Fetch all Windows apps from the agent
4. Generate individual `.app` bundles in `/Applications/Remote Apps/`
5. Register file type associations
6. Reset LaunchServices so Spotlight finds them immediately

### That's it. Now:

- **⌘ + Space** → type "Word" → your remote Word appears in Spotlight
- **Double-click** any `.docx` → uploads to Windows → opens in remote Word
- **Drag** any app from `/Applications/Remote Apps/` to your **Dock**
- **Right-click** a file → **Open With** → pick the `(Remote)` version

## Setting Default Apps for File Types

Want `.docx` files to ALWAYS open with remote Word?

1. Right-click any `.docx` file in Finder
2. Click **Get Info**
3. Under **Open with:** select **Microsoft Word (Remote)**
4. Click **Change All...**

Now every `.docx` automatically goes to your Windows PC.

## File Flow

When you open a file with a remote app:

```
Mac: ~/Downloads/report.docx
  ↓ HTTP POST to agent
Windows: C:\Users\You\.remote-launch\uploads\report.docx
  ↓ FreeRDP RemoteApp launches
Word.exe opens report.docx in seamless window on Mac
```

## Files

| File | Where | What |
|------|-------|------|
| `windows_agent.py` | Windows | Scans apps + handles file uploads |
| `windows_setup.ps1` | Windows | Enables RDP, firewall, power settings |
| `generate_apps.py` | Mac | Creates .app bundles with file associations |
| `setup_mac.sh` | Mac | Full Mac setup (FreeRDP + config + generate) |

## Xpra Mode (Per-App Windows)

Xpra forwards **individual Windows app windows** to your Mac — each app appears as its own native macOS window. No full desktop, no session conflicts. This is the recommended mode.

### Windows — one-line Xpra server start (PowerShell Admin)

```powershell
xpra shadow --bind-tcp=0.0.0.0:10000
```

To also open firewall for port 10000:
```powershell
New-NetFirewallRule -DisplayName "Xpra" -Direction Inbound -Protocol TCP -LocalPort 10000 -Action Allow; xpra shadow --bind-tcp=0.0.0.0:10000
```

### Mac — connect to Xpra server

```bash
brew install --cask xpra
xpra attach tcp://NETBIRD_IP:10000
```

Each Windows app window appears as a separate macOS window with clipboard, audio, and file transfer built-in.

### Xpra vs RDP vs Parsec

| Protocol | Per-App Windows | Latency | Clipboard/Audio |
|----------|:-:|:-:|:-:|
| **Xpra (NVENC)** | Yes | ~15-25ms | Built-in |
| **Parsec** | No (full desktop) | ~5-15ms | Yes |
| **Sunshine/Moonlight** | No (full desktop) | ~5-15ms | Limited |
| **FreeRDP RemoteApp** | Unreliable on Win Pro | ~15-30ms | Yes |

### Hybrid approach

Use both:
- **Xpra** for productivity apps (Word, Excel, VS Code, ANSYS) — per-app windows, Spotlight
- **Parsec/Sunshine** for latency-critical stuff (media editing, gaming) — hardware encoding

## Latency Optimization

The FreeRDP launcher scripts use these flags for minimum latency:

| Flag | Purpose |
|------|---------|
| `/network:lan` | Optimizes for LAN — disables WAN throttling |
| `/gfx:RFX:on` | RemoteFX codec — lowest latency for LAN |
| `/compression-level:2` | Light compression — faster than heavy |
| `+dynamic-resolution` | Match Mac display resolution |
| `+clipboard` | Shared clipboard between Mac and Windows |
| `+home-drive` | Maps Mac home folder to Windows |
| `/audio-mode:0` | Local audio playback |
| `/cert:ignore` | Skip certificate prompts |
| `/ipv4` | Force IPv4 (fixes Netbird routing) |

## Re-syncing Apps

When you install new software on Windows:

```bash
# On Mac:
python3 generate_apps.py

# Or open the RemoteLaunch Sync app (in ~/Applications/)
```

To force a clean rebuild:
```bash
python3 generate_apps.py --clean
```

## Agent API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/apps` | GET | All discovered apps |
| `/api/apps?search=code` | GET | Search apps |
| `/api/apps?refresh` | GET | Force rescan |
| `/api/status` | GET | Agent health check |
| `/api/upload` | POST | Upload file from Mac |
| `/api/launch` | POST | Launch an app on Windows `{"path":"...","file":"..."}` |
| `/api/enable-remoteapp` | GET | Enable RemoteApp allowlist bypass |
| `/api/download/<file>` | GET | Download file back |

## Running Agent as Windows Service

```powershell
# Task Scheduler (auto-start on boot)
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\path\to\windows_agent.py"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "RemoteLaunch Agent" -Action $action -Trigger $trigger -RunLevel Highest
```

## Troubleshooting

**"FreeRDP not found"**
```bash
brew install freerdp3  # or brew install freerdp
```

**Agent not reachable**
```bash
# Test from Mac:
curl http://NETBIRD_IP:7891/api/status

# Check Windows firewall allows port 7891
# Check Netbird is connected on both machines
```

**App opens full desktop instead of seamless window**
- Requires **Windows Pro** (not Home)
- Use FreeRDP **v3** (`brew install freerdp3`) — better RemoteApp support
- Some apps (browsers) don't support RemoteApp well

**Spotlight doesn't find apps**
```bash
# Force LaunchServices refresh:
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain user
```

**File upload fails**
- Make sure `windows_agent.py` is running
- Test: `curl -X POST -H "X-Filename: test.txt" --data "hello" http://NETBIRD_IP:7891/api/upload`

## Requirements

- **macOS 12+** with Python 3.8+, Homebrew
- **Windows Pro/Enterprise** with Python 3.8+
- **Netbird** connected on both machines
- **For RDP mode**: FreeRDP (`brew install freerdp`), RDP enabled on Windows
- **For Xpra mode** (recommended): Xpra on both machines (`brew install --cask xpra` / MSI from [xpra.org](https://xpra.org/dists/windows/))
