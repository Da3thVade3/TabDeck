import os
import socket
import subprocess
import threading
import time

PORT = 8765
DISCOVERY_PORT = 8766
_started = False


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _adb_watcher_loop():
    """Automatically run `adb reverse tcp:8765 tcp:8765` whenever a tablet is plugged in."""
    adb = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Android",
        "Sdk",
        "platform-tools",
        "adb.exe",
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    last_devices = ""

    while True:
        try:
            if os.path.exists(adb):
                r = subprocess.run(
                    [adb, "devices"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=creationflags,
                )
                lines = [
                    ln.strip()
                    for ln in r.stdout.splitlines()[1:]
                    if ln.strip() and "\tdevice" in ln
                ]
                sig = ",".join(sorted(lines))
                if sig and sig != last_devices:
                    subprocess.run(
                        [adb, "reverse", f"tcp:{PORT}", f"tcp:{PORT}"],
                        capture_output=True,
                        timeout=3,
                        creationflags=creationflags,
                    )
                    subprocess.run(
                        [adb, "forward", "tcp:8767", "tcp:8767"],
                        capture_output=True,
                        timeout=3,
                        creationflags=creationflags,
                    )
                last_devices = sig
        except Exception:
            pass
        time.sleep(3.0)


def _udp_discovery_responder_loop():
    """Respond to UDP discovery probes from TabDeck Android clients on port 8766."""
    hostname = socket.gethostname()
    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", DISCOVERY_PORT))
            sock.settimeout(2.0)

            while True:
                try:
                    data, addr = sock.recvfrom(512)
                    if b"TABDECK_DISCOVER" in data:
                        ip = get_lan_ip()
                        reply = f"TABDECK:{PORT}:{ip}:{hostname}".encode("utf-8")
                        sock.sendto(reply, addr)
                except socket.timeout:
                    # Also emit periodic broadcast beacon so tablet finds PC even passively
                    try:
                        ip = get_lan_ip()
                        if ip and not ip.startswith("127."):
                            beacon = f"TABDECK:{PORT}:{ip}:{hostname}".encode("utf-8")
                            sock.sendto(beacon, ("255.255.255.255", DISCOVERY_PORT))
                    except Exception:
                        pass
        except Exception:
            time.sleep(3.0)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass


def start_background_services():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_adb_watcher_loop, name="tabdeck-adb-watch", daemon=True).start()
    threading.Thread(target=_udp_discovery_responder_loop, name="tabdeck-udp-disc", daemon=True).start()
