"""
TabDeck Multi Control — Multi-Device 2D Spatial Laptop Mouse & Keyboard -> Android Devices.

Supports multiple Android tablets and phones arranged visually around your physical
Windows monitors (just like Samsung Multi Control / Windows Display Settings).

Features:
  - True 2D spatial edge crossing (e.g. Tab S6 Lite under Monitor 1, Phone right of Laptop)
  - Ignores hidden Virtual Display Driver (MTT1337) on physical edges unless Screen 3 is active
  - Fast corner-zero calibration on entry so the Android cursor appears immediately at the
    exact matching edge pixel (fixes halfway-screen offset & premature return bugs!)
  - Multi-device persistent socket pool (USB adb-forward + Wi-Fi auto-connect)
  - Zero-blocking Win32 WH_MOUSE_LL + WH_KEYBOARD_LL hooks
  - Instant hotkey: Ctrl + Alt + M (or ScrollLock) | Emergency return: Ctrl + Alt + Esc
"""
from __future__ import annotations

import ctypes
import json
import socket
import struct
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import mss

import video_stream

BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
MC_CONFIG_PATH = BASE_DIR / "multicontrol.json"
DEFAULT_MC_PORT = 8767

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Win32 Hook constants
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E

LLMHF_INJECTED = 0x00000001
LLKHF_INJECTED = 0x00000010

# Linux input-event-codes.h
EV_SYN = 0
EV_KEY = 1
EV_REL = 2
EV_RELEASE_ALL = 9
EV_PING = 10

REL_X = 0
REL_Y = 1
REL_HWHEEL = 6
REL_WHEEL = 8

BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

VK_TO_LINUX: dict[int, int] = {
    0x1B: 1,    # ESC -> Android Back
    0x31: 2, 0x32: 3, 0x33: 4, 0x34: 5, 0x35: 6, 0x36: 7, 0x37: 8, 0x38: 9, 0x39: 10, 0x30: 11,
    0xBD: 12, 0xBB: 13, 0x08: 14, 0x09: 15,
    0x51: 16, 0x57: 17, 0x45: 18, 0x52: 19, 0x54: 20, 0x59: 21, 0x55: 22, 0x49: 23, 0x4F: 24, 0x50: 25,
    0xDB: 26, 0xDD: 27, 0x0D: 28,
    0xA2: 29, 0x11: 29,
    0x41: 30, 0x53: 31, 0x44: 32, 0x46: 33, 0x47: 34, 0x48: 35, 0x4A: 36, 0x4B: 37, 0x4C: 38,
    0xBA: 39, 0xDE: 40, 0xC0: 41,
    0xA0: 42, 0x10: 42, 0xDC: 43,
    0x5A: 44, 0x58: 45, 0x43: 46, 0x56: 47, 0x42: 48, 0x4E: 49, 0x4D: 50,
    0xBC: 51, 0xBE: 52, 0xBF: 53,
    0xA1: 54, 0x6A: 55, 0xA4: 56, 0x12: 56, 0x20: 57, 0x14: 58,
    0x70: 59, 0x71: 60, 0x72: 61, 0x73: 62, 0x74: 63, 0x75: 64, 0x76: 65, 0x77: 66, 0x78: 67, 0x79: 68,
    0x90: 69,
    0x67: 71, 0x68: 72, 0x69: 73, 0x6D: 74,
    0x64: 75, 0x65: 76, 0x66: 77, 0x6B: 78,
    0x61: 79, 0x62: 80, 0x63: 81, 0x60: 82, 0x6E: 83,
    0x7A: 87, 0x7B: 88,
    0xA3: 97, 0x6F: 98, 0xA5: 100,
    0x24: 102, 0x26: 103, 0x21: 104, 0x25: 105, 0x27: 106, 0x23: 107, 0x28: 108, 0x22: 109,
    0x2D: 110, 0x2E: 111,
    0xAD: 113, 0xAE: 114, 0xAF: 115,
    0x5B: 125, 0x5C: 126,  # Win -> Android Home / Meta
    0xB3: 164, 0xB0: 163, 0xB1: 165,
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_uint32),
        ("scanCode", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint32),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt", POINT),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, ctypes.c_uint32]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
user32.PostThreadMessageW.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_ssize_t]


def _pack_ev(ev_type: int, code: int, value: int) -> bytes:
    return struct.pack("<BHBi", ev_type & 0xFF, code & 0xFFFF, 0, int(value))


