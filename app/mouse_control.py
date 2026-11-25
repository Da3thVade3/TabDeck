import ctypes
import time

import mss

user32 = ctypes.windll.user32

# Mouse event flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

# Win32 Synthetic Pointer (Windows Ink PT_PEN) constants
PT_PEN = 3
POINTER_FEEDBACK_DEFAULT = 1
POINTER_FEEDBACK_INDIRECT = 2
POINTER_FLAG_NONE = 0x00000000
POINTER_FLAG_NEW = 0x00000001
POINTER_FLAG_INRANGE = 0x00000002
POINTER_FLAG_INCONTACT = 0x00000004
POINTER_FLAG_FIRSTBUTTON = 0x00000010
POINTER_FLAG_SECONDBUTTON = 0x00000020
POINTER_FLAG_PRIMARY = 0x00002000
POINTER_FLAG_DOWN = 0x00010000
POINTER_FLAG_UPDATE = 0x00020000
POINTER_FLAG_UP = 0x00040000

PEN_FLAG_BARREL = 0x00000001
PEN_FLAG_INVERTED = 0x00000002
PEN_FLAG_ERASER = 0x00000004

PEN_MASK_PRESSURE = 0x00000001
PEN_MASK_TILT_X = 0x00000004
PEN_MASK_TILT_Y = 0x00000008


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", ctypes.c_uint32),
        ("pointerId", ctypes.c_uint32),
        ("frameId", ctypes.c_uint32),
        ("pointerFlags", ctypes.c_uint32),
        ("sourceDevice", ctypes.c_void_p),
        ("hwndTarget", ctypes.c_void_p),
        ("ptPixelLocation", POINT),
        ("ptHimetricLocation", POINT),
        ("ptPixelLocationRaw", POINT),
        ("ptHimetricLocationRaw", POINT),
        ("dwTime", ctypes.c_uint32),
        ("historyCount", ctypes.c_uint32),
        ("InputData", ctypes.c_int32),
        ("dwKeyStates", ctypes.c_uint32),
        ("PerformanceCount", ctypes.c_uint64),
        ("ButtonChangeType", ctypes.c_int32),
    ]


class POINTER_PEN_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("penFlags", ctypes.c_uint32),
        ("penMask", ctypes.c_uint32),
        ("pressure", ctypes.c_uint32),
        ("rotation", ctypes.c_uint32),
        ("tiltX", ctypes.c_int32),
        ("tiltY", ctypes.c_int32),
    ]


class _POINTER_UNION(ctypes.Union):
    _fields_ = [
        ("penInfo", POINTER_PEN_INFO),
        ("_pad", ctypes.c_byte * 144),
    ]


class POINTER_TYPE_INFO(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("u", _POINTER_UNION),
    ]


try:
    user32.CreateSyntheticPointerDevice.restype = ctypes.c_void_p
    user32.CreateSyntheticPointerDevice.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    user32.InjectSyntheticPointerInput.restype = ctypes.c_int
    user32.InjectSyntheticPointerInput.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINTER_TYPE_INFO), ctypes.c_uint32]
    user32.DestroySyntheticPointerDevice.argtypes = [ctypes.c_void_p]
except Exception:
    pass


