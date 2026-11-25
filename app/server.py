import json
import socket
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import adb_deploy
import audio_stream
import mouse_control
import multi_control
import pc_control
import video_stream

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
STATIC_DIR = BASE_DIR / "static"

DEFAULT_CONFIG: dict[str, Any] = {
    "macros": [
        {"id": "mic_mute", "label": "Mic Mute", "icon": "mic", "color": "#ef4444", "type": "action", "value": "mic_mute"},
        {"id": "screenshot", "label": "Snip Tool", "icon": "scissors", "color": "#38bdf8", "type": "hotkey", "value": "win+shift+s"},
        {"id": "desktop", "label": "Desktop", "icon": "monitor", "color": "#818cf8", "type": "hotkey", "value": "win+d"},
        {"id": "taskmgr", "label": "Task Mgr", "icon": "activity", "color": "#f59e0b", "type": "hotkey", "value": "ctrl+shift+esc"},
        {"id": "alttab", "label": "Switch App", "icon": "layers", "color": "#a78bfa", "type": "hotkey", "value": "alt+tab"},
        {"id": "newtab", "label": "New Tab", "icon": "plus", "color": "#34d399", "type": "hotkey", "value": "ctrl+t"},
        {"id": "ytmusic", "label": "YT Music", "icon": "music", "color": "#f43f5e", "type": "url", "value": "https://music.youtube.com"},
        {"id": "youtube", "label": "YouTube", "icon": "play", "color": "#fb7185", "type": "url", "value": "https://www.youtube.com"},
        {"id": "calc", "label": "Calculator", "icon": "hash", "color": "#2dd4bf", "type": "app", "value": "calc.exe"},
        {"id": "notepad", "label": "Notepad", "icon": "file", "color": "#60a5fa", "type": "app", "value": "notepad.exe"},
        {"id": "display_off", "label": "Screen Off", "icon": "moon", "color": "#94a3b8", "type": "action", "value": "display_off"},
        {"id": "lock", "label": "Lock PC", "icon": "lock", "color": "#f97316", "type": "action", "value": "lock"},
    ],
}

