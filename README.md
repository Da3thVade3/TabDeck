# TabDeck

**Turn your Android tablet & phone into an all-in-one Windows companion: Stream Deck macropad, per-app audio mixer, low-latency wireless speaker, SuperDisplay-style touchscreen + Windows Ink S-Pen display, 3rd extended monitor, and Samsung Multi Control-style mouse & keyboard sharing across rooted & unrooted Android devices.**

---

## Features

- **Single Clickable Windows App (`TabDeck.exe`)** — Standalone Windows release (no Python required) that runs quietly in the System Tray with auto-start on login, automatic USB ADB forwarding, UDP LAN auto-discovery, and a one-click Windows Firewall setup helper.
- **Elgato Stream Deck-Style Macropad** — 5×4 customizable macro tile grid supporting hotkeys, apps, URLs, and Windows system actions.
- **Now Playing + Per-App Windows Audio Mixer + Tablet Speaker** — Live Windows GSMTC media info & album art, master & per-app volume sliders/mutes, and 48 kHz low-latency WASAPI loopback PC-to-tablet audio streaming.
- **Fullscreen Touchscreen + Native Windows Ink S-Pen** — Direct touch, relative trackpad, native Win32 `PT_PEN` Windows Ink (pressure, tilt, hover, barrel button, palm rejection, auto-hiding mouse cursor), floating Android keyboard typing bar (`⌨`), and a long-press movable corner toolbar.
- **Living-Room Expanded Mouse Pad & Keyboard** — Tap **`⛶ Expand`** on the Mouse Pad for a dedicated full-screen couch controller: top-half trackpad + bottom default Android keyboard on phones, and left trackpad + right-side floating PC keyboard (plus 1-tap System KB toggle) on landscape tablets.
- **Per-Screen Auto-Adaptive Quality** — Inspects the topmost visible app on *whichever monitor you are currently viewing*: sharp High-Res for Netflix/YouTube/Hotstar/VLC, high-FPS smoothness for OneNote/drawing apps & S-Pen, with separate USB and Wi-Fi profiles.
- **Mirror Mode ↔ 3rd Screen (Extended Display)** — One-tap toggle between mirroring your physical monitors and extending Windows onto a native 2000×1200 virtual 3rd screen (via optional signed Virtual Display Driver).
- **Multi-Device 2D Spatial Multi Control (Rooted & Unrooted Android)** — Control your Android tablet *and* unrooted phone (e.g., Samsung Galaxy S24) natively with your laptop's physical mouse and keyboard:
  - Visual **Drag-and-Drop Device Layout Studio** (`⧉ Devices` or Tray → *Arrange Devices*) with magnetic edge snapping and glowing crossing-edge portals.
  - Works on **rooted Android** via `/dev/uinput` (auto-starts via Magisk) AND **unrooted Android 11–15+ phones** via `/dev/uhid` over Wireless Debugging or a 3-second USB deploy (no root required).
  - Instant toggle hotkey **`Ctrl + Alt + M`** (or **`ScrollLock`**) and emergency return **`Ctrl + Alt + Esc`**.

---

## Windows Installation Guide (Choose Your Preferred Method)

Pick whichever installation method you're most comfortable with — **no Python installation required** for Options 1–3:

### Option 1: One-Line Plug-and-Play Installer (Fastest!)
Open **PowerShell** (press `Win + X` → *Terminal / PowerShell*) and paste:
```powershell
irm https://raw.githubusercontent.com/Da3thVade3/TabDeck/main/install.ps1 | iex
```
This automatically downloads the latest standalone release, installs to `%LOCALAPPDATA%\TabDeck`, creates **Start Menu** and **Desktop** shortcuts, preserves your settings on future upgrades, and launches **TabDeck** right into your System Tray.

To cleanly uninstall anytime:
```powershell
irm https://raw.githubusercontent.com/Da3thVade3/TabDeck/main/uninstall.ps1 | iex
```

