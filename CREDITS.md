# Credits & Open-Source Attributions

TabDeck builds on the shoulders of the open-source community. Below is every external library, driver, tool, and technical inspiration used by TabDeck, along with their respective authors and licenses.

## Optional Virtual Display Driver (3rd Screen Extended Display)
- **[VirtualDrivers / Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver)**
  - **Author:** Mike Rodriguez (MikeTheTech) / PyroSoft Productions
  - **License:** MIT License
  - **Usage:** Optional signed UMDF Indirect Display Driver (`MttVDD`, v25.7.23) that creates a native 2000×1200 virtual monitor in Windows for TabDeck's 3rd Screen extended display mode.

## Python Backend Libraries
- **[FastAPI](https://github.com/fastapi/fastapi)** — Sebastián Ramírez (Tiangolo) — MIT License (HTTP & WebSocket API server)
- **[Uvicorn](https://github.com/encode/uvicorn)** — Encode — BSD-3-Clause License (ASGI server)
- **[python-mss](https://github.com/BoboTiG/python-mss)** — Mickaël Schoentgen — MIT License (Per-monitor low-latency screen capture)
- **[Pillow](https://github.com/python-pillow/Pillow)** — Jeffrey A. Clark & contributors — MIT-CMU / HPND License (JPEG encoding & cursor rendering)
- **[PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)** — s0d3s — MIT License (Windows WASAPI loopback audio streaming)
- **[pycaw](https://github.com/AndreMiras/pycaw)** — AndreMiras — MIT License & **[comtypes](https://github.com/enthought/comtypes)** — MIT License (Windows Core Audio master & per-app mixer)
- **[PyWinRT (`winrt-*`)](https://github.com/pywinrt/pywinrt)** — David Lechner & contributors — MIT License (Windows Global System Media Transport Controls / Now Playing)
- **[psutil](https://github.com/giampaolo/psutil)** — Giampaolo Rodola — BSD-3-Clause License (CPU, RAM, battery, and active window process lookup)
- **[pystray](https://github.com/moses-palmer/pystray)** — Moses Palmér — LGPL-3.0 License (Windows System Tray integration)
- **[PyInstaller](https://github.com/pyinstaller/pyinstaller)** — PyInstaller Development Team — GPL-2.0 License with Bootloader Exception (Packaging standalone Windows release executable)

## Android Build & Device Tooling
- **[Android SDK Platform Tools (`adb`)](https://developer.android.com/tools/releases/platform-tools)** & **[Android NDK](https://developer.android.com/ndk)** — Google / AOSP — Apache-2.0 License (USB port forwarding, Wireless Debugging pairing, and compiling the `arm64-v8a` Multi Control binary)

## Technical & UX Inspirations (No Source Code Copied)
- **[Genymobile / scrcpy](https://github.com/Genymobile/scrcpy)** (Apache-2.0 License) — Technical inspiration for using Android's non-root `/dev/uhid` USB HID descriptor injection via `adb shell` (`uid=2000`, group `uhid`) to deliver native mouse & keyboard control on stock unrooted phones.
- **Elgato Stream Deck Mobile** — Inspiration for the customizable macro tile grid layout.
- **SuperDisplay** — Inspiration for fullscreen direct touchscreen + native Windows Ink S-Pen interaction.
- **Samsung Multi Control** & **ShareMouse / Deskflow** — Inspiration for 2D spatial drag-and-drop multi-device mouse/keyboard crossing across monitors, tablets, and phones.
