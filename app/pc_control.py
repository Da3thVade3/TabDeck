import asyncio
import base64
import ctypes
import os
import subprocess
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psutil

# Prime cpu_percent so the first API read returns real CPU usage
psutil.cpu_percent(interval=None)

# Windows virtual key codes for hotkeys & media controls
VK_MAP = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
    "meta": 0x5B,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play": 0xB3,
    "vol_mute": 0xAD,
    "vol_down": 0xAE,
    "vol_up": 0xAF,
}
for _i in range(1, 13):
    VK_MAP[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_c] = ord(_c.upper())
for _d in "0123456789":
    VK_MAP[_d] = ord(_d)

KEYEVENTF_KEYUP = 0x0002
user32 = ctypes.windll.user32


def send_hotkey(keys: list[str]) -> None:
    codes = [VK_MAP[k.strip().lower()] for k in keys if k.strip().lower() in VK_MAP]
    if not codes:
        return
    for vk in codes:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.015)
    for vk in reversed(codes):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.015)


def send_media_key(action: str) -> None:
    mapping = {
        "play_pause": "media_play",
        "next": "media_next",
        "prev": "media_prev",
        "stop": "media_stop",
    }
    vk_name = mapping.get(action)
    if vk_name:
        send_hotkey([vk_name])


# ---------------------------------------------------------------------------
# Windows GSMTC (Global System Media Transport Controls) — Now Playing
# ---------------------------------------------------------------------------
_last_thumb_key: str = ""
_last_thumb_b64: str = ""


async def _get_gsmtc_state_async() -> dict[str, Any]:
    global _last_thumb_key, _last_thumb_b64
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        from winrt.windows.storage.streams import Buffer, InputStreamOptions

        manager = await asyncio.wait_for(MediaManager.request_async(), timeout=1.5)
        session = manager.get_current_session()
        if session is None:
            return {
                "active": False,
                "title": "Nothing Playing",
                "artist": "Start music on your PC",
                "album": "",
                "source": "",
                "status": "stopped",
                "thumbnail": "",
            }

        props = await asyncio.wait_for(session.try_get_media_properties_async(), timeout=1.5)
        playback = session.get_playback_info()
        status_map = {
            PlaybackStatus.PLAYING: "playing",
            PlaybackStatus.PAUSED: "paused",
            PlaybackStatus.STOPPED: "stopped",
            PlaybackStatus.CHANGING: "playing",
        }
        status = status_map.get(playback.playback_status, "paused")
        title = props.title or "Unknown Title"
        artist = props.artist or ""
        album = props.album_title or ""
        source_raw = session.source_app_user_model_id or ""
        source = source_raw.split("!")[0].split(".")[-1].replace(".exe", "")

        thumb_key = f"{title}|{artist}|{album}"
        thumb_b64 = _last_thumb_b64 if thumb_key == _last_thumb_key else ""
        if thumb_key != _last_thumb_key:
            thumb_b64 = ""
            if props.thumbnail:
                try:
                    stream = await props.thumbnail.open_read_async()
                    size = stream.size
                    if 0 < size < 3_000_000:
                        buf = Buffer(size)
                        await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
                        raw = bytes(buf)
                        mime = stream.content_type or "image/png"
                        thumb_b64 = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                except Exception:
                    thumb_b64 = ""
            _last_thumb_key = thumb_key
            _last_thumb_b64 = thumb_b64

        return {
            "active": True,
            "title": title,
            "artist": artist,
            "album": album,
            "source": source,
            "status": status,
            "thumbnail": thumb_b64,
        }
    except Exception:
        return {
            "active": False,
            "title": "Media Control Ready",
            "artist": "Use buttons to control PC playback",
            "album": "",
            "source": "",
            "status": "stopped",
            "thumbnail": "",
        }


async def control_media_async(action: str) -> dict[str, Any]:
    handled = False
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        )

        manager = await asyncio.wait_for(MediaManager.request_async(), timeout=1.5)
        session = manager.get_current_session()
        if session is not None:
            if action == "play_pause":
                handled = bool(await asyncio.wait_for(session.try_toggle_play_pause_async(), timeout=1.5))
            elif action == "next":
                handled = bool(await asyncio.wait_for(session.try_skip_next_async(), timeout=1.5))
            elif action == "prev":
                handled = bool(await asyncio.wait_for(session.try_skip_previous_async(), timeout=1.5))
            elif action == "stop":
                handled = bool(await asyncio.wait_for(session.try_stop_async(), timeout=1.5))
    except Exception:
        handled = False

    if not handled:
        send_media_key(action)

    await asyncio.sleep(0.15)
    return await _get_gsmtc_state_async()


