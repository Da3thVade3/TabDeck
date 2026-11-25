# TabDeck — Project Guidelines

## Architecture Overview
TabDeck is an all-in-one Windows + Android companion app with four clean components:
- `TabDeck.exe` & `launcher/` — Single clickable Windows entry point (`TabDeckLauncher.cs` for dev auto-bootstrap; `build_windows_release.ps1` for standalone PyInstaller ZIP).
- `app/` — Unified Windows Python backend (`tray.py`, `server.py`, `pc_control.py`, `audio_stream.py`, `video_stream.py`, `mouse_control.py`, `multi_control.py`, `discovery_and_adb.py`, `adb_deploy.py`).
- `static/` — Responsive web UI (`index.html`, `manifest.json`) supporting phones, portrait/landscape tablets, and desktop browsers (Stream Deck macropad, audio mixer, fullscreen touch + Windows Ink S-Pen, living-room trackpad + keyboard, 2D drag-and-drop Multi Control layout studio).
- `android-app/` — Ultra-compact native Android companion APK (~29 KB release / ~33 KB debug) with 3-step Welcome Guide, USB/Wi-Fi auto-discovery, and 48 kHz low-latency `AudioTrack` PCM streaming.
- `android-mc/` — Tiny ~15 KB `arm64-v8a` C daemon (`tabdeck_mc.c`) supporting both rooted `/dev/uinput` and non-root `/dev/uhid` (stock Android 11–15+ phones via Wireless Debugging or USB).

## Project Rules
1. **Zero Personal Information:** Never commit personal usernames, local LAN IPs, Wi-Fi SSIDs, device serials, hostnames, `.jks` keystores, `config.json`, `multicontrol.json`, or runtime logs. Always verify clean diffs before pushing or building releases.
2. **Single-App Experience:** Keep Windows usage unified around `TabDeck.exe` and the System Tray. Do not scatter standalone `.bat`/`.vbs` helper scripts in the repo root.
3. **Battery-First Design:** Keep Android features strictly on-demand (lazy `/ws/input` WebSocket with idle auto-sleep, DOM diffing on polls, adaptive polling backoff, pause on `visibilitychange` and `Activity.onPause()`, no heavy `backdrop-filter` blur).
4. **Frozen-App Compatibility:** Any new backend path lookup in `app/` must handle both normal execution and PyInstaller frozen execution (`getattr(sys, "frozen", False)`).
5. **Open-Source Attribution:** Whenever adding or updating any third-party library, driver, or tool, document its author, license, and link in `CREDITS.md` and `README.md`.
6. **Keep Releases & WinGet Synced:** When cutting a new release, rebuild both Android APKs (`android-app/build_apk.ps1`), rebuild the standalone Windows ZIP (`launcher/build_windows_release.ps1`), update the SHA-256 in `winget/`, and validate with `winget validate`.
