import ctypes
import io
import time
from typing import Iterator

import mss
import psutil
from PIL import Image, ImageDraw, ImageGrab

import mouse_control

# Enable Per-Monitor DPI Awareness v2 so mixed-scaling displays (1080p + 1200p)
# capture exact, uncropped pixel coordinates on Windows 10/11.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9

# Keywords matched against top visible window on the STREAMED monitor
MEDIA_KEYWORDS = (
    "netflix",
    "youtube",
    "prime video",
    "disney+",
    "hotstar",
    "twitch",
    "crunchyroll",
    "vlc",
    "mpv",
    "plex",
    "jellyfin",
    "hulu",
    "max —",
    "stremio",
    "potplayer",
    "media player",
)

DRAWING_KEYWORDS = (
    "onenote",
    "whiteboard",
    "krita",
    "photoshop",
    "clipstudio",
    "clip studio",
    "mspaint",
    "paint.net",
    "gimp",
    "inkscape",
    "blender",
    "figma",
    "excalidraw",
    "xournal",
    "goodnotes",
    "sketchbook",
    "affinity",
    "illustrator",
    "obsidian",
    "draw.io",
    "miro",
    "freeform",
    "journal",
)

IGNORED_PROCS = {
    "explorer.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "applicationframehost.exe",
    "textinputhost.exe",
    "lockapp.exe",
}

_current_adaptive_state = {
    "mode": "balanced",
    "app": "",
    "monitor": 1,
    "width": 1280,
    "fps": 24,
    "quality": 72,
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def get_adaptive_state() -> dict:
    return dict(_current_adaptive_state)


def _window_rect(hwnd: int) -> RECT:
    r = RECT()
    try:
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r))
        if res == 0 and (r.right - r.left) > 0 and (r.bottom - r.top) > 0:
            return r
    except Exception:
        pass
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def _is_window_cloaked(hwnd: int) -> bool:
    cloaked = ctypes.c_int(0)
    try:
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return res == 0 and cloaked.value != 0
    except Exception:
        return False


def get_top_window_on_monitor(mon: dict) -> tuple[str, str]:
    """Walk Z-order top-to-bottom and return (proc_lower, title_lower) of the topmost visible window on `mon`."""
    m_left = mon["left"]
    m_top = mon["top"]
    m_right = m_left + mon["width"]
    m_bottom = m_top + mon["height"]
    min_area = (mon["width"] * mon["height"]) * 0.08  # ignore tiny popups/tooltips

    found: list[tuple[str, str]] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if _is_window_cloaked(hwnd):
            return True
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        r = _window_rect(hwnd)
        # Compute intersection with target monitor
        ix = max(0, min(r.right, m_right) - max(r.left, m_left))
        iy = max(0, min(r.bottom, m_bottom) - max(r.top, m_top))
        if (ix * iy) < min_area:
            return True

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip().lower()
        if not title or title == "program manager":
            return True

        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = ""
        if pid.value:
            try:
                proc = psutil.Process(pid.value).name().lower()
            except Exception:
                proc = ""

        # Skip pure shell chrome unless it's a UWP app hosted inside ApplicationFrameHost (e.g. Netflix/Whiteboard UWP)
        if proc in IGNORED_PROCS and proc != "applicationframehost.exe":
            return True

        found.append((proc, title))
        return False  # Stop at the topmost real window on this monitor

    try:
        user32.EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception:
        pass

    return found[0] if found else ("", "")


def _detect_profile_for_monitor(
    mon: dict,
    mon_number: int,
    conn: str,
    base_width: int,
    base_fps: int,
    base_quality: int,
) -> tuple[str, str, int, int, int]:
    """Choose dynamic (mode, app_label, width, fps, quality) specifically for the monitor being viewed."""
    proc, title = get_top_window_on_monitor(mon)
    combined = f"{proc} {title}"
    is_usb = (conn or "usb").lower() == "usb"

    # Active S-Pen writing or drawing/note-taking app on THIS screen -> Smoothness & High FPS
    if mouse_control.is_pen_active() or any(k in combined for k in DRAWING_KEYWORDS):
        label = "S-Pen Active" if mouse_control.is_pen_active() else (
            next((k.title() for k in DRAWING_KEYWORDS if k in combined), proc.replace(".exe", "") or "Drawing")
        )
        if is_usb:
            return ("drawing", f"S{mon_number}: {label}", min(base_width, 1280), 30, 62)
        return ("drawing", f"S{mon_number}: {label}", min(base_width, 960), 24, 58)

    # Shows / Movies / Video app on THIS screen -> Sharp High-Res Image Quality
    if any(k in combined for k in MEDIA_KEYWORDS):
        label = next((k.title() for k in MEDIA_KEYWORDS if k in combined), "Media")
        if is_usb:
            return ("media", f"S{mon_number}: {label}", max(base_width, 1920), 24, 86)
        return ("media", f"S{mon_number}: {label}", max(base_width, 1280), 22, 78)

    # Normal desktop/coding/browsing on THIS screen -> User's configured profile
    clean_name = proc.replace(".exe", "") if proc else "Desktop"
    return ("balanced", f"S{mon_number}: {clean_name}", base_width, base_fps, base_quality)