async def get_media_state_async() -> dict[str, Any]:
    return await _get_gsmtc_state_async()


# ---------------------------------------------------------------------------
# Windows Audio (Master Volume, Per-App Mixer, Mic Mute) via pycaw
# Keep ALL COM objects strictly on a single persistent MTA thread and cache
# endpoints so comtypes never leaks or releases pointers across threads.
# ---------------------------------------------------------------------------
import queue
import threading

_audio_cache: dict[str, Any] = {
    "master_volume": 50,
    "master_muted": False,
    "mic_muted": False,
    "apps": [],
}
_audio_cmd_q: queue.Queue = queue.Queue()
_audio_worker_started = False
_audio_worker_lock = threading.Lock()


def _activate_endpoint(device):
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    if device is None:
        return None
    if hasattr(device, "EndpointVolume"):
        return device.EndpointVolume
    raw = getattr(device, "_dev", device)
    interface = raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _audio_worker_loop():
    import comtypes
    from pycaw.pycaw import AudioUtilities

    # COINIT_MULTITHREADED (0x0) avoids STA cross-thread GC release crashes
    try:
        comtypes.CoInitializeEx(0x0)
    except Exception:
        comtypes.CoInitialize()

    master_ep = None
    mic_ep = None
    last_refresh = 0.0
    last_apps_refresh = 0.0
    cached_apps: list[dict[str, Any]] = []

    def ensure_endpoints():
        nonlocal master_ep, mic_ep
        if master_ep is None:
            try:
                master_ep = _activate_endpoint(AudioUtilities.GetSpeakers())
            except Exception:
                master_ep = None
        if mic_ep is None:
            try:
                mic_ep = _activate_endpoint(AudioUtilities.GetMicrophone())
            except Exception:
                mic_ep = None

    def refresh_state(force_apps: bool = False):
        nonlocal last_refresh, last_apps_refresh, cached_apps, master_ep, mic_ep
        ensure_endpoints()
        master_vol = _audio_cache["master_volume"]
        master_muted = _audio_cache["master_muted"]
        mic_muted = _audio_cache["mic_muted"]

        if master_ep is not None:
            try:
                master_vol = round(master_ep.GetMasterVolumeLevelScalar() * 100)
                master_muted = bool(master_ep.GetMute())
            except Exception:
                master_ep = None

        if mic_ep is not None:
            try:
                mic_muted = bool(mic_ep.GetMute())
            except Exception:
                mic_ep = None

        now = time.monotonic()
        if force_apps or (now - last_apps_refresh >= 5.0):
            apps: dict[str, dict[str, Any]] = {}
            try:
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    try:
                        if s.Process and s.SimpleAudioVolume:
                            raw_name = s.Process.name()
                            if not raw_name:
                                continue
                            clean = raw_name.replace(".exe", "")
                            vol = round(s.SimpleAudioVolume.GetMasterVolume() * 100)
                            muted = bool(s.SimpleAudioVolume.GetMute())
                            if clean not in apps:
                                apps[clean] = {
                                    "name": raw_name,
                                    "label": clean.capitalize(),
                                    "volume": vol,
                                    "muted": muted,
                                }
                    except Exception:
                        continue
                cached_apps = sorted(apps.values(), key=lambda x: x["label"].lower())[:8]
                last_apps_refresh = now
            except Exception:
                pass

        _audio_cache.update(
            {
                "master_volume": master_vol,
                "master_muted": master_muted,
                "mic_muted": mic_muted,
                "apps": cached_apps,
            }
        )
        last_refresh = now

    refresh_state(force_apps=True)

    while True:
        try:
            cmd, args, done_ev = _audio_cmd_q.get(timeout=1.5)
        except queue.Empty:
            refresh_state(force_apps=False)
            continue

        try:
            ensure_endpoints()
            if cmd == "master_vol" and master_ep is not None:
                lvl = max(0, min(100, int(args[0])))
                master_ep.SetMasterVolumeLevelScalar(lvl / 100.0, None)
                if lvl > 0 and master_ep.GetMute():
                    master_ep.SetMute(0, None)
                refresh_state(force_apps=False)
            elif cmd == "master_mute" and master_ep is not None:
                master_ep.SetMute(0 if master_ep.GetMute() else 1, None)
                refresh_state(force_apps=False)
            elif cmd == "mic_mute" and mic_ep is not None:
                mic_ep.SetMute(0 if mic_ep.GetMute() else 1, None)
                refresh_state(force_apps=False)
            elif cmd == "app_vol":
                proc_name, lvl = str(args[0]).lower(), max(0, min(100, int(args[1])))
                for s in AudioUtilities.GetAllSessions():
                    if s.Process and s.Process.name().lower() == proc_name:
                        s.SimpleAudioVolume.SetMasterVolume(lvl / 100.0, None)
                refresh_state(force_apps=True)
            elif cmd == "app_mute":
                proc_name = str(args[0]).lower()
                for s in AudioUtilities.GetAllSessions():
                    if s.Process and s.Process.name().lower() == proc_name:
                        cur = bool(s.SimpleAudioVolume.GetMute())
                        s.SimpleAudioVolume.SetMute(0 if cur else 1, None)
                refresh_state(force_apps=True)
        except Exception:
            pass
        finally:
            if done_ev is not None:
                done_ev.set()


