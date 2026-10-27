import json
import os
import subprocess
import sys

from comfy_apc40 import nodes

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def cc_list(**values):
    floats = [0.0] * 128
    for cc, value in values.items():
        floats[int(cc)] = value / 127.0
    return floats


def test_knob_scales_into_range():
    knob = nodes.APC40Knob()
    value, raw = knob.read(cc_list(**{"16": 127}), "device knob 1 (CC 16)", -20.0, 20.0, 0.0)
    assert (value, raw) == (20.0, 127)
    value, raw = knob.read(cc_list(**{"14": 64}), "master fader (CC 14)", 1.5, 2.5, 1.7)
    assert raw == 64 and abs(value - (1.5 + 1.0 * 64 / 127)) < 1e-9


def test_knob_untouched_returns_resting_value():
    knob = nodes.APC40Knob()
    assert knob.read(cc_list(), "device knob 3 (CC 18)", -20.0, 20.0, 0.0) == (0.0, 0)
    assert knob.read(None, "device knob 3 (CC 18)", -20.0, 20.0, 5.0) == (5.0, 0)


def test_knob_choices_name_every_knob_and_master():
    choices = nodes.KNOB_CHOICES
    assert "device knob 8 (CC 23)" in choices and "track knob 1 (CC 48)" in choices
    assert "master fader (CC 14)" in choices and "crossfader (CC 15)" in choices
    assert not any("fader 1" in c for c in choices)   # channel-keyed faders are not offered


def test_pad_reads_note_state_with_top_left_as_row_1():
    pad = nodes.APC40Pad()
    notes = [False] * 128
    notes[32] = True                                   # mk2 note 32 = top-left pad
    assert pad.read(notes, "pad col 1 row 1") == (True,)
    assert pad.read(notes, "pad col 1 row 5") == (False,)
    notes[82] = True
    assert pad.read(notes, "scene launch 1") == (True,)


def test_generated_workflow_matches_node_signatures():
    """Both generated files agree with each other and with the node classes."""
    ui = json.load(open(os.path.join(ROOT, "workflows", "liveportrait_apc40.json"), encoding="utf-8"))
    api = json.load(open(os.path.join(ROOT, "workflows", "liveportrait_apc40_api.json"), encoding="utf-8"))
    by_id = {n["id"]: n for n in ui["nodes"]}
    for link_id, src, src_slot, dst, dst_slot, _type in ui["links"]:
        assert by_id[dst]["inputs"][dst_slot]["link"] == link_id
        assert link_id in by_id[src]["outputs"][src_slot]["links"]
    knob_inputs = list(nodes.APC40Knob.INPUT_TYPES()["required"])
    for node in ui["nodes"]:
        if node["type"] == "APC40Knob":
            assert [i["name"] for i in node["inputs"]] == knob_inputs
            assert node["widgets_values"][0] in nodes.KNOB_CHOICES
            assert api[str(node["id"])]["inputs"]["control"] == node["widgets_values"][0]


def test_generator_is_deterministic(tmp_path):
    script = os.path.join(ROOT, "scripts", "build_liveportrait_apc40.py")
    before = open(os.path.join(ROOT, "workflows", "liveportrait_apc40.json"), encoding="utf-8").read()
    subprocess.run([sys.executable, script], check=True, capture_output=True)
    after = open(os.path.join(ROOT, "workflows", "liveportrait_apc40.json"), encoding="utf-8").read()
    assert before == after
