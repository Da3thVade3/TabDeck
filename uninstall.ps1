<#
.SYNOPSIS
  Cleanly uninstalls TabDeck installed via install.ps1.
  Run via: irm https://raw.githubusercontent.com/Da3thVade3/TabDeck/main/uninstall.ps1 | iex
#>
$ErrorActionPreference = "SilentlyContinue"
Write-Host "Stopping TabDeck..."
Get-Process -Name "TabDeck" | Stop-Process -Force
Start-Sleep -Milliseconds 400

$paths = @(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\TabDeck.lnk"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\TabDeck.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "TabDeck.lnk"),
    (Join-Path $env:LOCALAPPDATA "TabDeck")
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        Remove-Item -Path $p -Recurse -Force
        Write-Host "Removed $p"
    }
}
Write-Host "TabDeck has been uninstalled." -ForegroundColor Green
