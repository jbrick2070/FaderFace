import os

import pytest

from comfy_apc40 import skin as skin_module
from comfy_apc40.skin import Knob, Skin, SkinError, build_prompt, get_target, resolve_target

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
KLEIN_SKIN = os.path.join(ROOT, "mappings", "flux3_klein_edit.json")


@pytest.fixture
def klein():
    return Skin.load(KLEIN_SKIN)


def test_klein_skin_loads_and_validates(klein):
    assert len(klein.pads) == 40
    assert klein.prompt_target == "prompt.text"
    assert "device_1" in klein.knobs


def test_resolve_target_by_id_and_by_title(klein):
    assert resolve_target(klein.workflow, "sampler.steps") == ("sampler", "steps")
    assert resolve_target(klein.workflow, "Klein model.unet_name") == ("unet", "unet_name")
    with pytest.raises(SkinError):
        resolve_target(klein.workflow, "sampler.no_such_input")
    with pytest.raises(SkinError):
        resolve_target(klein.workflow, "nobody.steps")


def test_knob_scaling():
    steps = Knob(target="sampler.steps", low=4, high=32, kind="int")
    assert steps.value_for(0) == 4
    assert steps.value_for(127) == 32
    assert steps.value_for(64) == 18
    cfg = Knob(target="sampler.cfg", low=1.0, high=4.0, kind="float")
    assert cfg.value_for(127) == 4.0
    choice = Knob(target="sampler.sampler_name", kind="choice", choices=["a", "b", "c"])
    assert choice.value_for(0) == "a"
    assert choice.value_for(127) == "c"
    assert choice.value_for(60) == "b"


def test_build_prompt_with_source_keeps_reference_chain(klein):
    pad = klein.pads[(0, 0)]
    prompt = build_prompt(klein, pad, {"sampler.steps": 12}, seed=7, source_image="photo.png")
    assert get_target(prompt, "prompt.text") == pad.prompt
    assert get_target(prompt, "sampler.steps") == 12
    assert get_target(prompt, "sampler.seed") == 7
    assert get_target(prompt, "reference.image") == "photo.png"
    assert prompt["sampler"]["inputs"]["positive"] == ["ref_pos", 0]
    # The skin's own workflow is never mutated.
    assert get_target(klein.workflow, "prompt.text") == ""


def test_build_prompt_without_source_strips_reference_chain(klein):
    pad = klein.pads[(1, 1)]
    prompt = build_prompt(klein, pad, {}, seed=1, source_image=None)
    for node in klein.reference_nodes:
        assert node not in prompt
    assert prompt["sampler"]["inputs"]["positive"] == ["prompt", 0]
    assert prompt["sampler"]["inputs"]["negative"] == ["negative", 0]


def test_base_prompt_is_joined(tmp_path, klein):
    klein.base_prompt = "photo of a street"
    prompt = build_prompt(klein, klein.pads[(0, 0)], {}, seed=1, source_image=None)
    assert get_target(prompt, "prompt.text").startswith("photo of a street, ")


def test_skin_rejects_ui_format_workflow(tmp_path):
    workflow = tmp_path / "ui.json"
    workflow.write_text('{"nodes": [], "links": []}', encoding="utf-8")
    spec = tmp_path / "skin.json"
    spec.write_text('{"workflow": "ui.json", "prompt_target": "x.text"}', encoding="utf-8")
    with pytest.raises(SkinError):
        Skin.load(str(spec))


def test_module_has_no_midi_or_network_imports():
    source = open(skin_module.__file__, encoding="utf-8").read()
    assert "import mido" not in source and "import requests" not in source