SCENES: dict[str, dict[str, dict[str, Any]]] = {
    "study": {
        "ledvance_bulb": {"power": True, "brightness": 100, "temp": 85},
        "battletron_strip": {"power": True, "brightness": 75, "color": "#38bdf8"},
    },
    "cozy": {
        "ledvance_bulb": {"power": True, "brightness": 55, "temp": 15},
        "battletron_strip": {"power": True, "brightness": 50, "color": "#ff7b29"},
    },
    "gaming": {
        "ledvance_bulb": {"power": True, "brightness": 35, "color": "#7c3aed"},
        "battletron_strip": {"power": True, "brightness": 95, "color": "#00f0ff"},
    },
    "movie": {
        "ledvance_bulb": {"power": False},
        "battletron_strip": {"power": True, "brightness": 22, "color": "#4f46e5"},
    },
    "all_off": {
        "ledvance_bulb": {"power": False},
        "battletron_strip": {"power": False},
    },
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict[str, Any]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


app = FastAPI(title="TabDeck Dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.json")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/api/state")
async def api_state(request: Request):
    if request.client and request.client.host:
        multi_control.manager.note_tablet_ip(request.client.host)
    cfg = load_config()
    media = await pc_control.get_media_state_async()
    audio = pc_control.get_audio_state()
    stats = pc_control.get_system_stats()
    return {
        "media": media,
        "audio": audio,
        "stats": stats,
        "macros": cfg.get("macros", []),
        "host_ip": get_local_ip(),
        "video_mode": video_stream.get_adaptive_state(),
        "multi_control": multi_control.manager.get_status(),
    }


class MultiControlLayoutBody(BaseModel):
    enabled: bool | None = None
    devices: list[dict[str, Any]] | None = None


class MultiControlDeviceAddBody(BaseModel):
    name: str
    kind: str = "phone"
    ip: str = ""
    orientation: str = "portrait"


class MultiControlToggleBody(BaseModel):
    device_id: str | None = None


@app.get("/api/multicontrol/status")
def api_mc_status():
    return multi_control.manager.get_status()


@app.get("/api/multicontrol/layout")
def api_mc_layout():
    return multi_control.manager.get_layout()


@app.post("/api/multicontrol/layout")
def api_mc_update_layout(body: MultiControlLayoutBody):
    return multi_control.manager.update_layout(enabled=body.enabled, devices=body.devices)


@app.post("/api/multicontrol/devices")
def api_mc_add_device(body: MultiControlDeviceAddBody):
    return multi_control.manager.add_device(
        name=body.name,
        kind=body.kind,
        ip=body.ip,
        orientation=body.orientation,
    )


@app.delete("/api/multicontrol/devices/{device_id}")
def api_mc_delete_device(device_id: str):
    return multi_control.manager.delete_device(device_id)


@app.post("/api/multicontrol/toggle")
def api_mc_toggle(body: MultiControlToggleBody | None = None):
    return multi_control.manager.toggle_device(body.device_id if body else None)


class MediaAction(BaseModel):
    action: str


@app.post("/api/media")
async def api_media(body: MediaAction):
    media = await pc_control.control_media_async(body.action)
    return {"ok": True, "media": media}


class VolumeBody(BaseModel):
    volume: int


@app.post("/api/audio/master")
def api_master_volume(body: VolumeBody):
    return {"ok": True, "audio": pc_control.set_master_volume(body.volume)}


@app.post("/api/audio/mute")
def api_master_mute():
    return {"ok": True, "audio": pc_control.toggle_master_mute()}


@app.post("/api/audio/mic-mute")
def api_mic_mute():
    return {"ok": True, "audio": pc_control.toggle_mic_mute()}


@app.get("/api/audio/stream")
def api_audio_stream():
    rate, channels, gen = audio_stream.pcm_generator()
    return StreamingResponse(
        gen,
        media_type="application/octet-stream",
        headers={
            "X-Sample-Rate": str(rate),
            "X-Channels": str(channels),
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/audio/stream-info")
def api_audio_stream_info():
    return audio_stream.get_stream_info()


@app.get("/api/video/monitors")
def api_video_monitors():
    return {"monitors": video_stream.list_monitors()}


@app.get("/api/pen/status")
def api_pen_status():
    return mouse_control.get_pen_status()


@app.get("/api/video/stream")
def api_video_stream(
    monitor: int = 1,
    width: int = 1280,
    fps: int = 24,
    quality: int = 72,
    cursor: int = 1,
    adaptive: int = 1,
    conn: str = "usb",
):
    return StreamingResponse(
        video_stream.mjpeg_generator(
            monitor=monitor,
            max_width=width,
            fps=fps,
            quality=quality,
            show_cursor=bool(cursor),
            adaptive=bool(adaptive),
            conn=conn,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.websocket("/ws/input")
async def ws_input(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            ev = await websocket.receive_json()
            mouse_control.handle_input_event(ev)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


class AppVolumeBody(BaseModel):
    name: str
    volume: int | None = None
    toggle_mute: bool = False


@app.post("/api/audio/app")
def api_app_audio(body: AppVolumeBody):
    if body.toggle_mute:
        audio = pc_control.toggle_app_mute(body.name)
    elif body.volume is not None:
        audio = pc_control.set_app_volume(body.name, body.volume)
    else:
        audio = pc_control.get_audio_state()
    return {"ok": True, "audio": audio}


@app.post("/api/macros/{macro_id}/run")
def api_run_macro(macro_id: str):
    cfg = load_config()
    macro = next((m for m in cfg.get("macros", []) if m["id"] == macro_id), None)
    if not macro:
        raise HTTPException(status_code=404, detail="Macro not found")
    return pc_control.execute_macro(macro)


class MacroItem(BaseModel):
    id: str | None = None
    label: str
    icon: str = "zap"
    color: str = "#38bdf8"
    type: str = "hotkey"
    value: str


@app.post("/api/macros")
def api_save_macro(item: MacroItem):
    cfg = load_config()
    macros = cfg.setdefault("macros", [])
    mid = item.id or f"custom_{len(macros) + 1}_{abs(hash(item.label)) % 10000}"
    data = item.model_dump()
    data["id"] = mid
    idx = next((i for i, m in enumerate(macros) if m["id"] == mid), None)
    if idx is not None:
        macros[idx] = data
    else:
        macros.append(data)
    save_config(cfg)
    return {"ok": True, "macros": macros}


@app.delete("/api/macros/{macro_id}")
def api_delete_macro(macro_id: str):
    cfg = load_config()
    cfg["macros"] = [m for m in cfg.get("macros", []) if m["id"] != macro_id]
    save_config(cfg)
    return {"ok": True, "macros": cfg["macros"]}


class WirelessSetupBody(BaseModel):
    connect_addr: str
    pair_addr: str = ""
    pair_code: str = ""
    name: str = ""
    kind: str = "phone"
    orientation: str = "portrait"


class UsbSetupBody(BaseModel):
    serial: str
    name: str = ""
    kind: str = "phone"
    orientation: str = "portrait"


def _upsert_deployed_device(res: dict[str, Any], name: str, kind: str, orientation: str) -> dict[str, Any]:
    wifi_ip = res.get("wifi_ip") or ""
    label = (name or res.get("model") or "Android Phone").strip()
    layout = multi_control.manager.get_layout()
    devs = list(layout["devices"])
    existing = next((d for d in devs if (wifi_ip and d.get("ip") == wifi_ip) or d.get("name") == label), None)
    if existing:
        if wifi_ip:
            existing["ip"] = wifi_ip
        existing["enabled"] = True
        if res.get("screen_w") and res.get("screen_h"):
            sw, sh = int(res["screen_w"]), int(res["screen_h"])
            existing["screen_w"], existing["screen_h"] = (min(sw, sh), max(sw, sh)) if existing.get("orientation") == "portrait" else (max(sw, sh), min(sw, sh))
        return multi_control.manager.update_layout(devices=devs)
    return multi_control.manager.add_device(name=label, kind=kind, ip=wifi_ip, orientation=orientation)


@app.get("/api/multicontrol/adb-devices")
def api_mc_adb_devices():
    return {"devices": adb_deploy.list_adb_devices()}


@app.post("/api/multicontrol/setup-wireless")
def api_mc_setup_wireless(body: WirelessSetupBody):
    res = adb_deploy.pair_and_deploy_wireless(
        connect_addr=body.connect_addr,
        pair_addr=body.pair_addr,
        pair_code=body.pair_code,
    )
    if not res.get("ok"):
        return res
    layout = _upsert_deployed_device(res, body.name, body.kind, body.orientation)
    return {"ok": True, "message": res.get("message", "Connected!"), "device": res, "layout": layout}


@app.post("/api/multicontrol/setup-usb")
def api_mc_setup_usb(body: UsbSetupBody):
    res = adb_deploy.deploy_nonroot_uhid(body.serial)
    if not res.get("ok"):
        return res
    layout = _upsert_deployed_device(res, body.name, body.kind, body.orientation)
    return {"ok": True, "message": res.get("message", "Deployed!"), "device": res, "layout": layout}
