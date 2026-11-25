import ctypes
import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    APP_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    BASE_DIR = APP_DIR.parent
os.chdir(BASE_DIR)
for p in (str(APP_DIR), str(BASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

LOG_PATH = BASE_DIR / "tabdeck.log"
PID_PATH = BASE_DIR / "tabdeck.pid"
ICON_PATH = BASE_DIR / "tabdeck.ico"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
STARTUP_SHORTCUT = STARTUP_DIR / "TabDeck.lnk"

# Redirect stdout/stderr cleanly when running windowless under pythonw.exe
if sys.stdout is None or sys.stderr is None:
    _log_f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log_f
    if sys.stderr is None:
        sys.stderr = _log_f

from PIL import Image, ImageDraw
import pystray
import uvicorn

import discovery_and_adb
import multi_control
import server

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def log_msg(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def build_icon_image(size: int = 128) -> Image.Image:
    """Generate the signature 4-tile TabDeck app icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(4, size // 5)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(11, 17, 32, 255))

    pad = int(size * 0.16)
    gap = int(size * 0.08)
    mid_x = size // 2
    mid_y = size // 2
    tr = max(3, size // 12)

    # Top-left cyan, top-right indigo, bottom-left emerald, bottom-right amber
    d.rounded_rectangle([pad, pad, mid_x - gap // 2, mid_y - gap // 2], radius=tr, fill=(56, 189, 248, 255))
    d.rounded_rectangle([mid_x + gap // 2, pad, size - pad, mid_y - gap // 2], radius=tr, fill=(129, 140, 248, 255))
    d.rounded_rectangle([pad, mid_y + gap // 2, mid_x - gap // 2, size - pad], radius=tr, fill=(52, 211, 153, 255))
    d.rounded_rectangle([mid_x + gap // 2, mid_y + gap // 2, size - pad, size - pad], radius=tr, fill=(245, 158, 11, 255))
    return img


def ensure_ico_file() -> None:
    if not ICON_PATH.exists():
        img = build_icon_image(256)
        img.save(ICON_PATH, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def stop_previous_instances() -> None:
    my_pid = os.getpid()
    # Stop PID recorded in tabdeck.pid
    if PID_PATH.exists():
        try:
            old_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            if old_pid != my_pid:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(old_pid)],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=3,
                )
        except Exception:
            pass

    # Also stop anything currently listening on port 8765
    try:
        ps = (
            "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.OwningProcess -ne {my_pid} }} | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
        time.sleep(0.4)
    except Exception:
        pass

    try:
        PID_PATH.write_text(str(my_pid), encoding="utf-8")
    except Exception:
        pass


def open_on_tablet() -> None:
    adb = Path(os.environ.get("LOCALAPPDATA", "")) / r"Android\Sdk\platform-tools\adb.exe"
    if not adb.exists():
        return
    try:
        subprocess.run([str(adb), "reverse", "tcp:8765", "tcp:8765"], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=3)
        subprocess.run([str(adb), "shell", "am", "start", "-n", "com.tabdeck.app/.MainActivity"], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=3)
    except Exception:
        pass


def is_wifi_firewall_ready() -> bool:
    try:
        ps = (
            "$r1 = Get-NetFirewallRule -DisplayName 'TabDeck Dashboard (TCP 8765)' -ErrorAction SilentlyContinue; "
            "$r2 = Get-NetFirewallRule -DisplayName 'TabDeck Discovery (UDP 8766)' -ErrorAction SilentlyContinue; "
            "if ($r1 -and $r2 -and ($r1.Profile -match 'Any|Public')) { 'OK' } else { 'NEED' }"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
        return "OK" in r.stdout
    except Exception:
        return False


def enable_wifi_firewall_elevated() -> None:
    cmd = (
        'netsh advfirewall firewall delete rule name="TabDeck Dashboard (TCP 8765)" & '
        'netsh advfirewall firewall delete rule name="TabDeck Discovery (UDP 8766)" & '
        'netsh advfirewall firewall add rule name="TabDeck Dashboard (TCP 8765)" dir=in action=allow protocol=TCP localport=8765 profile=any & '
        'netsh advfirewall firewall add rule name="TabDeck Discovery (UDP 8766)" dir=in action=allow protocol=UDP localport=8766 profile=any'
    )
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {cmd}", None, 0)


def is_autostart_enabled() -> bool:
    return STARTUP_SHORTCUT.exists()


def set_autostart(enable: bool) -> None:
    if not enable:
        try:
            if STARTUP_SHORTCUT.exists():
                STARTUP_SHORTCUT.unlink()
        except Exception:
            pass
        return

    ensure_ico_file()
    exe_path = BASE_DIR / "TabDeck.exe"
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{STARTUP_SHORTCUT}'); "
        f"$s.TargetPath = '{exe_path}'; "
        f"$s.WorkingDirectory = '{BASE_DIR}'; "
        f"$s.IconLocation = '{exe_path},0'; "
        "$s.Description = 'TabDeck — Stream Deck, Touchscreen, S-Pen & Multi Control'; "
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        timeout=6,
    )


class TabDeckApp:
    def __init__(self) -> None:
        self.uvicorn_server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.tray: pystray.Icon | None = None
        self.stopping = False

    def start_server_thread(self) -> None:
        discovery_and_adb.start_background_services()
        multi_control.manager.start()

        def _run():
            while not self.stopping:
                try:
                    config = uvicorn.Config(
                        server.app,
                        host="0.0.0.0",
                        port=8765,
                        log_config=None,
                    )
                    self.uvicorn_server = uvicorn.Server(config)
                    self.uvicorn_server.install_signal_handlers = lambda: None
                    self.uvicorn_server.run()
                    break
                except Exception:
                    log_msg("Server error:\n" + traceback.format_exc())
                    if self.stopping:
                        break
                    time.sleep(2.0)

        self.server_thread = threading.Thread(target=_run, name="tabdeck-http", daemon=True)
        self.server_thread.start()

    def stop_server(self) -> None:
        self.stopping = True
        multi_control.manager.stop()
        if self.uvicorn_server is not None:
            self.uvicorn_server.should_exit = True

    def on_open_tablet(self, icon, item) -> None:
        threading.Thread(target=open_on_tablet, daemon=True).start()

    def on_enable_firewall(self, icon, item) -> None:
        enable_wifi_firewall_elevated()

    def on_toggle_autostart(self, icon, item) -> None:
        set_autostart(not is_autostart_enabled())
        if self.tray:
            self.tray.update_menu()

    def on_open_browser(self, icon, item) -> None:
        webbrowser.open("http://127.0.0.1:8765")

    def on_restart(self, icon, item) -> None:
        self.stop_server()
        exe_path = str(BASE_DIR / "TabDeck.exe")
        subprocess.Popen([exe_path], cwd=str(BASE_DIR), creationflags=CREATE_NO_WINDOW)
        if self.tray:
            self.tray.stop()

    def on_quit(self, icon, item) -> None:
        self.stop_server()
        try:
            if PID_PATH.exists():
                PID_PATH.unlink()
        except Exception:
            pass
        if self.tray:
            self.tray.stop()

    def run(self) -> None:
        stop_previous_instances()
        ensure_ico_file()
        self.start_server_thread()
        threading.Thread(target=open_on_tablet, daemon=True).start()

        ip = discovery_and_adb.get_lan_ip()
        fw_ok = is_wifi_firewall_ready()

        mc_menu = pystray.Menu(
            pystray.MenuItem(
                "Arrange Devices (Drag & Drop Layout)...",
                lambda i, it: webbrowser.open("http://127.0.0.1:8765/?layout=1"),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Switch Mouse & KB to Device Now (Ctrl+Alt+M)",
                lambda i, it: multi_control.manager.toggle_device(),
                checked=lambda item: multi_control.manager.active_device_id is not None,
            ),
            pystray.MenuItem(
                "Enable Multi Control",
                lambda i, it: multi_control.manager.update_layout(enabled=not multi_control.manager.enabled),
                checked=lambda item: multi_control.manager.enabled,
            ),
        )

        menu = pystray.Menu(
            pystray.MenuItem(f"TabDeck Running · {ip}:8765", lambda i, it: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open on Tablet (USB)", self.on_open_tablet, default=True),
            pystray.MenuItem("Open in PC Browser", self.on_open_browser),
            pystray.MenuItem("Multi Control (Laptop → Tablet)", mc_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Wi-Fi Firewall Allowed" if fw_ok else "Enable Wi-Fi Access (Allow Firewall)",
                self.on_enable_firewall,
            ),
            pystray.MenuItem(
                "Start with Windows",
                self.on_toggle_autostart,
                checked=lambda item: is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart Server", self.on_restart),
            pystray.MenuItem("Quit TabDeck", self.on_quit),
        )

        self.tray = pystray.Icon(
            "TabDeck",
            build_icon_image(64),
            f"TabDeck ({ip}:8765)",
            menu,
        )
        log_msg(f"TabDeck unified app started (PID {os.getpid()}, IP {ip})")
        self.tray.run()


if __name__ == "__main__":
    TabDeckApp().run()
