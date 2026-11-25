# TabDeck

**Turn your Android tablet & phone into an all-in-one Windows companion: Stream Deck macropad, per-app audio mixer, low-latency wireless speaker, SuperDisplay-style touchscreen + Windows Ink S-Pen display, 3rd extended monitor, and Samsung Multi Control-style mouse & keyboard sharing across rooted & unrooted Android devices.**

---

## Features

- **Single Clickable Windows App (`TabDeck.exe`)** — Runs quietly in the Windows System Tray with auto-start on login, automatic USB ADB port forwarding, UDP LAN auto-discovery, and a one-click Windows Firewall setup helper.
- **Elgato Stream Deck-Style Macropad** — 5×4 customizable macro tile grid supporting hotkeys, apps, URLs, and Windows system actions.
- **Now Playing + Per-App Windows Audio Mixer + Tablet Speaker** — Live Windows GSMTC media info & album art, master & per-app volume sliders/mutes, and 48 kHz low-latency WASAPI loopback PC-to-tablet audio streaming.
- **Fullscreen Touchscreen + Native Windows Ink S-Pen** — Direct touch, relative trackpad, native Win32 `PT_PEN` Windows Ink (pressure, tilt, hover, barrel button, palm rejection, auto-hiding mouse cursor), floating Android keyboard typing bar (`⌨`), and a long-press movable corner toolbar.
- **Per-Screen Auto-Adaptive Quality** — Inspects the topmost visible app on *whichever monitor you are currently viewing*: sharp High-Res for Netflix/YouTube/Hotstar/VLC, high-FPS smoothness for OneNote/drawing apps & S-Pen, with separate USB and Wi-Fi profiles.
- **Mirror Mode ↔ 3rd Screen (Extended Display)** — One-tap toggle between mirroring your physical monitors and extending Windows onto a native 2000×1200 virtual 3rd screen (via optional signed Virtual Display Driver).
- **Multi-Device 2D Spatial Multi Control (Rooted & Unrooted Android!)** — Control your Android tablet *and* unrooted phone (e.g., Samsung Galaxy S24) natively with your laptop's physical mouse and keyboard:
  - Visual **Drag-and-Drop Device Layout Studio** (`⧉ Devices` or Tray → *Arrange Devices*) with magnetic edge snapping and glowing crossing-edge portals.
  - Works on **rooted Android** via `/dev/uinput` (auto-starts via Magisk) AND **unrooted Android 11–15+ phones** (like Samsung Galaxy S24) via `/dev/uhid` over Wireless Debugging or 3-second USB setup (no root required!).
  - Instant toggle hotkey **`Ctrl + Alt + M`** (or **`ScrollLock`**) and emergency return **`Ctrl + Alt + Esc`**.

---

## Repository Structure

```text
tabdeck/
├── TabDeck.exe             # Single clickable Windows app launcher (custom icon, no console)
├── app/                    # Unified Python Windows backend (tray, FastAPI, Multi Control, video/audio/pen)
├── static/                 # Responsive dashboard, fullscreen touch/pen UI, & 2D Device Layout Studio
├── android-app/            # Native Android companion APK (immersive WebView + 48kHz PCM audio + auto-discovery)
├── android-mc/             # Tiny 15 KB C dual-mode /dev/uinput + non-root /dev/uhid Multi Control daemon
├── launcher/               # C# source for TabDeck.exe
├── config.example.json     # Example macro configuration
├── requirements.txt        # Python dependencies
├── CREDITS.md              # Full open-source attributions & licenses
└── LICENSE                 # MIT License
```

---

## Quick Start (Minimum Setup)

1. **Windows (1 Click):** Download or clone TabDeck and double-click **`TabDeck.exe`**.
   - On first run, `TabDeck.exe` automatically creates `.venv` and installs all Python dependencies for you (requires Python 3.11+), then launches silently into your Windows System Tray.
   - Right-click the **TabDeck** tray icon to enable **Start with Windows**, allow **Wi-Fi Firewall**, or open **Arrange Devices (Drag & Drop Layout)**.
2. **Android (2 Builds Available on Releases):**
   - **`TabDeck-release.apk` (~29 KB)** — Lean production build for daily use.
   - **`TabDeck-debug.apk` (~33 KB)** — Installs side-by-side (`TabDeck Debug`) with Chrome DevTools WebView debugging and a live connection diagnostics badge.
   - On first launch, a quick **3-step Welcome Guide** walks you through connecting via USB or Wi-Fi (auto-discovered with zero IP setup).
   - To build both APKs from source: `.\android-app\build_apk.ps1`
3. **Add an Unrooted Phone (e.g., Samsung Galaxy S24) to Multi Control:**
   - Open **Tray → Multi Control → Arrange Devices** (or tap **`⧉ Devices`** in TabDeck).
   - Click **`Setup Unrooted Phone (S24)`**:
     - **Wireless Debugging (no cable):** Enable *Developer Options → Wireless debugging* on your phone, enter the IP:Port + pairing code once, and click **Pair & Start**.
     - **USB Quick-Deploy:** Plug your phone in for 3 seconds with USB Debugging enabled, click **Deploy**, then unplug and place it on your wireless charger.
   - Drag your tablet and phone cards wherever you physically place them around your monitors!
5. *(Optional)* **Enable 3rd Extended Screen:** Install [VirtualDrivers / Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver) configured with your tablet's native resolution (e.g., `2000×1200 @ 60 Hz`), then tap **`3rd Scr`** in TabDeck's fullscreen toolbar.

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
| [Android Platform Tools & NDK](https://developer.android.com/ndk) | Google / AOSP | Apache-2.0 | ADB forwarding, Wireless Debugging & `arm64-v8a` build |
| [scrcpy](https://github.com/Genymobile/scrcpy) *(inspiration)* | Genymobile | Apache-2.0 | Inspiration for non-root Android `/dev/uhid` mouse/keyboard HID injection |

---

## License

Released under the [MIT License](LICENSE).
