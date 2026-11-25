<#
.SYNOPSIS
  TabDeck Plug-and-Play Windows Installer
  Run via: irm https://raw.githubusercontent.com/Da3thVade3/TabDeck/main/install.ps1 | iex
#>
$ErrorActionPreference = "Stop"

$Repo = "Da3thVade3/TabDeck"
$InstallDir = Join-Path $env:LOCALAPPDATA "TabDeck"
$StartMenuLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\TabDeck.lnk"
$DesktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "TabDeck.lnk"

Write-Host ""
Write-Host "=== TabDeck Plug-and-Play Installer ===" -ForegroundColor Cyan

# 1. Fetch latest release asset URL from GitHub
Write-Host "[1/4] Finding latest TabDeck Windows release..."
$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "TabDeck-Installer" }
$asset = $rel.assets | Where-Object { $_.name -like "TabDeck-Windows-*.zip" } | Select-Object -First 1
if (-not $asset) {
    throw "Could not find a TabDeck-Windows-*.zip asset in the latest GitHub release."
}

$tmpZip = Join-Path $env:TEMP $asset.name
Write-Host "[2/4] Downloading $($asset.name) ($([math]::Round($asset.size / 1MB, 1)) MB)..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmpZip -UseBasicParsing

# 2. Stop any running instance and preserve existing user configs on upgrade
Get-Process -Name "TabDeck" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 400

$backupCfg = $null
$backupMc = $null
if (Test-Path "$InstallDir\config.json") { $backupCfg = Get-Content "$InstallDir\config.json" -Raw }
if (Test-Path "$InstallDir\multicontrol.json") { $backupMc = Get-Content "$InstallDir\multicontrol.json" -Raw }

Write-Host "[3/4] Installing to $InstallDir..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Expand-Archive -Path $tmpZip -DestinationPath $InstallDir -Force
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue

if ($backupCfg) { Set-Content -Path "$InstallDir\config.json" -Value $backupCfg -Encoding UTF8 }
if ($backupMc) { Set-Content -Path "$InstallDir\multicontrol.json" -Value $backupMc -Encoding UTF8 }

# 3. Create Start Menu & Desktop shortcuts
Write-Host "[4/4] Creating Start Menu & Desktop shortcuts..."
$ws = New-Object -ComObject WScript.Shell
foreach ($lnk in @($StartMenuLnk, $DesktopLnk)) {
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = "$InstallDir\TabDeck.exe"
    $s.WorkingDirectory = $InstallDir
    $s.IconLocation = "$InstallDir\TabDeck.exe,0"
    $s.Description = "TabDeck — Stream Deck, Touchscreen, S-Pen & Multi Control"
    $s.Save()
}

Write-Host ""
Write-Host "TabDeck ($($rel.tag_name)) installed successfully!" -ForegroundColor Green
Write-Host "Launching TabDeck in your Windows System Tray..." -ForegroundColor Cyan
Start-Process -FilePath "$InstallDir\TabDeck.exe" -WorkingDirectory $InstallDir
Write-Host ""
Write-Host "Next step: Right-click the TabDeck icon in your System Tray (near the clock)"
Write-Host "           -> 'Enable Wi-Fi Access (Allow Firewall)' so your tablet/phone connects over Wi-Fi."
Write-Host ""
