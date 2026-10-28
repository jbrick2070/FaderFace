"""Turn a ComfyUI canvas workflow (litegraph JSON) into the API form the
/prompt endpoint takes, using the running server's /object_info for widget
order. Resolves KJNodes Set/Get virtual nodes and skips notes and other
frontend-only nodes.

Usage (as a library):
    prompt = ui_to_api(ui_json, object_info, overrides={"107": {"image": "x.png"}})
Usage (CLI):
    python scripts/ui_to_api.py workflows/foo.json --port 8000 [--set NODE.input=value ...]
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

FRONTEND_ONLY = {"Note", "MarkdownNote", "PrimitiveNode", "Reroute", "SetNode", "GetNode"}


def _widget_names(class_type, object_info):
    info = object_info[class_type]["input"]
    names = []
    for section in ("required", "optional"):
        for name, spec in info.get(section, {}).items():
            kind = spec[0]
            cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if isinstance(kind, list) or kind in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"):
                if not cfg.get("forceInput"):
                    names.append(name)
    return names


def _resolve_sources(ui):
    """Map (node_id, slot) through Set/Get and Reroute nodes to the real source."""
    nodes = {n["id"]: n for n in ui["nodes"]}
    links = {l[0]: l for l in ui["links"]}
    set_by_name = {}
    for n in ui["nodes"]:
        if n["type"] == "SetNode":
            link = n["inputs"][0].get("link")
            if link is not None:
                set_by_name[n["widgets_values"][0]] = (links[link][1], links[link][2])

    def real(node_id, slot):
        node = nodes[node_id]
        if node["type"] == "GetNode":
            return real(*set_by_name[node["widgets_values"][0]])
        if node["type"] == "Reroute":
            link = node["inputs"][0].get("link")
            return real(links[link][1], links[link][2])
        return node_id, slot

    return nodes, links, real


def ui_to_api(ui, object_info, overrides=None):
    nodes, links, real = _resolve_sources(ui)
    prompt = {}
    for node in ui["nodes"]:
        if node["type"] in FRONTEND_ONLY or node.get("mode") in (2, 4):
            continue
        if node["type"] not in object_info:
            raise KeyError(f"node {node['id']} type {node['type']} is not on the server")
        inputs = {}
        widgets = node.get("widgets_values") or []
        names = _widget_names(node["type"], object_info)
        if isinstance(widgets, dict):
            for name in names:
                if name in widgets:
                    inputs[name] = widgets[name]
        else:
            # Positional. Seed-type widgets carry a hidden "control_after_generate" value.
            values = list(widgets)
            for name in names:
                if not values:
                    break
                inputs[name] = values.pop(0)
                if name in ("seed", "noise_seed") and values and values[0] in ("fixed", "increment", "decrement", "randomize"):
                    values.pop(0)
        for inp in node.get("inputs", []):
            link = inp.get("link")
            if link is None:
                continue
            src_id, src_slot = real(links[link][1], links[link][2])
            inputs[inp["name"]] = [str(src_id), src_slot]
        for name, value in (overrides or {}).get(str(node["id"]), {}).items():
            inputs[name] = value
        prompt[str(node["id"])] = {"class_type": node["type"], "inputs": inputs,
                                   "_meta": {"title": node.get("title", node["type"])}}
    return prompt


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--set", action="append", default=[], metavar="NODE.input=value")
    parser.add_argument("--out", default=None, help="write the API JSON here instead of printing")
    args = parser.parse_args(argv)
    object_info = requests.get(f"http://{args.host}:{args.port}/object_info", timeout=60).json()
    with open(args.workflow, "r", encoding="utf-8") as handle:
        ui = json.load(handle)
    overrides = {}
    for item in args.set:
        target, value = item.split("=", 1)
        node_id, name = target.split(".", 1)
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
        overrides.setdefault(node_id, {})[name] = value
    prompt = ui_to_api(ui, object_info, overrides)
    text = json.dumps(prompt, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
        print(f"wrote {args.out} ({len(prompt)} nodes)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