def get_physical_monitors() -> list[dict[str, Any]]:
    """Return physical Windows displays in virtual-desktop coordinates (excluding virtual MTT1337 3rd screen)."""
    try:
        with mss.MSS() as sct:
            raw = list(sct.monitors[1:])
    except Exception:
        return [{"id": "win_1", "index": 1, "name": "Primary Monitor", "x": 0, "y": 0, "width": 1920, "height": 1080, "is_primary": True}]

    raw.sort(key=lambda m: (0 if m.get("is_primary") else 1, m.get("left", 0)))
    physical: list[dict[str, Any]] = []
    for m in raw:
        uid = str(m.get("unique_id", "")).upper()
        if "MTT1337" in uid or "SUPERDISPLAY" in uid:
            continue
        idx = len(physical) + 1
        label = "Monitor 1 (Primary)" if m.get("is_primary") else f"Monitor {idx} (Laptop)"
        physical.append(
            {
                "id": f"win_{idx}",
                "index": idx,
                "name": label,
                "x": int(m["left"]),
                "y": int(m["top"]),
                "width": int(m["width"]),
                "height": int(m["height"]),
                "is_primary": bool(m.get("is_primary")),
            }
        )
    if not physical and raw:
        m = raw[0]
        physical.append(
            {
                "id": "win_1",
                "index": 1,
                "name": "Monitor 1",
                "x": int(m["left"]),
                "y": int(m["top"]),
                "width": int(m["width"]),
                "height": int(m["height"]),
                "is_primary": True,
            }
        )
    return physical


def _default_devices() -> list[dict[str, Any]]:
    """Default spatial layout: Android Tablet docked directly underneath Monitor 1."""
    mons = get_physical_monitors()
    m1 = mons[0] if mons else {"x": 0, "y": 0, "width": 1920, "height": 1080}
    return [
        {
            "id": "primary_tablet",
            "name": "Android Tablet",
            "kind": "tablet",
            "ip": "",
            "port": DEFAULT_MC_PORT,
            "use_usb_first": True,
            "x": int(m1["x"]),
            "y": int(m1["y"] + m1["height"]),
            "width": 1920,
            "height": 1152,
            "screen_w": 2000,
            "screen_h": 1200,
            "orientation": "landscape",
            "sensitivity": 1.25,
            "enabled": True,
        }
    ]


class _DeviceConn:
    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.connected_via: str = ""
        self.last_error: str = ""


class MultiControlManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.enabled: bool = True
        self.devices: list[dict[str, Any]] = []
        self._conns: dict[str, _DeviceConn] = {}

        # Active state
        self.active_device_id: str | None = None
        self._monitors_cache: list[dict[str, Any]] = []
        self._monitors_ts: float = 0.0

        self._thread: threading.Thread | None = None
        self._conn_thread: threading.Thread | None = None
        self._stop_ev = threading.Event()
        self._thread_id: int = 0
        self._mouse_hook = None
        self._kbd_hook = None
        self._mouse_cb = None
        self._kbd_cb = None

        # Anchor cursor inside primary monitor while controlling an Android device
        self._anchor_x: int = 960
        self._anchor_y: int = 540
        self._return_x: int = 960
        self._return_y: int = 540

        # Tracked cursor inside active Android device (in Android pixels)
        self._dev_x: float = 1000.0
        self._dev_y: float = 600.0
        self._overshoot_x: float = 0.0
        self._overshoot_y: float = 0.0
        self._last_switch_ts: float = 0.0
        self._edge_dwell_start: float = 0.0
        self._edge_dwell_target: str = ""
        self._held_vks: set[int] = set()

        self._load_config()

    # -----------------------------------------------------------------------
    # Configuration & Device Management
    # -----------------------------------------------------------------------
    def _load_config(self) -> None:
        loaded_devices = None
        try:
            if MC_CONFIG_PATH.exists():
                cfg = json.loads(MC_CONFIG_PATH.read_text(encoding="utf-8"))
                self.enabled = bool(cfg.get("enabled", True))
                if isinstance(cfg.get("devices"), list) and cfg["devices"]:
                    loaded_devices = cfg["devices"]
        except Exception:
            pass

        self.devices = loaded_devices if loaded_devices else _default_devices()
        for d in self.devices:
            self._normalize_device(d)
            self._conns.setdefault(d["id"], _DeviceConn())
        self._save_config()

    def _normalize_device(self, d: dict[str, Any]) -> None:
        d.setdefault("id", f"dev_{uuid.uuid4().hex[:6]}")
        d.setdefault("name", "Android Device")
        d.setdefault("kind", "phone")
        d.setdefault("ip", "")
        d["port"] = int(d.get("port", DEFAULT_MC_PORT))
        d["use_usb_first"] = bool(d.get("use_usb_first", d["kind"] == "tablet"))
        d["x"] = int(round(float(d.get("x", 0))))
        d["y"] = int(round(float(d.get("y", 1080))))
        orient = str(d.get("orientation", "landscape" if d["kind"] == "tablet" else "portrait"))
        d["orientation"] = orient
        if d["kind"] == "tablet":
            default_sw, default_sh = (2000, 1200) if orient == "landscape" else (1200, 2000)
            default_w, default_h = (1920, 1152) if orient == "landscape" else (1152, 1920)
        else:
            default_sw, default_sh = (1080, 2400) if orient == "portrait" else (2400, 1080)
            default_w, default_h = (540, 1120) if orient == "portrait" else (1120, 540)
        d["screen_w"] = int(d.get("screen_w", default_sw))
        d["screen_h"] = int(d.get("screen_h", default_sh))
        d["width"] = int(d.get("width", default_w))
        d["height"] = int(d.get("height", default_h))
        d["sensitivity"] = max(0.4, min(3.0, float(d.get("sensitivity", 1.25))))
        d["enabled"] = bool(d.get("enabled", True))

    def _save_config(self) -> None:
        try:
            MC_CONFIG_PATH.write_text(
                json.dumps({"enabled": self.enabled, "devices": self.devices}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def note_tablet_ip(self, ip: str) -> None:
        if not ip or ip.startswith("127.") or ip == "::1":
            return
        with self._lock:
            tab = next((d for d in self.devices if d.get("kind") == "tablet"), None)
            if tab and tab.get("ip") != ip:
                tab["ip"] = ip
                self._save_config()

    def _get_monitors(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if not self._monitors_cache or (now - self._monitors_ts) > 5.0:
            self._monitors_cache = get_physical_monitors()
            self._monitors_ts = now
        return self._monitors_cache

    def _get_device(self, dev_id: str | None) -> dict[str, Any] | None:
        if not dev_id:
            return None
        for d in self.devices:
            if d["id"] == dev_id:
                return d
        return None

    def get_layout(self) -> dict[str, Any]:
        mons = get_physical_monitors()
        self._monitors_cache = mons
        self._monitors_ts = time.monotonic()
        dev_out = []
        with self._lock:
            for d in self.devices:
                c = self._conns.get(d["id"])
                item = dict(d)
                item["online"] = bool(c and c.sock is not None)
                item["connected_via"] = c.connected_via if c else ""
                item["last_error"] = c.last_error if c else ""
                item["active"] = self.active_device_id == d["id"]
                dev_out.append(item)
        return {
            "enabled": self.enabled,
            "active_device_id": self.active_device_id,
            "active_on_tablet": self.active_device_id is not None,
            "hotkey": "Ctrl+Alt+M",
            "monitors": mons,
            "devices": dev_out,
        }

    def get_status(self) -> dict[str, Any]:
        layout = self.get_layout()
        online_devs = [d for d in layout["devices"] if d["online"]]
        active_dev = next((d for d in layout["devices"] if d["active"]), None)
        return {
            "enabled": self.enabled,
            "active_device_id": self.active_device_id,
            "active_device_name": active_dev["name"] if active_dev else "",
            "active_on_tablet": self.active_device_id is not None,
            "connected_via": (active_dev["connected_via"] if active_dev else (online_devs[0]["connected_via"] if online_devs else "")),
            "online_count": len(online_devs),
            "device_count": len(layout["devices"]),
            "hotkey": "Ctrl+Alt+M",
            "devices": layout["devices"],
        }

    def update_layout(self, enabled: bool | None = None, devices: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if enabled is not None:
            self.enabled = bool(enabled)
            if not self.enabled and self.active_device_id:
                self.leave_device()

        if devices is not None:
            new_list = []
            keep_ids = set()
            for raw in devices:
                d = dict(raw)
                self._normalize_device(d)
                new_list.append(d)
                keep_ids.add(d["id"])

            with self._lock:
                # Close sockets for removed or IP-changed devices
                old_by_id = {d["id"]: d for d in self.devices}
                for did in list(self._conns.keys()):
                    if did not in keep_ids:
                        self._close_device_conn_unlocked(did)
                        self._conns.pop(did, None)
                for d in new_list:
                    self._conns.setdefault(d["id"], _DeviceConn())
                    old = old_by_id.get(d["id"])
                    if old and (old.get("ip") != d.get("ip") or old.get("port") != d.get("port")):
                        self._close_device_conn_unlocked(d["id"])
                self.devices = new_list
                if self.active_device_id and self.active_device_id not in keep_ids:
                    self.active_device_id = None

        self._save_config()
        return self.get_layout()

    def add_device(self, name: str, kind: str = "phone", ip: str = "", orientation: str = "portrait") -> dict[str, Any]:
        mons = self._get_monitors()
        rightmost = max(mons, key=lambda m: m["x"] + m["width"])
        dev: dict[str, Any] = {
            "id": f"dev_{uuid.uuid4().hex[:6]}",
            "name": (name or ("My Phone" if kind == "phone" else "Android Tablet")).strip(),
            "kind": "tablet" if kind == "tablet" else "phone",
            "ip": (ip or "").strip(),
            "port": DEFAULT_MC_PORT,
            "use_usb_first": False,
            "orientation": "landscape" if orientation == "landscape" else "portrait",
            "x": int(rightmost["x"] + rightmost["width"]),
            "y": int(rightmost["y"] + 40),
            "sensitivity": 1.25,
            "enabled": True,
        }
        self._normalize_device(dev)
        with self._lock:
            self.devices.append(dev)
            self._conns[dev["id"]] = _DeviceConn()
        self._save_config()
        return self.get_layout()

    def delete_device(self, dev_id: str) -> dict[str, Any]:
        if self.active_device_id == dev_id:
            self.leave_device()
        with self._lock:
            self.devices = [d for d in self.devices if d["id"] != dev_id]
            self._close_device_conn_unlocked(dev_id)
            self._conns.pop(dev_id, None)
        self._save_config()
        return self.get_layout()

    # -----------------------------------------------------------------------
    # Persistent Background Socket Pool
    # -----------------------------------------------------------------------
    def _close_device_conn_unlocked(self, dev_id: str) -> None:
        c = self._conns.get(dev_id)
        if not c:
            return
        if c.sock is not None:
            try:
                c.sock.sendall(_pack_ev(EV_RELEASE_ALL, 0, 0))
            except Exception:
                pass
            try:
                c.sock.close()
            except Exception:
                pass
            c.sock = None
        c.connected_via = ""

    def _connect_device(self, dev: dict[str, Any]) -> bool:
        dev_id = dev["id"]
        port = int(dev.get("port", DEFAULT_MC_PORT))
        ip = str(dev.get("ip", "")).strip()
        targets: list[tuple[str, str]] = []
        if dev.get("use_usb_first"):
            targets.append(("127.0.0.1", "USB"))
        if ip:
            targets.append((ip, f"Wi-Fi ({ip})"))
        if not targets:
            with self._lock:
                c = self._conns.setdefault(dev_id, _DeviceConn())
                c.last_error = "No IP configured"
            return False

        last_err = "Device unreachable"
        for host, label in targets:
            s = None
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.45)
                s.connect((host, port))
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.sendall(_pack_ev(EV_PING, 0, 0))
                if s.recv(4) == b"PONG":
                    s.settimeout(1.5)
                    with self._lock:
                        c = self._conns.setdefault(dev_id, _DeviceConn())
                        c.sock = s
                        c.connected_via = label
                        c.last_error = ""
                    return True
                s.close()
            except Exception as exc:
                last_err = str(exc)
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass

        with self._lock:
            c = self._conns.setdefault(dev_id, _DeviceConn())
            c.connected_via = ""
            c.last_error = last_err
        return False

    def _send_to_device(self, dev_id: str, payload: bytes) -> bool:
        with self._lock:
            c = self._conns.get(dev_id)
            s = c.sock if c else None
        if s is None:
            return False
        try:
            s.sendall(payload)
            return True
        except Exception as exc:
            with self._lock:
                c2 = self._conns.get(dev_id)
                if c2:
                    c2.last_error = str(exc)
                self._close_device_conn_unlocked(dev_id)
            if self.active_device_id == dev_id:
                self.active_device_id = None
            return False

    # -----------------------------------------------------------------------
    # Entry Calibration & Spatial Transitions
    # -----------------------------------------------------------------------
    def _calibrate_android_cursor(self, dev_id: str, target_x: float, target_y: float, sensitivity: float) -> None:
        """
        Zero-slam Android's uinput pointer to exact (0, 0) in small uniform steps,
        then step smoothly to (target_x, target_y). Fixes Android's center-spawn
        offset so the cursor appears immediately right at the crossed screen edge!
        """
        # Convert Android pixels -> raw REL counts (inverse of pointer gain)
        px_per_unit = max(0.5, float(sensitivity) * 0.78)
        raw_x = int(round(target_x / px_per_unit))
        raw_y = int(round(target_y / px_per_unit))

        buf = bytearray()
        # 1. Slam to top-left corner (0, 0) using moderate steps so Android never drops events
        for _ in range(18):
            buf += _pack_ev(EV_REL, REL_X, -180)
            buf += _pack_ev(EV_REL, REL_Y, -180)
            buf += _pack_ev(EV_SYN, 0, 0)

        # 2. Walk smoothly in uniform <= 36-unit steps to avoid VelocityControl acceleration skew
        rem_x, rem_y = raw_x, raw_y
        step = 36
        while rem_x > 0 or rem_y > 0:
            sx = min(step, rem_x)
            sy = min(step, rem_y)
            if sx:
                buf += _pack_ev(EV_REL, REL_X, sx)
            if sy:
                buf += _pack_ev(EV_REL, REL_Y, sy)
            buf += _pack_ev(EV_SYN, 0, 0)
            rem_x -= sx
            rem_y -= sy

        self._send_to_device(dev_id, bytes(buf))

    def enter_device(self, dev_id: str, entry_rx: float = 0.5, entry_ry: float = 0.5) -> bool:
        with self._lock:
            dev = self._get_device(dev_id)
            c = self._conns.get(dev_id)
            ready = bool(dev and dev.get("enabled") and c and c.sock is not None)
        if not ready or not dev:
            return False

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self._return_x, self._return_y = pt.x, pt.y

        mons = self._get_monitors()
        m1 = mons[0]
        self._anchor_x = m1["x"] + m1["width"] // 2
        self._anchor_y = m1["y"] + m1["height"] // 2

        sw = float(dev["screen_w"])
        sh = float(dev["screen_h"])
        tx = max(8.0, min(sw - 8.0, entry_rx * sw))
        ty = max(8.0, min(sh - 8.0, entry_ry * sh))

        self._dev_x = tx
        self._dev_y = ty
        self._overshoot_x = 0.0
        self._overshoot_y = 0.0
        self.active_device_id = dev_id
        self._last_switch_ts = time.monotonic()
        self._edge_dwell_start = 0.0

        user32.SetCursorPos(self._anchor_x, self._anchor_y)
        self._calibrate_android_cursor(dev_id, tx, ty, float(dev.get("sensitivity", 1.25)))
        return True

    def leave_device(self, target_win_x: int | None = None, target_win_y: int | None = None) -> None:
        dev_id = self.active_device_id
        if not dev_id:
            return
        self.active_device_id = None
        self._last_switch_ts = time.monotonic()
        self._edge_dwell_start = 0.0
        self._overshoot_x = 0.0
        self._overshoot_y = 0.0
        self._send_to_device(dev_id, _pack_ev(EV_RELEASE_ALL, 0, 0))

        rx = self._return_x if target_win_x is None else target_win_x
        ry = self._return_y if target_win_y is None else target_win_y
        user32.SetCursorPos(int(rx), int(ry))

    def toggle_device(self, dev_id: str | None = None) -> dict[str, Any]:
        if self.active_device_id:
            if dev_id is None or dev_id == self.active_device_id:
                self.leave_device()
                return self.get_status()
            self.leave_device()

        with self._lock:
            candidates = [d for d in self.devices if d.get("enabled") and self._conns.get(d["id"]) and self._conns[d["id"]].sock]
        target = None
        if dev_id:
            target = next((d for d in candidates if d["id"] == dev_id), None)
        elif candidates:
            target = candidates[0]

        if target:
            self.enter_device(target["id"], 0.5, 0.5)
        return self.get_status()

    # -----------------------------------------------------------------------
    # 2D Spatial Crossing Helpers
    # -----------------------------------------------------------------------
    def _is_virtual_3rd_streaming(self) -> bool:
        try:
            st = video_stream.get_adaptive_state()
            return int(st.get("monitor", 1)) >= 3
        except Exception:
            return False

    def _point_in_rect(self, x: float, y: float, r: dict[str, Any], pad: int = 0) -> bool:
        return (r["x"] - pad) <= x <= (r["x"] + r["width"] + pad) and (r["y"] - pad) <= y <= (r["y"] + r["height"] + pad)

    def _find_device_crossing_from_windows(self, x: int, y: int) -> tuple[str, float, float] | None:
        """Check if Windows cursor (x, y) is touching an edge adjacent to an online Android device."""
        mons = self._get_monitors()
        cur_mon = next((m for m in mons if self._point_in_rect(x, y, m, pad=2)), None)
        if not cur_mon:
            # Cursor wandered onto virtual Display 3 (MTT1337) — check if right of Monitor 2 has a device
            if not self._is_virtual_3rd_streaming():
                rightmost = max(mons, key=lambda m: m["x"] + m["width"])
                if x >= rightmost["x"] + rightmost["width"] - 2:
                    cur_mon = rightmost
                    x = rightmost["x"] + rightmost["width"] - 1
            if not cur_mon:
                return None

        mx, my, mw, mh = cur_mon["x"], cur_mon["y"], cur_mon["width"], cur_mon["height"]
        edge_tol = 4
        snap_tol = 45

        with self._lock:
            online_devs = [
                d for d in self.devices
                if d.get("enabled") and self._conns.get(d["id"]) and self._conns[d["id"]].sock is not None
            ]
        if not online_devs:
            return None

        # Check Bottom edge of current physical monitor
        if y >= my + mh - edge_tol and not any(self._point_in_rect(x, y + 10, m) for m in mons if m["id"] != cur_mon["id"]):
            for d in online_devs:
                if abs(d["y"] - (my + mh)) <= snap_tol and d["x"] <= x <= d["x"] + d["width"]:
                    rx = (x - d["x"]) / max(1, d["width"])
                    return (d["id"], rx, 0.02)

        # Check Top edge
        if y <= my + edge_tol and not any(self._point_in_rect(x, y - 10, m) for m in mons if m["id"] != cur_mon["id"]):
            for d in online_devs:
                if abs((d["y"] + d["height"]) - my) <= snap_tol and d["x"] <= x <= d["x"] + d["width"]:
                    rx = (x - d["x"]) / max(1, d["width"])
                    return (d["id"], rx, 0.98)

        # Check Right edge (also intercepts before hidden Virtual Display 3 unless streaming Screen 3!)
        if x >= mx + mw - edge_tol and not any(self._point_in_rect(x + 10, y, m) for m in mons if m["id"] != cur_mon["id"]):
            if not self._is_virtual_3rd_streaming():
                for d in online_devs:
                    if abs(d["x"] - (mx + mw)) <= snap_tol and d["y"] <= y <= d["y"] + d["height"]:
                        ry = (y - d["y"]) / max(1, d["height"])
                        return (d["id"], 0.02, ry)

        # Check Left edge
        if x <= mx + edge_tol and not any(self._point_in_rect(x - 10, y, m) for m in mons if m["id"] != cur_mon["id"]):
            for d in online_devs:
                if abs((d["x"] + d["width"]) - mx) <= snap_tol and d["y"] <= y <= d["y"] + d["height"]:
                    ry = (y - d["y"]) / max(1, d["height"])
                    return (d["id"], 0.98, ry)

        return None

    def _try_exit_device(self, dev: dict[str, Any], side: str) -> bool:
        """
        Attempt to exit `dev` across `side` ('top' | 'bottom' | 'left' | 'right').
        Only crosses if a Windows monitor or another online Android device sits across that edge!
        """
        mons = self._get_monitors()
        rx = self._dev_x / max(1.0, float(dev["screen_w"]))
        ry = self._dev_y / max(1.0, float(dev["screen_h"]))
        snap_tol = 45

        world_x = dev["x"] + rx * dev["width"]
        world_y = dev["y"] + ry * dev["height"]

        # 1. Check neighboring physical Windows monitors
        for m in mons:
            if side == "top" and abs((m["y"] + m["height"]) - dev["y"]) <= snap_tol and m["x"] <= world_x <= m["x"] + m["width"]:
                self.leave_device(int(max(m["x"] + 8, min(m["x"] + m["width"] - 8, world_x))), int(m["y"] + m["height"] - 14))
                return True
            if side == "bottom" and abs(m["y"] - (dev["y"] + dev["height"])) <= snap_tol and m["x"] <= world_x <= m["x"] + m["width"]:
                self.leave_device(int(max(m["x"] + 8, min(m["x"] + m["width"] - 8, world_x))), int(m["y"] + 14))
                return True
            if side == "left" and abs((m["x"] + m["width"]) - dev["x"]) <= snap_tol and m["y"] <= world_y <= m["y"] + m["height"]:
                self.leave_device(int(m["x"] + m["width"] - 14), int(max(m["y"] + 8, min(m["y"] + m["height"] - 8, world_y))))
                return True
            if side == "right" and abs(m["x"] - (dev["x"] + dev["width"])) <= snap_tol and m["y"] <= world_y <= m["y"] + m["height"]:
                self.leave_device(int(m["x"] + 14), int(max(m["y"] + 8, min(m["y"] + m["height"] - 8, world_y))))
                return True

        # 2. Check neighboring online Android devices (direct Tablet <-> Phone crossing!)
        with self._lock:
            others = [
                o for o in self.devices
                if o["id"] != dev["id"] and o.get("enabled") and self._conns.get(o["id"]) and self._conns[o["id"]].sock is not None
            ]
        for o in others:
            if side == "top" and abs((o["y"] + o["height"]) - dev["y"]) <= snap_tol and o["x"] <= world_x <= o["x"] + o["width"]:
                self._send_to_device(dev["id"], _pack_ev(EV_RELEASE_ALL, 0, 0))
                return self.enter_device(o["id"], (world_x - o["x"]) / max(1, o["width"]), 0.98)
            if side == "bottom" and abs(o["y"] - (dev["y"] + dev["height"])) <= snap_tol and o["x"] <= world_x <= o["x"] + o["width"]:
                self._send_to_device(dev["id"], _pack_ev(EV_RELEASE_ALL, 0, 0))
                return self.enter_device(o["id"], (world_x - o["x"]) / max(1, o["width"]), 0.02)
            if side == "left" and abs((o["x"] + o["width"]) - dev["x"]) <= snap_tol and o["y"] <= world_y <= o["y"] + o["height"]:
                self._send_to_device(dev["id"], _pack_ev(EV_RELEASE_ALL, 0, 0))
                return self.enter_device(o["id"], 0.98, (world_y - o["y"]) / max(1, o["height"]))
            if side == "right" and abs(o["x"] - (dev["x"] + dev["width"])) <= snap_tol and o["y"] <= world_y <= o["y"] + o["height"]:
                self._send_to_device(dev["id"], _pack_ev(EV_RELEASE_ALL, 0, 0))
                return self.enter_device(o["id"], 0.02, (world_y - o["y"]) / max(1, o["height"]))

        return False

    # -----------------------------------------------------------------------
    # Low-Level Mouse & Keyboard Hook Callbacks (< 0.5ms!)
    # -----------------------------------------------------------------------
    def _on_mouse(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode < 0:
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if info.flags & LLMHF_INJECTED:
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        now = time.monotonic()

        if not self.active_device_id:
            if self.enabled and wParam == WM_MOUSEMOVE and (now - self._last_switch_ts) > 0.45:
                hit = self._find_device_crossing_from_windows(info.pt.x, info.pt.y)
                if hit:
                    dev_id, rx, ry = hit
                    if self._edge_dwell_target != dev_id or self._edge_dwell_start == 0.0:
                        self._edge_dwell_target = dev_id
                        self._edge_dwell_start = now
                    elif (now - self._edge_dwell_start) >= 0.07:
                        self._edge_dwell_start = 0.0
                        if self.enter_device(dev_id, rx, ry):
                            return 1
                else:
                    self._edge_dwell_start = 0.0
                    self._edge_dwell_target = ""
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        # ---- Currently controlling an Android Device ----
        dev_id = self.active_device_id
        dev = self._get_device(dev_id)
        if not dev:
            self.leave_device()
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        if wParam == WM_MOUSEMOVE:
            dx = info.pt.x - self._anchor_x
            dy = info.pt.y - self._anchor_y
            if dx != 0 or dy != 0:
                sens = float(dev.get("sensitivity", 1.25))
                sw = float(dev["screen_w"])
                sh = float(dev["screen_h"])

                # Send scaled raw deltas to Android uinput, and track Android pixels symmetrically
                send_dx = int(round(dx * sens))
                send_dy = int(round(dy * sens))
                est_px_dx = send_dx * 0.78
                est_px_dy = send_dy * 0.78

                nx = self._dev_x + est_px_dx
                ny = self._dev_y + est_px_dy

                can_exit = (now - self._last_switch_ts) > 0.35
                overshoot_thresh = 24.0

                if nx < 0.0:
                    self._dev_x = 0.0
                    self._overshoot_x += (-nx)
                    if can_exit and self._overshoot_x >= overshoot_thresh and self._try_exit_device(dev, "left"):
                        return 1
                elif nx > sw:
                    self._dev_x = sw
                    self._overshoot_x += (nx - sw)
                    if can_exit and self._overshoot_x >= overshoot_thresh and self._try_exit_device(dev, "right"):
                        return 1
                else:
                    self._dev_x = nx
                    self._overshoot_x = 0.0

                if ny < 0.0:
                    self._dev_y = 0.0
                    self._overshoot_y += (-ny)
                    if can_exit and self._overshoot_y >= overshoot_thresh and self._try_exit_device(dev, "top"):
                        return 1
                elif ny > sh:
                    self._dev_y = sh
                    self._overshoot_y += (ny - sh)
                    if can_exit and self._overshoot_y >= overshoot_thresh and self._try_exit_device(dev, "bottom"):
                        return 1
                else:
                    self._dev_y = ny
                    self._overshoot_y = 0.0

                buf = b""
                if send_dx:
                    buf += _pack_ev(EV_REL, REL_X, send_dx)
                if send_dy:
                    buf += _pack_ev(EV_REL, REL_Y, send_dy)
                if buf:
                    buf += _pack_ev(EV_SYN, 0, 0)
                    self._send_to_device(dev_id, buf)
                user32.SetCursorPos(self._anchor_x, self._anchor_y)
            return 1

        if wParam == WM_LBUTTONDOWN:
            self._send_to_device(dev_id, _pack_ev(EV_KEY, BTN_LEFT, 1) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_LBUTTONUP:
            self._send_to_device(dev_id, _pack_ev(EV_KEY, BTN_LEFT, 0) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_RBUTTONDOWN:
            self._send_to_device(dev_id, _pack_ev(EV_KEY, BTN_RIGHT, 1) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_RBUTTONUP:
            self._send_to_device(dev_id, _pack_ev(EV_KEY, BTN_RIGHT, 0) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_MBUTTONDOWN:
            self._send_to_device(dev_id, _pack_ev(EV_KEY, BTN_MIDDLE, 1) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_MBUTTONUP:
            self._send_to_device(dev_id, _pack_ev(EV_KEY, BTN_MIDDLE, 0) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_MOUSEWHEEL:
            delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
            steps = 1 if delta > 0 else -1
            self._send_to_device(dev_id, _pack_ev(EV_REL, REL_WHEEL, steps) + _pack_ev(EV_SYN, 0, 0))
            return 1
        if wParam == WM_MOUSEHWHEEL:
            delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
            steps = 1 if delta > 0 else -1
            self._send_to_device(dev_id, _pack_ev(EV_REL, REL_HWHEEL, steps) + _pack_ev(EV_SYN, 0, 0))
            return 1

        return 1

    def _on_kbd(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode < 0:
            return user32.CallNextHookEx(self._kbd_hook, nCode, wParam, lParam)

        info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if info.flags & LLKHF_INJECTED:
            return user32.CallNextHookEx(self._kbd_hook, nCode, wParam, lParam)

        vk = info.vkCode
        is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)

        if is_down:
            self._held_vks.add(vk)
        elif is_up:
            self._held_vks.discard(vk)

        ctrl_held = bool(self._held_vks & {0x11, 0xA2, 0xA3})
        alt_held = bool(self._held_vks & {0x12, 0xA4, 0xA5})

        if is_down and self.enabled:
            if (ctrl_held and alt_held and vk == 0x4D) or vk == 0x91:
                self.toggle_device()
                return 1
            if self.active_device_id and ctrl_held and alt_held and vk == 0x1B:
                self.leave_device()
                return 1

        if not self.active_device_id:
            return user32.CallNextHookEx(self._kbd_hook, nCode, wParam, lParam)

        linux_code = VK_TO_LINUX.get(vk)
        if linux_code:
            val = 1 if is_down else 0
            self._send_to_device(self.active_device_id, _pack_ev(EV_KEY, linux_code, val) + _pack_ev(EV_SYN, 0, 0))
        return 1

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_ev.clear()

        def _conn_loop():
            while not self._stop_ev.is_set():
                if self.enabled:
                    with self._lock:
                        devs_snapshot = [dict(d) for d in self.devices if d.get("enabled")]
                    for d in devs_snapshot:
                        with self._lock:
                            c = self._conns.setdefault(d["id"], _DeviceConn())
                            has_sock = c.sock is not None
                        if not has_sock:
                            self._connect_device(d)
                self._stop_ev.wait(2.5)

        self._conn_thread = threading.Thread(target=_conn_loop, name="tabdeck-mc-conn", daemon=True)
        self._conn_thread.start()

        def _hook_loop():
            self._thread_id = kernel32.GetCurrentThreadId()
            self._mouse_cb = HOOKPROC(self._on_mouse)
            self._kbd_cb = HOOKPROC(self._on_kbd)
            self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_cb, None, 0)
            self._kbd_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kbd_cb, None, 0)

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
                self._mouse_hook = None
            if self._kbd_hook:
                user32.UnhookWindowsHookEx(self._kbd_hook)
                self._kbd_hook = None
            with self._lock:
                for did in list(self._conns.keys()):
                    self._close_device_conn_unlocked(did)

        self._thread = threading.Thread(target=_hook_loop, name="tabdeck-multicontrol", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_ev.set()
        if self.active_device_id:
            self.leave_device()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        with self._lock:
            for did in list(self._conns.keys()):
                self._close_device_conn_unlocked(did)


manager = MultiControlManager()
