"""
Zero-CLI ADB helper for deploying TabDeck Multi Control to UNROOTED Android phones
(e.g. Samsung Galaxy S24) via Wireless Debugging or USB Quick-Deploy.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def find_adb() -> str | None:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / r"Android\Sdk\platform-tools\adb.exe",
        Path(__file__).resolve().parent.parent / "platform-tools" / "adb.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return "adb"


def find_mc_binary() -> Path | None:
    roots = [
        Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent,
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)),
    ]
    for root in roots:
        p = root / "android-mc" / "tabdeck_mc"
        if p.exists():
            return p
    return None


def _run_adb(args: list[str], timeout: int = 12) -> tuple[bool, str]:
    adb = find_adb()
    if not adb:
        return False, "ADB not found"
    try:
        r = subprocess.run(
            [adb] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        return r.returncode == 0, out
    except Exception as exc:
        return False, str(exc)


def list_adb_devices() -> list[dict[str, str]]:
    ok, out = _run_adb(["devices", "-l"], timeout=5)
    if not ok:
        return []
    devices: list[dict[str, str]] = []
    for ln in out.splitlines()[1:]:
        ln = ln.strip()
        if not ln or "\t" not in ln and " device " not in ln:
            continue
        parts = ln.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        model = serial
        for tok in parts[2:]:
            if tok.startswith("model:"):
                model = tok.split(":", 1)[1].replace("_", " ")
        devices.append({"serial": serial, "model": model})
    return devices


def _detect_device_wifi_ip(serial: str) -> str:
    ok, out = _run_adb(["-s", serial, "shell", "ip route get 1.1.1.1 2>/dev/null || ip addr show wlan0"], timeout=5)
    if not ok:
        return ""
    m = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", out)
    if m:
        return m.group(1)
    m2 = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", out)
    return m2.group(1) if m2 else ""


def _detect_device_screen_size(serial: str) -> tuple[int, int]:
    ok, out = _run_adb(["-s", serial, "shell", "wm size"], timeout=5)
    if ok:
        m = re.search(r"(\d+)x(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1080, 2340


def deploy_nonroot_uhid(serial: str) -> dict[str, Any]:
    """Push tabdeck_mc and start it in non-root /dev/uhid mode on an unrooted Android phone/tablet."""
    mc_bin = find_mc_binary()
    if not mc_bin:
        return {"ok": False, "error": "android-mc/tabdeck_mc binary not found"}

    ok, out = _run_adb(["-s", serial, "push", str(mc_bin), "/data/local/tmp/tabdeck_mc"], timeout=15)
    if not ok:
        return {"ok": False, "error": f"Push failed: {out}"}

    start_cmd = (
        "for p in $(pidof tabdeck_mc 2>/dev/null); do kill $p 2>/dev/null; done; "
        "sleep 0.3; "
        "chmod 755 /data/local/tmp/tabdeck_mc && "
        "/data/local/tmp/tabdeck_mc --uhid --daemon"
    )
    ok, out = _run_adb(["-s", serial, "shell", start_cmd], timeout=10)
    if not ok:
        return {"ok": False, "error": f"Start failed: {out}"}

    wifi_ip = _detect_device_wifi_ip(serial)
    w, h = _detect_device_screen_size(serial)
    ok_m, model_out = _run_adb(["-s", serial, "shell", "getprop ro.product.model"], timeout=5)
    model = model_out.strip() if ok_m and model_out.strip() else "Android Phone"

    return {
        "ok": True,
        "serial": serial,
        "model": model,
        "wifi_ip": wifi_ip,
        "screen_w": w,
        "screen_h": h,
        "message": f"Non-root Multi Control (UHID) running on {model} ({wifi_ip or serial})",
    }


def pair_and_deploy_wireless(
    connect_addr: str,
    pair_addr: str = "",
    pair_code: str = "",
) -> dict[str, Any]:
    """
    Pair (optional, first time only) and connect via Android Wireless Debugging,
    then deploy & start non-root UHID Multi Control over Wi-Fi.
    """
    connect_addr = (connect_addr or "").strip()
    pair_addr = (pair_addr or "").strip()
    pair_code = (pair_code or "").strip()

    if pair_addr and pair_code:
        ok, out = _run_adb(["pair", pair_addr, pair_code], timeout=15)
        if not ok or "failed" in out.lower():
            return {"ok": False, "error": f"Wireless pairing failed: {out}"}

    if not connect_addr:
        return {"ok": False, "error": "Enter your phone's Wireless Debugging IP:Port"}

    ok, out = _run_adb(["connect", connect_addr], timeout=12)
    if not ok or ("connected to" not in out.lower() and "already connected" not in out.lower()):
        return {"ok": False, "error": f"Wireless ADB connect failed: {out}"}

    return deploy_nonroot_uhid(connect_addr)
