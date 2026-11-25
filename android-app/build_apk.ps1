<#
.SYNOPSIS
  Builds both ultra-compact TabDeck Android APKs:
    - android-app/dist/TabDeck-debug.apk   (com.tabdeck.app.debug, debuggable, WebView DevTools enabled)
    - android-app/dist/TabDeck-release.apk (com.tabdeck.app, production optimized)

.NOTES
  Requires Android SDK (build-tools + platform jar) and JDK 11+ (or Android Studio JBR).
  Optionally set TABDECK_KS_PASS for the local release keystore password.
#>
param(
    [ValidateSet("all", "debug", "release")]
    [string]$Variant = "all"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "$env:LOCALAPPDATA\Android\Sdk" }

$BuildTools = Get-ChildItem "$Sdk\build-tools" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
$PlatformDir = Get-ChildItem "$Sdk\platforms" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $BuildTools -or -not $PlatformDir) {
    throw "Android SDK build-tools or platforms not found under $Sdk"
}
$AndroidJar = "$PlatformDir\android.jar"

$JavaBin = $null
foreach ($cand in @(
    "$env:ProgramFiles\Android\Android Studio\jbr\bin",
    "$env:JAVA_HOME\bin"
)) {
    if ($cand -and (Test-Path "$cand\javac.exe")) {
        $JavaBin = $cand
        $env:JAVA_HOME = Split-Path $cand -Parent
        break
    }
}
if (-not $JavaBin) { throw "JDK / Android Studio JBR not found (set JAVA_HOME)." }

$DistDir = "$Root\dist"
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

function Build-Variant([string]$Mode) {
    $isDebug = ($Mode -eq "debug")
    $BuildDir = "$Root\build\$Mode"
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
    New-Item -ItemType Directory -Force -Path "$BuildDir\gen", "$BuildDir\classes", "$BuildDir\dex" | Out-Null

    # Prepare variant-specific AndroidManifest.xml
    $manifestText = Get-Content "$Root\AndroidManifest.xml" -Raw
    if ($isDebug) {
        $manifestText = $manifestText -replace 'android:label="TabDeck"', 'android:label="TabDeck Debug"'
        $manifestText = $manifestText -replace '<application', '<application android:debuggable="true"'
    } else {
        $manifestText = $manifestText -replace '<application', '<application android:debuggable="false"'
    }
    $variantManifest = "$BuildDir\AndroidManifest.xml"
    [System.IO.File]::WriteAllText($variantManifest, $manifestText, [System.Text.UTF8Encoding]::new($false))

    Write-Host "[$Mode] 1/6 Compiling resources..."
    & "$BuildTools\aapt2.exe" compile --dir "$Root\res" -o "$BuildDir\res.zip"
    if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed" }

    Write-Host "[$Mode] 2/6 Linking resources & manifest..."
    $linkArgs = @(
        "link", "-I", $AndroidJar,
        "--manifest", $variantManifest,
        "--java", "$BuildDir\gen",
        "-o", "$BuildDir\unaligned.apk",
        "$BuildDir\res.zip"
    )
    if ($isDebug) {
        $linkArgs += @("--rename-manifest-package", "com.tabdeck.app.debug")
    }
    & "$BuildTools\aapt2.exe" @linkArgs
    if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed" }

    Write-Host "[$Mode] 3/6 Compiling Java..."
    $JavaFiles = @(Get-ChildItem -Recurse -Filter *.java "$BuildDir\gen", "$Root\src" | ForEach-Object { $_.FullName })
    $javacFlag = if ($isDebug) { "-g" } else { "-g:none" }
    & "$JavaBin\javac.exe" --release 11 $javacFlag -classpath $AndroidJar -d "$BuildDir\classes" @JavaFiles
    if ($LASTEXITCODE -ne 0) { throw "javac failed" }

    Write-Host "[$Mode] 4/6 Converting to DEX..."
    $ClassFiles = @(Get-ChildItem -Recurse -Filter *.class "$BuildDir\classes" | ForEach-Object { $_.FullName })
    $d8Mode = if ($isDebug) { "--debug" } else { "--release" }
    & "$BuildTools\d8.bat" $d8Mode --min-api 26 --lib $AndroidJar --output "$BuildDir\dex" @ClassFiles
    if ($LASTEXITCODE -ne 0) { throw "d8 failed" }

    Write-Host "[$Mode] 5/6 Packaging & zipaligning..."
    Push-Location "$BuildDir\dex"
    & "$JavaBin\jar.exe" uf "$BuildDir\unaligned.apk" classes.dex
    Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "jar uf failed" }

    & "$BuildTools\zipalign.exe" -f -p 4 "$BuildDir\unaligned.apk" "$BuildDir\aligned.apk"
    if ($LASTEXITCODE -ne 0) { throw "zipalign failed" }

    Write-Host "[$Mode] 6/6 Signing APK..."
    if ($isDebug) {
        $ks = "$BuildDir\debug.keystore"
        $alias = "androiddebugkey"
        $pass = "android"
        & "$JavaBin\keytool.exe" -genkeypair -v -keystore $ks -alias $alias `
            -keyalg RSA -keysize 2048 -validity 10000 -storepass $pass -keypass $pass `
            -dname "CN=Android Debug, O=Android, C=US" | Out-Null
    } else {
        $ks = "$Root\tabdeck.jks"
        $alias = "tabdeck"
        $pass = if ($env:TABDECK_KS_PASS) { $env:TABDECK_KS_PASS } else { "tabdeck123" }
        if (-not (Test-Path $ks)) {
            & "$JavaBin\keytool.exe" -genkeypair -v -keystore $ks -alias $alias `
                -keyalg RSA -keysize 2048 -validity 10000 -storepass $pass -keypass $pass `
                -dname "CN=TabDeck, OU=Release, O=TabDeck, L=Local, ST=Local, C=US" | Out-Null
        }
    }

    $OutApk = "$DistDir\TabDeck-$Mode.apk"
    & "$BuildTools\apksigner.bat" sign `
        --ks $ks --ks-key-alias $alias --ks-pass "pass:$pass" --key-pass "pass:$pass" `
        --out $OutApk "$BuildDir\aligned.apk"
    if ($LASTEXITCODE -ne 0) { throw "apksigner failed" }

    $sizeKB = [math]::Round((Get-Item $OutApk).Length / 1KB, 1)
    Write-Host "SUCCESS [$Mode]: $OutApk ($sizeKB KB)"
}

if ($Variant -in @("all", "debug")) { Build-Variant "debug" }
if ($Variant -in @("all", "release")) { Build-Variant "release" }
