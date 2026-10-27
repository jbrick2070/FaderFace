"""Submit the API form of the LivePortrait workflow with synthetic MIDI state
and wait for ComfyUI to finish it. Proves the graph validates and executes
without the controller or the browser.

Run:  python scripts/validate_liveportrait_api.py [--port 8000] [--cc 64]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
API_PATH = os.path.normpath(os.path.join(HERE, "..", "workflows", "liveportrait_apc40_api.json"))


def synthetic_midi(cc_value: int) -> str:
    """What the browser-side loader writes into raw_data: every CC at one value."""
    return json.dumps({"cc": [{"number": n, "value": cc_value} for n in range(128)], "notes": []})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cc", type=int, default=64, help="synthetic value for every CC (0..127)")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait (first run downloads models)")
    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"

    with open(API_PATH, "r", encoding="utf-8") as handle:
        prompt = json.load(handle)
    loader = next(v for v in prompt.values() if v["class_type"] == "VrchMidiDeviceLoaderNode")
    loader["inputs"]["raw_data"] = synthetic_midi(args.cc)

    response = requests.post(f"{base}/prompt", json={"prompt": prompt, "client_id": "apc40-validate"}, timeout=30)
    if response.status_code != 200:
        print("REFUSED", response.status_code, response.text[:1500])
        return 1
    prompt_id = response.json()["prompt_id"]
    print("queued", prompt_id)

    started = time.time()
    while time.time() - started < args.timeout:
        history = requests.get(f"{base}/history/{prompt_id}", timeout=30).json().get(prompt_id)
        if history:
            status = history.get("status", {})
            print("status:", status.get("status_str"), "completed:", status.get("completed"))
            for node_id, out in history.get("outputs", {}).items():
                for image in out.get("images", []):
                    print(f"  node {node_id} ({prompt[node_id]['_meta']['title']}): {image['type']}/{image.get('subfolder', '')}/{image['filename']}")
            if status.get("status_str") == "error":
                for message in status.get("messages", []):
                    if message[0] == "execution_error":
                        print("  error:", message[1].get("exception_message", "")[:800])
                        print("  node:", message[1].get("node_type"))
                return 1
            return 0
        time.sleep(3)
    print("TIMEOUT after", args.timeout, "s")
    return 2


if __name__ == "__main__":
    sys.exit(main())
