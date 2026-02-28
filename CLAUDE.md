# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RemoteLaunch v2 turns a Mac into a thin client for a Windows PC. It creates native macOS `.app` bundles for every installed Windows application so they appear in Spotlight, Launchpad, and Dock. Double-clicking a file (e.g. `.docx`) on Mac uploads it to the Windows agent via HTTP, then launches the Windows app in FreeRDP RemoteApp mode (seamless window, no full desktop). Connectivity is over Netbird VPN.

## Architecture

Two-machine system with no shared codebase — the Mac side and Windows side are independent Python scripts communicating over HTTP:

**Windows side** (`windows_agent.py`):
- HTTP server on port 7891 using stdlib `http.server`
- Discovers installed apps by scanning the Windows Registry (`HKLM/HKCU Uninstall` keys) and Start Menu `.lnk` shortcuts (resolved via PowerShell COM)
- Apps are deduplicated by MD5 hash of the exe path and cached in `~/.remote-launch/app_cache.json` (5-minute TTL)
- File uploads land in `~/.remote-launch/uploads/` and return the Windows path for FreeRDP to pass as an argument
- `FILE_TYPE_MAP` dict maps file extensions to exe names to determine which app handles which file types

**Mac side** (`generate_apps.py`):
- Fetches app list JSON from the Windows agent's `/api/apps` endpoint
- Creates individual `.app` bundles under `/Applications/Remote Apps/`, each containing:
  - `Info.plist` with `CFBundleDocumentTypes` for file type associations (UTIs from `FILE_TYPE_UTIS` dict)
  - `MacOS/launch` bash script that handles file upload + FreeRDP invocation
- Resets LaunchServices DB after generation so Spotlight picks up the new apps
- Config stored in `~/.remote-launch/config.json` (host, credentials, RDP port, extra flags)

**Setup scripts**:
- `setup_mac.sh` — installs Homebrew/FreeRDP, prompts for credentials, writes config, runs `generate_apps.py`, creates a `~/Applications/RemoteLaunch.app` sync utility
- `windows_setup.ps1` — enables RDP, opens firewall port 7891, disables sleep, detects Netbird IP

## Key Commands

```bash
# Windows: start the agent
python windows_agent.py

# Windows: one-time setup (run as Admin)
powershell -ExecutionPolicy Bypass -File windows_setup.ps1

# Mac: full setup (interactive, prompts for IP/credentials)
chmod +x setup_mac.sh && ./setup_mac.sh

# Mac: regenerate app bundles (after installing new Windows software)
python3 generate_apps.py --host <NETBIRD_IP>

# Mac: clean rebuild of all app bundles
python3 generate_apps.py --clean
```

## Agent API (port 7891)

- `GET /api/apps` — all discovered apps (supports `?search=`, `?category=`, `?refresh`)
- `GET /api/status` — health check
- `GET /api/refresh` — force app rescan
- `POST /api/upload` — file upload (binary with `X-Filename` header, or multipart)
- `GET /api/download/<filename>` — retrieve uploaded file

## Important Details

- The generated launcher scripts handle both FreeRDP v2 (`xfreerdp`) and v3 (`xfreerdp3`) with different RemoteApp flag syntax (`/app:` vs `/app:program:`)
- UWP apps are skipped during generation (they don't work with RemoteApp)
- The `EXCLUDE_PATTERNS` regex list in `windows_agent.py` filters out uninstallers, update helpers, runtimes, etc.
- All Python files use only stdlib — no pip dependencies on either side
- The `remote-launch/` subdirectory contains the same files as the root (extracted from `remote-launch.zip`)