class SyntheticPen:
    """Native Windows Ink Pen injector following Win32's strict NEW/INRANGE/DOWN/UPDATE/UP state machine."""

    def __init__(self) -> None:
        self._handle = None
        self._in_range = False
        self._in_contact = False
        self._last_px = 0
        self._last_py = 0
        self.last_ok = None
        self.last_error = 0
        self.events_count = 0

    def _ensure_device(self) -> bool:
        if self._handle:
            return True
        try:
            h = user32.CreateSyntheticPointerDevice(PT_PEN, 1, POINTER_FEEDBACK_DEFAULT)
            if h:
                self._handle = h
                return True
        except Exception:
            pass
        return False

    def _send_packet(
        self,
        flags: int,
        px: int,
        py: int,
        pressure: float,
        tilt_x: int,
        tilt_y: int,
        barrel: bool,
        eraser: bool,
        in_contact: bool,
    ) -> bool:
        info = POINTER_TYPE_INFO()
        info.type = PT_PEN
        pinfo = info.u.penInfo.pointerInfo
        pinfo.pointerType = PT_PEN
        pinfo.pointerId = 1
        pinfo.pointerFlags = flags
        pinfo.ptPixelLocation = POINT(px, py)
        pinfo.ptPixelLocationRaw = POINT(px, py)

        pen_flags = 0
        if barrel:
            pen_flags |= PEN_FLAG_BARREL
        if eraser:
            pen_flags |= PEN_FLAG_ERASER | PEN_FLAG_INVERTED
        info.u.penInfo.penFlags = pen_flags
        info.u.penInfo.penMask = PEN_MASK_PRESSURE | PEN_MASK_TILT_X | PEN_MASK_TILT_Y
        p_norm = max(0.0, min(1.0, float(pressure)))
        info.u.penInfo.pressure = max(1, int(p_norm * 1024)) if in_contact else 0
        info.u.penInfo.tiltX = max(-90, min(90, int(tilt_x)))
        info.u.penInfo.tiltY = max(-90, min(90, int(tilt_y)))

        ctypes.set_last_error(0)
        ok = bool(user32.InjectSyntheticPointerInput(self._handle, ctypes.byref(info), 1))
        self.last_ok = ok
        self.last_error = 0 if ok else ctypes.windll.kernel32.GetLastError()
        return ok

    def inject(
        self,
        action: str,
        px: int,
        py: int,
        pressure: float = 0.5,
        tilt_x: int = 0,
        tilt_y: int = 0,
        barrel: bool = False,
        eraser: bool = False,
    ) -> bool:
        if not self._ensure_device():
            return False

        self.events_count += 1
        self._last_px, self._last_py = px, py
        btn_flag = POINTER_FLAG_SECONDBUTTON if barrel else POINTER_FLAG_FIRSTBUTTON

        if action == "hover":
            if self._in_contact:
                # Release contact cleanly first if a previous stroke wasn't closed
                self._send_packet(
                    POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_UP,
                    px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False,
                )
                self._in_contact = False
            flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_UPDATE
            if not self._in_range:
                flags |= POINTER_FLAG_NEW
                self._in_range = True
            return self._send_packet(flags, px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False)

        if action == "down":
            if not self._in_range:
                # Enter range first (hover NEW) so Windows transitions cleanly into Ink mode
                self._send_packet(
                    POINTER_FLAG_PRIMARY | POINTER_FLAG_NEW | POINTER_FLAG_INRANGE | POINTER_FLAG_UPDATE,
                    px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False,
                )
                self._in_range = True
            if self._in_contact:
                # Already down -> send UPDATE instead of illegal double-DOWN
                flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_UPDATE | btn_flag
            else:
                flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_DOWN | btn_flag
                self._in_contact = True
            return self._send_packet(flags, px, py, pressure, tilt_x, tilt_y, barrel, eraser, True)

        if action == "move":
            if not self._in_range:
                self._in_range = True
                flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_NEW | POINTER_FLAG_INRANGE | POINTER_FLAG_UPDATE
                return self._send_packet(flags, px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False)
            if self._in_contact:
                flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_UPDATE | btn_flag
                return self._send_packet(flags, px, py, pressure, tilt_x, tilt_y, barrel, eraser, True)
            flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_UPDATE
            return self._send_packet(flags, px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False)

        if action == "up":
            if not self._in_range:
                return True
            if self._in_contact:
                self._in_contact = False
                flags = POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_UP
                return self._send_packet(flags, px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False)
            return True

        if action == "leave":
            if self._in_contact:
                self._in_contact = False
                self._send_packet(
                    POINTER_FLAG_PRIMARY | POINTER_FLAG_INRANGE | POINTER_FLAG_UP,
                    px, py, 0.0, tilt_x, tilt_y, barrel, eraser, False,
                )
            if self._in_range:
                self._in_range = False
                return self._send_packet(
                    POINTER_FLAG_PRIMARY | POINTER_FLAG_UPDATE,
                    px, py, 0.0, 0, 0, False, False, False,
                )
            return True

        return False


_pen = SyntheticPen()
_mon_cache: list[dict] = []
_mon_cache_ts: float = 0.0