### Option 2: Portable ZIP Download (No Installer / No Scripts)
1. Download **`TabDeck-Windows-v0.9.zip`** from the [Releases](https://github.com/Da3thVade3/TabDeck/releases) page.
2. Right-click the ZIP → **Extract All...** into any folder you like (e.g., `C:\Apps\TabDeck`).
   - *Important:* Extract the ZIP first rather than launching from inside the ZIP preview.
3. Double-click **`TabDeck.exe`**.
   - **If Windows SmartScreen shows *"Windows protected your PC"*:** Because TabDeck is an unsigned open-source app, click **More info** → **Run anyway** *(or build from source in Option 4)*.

### Option 3: WinGet (Windows Package Manager)
Validated WinGet manifests are included in [`winget/manifests/d/Da3thVade3/TabDeck/0.9`](winget/manifests/d/Da3thVade3/TabDeck/0.9):
- **Once published to `microsoft/winget-pkgs`:**
  ```powershell
  winget install --id Da3thVade3.TabDeck -e
  ```
- **Or install via local manifest right now** (requires `winget settings --enable LocalManifestFiles`):
  ```powershell
  git clone https://github.com/Da3thVade3/TabDeck.git
  winget install --manifest .\TabDeck\winget\manifests\d\Da3thVade3\TabDeck\0.9
  ```

### Option 4: Run or Build From Source (Developers · Python 3.11+)
```powershell
git clone https://github.com/Da3thVade3/TabDeck.git
cd TabDeck
```
Then simply **double-click `TabDeck.exe`** — on first launch it automatically creates `.venv`, installs `requirements.txt`, and launches into the System Tray.

To rebuild the standalone Windows ZIP yourself:
```powershell
.\.venv\Scripts\pip install pyinstaller
.\launcher\build_windows_release.ps1 -Version 0.9
```

### First-Launch Checklist (Windows — 10 Seconds)
1. **Find the System Tray Icon:** TabDeck runs silently with no console window. Look for the **4-tile TabDeck icon** in the bottom-right System Tray (click the **`^`** arrow near the clock if hidden).
2. **Allow Wi-Fi Connections (1 Click):** Right-click the **TabDeck** tray icon → **Enable Wi-Fi Access (Allow Firewall)** → click **Yes** on the admin prompt (opens TCP `8765` + UDP `8766` across all network profiles so your tablet/phone connects automatically over Wi-Fi).
3. *(Optional)* **Start with Windows:** Right-click the tray icon → check **Start with Windows**.

---

## Android Installation Guide

1. **Download an APK from [Releases](https://github.com/Da3thVade3/TabDeck/releases):**
   - **`TabDeck-release.apk` (~29 KB)** — Lean production build for daily use on tablets and phones.
   - **`TabDeck-debug.apk` (~33 KB)** — Installs side-by-side as *TabDeck Debug* with Chrome DevTools WebView debugging and a live connection diagnostics badge.
2. **Install & Open:** Tap the downloaded `.apk` on your Android device (allow *"Install unknown apps"* for your browser/file manager if prompted).
3. **Zero-Config Connection:** On first launch, follow the quick **3-step Welcome Guide**. As long as `TabDeck.exe` is running on Windows on the **same Wi-Fi** (or connected over USB with ADB), TabDeck discovers and connects to your PC automatically — no IP address typing required.

To build both APKs from source (requires Android SDK & JDK 11+):
```powershell
.\android-app\build_apk.ps1
```

---

## Optional Add-Ons

### 1. Wired USB Mode & Unrooted Phone Multi Control (ADB)
Wi-Fi dashboard, audio streaming, and touchscreen work **without** ADB. To use **wired USB mode** or **Multi Control on an unrooted phone (Android 11–15+)**:
1. Install Google's official ADB Platform Tools on Windows (one command in PowerShell):
   ```powershell
   winget install --id Google.PlatformTools -e
   ```
   *(Or download [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) and place `adb.exe` in a `platform-tools\` folder next to `TabDeck.exe`.)*
2. On your Android phone, enable **Developer Options** (*Settings → About phone → tap Build number 7 times*), then turn on **Wireless debugging** (or **USB debugging**).
3. In TabDeck, open **Tray → Multi Control → Arrange Devices** (or tap **`⧉ Devices`** in the app) → click **`Setup Unrooted Phone (S24)`**:
   - **Wireless Debugging (no cable):** Enter the IP:Port (and 6-digit pairing code the first time) → click **Pair & Start**.
   - **3-Second USB Deploy:** Plug in briefly via USB → click **Deploy** → unplug and place your phone on a wireless charger; it stays connected over Wi-Fi.
4. Drag your tablet and phone cards anywhere around your monitors to snap crossing edges!

### 2. 3rd Extended Screen (Virtual Display Driver)
To use your tablet as a true independent **3rd Windows monitor** (via the **`3rd Scr`** button in fullscreen):
1. Install the open-source signed [VirtualDrivers / Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver):
   ```powershell
   winget install --id VirtualDrivers.Virtual-Display-Driver -e
   ```
2. Add your tablet's native resolution (e.g., `2000×1200 @ 60 Hz` for Galaxy Tab S6 Lite) inside `C:\VirtualDisplayDriver\vdd_settings.xml`.
3. Open TabDeck Fullscreen on your tablet and tap **`3rd Scr`** to switch between Mirroring and Extended Display mode.

---

## Troubleshooting (Windows)

| Issue | Quick Fix |
| :--- | :--- |
| **Tablet / phone stays on *"Waiting for laptop..."* over Wi-Fi** | Right-click the **TabDeck** tray icon → **Enable Wi-Fi Access (Allow Firewall)** and confirm the admin prompt. Make sure both devices are on the same Wi-Fi (not a guest network with client isolation). |
| **Can't see any window after double-clicking `TabDeck.exe`** | TabDeck runs in the **System Tray** (bottom-right near the clock, inside the `^` icon). Right-click it → **Open in PC Browser** (`http://127.0.0.1:8765`) to verify it's running. |
| **SmartScreen blocks `TabDeck.exe`** | Click **More info → Run anyway**, or right-click `TabDeck.exe` → **Properties** → check **Unblock** → **OK**. |
| **Multi Control cursor feels stuck on tablet/phone** | Press **`Ctrl + Alt + M`** (or **`ScrollLock`** / emergency **`Ctrl + Alt + Esc`**) to snap immediately back to Windows and release all keys. |
| **Unrooted phone disconnects Multi Control after a phone reboot** | Re-open **`⧉ Devices` → `Setup Unrooted Phone`** and click **Pair & Start** (or plug in for 3 seconds and click **Deploy**). |

---

## Repository Structure

```text
tabdeck/
├── TabDeck.exe             # Clickable Windows launcher (auto-bootstraps .venv when run from source)
├── app/                    # Unified Python Windows backend (tray, FastAPI, Multi Control, video/audio/pen)
├── static/                 # Responsive dashboard, fullscreen touch/pen UI, & 2D Device Layout Studio
├── android-app/            # Native Android companion APK source & dual Debug/Release build script
├── android-mc/             # Tiny 15 KB C dual-mode /dev/uinput + non-root /dev/uhid Multi Control daemon
├── launcher/               # C# source for TabDeck.exe & PyInstaller standalone release packager
├── config.example.json     # Example macro configuration
├── requirements.txt        # Python dependencies
├── CREDITS.md              # Full open-source attributions & licenses
└── LICENSE                 # MIT License
```

---

## Credits & Open-Source Attributions

TabDeck uses and gratefully acknowledges the following open-source projects (full details and license list in [CREDITS.md](CREDITS.md)):

| Project | Author / Org | License | Role in TabDeck |
| :--- | :--- | :--- | :--- |
| [Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver) | Mike Rodriguez / PyroSoft Productions | MIT | Optional 3rd virtual monitor (`MttVDD`) |
| [FastAPI](https://github.com/fastapi/fastapi) | Sebastián Ramírez (Tiangolo) | MIT | HTTP & WebSocket API server |
| [Uvicorn](https://github.com/encode/uvicorn) | Encode | BSD-3-Clause | ASGI server |
| [python-mss](https://github.com/BoboTiG/python-mss) | Mickaël Schoentgen | MIT | Low-latency multi-monitor screen capture |
| [Pillow](https://github.com/python-pillow/Pillow) | Jeffrey A. Clark & contributors | MIT-CMU | Frame encoding & cursor rendering |
| [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | s0d3s | MIT | Windows WASAPI loopback audio streaming |
| [pycaw](https://github.com/AndreMiras/pycaw) & [comtypes](https://github.com/enthought/comtypes) | AndreMiras / Enthought | MIT | Windows master & per-app audio mixer |
| [PyWinRT](https://github.com/pywinrt/pywinrt) | David Lechner & contributors | MIT | Windows GSMTC Now Playing controls |
| [psutil](https://github.com/giampaolo/psutil) | Giampaolo Rodola | BSD-3-Clause | System telemetry & per-screen app detection |
| [pystray](https://github.com/moses-palmer/pystray) | Moses Palmér | LGPL-3.0 | Windows System Tray integration |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | PyInstaller Development Team | GPL-2.0 with Bootloader Exception | Packaging standalone Windows `.exe` release |
| [Android Platform Tools & NDK](https://developer.android.com/ndk) | Google / AOSP | Apache-2.0 | ADB forwarding, Wireless Debugging & `arm64-v8a` build |
| [scrcpy](https://github.com/Genymobile/scrcpy) *(inspiration)* | Genymobile | Apache-2.0 | Inspiration for non-root Android `/dev/uhid` mouse/keyboard HID injection |

---

## License

Released under the [MIT License](LICENSE).
