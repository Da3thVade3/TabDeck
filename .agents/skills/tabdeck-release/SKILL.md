---
name: tabdeck-release
description: Build, privacy-audit, test, and publish a TabDeck release (Android Debug/Release APKs, standalone Windows ZIP, WinGet manifest validation, and GitHub Release upload). Use when preparing or updating a TabDeck version.
---

# TabDeck Release Workflow

## 1. Bump Version (if cutting a new tag)
- Update `android:versionCode` and `android:versionName` in `android-app/AndroidManifest.xml`.
- Update version references in `README.md` and `winget/manifests/d/Da3thVade3/TabDeck/<version>/`.

## 2. Build Android Debug & Release APKs
```powershell
.\android-app\build_apk.ps1 -Variant all
```
Outputs:
- `android-app/dist/TabDeck-release.apk` (`com.tabdeck.app`)
- `android-app/dist/TabDeck-debug.apk` (`com.tabdeck.app.debug`, installs side-by-side)

## 3. Build & Privacy-Audit Standalone Windows Package
```powershell
.\launcher\build_windows_release.ps1 -Version <version>
```
This builds `dist/TabDeck/TabDeck.exe` via PyInstaller, runs a binary + ZIP privacy scan across every packaged file, and outputs `dist/TabDeck-Windows-v<version>.zip`.

## 4. Update & Validate WinGet Manifest
Compute the SHA-256 of `dist/TabDeck-Windows-v<version>.zip`, update `InstallerSha256` and `InstallerUrl` in the manifest under `winget/manifests/d/Da3thVade3/TabDeck/<version>/`, and validate:
```powershell
(Get-FileHash .\dist\TabDeck-Windows-v<version>.zip -Algorithm SHA256).Hash
winget validate --manifest .\winget\manifests\d\Da3thVade3\TabDeck\<version>
```

## 5. Publish to GitHub
```powershell
git status
git add -A
git commit -m "Release v<version>"
git push origin main
gh release create v<version> `
  .\dist\TabDeck-Windows-v<version>.zip `
  .\android-app\dist\TabDeck-release.apk `
  .\android-app\dist\TabDeck-debug.apk `
  --title "TabDeck v<version>"
```
(Use `gh release upload v<version> ... --clobber` to refresh assets on an existing tag.)
