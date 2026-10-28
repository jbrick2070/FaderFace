import importlib.util
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def load(name):
    path = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OBJECT_INFO = {
    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["a.safetensors"]]}}},
    "KSampler": {"input": {"required": {
        "model": ["MODEL"], "seed": ["INT", {}], "steps": ["INT", {}], "cfg": ["FLOAT", {}],
        "sampler_name": [["lcm"]], "scheduler": [["sgm_uniform"]], "positive": ["CONDITIONING"],
        "negative": ["CONDITIONING"], "latent_image": ["LATENT"], "denoise": ["FLOAT", {}]}}},
    "VHS_VideoCombine": {"input": {"required": {"images": ["IMAGE"], "frame_rate": ["INT", {}],
                                                "filename_prefix": ["STRING", {}]}}},
}


def test_ui_to_api_resolves_set_get_and_seed_control():
    mod = load("ui_to_api.py")
    ui = {
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "inputs": [], "outputs": [{"links": [10]}],
             "widgets_values": ["a.safetensors"]},
            {"id": 2, "type": "SetNode", "inputs": [{"name": "MODEL", "link": 10}], "outputs": [],
             "widgets_values": ["MODEL"]},
            {"id": 3, "type": "GetNode", "inputs": [], "outputs": [{"links": [11]}], "widgets_values": ["MODEL"]},
            {"id": 4, "type": "KSampler", "inputs": [{"name": "model", "link": 11}], "outputs": [{"links": [12]}],
             "widgets_values": [43, "fixed", 10, 1, "lcm", "sgm_uniform", 0.6]},
            {"id": 5, "type": "VHS_VideoCombine", "inputs": [{"name": "images", "link": 12}], "outputs": [],
             "widgets_values": {"frame_rate": 15, "filename_prefix": "x", "videopreview": {}}},
            {"id": 6, "type": "Note", "inputs": [], "outputs": [], "widgets_values": ["hi"]},
        ],
        "links": [[10, 1, 0, 2, 0, "MODEL"], [11, 3, 0, 4, 0, "MODEL"], [12, 4, 0, 5, 0, "IMAGE"]],
    }
    prompt = mod.ui_to_api(ui, OBJECT_INFO, overrides={"4": {"denoise": 0.3}})
    assert set(prompt) == {"1", "4", "5"}                       # Set/Get/Note are gone
    assert prompt["4"]["inputs"]["model"] == ["1", 0]           # Get resolved through Set
    assert prompt["4"]["inputs"]["seed"] == 43 and prompt["4"]["inputs"]["steps"] == 10
    assert prompt["4"]["inputs"]["denoise"] == 0.3              # override applied
    assert prompt["5"]["inputs"] == {"images": ["4", 0], "frame_rate": 15, "filename_prefix": "x"}


def test_convert_graph_repairs_slots_by_identity():
    mod = load("convert_animatediff_lcm.py")
    data = {"last_node_id": 3, "last_link_id": 2, "nodes": [
        {"id": 1, "type": "A", "pos": [0, 0], "inputs": [], "outputs": [{"name": "o", "type": "IMAGE", "links": [1]}],
         "widgets_values": [], "properties": {}},
        {"id": 2, "type": "FL_ImageSelector", "pos": [0, 0], "inputs": [{"name": "images", "type": "IMAGE", "link": 1}],
         "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [2]}], "widgets_values": ["0"], "properties": {}},
        {"id": 3, "type": "PreviewImage", "pos": [0, 0], "inputs": [{"name": "spare", "type": "X", "link": None},
                                                                     {"name": "images", "type": "IMAGE", "link": 2}],
         "outputs": [], "widgets_values": [], "properties": {}},
    ], "links": [[1, 1, 0, 2, 0, "IMAGE"], [2, 2, 0, 3, 1, "IMAGE"]]}
    g = mod.Graph(data)
    g.bypass_node(2, "images")
    out = g.dump()
    assert [n["id"] for n in out["nodes"]] == [1, 3]
    assert len(out["links"]) == 1
    link = out["links"][0]
    assert (link[1], link[3]) == (1, 3)
    assert out["nodes"][1]["inputs"][link[4]]["name"] == "images"   # slot index found by identity