# Track active S-Pen state so video_stream hides the mouse arrow while using S-Pen
_pen_active: bool = False
_last_pen_ts: float = 0.0


def is_pen_active() -> bool:
    if not _pen_active:
        return False
    return (time.monotonic() - _last_pen_ts) < 1.5


def get_pen_status() -> dict:
    return {
        "device_ready": bool(_pen._ensure_device()),
        "in_range": _pen._in_range,
        "in_contact": _pen._in_contact,
        "pen_active": is_pen_active(),
        "last_ok": _pen.last_ok,
        "last_error": _pen.last_error,
        "events_count": _pen.events_count,
    }


def _mark_mouse_active() -> None:
    global _pen_active
    _pen_active = False


def _get_ordered_monitors() -> list[dict]:
    global _mon_cache, _mon_cache_ts
    now = time.monotonic()
    if _mon_cache and (now - _mon_cache_ts) < 5.0:
        return _mon_cache
    with mss.MSS() as sct:
        raw = list(sct.monitors[1:])
        raw.sort(key=lambda m: (0 if m.get("is_primary") else 1))
        _mon_cache = raw
        _mon_cache_ts = now
    return _mon_cache


def _normalized_to_screen_xy(monitor: int, rx: float, ry: float) -> tuple[int, int]:
    mons = _get_ordered_monitors()
    idx = (monitor - 1) if 1 <= monitor <= len(mons) else 0
    mon = mons[idx]
    rx = max(0.0, min(1.0, float(rx)))
    ry = max(0.0, min(1.0, float(ry)))
    px = int(mon["left"] + rx * (mon["width"] - 1))
    py = int(mon["top"] + ry * (mon["height"] - 1))
    return px, py


def move_relative(dx: float, dy: float) -> None:
    _mark_mouse_active()
    pt = POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        user32.SetCursorPos(int(pt.x + dx), int(pt.y + dy))
    else:
        user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


def move_absolute(monitor: int, rx: float, ry: float) -> None:
    _mark_mouse_active()
    px, py = _normalized_to_screen_xy(monitor, rx, ry)
    user32.SetCursorPos(px, py)


def click(button: str = "left", double: bool = False) -> None:
    _mark_mouse_active()
    down, up = (
        (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
        if button == "right"
        else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    )
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)
    if double:
        time.sleep(0.04)
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)


def button_down(button: str = "left") -> None:
    _mark_mouse_active()
    flag = MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_LEFTDOWN
    user32.mouse_event(flag, 0, 0, 0, 0)


def button_up(button: str = "left") -> None:
    flag = MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_LEFTUP
    user32.mouse_event(flag, 0, 0, 0, 0)


def scroll(dy: float = 0.0, dx: float = 0.0) -> None:
    if dy:
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(dy), 0)
    if dx:
        user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, int(dx), 0)


# ---------------------------------------------------------------------------
# Win32 SendInput Keyboard (Unicode text + PC special keys from Android KB)
# ---------------------------------------------------------------------------
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("_pad", ctypes.c_byte * 32),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("u", _INPUT_UNION),
    ]


_VK_MAP = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
    "del": 0x2E,
    "win": 0x5B,
    "a": 0x41,
    "c": 0x43,
    "v": 0x56,
    "x": 0x58,
    "z": 0x5A,
    "y": 0x59,
}

_EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2E, 0x5B}


def _send_inputs(items: list[INPUT]) -> None:
    if not items:
        return
    arr = (INPUT * len(items))(*items)
    user32.SendInput(len(items), arr, ctypes.sizeof(INPUT))


def type_text(text: str) -> None:
    """Inject arbitrary Unicode text (including punctuation/emoji/swipe input) into the active Windows app."""
    if not text:
        return
    items: list[INPUT] = []
    for ch in text:
        if ch == "\n":
            send_key("enter")
            continue
        if ch == "\r":
            continue
        # Encode to UTF-16 code units so surrogate pairs (emoji) work too
        raw = ch.encode("utf-16-le")
        for i in range(0, len(raw), 2):
            code_unit = int.from_bytes(raw[i : i + 2], "little")
            inp_down = INPUT(type=INPUT_KEYBOARD)
            inp_down.u.ki = KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
            inp_up = INPUT(type=INPUT_KEYBOARD)
            inp_up.u.ki = KEYBDINPUT(
                wVk=0, wScan=code_unit, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0
            )
            items.append(inp_down)
            items.append(inp_up)
    _send_inputs(items)