def _draw_cursor(img: Image.Image, mon: dict, scale_x: float, scale_y: float) -> None:
    """Draw a crisp Windows-style pointer at the live cursor position (hidden while S-Pen is active)."""
    if mouse_control.is_pen_active():
        return
    pt = POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return
    rel_x = pt.x - mon["left"]
    rel_y = pt.y - mon["top"]
    if rel_x < 0 or rel_y < 0 or rel_x >= mon["width"] or rel_y >= mon["height"]:
        return

    cx = int(rel_x * scale_x)
    cy = int(rel_y * scale_y)
    s = max(0.85, scale_x * 1.15)
    pts = [
        (cx, cy),
        (cx, int(cy + 18 * s)),
        (int(cx + 4.5 * s), int(cy + 13.5 * s)),
        (int(cx + 8 * s), int(cy + 20 * s)),
        (int(cx + 10.5 * s), int(cy + 18.8 * s)),
        (int(cx + 7 * s), int(cy + 12.5 * s)),
        (int(cx + 13 * s), int(cy + 12.5 * s)),
    ]
    draw = ImageDraw.Draw(img)
    draw.polygon(pts, fill=(255, 255, 255), outline=(12, 16, 24))


def _ordered_monitors(sct) -> list[dict]:
    """Return monitors with the primary display first."""
    raw = list(sct.monitors[1:])
    raw.sort(key=lambda m: (0 if m.get("is_primary") else 1))
    return raw


def list_monitors() -> list[dict]:
    with mss.MSS() as sct:
        mons = []
        for idx, m in enumerate(_ordered_monitors(sct), start=1):
            tag = "Primary" if m.get("is_primary") else (f"3rd Screen" if idx >= 3 else f"Display {idx}")
            proc, title = get_top_window_on_monitor(m)
            mons.append(
                {
                    "index": idx,
                    "width": m["width"],
                    "height": m["height"],
                    "is_primary": bool(m.get("is_primary")),
                    "is_virtual": idx >= 3,
                    "top_app": proc.replace(".exe", "") if proc else "",
                    "top_title": title[:60],
                    "label": f"{tag} ({m['width']}x{m['height']})",
                }
            )
        return mons


def _status_jpeg(line1: str, line2: str) -> bytes:
    img = Image.new("RGB", (960, 540), (11, 16, 28))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 920, 500], outline=(56, 189, 248), width=2)
    draw.text((80, 210), line1, fill=(241, 245, 249))
    draw.text((80, 255), line2, fill=(148, 163, 184))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _wrap_frame(jpg: bytes) -> bytes:
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n"
        + f"Content-Length: {len(jpg)}\r\n\r\n".encode("ascii")
        + jpg
        + b"\r\n"
    )


def _grab_monitor_image(sct, mon: dict) -> Image.Image:
    try:
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        bbox = (
            mon["left"],
            mon["top"],
            mon["left"] + mon["width"],
            mon["top"] + mon["height"],
        )
        return ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")


def mjpeg_generator(
    monitor: int = 1,
    max_width: int = 1280,
    fps: int = 24,
    quality: int = 72,
    show_cursor: bool = True,
    adaptive: bool = True,
    conn: str = "usb",
) -> Iterator[bytes]:
    base_width = max(480, min(1920, int(max_width)))
    base_fps = max(5, min(30, int(fps)))
    base_quality = max(40, min(92, int(quality)))

    cur_mode = "balanced"
    cur_app = ""
    cur_width = base_width
    cur_fps = base_fps
    cur_quality = base_quality
    last_detect = 0.0

    with mss.MSS() as sct:
        mons = _ordered_monitors(sct)
        mon_idx = (monitor - 1) if 1 <= monitor <= len(mons) else 0
        mon_num = mon_idx + 1
        mon = mons[mon_idx]

        while True:
            t0 = time.monotonic()
            if adaptive and (t0 - last_detect >= 0.6):
                cur_mode, cur_app, cur_width, cur_fps, cur_quality = _detect_profile_for_monitor(
                    mon, mon_num, conn, base_width, base_fps, base_quality
                )
                _current_adaptive_state.update(
                    {
                        "mode": cur_mode,
                        "app": cur_app,
                        "monitor": mon_num,
                        "width": cur_width,
                        "fps": cur_fps,
                        "quality": cur_quality,
                    }
                )
                last_detect = t0
            elif not adaptive and last_detect == 0.0:
                _current_adaptive_state.update(
                    {
                        "mode": "manual",
                        "app": f"S{mon_num}: Manual",
                        "monitor": mon_num,
                        "width": base_width,
                        "fps": base_fps,
                        "quality": base_quality,
                    }
                )
                last_detect = t0

            frame_interval = 1.0 / max(5, cur_fps)
            try:
                img = _grab_monitor_image(sct, mon)
                orig_w, orig_h = img.width, img.height
                if img.width > cur_width:
                    ratio = cur_width / float(img.width)
                    new_h = max(2, int(img.height * ratio) & ~1)
                    img = img.resize((cur_width, new_h), Image.Resampling.BILINEAR)

                if show_cursor:
                    _draw_cursor(img, mon, img.width / float(orig_w), img.height / float(orig_h))

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=cur_quality, optimize=False)
                yield _wrap_frame(buf.getvalue())
            except Exception:
                jpg = _status_jpeg(
                    "PC screen unavailable (locked or started outside Windows desktop)",
                    "Unlock your laptop or open TabDeck from your Start Menu.",
                )
                yield _wrap_frame(jpg)
                time.sleep(1.0)
                continue

            elapsed = time.monotonic() - t0
            sleep_for = frame_interval - elapsed
            if sleep_for > 0.002:
                time.sleep(sleep_for)
