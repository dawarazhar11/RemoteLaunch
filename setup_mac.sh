#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# RemoteLaunch v2 — macOS Setup
# Installs FreeRDP, configures system, generates .app bundles
# ─────────────────────────────────────────────────────────────────────
set -e

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
BLUE="\033[34m"
CYAN="\033[36m"
RESET="\033[0m"

echo -e "${BOLD}${BLUE}"
echo "╔════════════════════════════════════════════╗"
echo "║  🚀 RemoteLaunch v2 — macOS Setup         ║"
echo "║  Turn your Mac into a Windows thin client  ║"
echo "╚════════════════════════════════════════════╝"
echo -e "${RESET}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.remote-launch"

# ── Step 1: Homebrew ──
echo -e "${BOLD}[1/5] Checking Homebrew...${RESET}"
if ! command -v brew &>/dev/null; then
    echo -e "${YELLOW}Installing Homebrew...${RESET}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
else
    echo -e "${GREEN}✅ Homebrew found${RESET}"
fi

# ── Step 2: FreeRDP ──
echo -e "\n${BOLD}[2/5] Installing FreeRDP...${RESET}"
if command -v xfreerdp3 &>/dev/null || command -v xfreerdp &>/dev/null; then
    FP=$(which xfreerdp3 2>/dev/null || which xfreerdp 2>/dev/null)
    echo -e "${GREEN}✅ FreeRDP: $FP${RESET}"
else
    echo -e "${YELLOW}Installing FreeRDP via Homebrew...${RESET}"
    brew install freerdp3 2>/dev/null || brew install freerdp
    if command -v xfreerdp3 &>/dev/null; then
        echo -e "${GREEN}✅ FreeRDP3 installed${RESET}"
    elif command -v xfreerdp &>/dev/null; then
        echo -e "${GREEN}✅ FreeRDP installed${RESET}"
    else
        echo -e "${RED}❌ FreeRDP install failed. Try: brew install freerdp${RESET}"
        exit 1
    fi
fi

# ── Step 3: Python check ──
echo -e "\n${BOLD}[3/5] Checking Python...${RESET}"
if command -v python3 &>/dev/null; then
    echo -e "${GREEN}✅ $(python3 --version)${RESET}"
else
    echo -e "${RED}❌ Python 3 required. Install: brew install python${RESET}"
    exit 1
fi

# ── Step 4: Configuration ──
echo -e "\n${BOLD}[4/5] Configuration...${RESET}"
mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_DIR/config.json" ]; then
    echo -e "${GREEN}✅ Config exists at $CONFIG_DIR/config.json${RESET}"
    HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_DIR/config.json')).get('connection',{}).get('host',''))" 2>/dev/null)
else
    HOST=""
fi

if [ -z "$HOST" ]; then
    echo ""
    echo -e "${CYAN}Enter your Windows PC's Netbird IP address:${RESET}"
    read -p "  Netbird IP: " HOST

    echo -e "${CYAN}Enter your Windows username:${RESET}"
    read -p "  Username: " USERNAME

    echo -e "${CYAN}Enter your Windows password (stored locally):${RESET}"
    read -s -p "  Password: " PASSWORD
    echo ""

    python3 -c "
import json
config = {
    'connection': {
        'host': '$HOST',
        'username': '$USERNAME',
        'password': '$PASSWORD',
        'domain': '',
        'port': 3389
    },
    'settings': {
        'agent_port': 7891,
        'extra_flags': '/cert:ignore',
        'columns': 4,
        'theme': 'dark'
    }
}
with open('$CONFIG_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('Config saved!')
"
    echo -e "${GREEN}✅ Config saved to $CONFIG_DIR/config.json${RESET}"
fi

# ── Step 5: Generate .app bundles ──
echo -e "\n${BOLD}[5/5] Generating .app bundles...${RESET}"
echo -e "${YELLOW}Make sure windows_agent.py is running on your Windows PC!${RESET}"
echo ""

if [ -n "$HOST" ]; then
    python3 "$SCRIPT_DIR/generate_apps.py" --host "$HOST"
    RESULT=$?

    if [ $RESULT -ne 0 ]; then
        echo -e "\n${YELLOW}⚠️  Could not reach Windows agent.${RESET}"
        echo -e "  Run this on your Windows PC first:"
        echo -e "    ${BOLD}python windows_agent.py${RESET}"
        echo -e "  Then re-run:"
        echo -e "    ${BOLD}python3 generate_apps.py${RESET}"
    fi
fi

# ── Create the RemoteLaunch control panel .app ──
echo -e "\n${BOLD}Creating RemoteLaunch control panel...${RESET}"
PANEL_APP="$HOME/Applications/RemoteLaunch.app"
mkdir -p "$PANEL_APP/Contents/MacOS" "$PANEL_APP/Contents/Resources"

cp "$SCRIPT_DIR/generate_apps.py" "$PANEL_APP/Contents/Resources/"

cat > "$PANEL_APP/Contents/MacOS/RemoteLaunch" << 'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec python3 "$DIR/../Resources/generate_apps.py"
EOF
chmod +x "$PANEL_APP/Contents/MacOS/RemoteLaunch"

cat > "$PANEL_APP/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>RemoteLaunch</string>
  <key>CFBundleIdentifier</key><string>com.remoteLaunch.generator</string>
  <key>CFBundleName</key><string>RemoteLaunch</string>
  <key>CFBundleDisplayName</key><string>RemoteLaunch Sync</string>
  <key>CFBundleVersion</key><string>2.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF

echo -e "${GREEN}✅ RemoteLaunch Sync app created at ~/Applications/${RESET}"

# ── Summary ──
echo -e "\n${BOLD}${BLUE}════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}✅ Setup Complete!${RESET}"
echo -e "${BOLD}${BLUE}════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Remote Apps:${RESET}     /Applications/Remote Apps/"
echo -e "  ${BOLD}Config:${RESET}          ~/.remote-launch/config.json"
echo -e "  ${BOLD}Sync App:${RESET}        ~/Applications/RemoteLaunch.app"
echo ""
echo -e "${BOLD}${CYAN}How to use:${RESET}"
echo -e "  🔍 Search any Windows app in ${BOLD}Spotlight${RESET} (Cmd+Space)"
echo -e "  📌 Drag apps from /Applications/Remote Apps/ to ${BOLD}Dock${RESET}"
echo -e "  📄 Double-click a .docx → opens in remote ${BOLD}Word${RESET}"
echo -e "  📊 Double-click a .xlsx → opens in remote ${BOLD}Excel${RESET}"
echo ""
echo -e "${BOLD}${CYAN}Set default apps:${RESET}"
echo -e "  Right-click any file → Get Info → Open With"
echo -e "  → Select the (Remote) app → Change All"
echo ""
echo -e "${BOLD}${CYAN}Re-sync apps:${RESET}"
echo -e "  python3 generate_apps.py        # or open RemoteLaunch Sync"
echo ""
echo -e "${BOLD}${YELLOW}Latency tips:${RESET}"
echo -e "  • Both machines on same Netbird network = best latency"
echo -e "  • FreeRDP uses /network:lan + /gfx:RFX + progressive encoding"
echo -e "  • For even lower latency, install Parsec on both + use it alongside"
echo ""
