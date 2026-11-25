import queue
import threading
import time
from typing import Iterator

import pyaudiowpatch as pyaudio

# Streams raw 16-bit little-endian stereo PCM from Windows WASAPI loopback
# to connected TabDeck clients with low latency.

_clients_lock = threading.Lock()
_clients: list[queue.Queue[bytes]] = []
_capture_thread: threading.Thread | None = None
_stop_event = threading.Event()
_stream_info = {"rate": 48000, "channels": 2, "device": "", "active": False, "error": ""}


def get_stream_info() -> dict:
    with _clients_lock:
        client_count = len(_clients)
    return {**_stream_info, "clients": client_count}


def _find_loopback_device(p: pyaudio.PyAudio):
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_out = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    if default_out.get("isLoopbackDevice"):
        return default_out
    for lb in p.get_loopback_device_info_generator():
        if default_out["name"] in lb["name"]:
            return lb
    # Fallback: first available loopback device
    for lb in p.get_loopback_device_info_generator():
        return lb
    raise RuntimeError("No WASAPI loopback audio device found")


def _capture_loop():
    p = pyaudio.PyAudio()
    stream = None
    try:
        dev = _find_loopback_device(p)
        rate = int(dev["defaultSampleRate"])
        channels = min(2, max(1, int(dev["maxInputChannels"])))
        frames_per_buf = max(256, int(rate * 0.02))  # ~20ms chunks

        _stream_info.update(
            {"rate": rate, "channels": channels, "device": dev["name"], "active": True, "error": ""}
        )

        def callback(in_data, frame_count, time_info, status):
            with _clients_lock:
                for q in list(_clients):
                    if q.full():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        q.put_nowait(in_data)
                    except queue.Full:
                        pass
            return (None, pyaudio.paContinue)

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=frames_per_buf,
            stream_callback=callback,
        )
        stream.start_stream()

        while not _stop_event.is_set():
            with _clients_lock:
                if not _clients:
                    break
            time.sleep(0.25)
    except Exception as exc:
        _stream_info["error"] = str(exc)
    finally:
        _stream_info["active"] = False
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        try:
            p.terminate()
        except Exception:
            pass


def _ensure_capture_started():
    global _capture_thread
    if _capture_thread is not None and _capture_thread.is_alive():
        return
    _stop_event.clear()
    _capture_thread = threading.Thread(target=_capture_loop, name="tabdeck-audio-stream", daemon=True)
    _capture_thread.start()
    # Wait briefly for device metadata (sample rate / channels) to populate
    deadline = time.monotonic() + 1.5
    while not _stream_info["active"] and not _stream_info["error"] and time.monotonic() < deadline:
        time.sleep(0.03)


def pcm_generator() -> tuple[int, int, Iterator[bytes]]:
    q: queue.Queue[bytes] = queue.Queue(maxsize=12)
    with _clients_lock:
        _clients.append(q)
    _ensure_capture_started()
    rate = _stream_info["rate"]
    channels = _stream_info["channels"]

    def _gen() -> Iterator[bytes]:
        try:
            while True:
                try:
                    chunk = q.get(timeout=2.0)
                    yield chunk
                except queue.Empty:
                    if not _stream_info["active"]:
                        break
                    # Yield tiny silence chunk to keep HTTP stream alive when PC is quiet
                    yield b"\x00" * (int(rate * 0.02) * channels * 2)
        finally:
            with _clients_lock:
                if q in _clients:
                    _clients.remove(q)

    return rate, channels, _gen()
