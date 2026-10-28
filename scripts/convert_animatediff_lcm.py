"""Convert Machine Delusions' AnimateDiff-LCM workflows into FaderFace copies
that run on this box without the Fill-Nodes pack.

Input:  the two Patreon JSON files (UI format), paths given on the command line.
Output: workflows/animatediff_lcm_part1.json and workflows/animatediff_lcm_part2.json

What changes, and why:
  * FL_UpscaleModel  -> ImageUpscaleWithModel + ImageScaleBy (core). Same maths:
                        4x GAN upscale, then scale by the node's downscale_by.
  * FL_ImageSelector -> removed; it only picked frame 0 for a PreviewImage,
                        so the preview is fed from the selector's own source.
  * FL_RIFE          -> removed; the final VideoCombine takes the frames straight
                        and its frame rate is set back to the source 15 fps.
                        (RIFE was interpolating 15 -> 30 fps as a last polish.)
  * LoadSAM3Model / SAM3Segmentation -> removed; they fed one MaskPreview and
                        nothing else, and the SAM3 pack is not installed.
  * Diff-LCM.ckpt    -> AnimateLCM_sd15_t2v.ckpt, the same AnimateLCM motion
                        module from Hugging Face (the Civitai copy needs a login).
  * videopreview widgets are cleared so the graph does not point at D:\\ paths.

Links are repaired by identity: every link's dst_slot is set to the index of
the input whose .link equals that link id, so removing inputs never leaves a
link pointing one slot off.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "workflows"))

MODEL_RENAMES = {
    "Diff-LCM.ckpt": "AnimateLCM_sd15_t2v.ckpt",
}


class Graph:
    def __init__(self, data):
        self.data = data
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.links = {l[0]: l for l in data["links"]}

    # ---------------------------------------------------------------- helpers
    def next_node_id(self):
        self.data["last_node_id"] += 1
        return self.data["last_node_id"]

    def next_link_id(self):
        self.data["last_link_id"] += 1
        return self.data["last_link_id"]

    def input_link(self, node, name):
        for inp in node["inputs"]:
            if inp["name"] == name:
                return inp.get("link")
        return None

    def source_of(self, link_id):
        link = self.links[link_id]
        return link[1], link[2]

    def consumers_of(self, node_id, slot=0):
        """(link_id, dst_node, dst_input_name) for every link leaving node:slot."""
        out = []
        for link_id, link in self.links.items():
            if link[1] == node_id and link[2] == slot:
                dst = self.nodes[link[3]]
                out.append((link_id, link[3], dst["inputs"][link[4]]["name"]))
        return out

    def add_node(self, class_type, title, pos, inputs, outputs, widgets, size=(270, 100)):
        node = {
            "id": self.next_node_id(), "type": class_type, "pos": list(pos), "size": list(size),
            "flags": {}, "order": 0, "mode": 0,
            "inputs": [dict(i, link=None) for i in inputs],
            "outputs": [dict(o, links=[]) for o in outputs],
            "properties": {"Node name for S&R": class_type},
            "widgets_values": list(widgets), "title": title,
        }
        self.nodes[node["id"]] = node
        self.data["nodes"].append(node)
        return node

    def connect(self, src_id, src_slot, dst_id, dst_input, link_type):
        link_id = self.next_link_id()
        dst = self.nodes[dst_id]
        dst_slot = next(i for i, inp in enumerate(dst["inputs"]) if inp["name"] == dst_input)
        old = dst["inputs"][dst_slot].get("link")
        if old is not None:
            self.drop_link(old)
        self.links[link_id] = [link_id, src_id, src_slot, dst_id, dst_slot, link_type]
        dst["inputs"][dst_slot]["link"] = link_id
        self.nodes[src_id]["outputs"][src_slot].setdefault("links", [])
        self.nodes[src_id]["outputs"][src_slot]["links"] = (self.nodes[src_id]["outputs"][src_slot]["links"] or []) + [link_id]
        return link_id

    def drop_link(self, link_id):
        link = self.links.pop(link_id, None)
        if not link:
            return
        src = self.nodes.get(link[1])
        if src:
            for out in src["outputs"]:
                if out.get("links") and link_id in out["links"]:
                    out["links"].remove(link_id)
        dst = self.nodes.get(link[3])
        if dst:
            for inp in dst["inputs"]:
                if inp.get("link") == link_id:
                    inp["link"] = None

    def remove_node(self, node_id):
        node = self.nodes.pop(node_id)
        for inp in node["inputs"]:
            if inp.get("link") is not None:
                self.drop_link(inp["link"])
        for out in node["outputs"]:
            for link_id in list(out.get("links") or []):
                self.drop_link(link_id)
        self.data["nodes"] = [n for n in self.data["nodes"] if n["id"] != node_id]

    def bypass_node(self, node_id, in_name, out_slot=0):
        """Rewire every consumer of node:out_slot to whatever feeds node.in_name, then remove the node."""
        node = self.nodes[node_id]
        feed = self.input_link(node, in_name)
        src_id, src_slot = self.source_of(feed)
        for link_id, dst_id, dst_input in self.consumers_of(node_id, out_slot):
            self.drop_link(link_id)
            self.connect(src_id, src_slot, dst_id, dst_input, self.links_type_guess(src_id, src_slot))
        self.remove_node(node_id)

    def links_type_guess(self, src_id, src_slot):
        return self.nodes[src_id]["outputs"][src_slot].get("type", "*")

    # --------------------------------------------------------------- finalise
    def repair_slots(self):
        """dst_slot and src_slot by identity, not arithmetic."""
        for link_id, link in self.links.items():
            dst = self.nodes[link[3]]
            link[4] = next(i for i, inp in enumerate(dst["inputs"]) if inp.get("link") == link_id)
            src = self.nodes[link[1]]
            link[2] = next(i for i, out in enumerate(src["outputs"]) if link_id in (out.get("links") or []))
        self.data["links"] = [self.links[k] for k in sorted(self.links)]

    def dump(self):
        self.repair_slots()
        return self.data


def convert(path, out_name, drop_rife=True):
    with open(path, "r", encoding="utf-8") as handle:
        g = Graph(json.load(handle))
    g.data["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "faderface/" + out_name))

    # FL_UpscaleModel -> ImageUpscaleWithModel + ImageScaleBy
    for node in [n for n in list(g.nodes.values()) if n["type"] == "FL_UpscaleModel"]:
        downscale_by, method = node["widgets_values"][0], node["widgets_values"][1]
        model_link = g.input_link(node, "upscale_model")
        image_link = g.input_link(node, "image")
        model_src, image_src = g.source_of(model_link), g.source_of(image_link)
        x, y = node["pos"]
        up = g.add_node("ImageUpscaleWithModel", "4x upscale", (x, y),
                        [{"name": "upscale_model", "type": "UPSCALE_MODEL"}, {"name": "image", "type": "IMAGE"}],
                        [{"name": "IMAGE", "type": "IMAGE"}], [], size=(240, 46))
        down = g.add_node("ImageScaleBy", f"scale by {downscale_by:g}", (x, y + 70),
                          [{"name": "image", "type": "IMAGE"},
                           {"name": "upscale_method", "type": "COMBO", "widget": {"name": "upscale_method"}},
                           {"name": "scale_by", "type": "FLOAT", "widget": {"name": "scale_by"}}],
                          [{"name": "IMAGE", "type": "IMAGE"}], [method, downscale_by], size=(240, 82))
        consumers = g.consumers_of(node["id"], 0)
        g.remove_node(node["id"])
        g.connect(model_src[0], model_src[1], up["id"], "upscale_model", "UPSCALE_MODEL")
        g.connect(image_src[0], image_src[1], up["id"], "image", "IMAGE")
        g.connect(up["id"], 0, down["id"], "image", "IMAGE")
        for _link_id, dst_id, dst_input in consumers:
            g.connect(down["id"], 0, dst_id, dst_input, "IMAGE")

    # FL_ImageSelector -> bypass (preview the source directly)
    for node in [n for n in list(g.nodes.values()) if n["type"] == "FL_ImageSelector"]:
        g.bypass_node(node["id"], "images")

    # FL_RIFE -> bypass, and put the downstream VideoCombine back at 15 fps
    for node in [n for n in list(g.nodes.values()) if n["type"] == "FL_RIFE"]:
        for _link_id, dst_id, _name in g.consumers_of(node["id"], 0):
            dst = g.nodes[dst_id]
            if dst["type"] == "VHS_VideoCombine" and isinstance(dst["widgets_values"], dict):
                dst["widgets_values"]["frame_rate"] = 15
        g.bypass_node(node["id"], "images")

    # SAM3 pair -> remove (dead-end preview)
    for node in [n for n in list(g.nodes.values()) if n["type"] in ("SAM3Segmentation", "LoadSAM3Model")]:
        for _link_id, dst_id, _name in g.consumers_of(node["id"], 0):
            if g.nodes[dst_id]["type"] == "MaskPreview":
                g.remove_node(dst_id)
        g.remove_node(node["id"])

    # Model names, stale previews
    for node in g.nodes.values():
        wv = node.get("widgets_values")
        if isinstance(wv, list):
            node["widgets_values"] = [MODEL_RENAMES.get(v, v) if isinstance(v, str) else v for v in wv]
        elif isinstance(wv, dict):
            wv.pop("videopreview", None)
        node["properties"].pop("ue_properties", None)

    g.data["extra"] = {"ds": {"scale": 0.4, "offset": [0, 0]}}
    out_path = os.path.join(OUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(g.dump(), handle, indent=2)
        handle.write("\n")
    print(f"wrote {out_path}: {len(g.nodes)} nodes, {len(g.links)} links")
    return out_path


def main(argv):
    if len(argv) != 3:
        print("usage: convert_animatediff_lcm.py <part1.json> <part2.json>")
        return 2
    convert(argv[1], "animatediff_lcm_part1.json")
    convert(argv[2], "animatediff_lcm_part2.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
