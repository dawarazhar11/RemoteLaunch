#Requires -RunAsAdministrator
# RemoteLaunch v2 — Windows Setup
# Enables RDP, opens agent port, configures power settings

Write-Host "`n╔════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🚀 RemoteLaunch v2 — Windows Setup       ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════╝`n" -ForegroundColor Cyan

# Check edition
$edition = (Get-WindowsEdition -Online).Edition
if ($edition -match "Home") {
    Write-Host "⚠️  Windows Home detected — RDP not natively supported." -ForegroundColor Red
    Write-Host "  Upgrade to Pro or use RDP Wrapper (github.com/stascorp/rdpwrap)" -ForegroundColor Yellow
}
else { Write-Host "✅ $edition supports RDP" -ForegroundColor Green }

# Enable RDP
Write-Host "`n[1/4] Enabling Remote Desktop..." -ForegroundColor Yellow
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name "UserAuthentication" -Value 1
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
    Write-Host "  ✅ RDP enabled" -ForegroundColor Green
} catch { Write-Host "  ❌ $_ " -ForegroundColor Red }

# Open firewall for agent port 7891
Write-Host "`n[2/4] Opening firewall for agent (port 7891)..." -ForegroundColor Yellow
try {
    $rule = Get-NetFirewallRule -DisplayName "RemoteLaunch Agent" -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -DisplayName "RemoteLaunch Agent" -Direction Inbound -Protocol TCP -LocalPort 7891 -Action Allow | Out-Null
    }
    Write-Host "  ✅ Port 7891 open" -ForegroundColor Green
} catch { Write-Host "  ⚠️  $_ " -ForegroundColor Yellow }

# Power settings
Write-Host "`n[3/4] Configuring power (prevent sleep)..." -ForegroundColor Yellow
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 30
Write-Host "  ✅ Sleep disabled on AC" -ForegroundColor Green

# Show connection info
Write-Host "`n[4/4] Connection info..." -ForegroundColor Yellow
$netbirdIP = ""
try {
    $nb = Get-NetIPAddress | Where-Object { $_.InterfaceAlias -match "wt0|netbird|Netbird" -and $_.AddressFamily -eq "IPv4" }
    if ($nb) { $netbirdIP = $nb.IPAddress; Write-Host "  ✅ Netbird IP: $netbirdIP" -ForegroundColor Green }
} catch {}
if (-not $netbirdIP) {
    try { $nbStatus = & netbird status 2>$null
        $m = $nbStatus | Select-String -Pattern "(\d+\.\d+\.\d+\.\d+)"
        if ($m) { $netbirdIP = $m.Matches[0].Value; Write-Host "  ✅ Netbird IP: $netbirdIP" -ForegroundColor Green }
    } catch { Write-Host "  ⚠️  Run 'netbird status' to find your IP" -ForegroundColor Yellow }
}

Write-Host "`n════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Hostname:   $env:COMPUTERNAME"
Write-Host "  Username:   $env:USERNAME"
if ($netbirdIP) { Write-Host "  Netbird IP: $netbirdIP  ← Use this on your Mac!" -ForegroundColor Green }
Write-Host ""
Write-Host "Next: Start the agent:" -ForegroundColor Yellow
Write-Host "  python windows_agent.py" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