def _ensure_audio_worker():
    global _audio_worker_started
    if _audio_worker_started:
        return
    with _audio_worker_lock:
        if not _audio_worker_started:
            t = threading.Thread(target=_audio_worker_loop, name="tabdeck-audio", daemon=True)
            t.start()
            _audio_worker_started = True


def _run_audio_cmd(cmd: str, *args) -> dict[str, Any]:
    _ensure_audio_worker()
    ev = threading.Event()
    _audio_cmd_q.put((cmd, args, ev))
    ev.wait(timeout=2.0)
    return dict(_audio_cache)


def get_audio_state() -> dict[str, Any]:
    _ensure_audio_worker()
    return dict(_audio_cache)


def set_master_volume(level: int) -> dict[str, Any]:
    return _run_audio_cmd("master_vol", level)


def toggle_master_mute() -> dict[str, Any]:
    return _run_audio_cmd("master_mute")


def toggle_mic_mute() -> dict[str, Any]:
    return _run_audio_cmd("mic_mute")


def set_app_volume(proc_name: str, level: int) -> dict[str, Any]:
    return _run_audio_cmd("app_vol", proc_name, level)


def toggle_app_mute(proc_name: str) -> dict[str, Any]:
    return _run_audio_cmd("app_mute", proc_name)


# ---------------------------------------------------------------------------
# System Stats & Macro Runner
# ---------------------------------------------------------------------------
def get_system_stats() -> dict[str, Any]:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    batt = psutil.sensors_battery()
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=None)),
        "ram_percent": round(mem.percent),
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "disk_percent": round(disk.percent),
        "battery_percent": round(batt.percent) if batt else None,
        "battery_plugged": bool(batt.power_plugged) if batt else None,
    }


def execute_macro(macro: dict[str, Any]) -> dict[str, Any]:
    mtype = macro.get("type", "hotkey")
    value = macro.get("value", "")

    if mtype == "hotkey":
        keys = value if isinstance(value, list) else [k.strip() for k in str(value).split("+")]
        send_hotkey(keys)
        return {"ok": True, "message": f"Sent {'+'.join(keys)}"}

    if mtype == "url":
        webbrowser.open(str(value))
        return {"ok": True, "message": f"Opened {value}"}

    if mtype == "app":
        cmd = str(value).strip()
        try:
            os.startfile(cmd)
        except Exception:
            subprocess.Popen(cmd, shell=True)
        return {"ok": True, "message": f"Launched {macro.get('label', cmd)}"}

    if mtype == "action":
        act = str(value).lower()
        if act == "lock":
            user32.LockWorkStation()
            return {"ok": True, "message": "PC Locked"}
        if act == "display_off":
            # WM_SYSCOMMAND = 0x0112, SC_MONITORPOWER = 0xF170, Power off = 2
            user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            return {"ok": True, "message": "Display turned off"}
        if act == "mic_mute":
            st = toggle_mic_mute()
            return {"ok": True, "message": "Mic muted" if st["mic_muted"] else "Mic unmuted", "audio": st}
        if act == "vol_mute":
            st = toggle_master_mute()
            return {"ok": True, "message": "Muted" if st["master_muted"] else "Unmuted", "audio": st}
        if act == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return {"ok": True, "message": "PC going to sleep"}

    return {"ok": False, "message": f"Unknown macro type: {mtype}"}
