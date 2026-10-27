"""Generate the APC40 -> Advanced Live Portrait workflow.

One node list produces two files:
  workflows/liveportrait_apc40.json      the litegraph graph you load in ComfyUI
  workflows/liveportrait_apc40_api.json  the API form, used to validate against /prompt

Signal path per control:
  MIDI Device Loader @ vrch.ai  (reads the APC40 in the browser via Web MIDI)
    -> FLOAT_CC_VALUES  (128 floats, 0..1, indexed by CC number)
    -> APC40 Knob       (this pack: picks the control by name, scales to a range)
    -> Expression Editor (PHM) input

The loader is channel-blind (it keys CC by number only), so the eight faders,
which all send CC 7 on different channels, collide and are not used here. The
sixteen knobs and the master fader are all distinct CC numbers on channel 0.

Run:  python scripts/build_liveportrait_apc40.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "workflows"))

PORTRAIT = "sample_pic_01_woman_head.png"
WEB_VIEWER_SERVER = "127.0.0.1:8188"

# (APC40 control, CC number, Expression Editor input, out_min, out_max, resting value)
# Resting value is what the face does before the knob is touched (knob at 0 reads
# as out_min otherwise). Centre the knobs before you start for the bipolar ones.
CONTROLS = [
    ("device knob 1", 16, "rotate_pitch", -20.0, 20.0, 0.0),
    ("device knob 2", 17, "rotate_yaw", -20.0, 20.0, 0.0),
    ("device knob 3", 18, "rotate_roll", -20.0, 20.0, 0.0),
    ("device knob 4", 19, "pupil_x", -15.0, 15.0, 0.0),
    ("device knob 5", 20, "pupil_y", -15.0, 15.0, 0.0),
    ("device knob 6", 21, "eyebrow", -10.0, 15.0, 0.0),
    ("device knob 7", 22, "blink", -20.0, 5.0, 0.0),
    ("device knob 8", 23, "wink", 0.0, 25.0, 0.0),
    ("track knob 1", 48, "aaa", -30.0, 120.0, 0.0),
    ("track knob 2", 49, "eee", -20.0, 15.0, 0.0),
    ("track knob 3", 50, "woo", -20.0, 15.0, 0.0),
    ("track knob 4", 51, "smile", -0.3, 1.3, 0.0),
    ("master fader", 14, "crop_factor", 1.5, 2.5, 1.7),
]

EXPRESSION_WIDGETS = [
    ("rotate_pitch", 0.0), ("rotate_yaw", 0.0), ("rotate_roll", 0.0), ("blink", 0.0),
    ("eyebrow", 0.0), ("wink", 0.0), ("pupil_x", 0.0), ("pupil_y", 0.0), ("aaa", 0.0),
    ("eee", 0.0), ("woo", 0.0), ("smile", 0.0), ("src_ratio", 1.0), ("sample_ratio", 1.0),
    ("sample_parts", "OnlyExpression"), ("crop_factor", 1.7),
]

CHEAT_SHEET = "\n".join(
    [f"{control:<14} -> {target}" for control, _cc, target, *_ in CONTROLS]
    + ["", "Faders are unused: the MIDI loader keys CC by number only,",
       "and every fader sends CC 7. Knobs are all distinct numbers.",
       "", "1. Plug in the APC40 BEFORE opening this tab (Web MIDI).",
       "2. Centre the device knobs so the head starts straight.",
       "3. Extra options -> Auto Queue -> instant, then Queue.",
       "4. Open the Web Viewer button for a clean full-size window."]
)


class Graph:
    """Builds litegraph nodes and links; slot indexes are looked up by name."""

    def __init__(self):
        self.nodes = []
        self.links = []
        self._next_node = 1
        self._next_link = 1

    def add(self, class_type, title, pos, size, inputs, outputs, widgets, api_inputs=None, api=True):
        node = {
            "id": self._next_node,
            "type": class_type,
            "pos": list(pos),
            "size": list(size),
            "flags": {},
            "order": self._next_node - 1,
            "mode": 0,
            "inputs": [dict(i) for i in inputs],
            "outputs": [dict(o, links=[]) for o in outputs],
            "properties": {"Node name for S&R": class_type},
            "widgets_values": list(widgets),
            "title": title,
            "_api": api,
            "_api_inputs": dict(api_inputs or {}),
        }
        self.nodes.append(node)
        self._next_node += 1
        return node

    def link(self, src, src_slot, dst, dst_input, link_type):
        dst_slot = next(i for i, inp in enumerate(dst["inputs"]) if inp["name"] == dst_input)
        link_id = self._next_link
        self._next_link += 1
        self.links.append([link_id, src["id"], src_slot, dst["id"], dst_slot, link_type])
        dst["inputs"][dst_slot]["link"] = link_id
        src["outputs"][src_slot]["links"].append(link_id)
        dst["_api_inputs"][dst_input] = [str(src["id"]), src_slot]

    def ui_json(self):
        nodes = []
        for node in self.nodes:
            clean = {k: v for k, v in node.items() if not k.startswith("_")}
            nodes.append(clean)
        return {
            "id": "apc40-live-portrait",
            "revision": 0,
            "last_node_id": self._next_node - 1,
            "last_link_id": self._next_link - 1,
            "nodes": nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {"ds": {"scale": 0.6, "offset": [40, 40]}},
            "version": 0.4,
        }

    def api_json(self):
        prompt = {}
        for node in self.nodes:
            if not node["_api"]:
                continue
            prompt[str(node["id"])] = {
                "class_type": node["type"],
                "_meta": {"title": node["title"]},
                "inputs": dict(node["_api_inputs"]),
            }
        return prompt


def widget_input(name, type_name):
    return {"name": name, "type": type_name, "widget": {"name": name}, "link": None}


def build():
    g = Graph()

    midi = g.add(
        "VrchMidiDeviceLoaderNode", "APC40 (MIDI Device Loader)", (40, 40), (420, 160),
        inputs=[widget_input("device_id", "STRING"), widget_input("name", "STRING"),
                widget_input("debug", "BOOLEAN"), widget_input("raw_data", "STRING")],
        outputs=[{"name": "RAW_DATA", "type": "JSON"}, {"name": "INT_CC_VALUES", "type": "INT"},
                 {"name": "FLOAT_CC_VALUES", "type": "FLOAT"},
                 {"name": "BOOLEAN_NOTE_VALUES", "type": "BOOL"}, {"name": "INT_NOTE_VALUES", "type": "INT"}],
        widgets=["", "", False, ""],
        api_inputs={"device_id": "", "name": "", "debug": False, "raw_data": ""},
    )

    portrait = g.add(
        "LoadImage", "portrait", (40, 260), (320, 400),
        inputs=[widget_input("image", "COMBO"), widget_input("upload", "IMAGEUPLOAD")],
        outputs=[{"name": "IMAGE", "type": "IMAGE"}, {"name": "MASK", "type": "MASK"}],
        widgets=[PORTRAIT, "image"],
        api_inputs={"image": PORTRAIT},
    )

    editor = g.add(
        "ExpressionEditor", "Expression Editor (PHM)", (1180, 40), (420, 720),
        inputs=[{"name": "src_image", "type": "IMAGE", "link": None},
                {"name": "motion_link", "type": "EDITOR_LINK", "link": None},
                {"name": "sample_image", "type": "IMAGE", "link": None},
                {"name": "add_exp", "type": "EXP_DATA", "link": None}]
               + [widget_input(name, "COMBO" if name == "sample_parts" else "FLOAT")
                  for name, _default in EXPRESSION_WIDGETS],
        outputs=[{"name": "image", "type": "IMAGE"}, {"name": "motion_link", "type": "EDITOR_LINK"},
                 {"name": "save_exp", "type": "EXP_DATA"}],
        widgets=[default for _name, default in EXPRESSION_WIDGETS],
        api_inputs={name: default for name, default in EXPRESSION_WIDGETS},
    )
    g.link(portrait, 0, editor, "src_image", "IMAGE")

    viewer = g.add(
        "VrchImageWebViewerNode", "Web Viewer (open for a clean window)", (1660, 40), (420, 420),
        inputs=[{"name": "images", "type": "IMAGE", "link": None},
                widget_input("channel", "COMBO"), widget_input("server", "STRING"),
                widget_input("ssl", "BOOLEAN"), widget_input("refresh_interval", "INT"),
                widget_input("fade_anim_duration", "INT"), widget_input("server_messages", "STRING"),
                widget_input("save_settings", "BOOLEAN"), widget_input("window_width", "INT"),
                widget_input("window_height", "INT"), widget_input("show_url", "BOOLEAN"),
                widget_input("dev_mode", "BOOLEAN"), widget_input("extra_params", "STRING"),
                widget_input("url", "STRING")],
        outputs=[{"name": "IMAGES", "type": "IMAGE"}, {"name": "URL", "type": "STRING"}],
        widgets=["1", WEB_VIEWER_SERVER, False, 100, 80, "", False, 600, 600, False, False, "", ""],
        api_inputs={"channel": "1", "server": WEB_VIEWER_SERVER, "ssl": False, "refresh_interval": 100,
                    "fade_anim_duration": 80, "server_messages": "", "save_settings": False,
                    "window_width": 600, "window_height": 600, "show_url": False, "dev_mode": False,
                    "extra_params": "", "url": ""},
    )
    g.link(editor, 0, viewer, "images", "IMAGE")

    for row, (control, cc, target, out_min, out_max, resting) in enumerate(CONTROLS):
        y = 40 + row * 130
        label = f"{control} (CC {cc})"
        knob = g.add(
            "APC40Knob", f"{target}", (620, y), (380, 150),
            inputs=[{"name": "cc_values", "type": "FLOAT", "link": None},
                    widget_input("control", "COMBO"), widget_input("output_min", "FLOAT"),
                    widget_input("output_max", "FLOAT"), widget_input("resting", "FLOAT")],
            outputs=[{"name": "value", "type": "FLOAT"}, {"name": "raw_cc", "type": "INT"}],
            widgets=[label, out_min, out_max, resting],
            api_inputs={"control": label, "output_min": out_min, "output_max": out_max, "resting": resting},
        )
        g.link(midi, 2, knob, "cc_values", "FLOAT")
        g.link(knob, 0, editor, target, "FLOAT")

    g.add(
        "Note", "APC40 cheat sheet", (40, 700), (440, 420),
        inputs=[], outputs=[], widgets=[CHEAT_SHEET], api=False,
    )
    return g


def main():
    graph = build()
    os.makedirs(OUT_DIR, exist_ok=True)
    ui_path = os.path.join(OUT_DIR, "liveportrait_apc40.json")
    api_path = os.path.join(OUT_DIR, "liveportrait_apc40_api.json")
    with open(ui_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(graph.ui_json(), handle, indent=2)
        handle.write("\n")
    with open(api_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(graph.api_json(), handle, indent=2)
        handle.write("\n")
    print(f"wrote {ui_path}\nwrote {api_path}\n{len(graph.nodes)} nodes, {len(graph.links)} links")


if __name__ == "__main__":
    main()