def send_key(key: str, ctrl: bool = False, alt: bool = False, shift: bool = False) -> None:
    """Press and release a Windows virtual key with optional Ctrl/Alt/Shift modifiers."""
    vk = _VK_MAP.get((key or "").lower())
    if not vk:
        return
    mods = []
    if ctrl:
        mods.append(0x11)
    if alt:
        mods.append(0x12)
    if shift:
        mods.append(0x10)

    items: list[INPUT] = []
    for m in mods:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=m, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        items.append(inp)

    ext = KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED_VKS else 0
    k_down = INPUT(type=INPUT_KEYBOARD)
    k_down.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=ext, time=0, dwExtraInfo=0)
    k_up = INPUT(type=INPUT_KEYBOARD)
    k_up.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=ext | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    items.extend([k_down, k_up])

    for m in reversed(mods):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=m, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        items.append(inp)

    _send_inputs(items)


def handle_pen_event(ev: dict) -> None:
    global _pen_active, _last_pen_ts
    action = ev.get("a", "hover")  # hover | down | move | up | leave
    mon = int(ev.get("mon", 1))
    px, py = _normalized_to_screen_xy(mon, ev.get("rx", 0.5), ev.get("ry", 0.5))
    pressure = float(ev.get("p", 0.5))
    tilt_x = int(ev.get("tx", 0))
    tilt_y = int(ev.get("ty", 0))
    barrel = bool(ev.get("barrel", False))
    eraser = bool(ev.get("eraser", False))
    use_ink = bool(ev.get("ink", True))

    if action == "leave":
        _pen_active = False
    else:
        _pen_active = True
        _last_pen_ts = time.monotonic()

    if use_ink:
        # Do NOT call SetCursorPos before PT_PEN injection — SetCursorPos switches
        # Windows back into Mouse mode and shows the mouse arrow!
        ok = _pen.inject(action, px, py, pressure, tilt_x, tilt_y, barrel, eraser)
        if ok:
            return

    # Fallback if Windows Ink is toggled OFF or blocked on an elevated window
    if action != "leave":
        user32.SetCursorPos(px, py)
    if action == "down":
        button_down("right" if barrel else "left")
        _pen_active = True
        _last_pen_ts = time.monotonic()
    elif action == "up":
        button_up("right" if barrel else "left")


def handle_input_event(ev: dict) -> None:
    t = ev.get("t", "")
    if t == "pen":
        handle_pen_event(ev)
    elif t == "move":
        move_relative(ev.get("dx", 0), ev.get("dy", 0))
    elif t == "click":
        click(ev.get("btn", "left"), bool(ev.get("dbl", False)))
    elif t == "down":
        button_down(ev.get("btn", "left"))
    elif t == "up":
        button_up(ev.get("btn", "left"))
    elif t == "scroll":
        scroll(ev.get("dy", 0), ev.get("dx", 0))
    elif t == "abs_move":
        move_absolute(int(ev.get("mon", 1)), ev.get("rx", 0.5), ev.get("ry", 0.5))
    elif t == "abs_down":
        move_absolute(int(ev.get("mon", 1)), ev.get("rx", 0.5), ev.get("ry", 0.5))
        button_down(ev.get("btn", "left"))
    elif t == "abs_up":
        if "rx" in ev and "ry" in ev:
            move_absolute(int(ev.get("mon", 1)), ev.get("rx", 0.5), ev.get("ry", 0.5))
        button_up(ev.get("btn", "left"))
    elif t == "abs_click":
        move_absolute(int(ev.get("mon", 1)), ev.get("rx", 0.5), ev.get("ry", 0.5))
        click(ev.get("btn", "left"), bool(ev.get("dbl", False)))
    elif t == "text":
        type_text(str(ev.get("s", "")))
    elif t == "key":
        send_key(
            str(ev.get("k", "")),
            ctrl=bool(ev.get("ctrl", False)),
            alt=bool(ev.get("alt", False)),
            shift=bool(ev.get("shift", False)),
        )
