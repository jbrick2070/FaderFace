"""Thin client for a running ComfyUI: queue a prompt, interrupt, upload a
source image, and stream execution events from the WebSocket.

Only the standard library plus ``requests`` and ``websocket-client`` are
used, so this runs from any Python that can see the server.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Callable, Optional

import requests


class ComfyClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8188, client_id: Optional[str] = None):
        self.host = host
        self.port = port
        self.client_id = client_id or uuid.uuid4().hex
        self.base = f"http://{host}:{port}"
        self._ws_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ HTTP
    def queue(self, prompt: dict) -> str:
        """POST an API-format workflow. Returns the prompt_id."""
        response = requests.post(
            f"{self.base}/prompt",
            json={"prompt": prompt, "client_id": self.client_id},
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"ComfyUI refused the prompt: {response.status_code} {response.text[:600]}")
        return response.json()["prompt_id"]

    def interrupt(self) -> None:
        requests.post(f"{self.base}/interrupt", timeout=10)

    def upload_image(self, path: str) -> str:
        """Copy a local image into ComfyUI's input folder. Returns the name a
        LoadImage node should be given."""
        name = os.path.basename(path)
        with open(path, "rb") as handle:
            response = requests.post(
                f"{self.base}/upload/image",
                files={"image": (name, handle, "application/octet-stream")},
                data={"overwrite": "true"},
                timeout=60,
            )
        response.raise_for_status()
        body = response.json()
        subfolder = body.get("subfolder") or ""
        return f"{subfolder}/{body['name']}" if subfolder else body["name"]

    def history(self, prompt_id: str) -> dict:
        response = requests.get(f"{self.base}/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        return response.json().get(prompt_id, {})

    def alive(self) -> bool:
        try:
            return requests.get(f"{self.base}/system_stats", timeout=5).status_code == 200
        except requests.RequestException:
            return False

    # ------------------------------------------------------------- WebSocket
    def listen(self, on_event: Callable[[dict], None]) -> None:
        """Start a background thread that forwards every JSON message from
        /ws to ``on_event``. Binary preview frames are ignored."""
        import websocket  # websocket-client

        url = f"ws://{self.host}:{self.port}/ws?clientId={self.client_id}"

        def run():
            while not self._stop.is_set():
                try:
                    socket = websocket.create_connection(url, timeout=5)
                except Exception:
                    self._stop.wait(2.0)
                    continue
                try:
                    while not self._stop.is_set():
                        try:
                            frame = socket.recv()
                        except websocket.WebSocketTimeoutException:
                            continue
                        if isinstance(frame, bytes):
                            continue
                        try:
                            on_event(json.loads(frame))
                        except json.JSONDecodeError:
                            continue
                except Exception:
                    pass
                finally:
                    try:
                        socket.close()
                    except Exception:
                        pass

        self._ws_thread = threading.Thread(target=run, name="comfy-ws", daemon=True)
        self._ws_thread.start()

    def close(self) -> None:
        self._stop.set()


def output_image_name(executed_event: dict) -> Optional[str]:
    """From an ``executed`` event, return the first saved image as the
    annotated name a LoadImage node accepts (``sub/file.png [output]``)."""
    images = (executed_event.get("data") or {}).get("output", {}).get("images") or []
    for image in images:
        if image.get("type") != "output":
            continue
        subfolder = image.get("subfolder") or ""
        name = f"{subfolder}/{image['filename']}" if subfolder else image["filename"]
        return f"{name} [output]"
    return None
