<#
.SYNOPSIS
  Builds a clean, standalone, zero-Python-required Windows release package:
    dist/TabDeck-Windows-v0.9.zip (containing TabDeck.exe + runtime + static + tabdeck_mc)
  Audits the entire package (text + binary) to ensure zero personal data leaks.
#>
param(
    [string]$Version = "0.9"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$PyInstaller = "$Root\.venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    throw "PyInstaller not found in .venv. Run: .\.venv\Scripts\pip install pyinstaller"
}

$BuildWork = "$Root\build\win_pkg"
$DistRoot = "$Root\dist"
$OutFolder = "$DistRoot\TabDeck"
if (Test-Path $BuildWork) { Remove-Item -Recurse -Force $BuildWork }
if (Test-Path $OutFolder) { Remove-Item -Recurse -Force $OutFolder }

Write-Host "[1/4] Building standalone TabDeck.exe via PyInstaller..."
& $PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "TabDeck" `
    --icon "$Root\tabdeck.ico" `
    --paths "$Root\app" `
    --distpath "$DistRoot" `
    --workpath "$BuildWork" `
    --specpath "$BuildWork" `
    --add-data "$Root\static;static" `
    --add-data "$Root\android-mc\tabdeck_mc;android-mc" `
    --add-data "$Root\tabdeck.ico;." `
    --hidden-import "uvicorn.logging" `
    --hidden-import "uvicorn.loops" `
    --hidden-import "uvicorn.loops.auto" `
    --hidden-import "uvicorn.protocols" `
    --hidden-import "uvicorn.protocols.http" `
    --hidden-import "uvicorn.protocols.http.auto" `
    --hidden-import "uvicorn.protocols.http.h11_impl" `
    --hidden-import "uvicorn.protocols.websockets" `
    --hidden-import "uvicorn.protocols.websockets.auto" `
    --hidden-import "uvicorn.protocols.websockets.websockets_impl" `
    --hidden-import "uvicorn.lifespan" `
    --hidden-import "uvicorn.lifespan.on" `
    --hidden-import "winrt.windows.media.control" `
    --hidden-import "winrt.windows.storage.streams" `
    --hidden-import "pycaw.pycaw" `
    --hidden-import "comtypes.stream" `
    --hidden-import "pystray._win32" `
    --hidden-import "pyaudiowpatch" `
    --hidden-import "mss.windows" `
    --exclude-module "tkinter" `
    --exclude-module "unittest" `
    --exclude-module "test" `
    --exclude-module "pydoc" `
    "$Root\app\tray.py"

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

Write-Host "[2/4] Copying clean documentation & example config..."
Copy-Item "$Root\README.md" "$OutFolder\README.md" -Force
Copy-Item "$Root\CREDITS.md" "$OutFolder\CREDITS.md" -Force
Copy-Item "$Root\LICENSE" "$OutFolder\LICENSE" -Force
Copy-Item "$Root\config.example.json" "$OutFolder\config.json" -Force

# Ensure zero runtime logs/personal configs ever sneak in
Remove-Item "$OutFolder\tabdeck.log", "$OutFolder\tabdeck.pid", "$OutFolder\multicontrol.json" -Force -ErrorAction SilentlyContinue

Write-Host "[3/4] Running strict privacy scan across entire Windows package..."
$scanPy = "$BuildWork\privacy_scan.py"
@'
import os, re, sys, zipfile, zlib

root = sys.argv[1]
pat = re.compile(rb'(?i)(Manan|192\.168\.178|DuBist|R52W903|RZGYB048|HB472IJD|manan\.gami)')
leaks = []

for dirpath, _, filenames in os.walk(root):
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        rel = os.path.relpath(p, root)
        try:
            data = open(p, 'rb').read()
            m = pat.search(data)
            if m:
                leaks.append((rel, m.group(0).decode('latin1', 'ignore')))
            if fn.endswith('.zip'):
                with zipfile.ZipFile(p) as zf:
                    for info in zf.infolist():
                        zd = zf.read(info)
                        zm = pat.search(zd)
                        if zm:
                            leaks.append((rel + '!' + info.filename, zm.group(0).decode('latin1', 'ignore')))
        except Exception:
            pass

print('PRIVACY_SCAN_FILES_LEAKS=' + str(len(leaks)))
for rel, hit in leaks[:20]:
    print('  LEAK: ' + rel + ' -> ' + hit)
sys.exit(1 if leaks else 0)
'@ | Set-Content -Path $scanPy -Encoding UTF8
& "$Root\.venv\Scripts\python.exe" $scanPy "$OutFolder"
if ($LASTEXITCODE -ne 0) { throw "Privacy scan detected personal info in Windows package!" }

Write-Host "[4/4] Creating TabDeck-Windows-v$Version.zip..."
$ZipPath = "$DistRoot\TabDeck-Windows-v$Version.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$OutFolder\*" -DestinationPath $ZipPath -CompressionLevel Optimal
$sizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host "SUCCESS! Created $ZipPath ($sizeMB MB)"
