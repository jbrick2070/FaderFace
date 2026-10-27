import os
from types import SimpleNamespace

from faderface import apc40
from faderface.bridge import Bridge
from faderface.skin import Skin, get_target

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
KLEIN_SKIN = os.path.join(ROOT, "mappings", "flux3_klein_edit.json")


class FakeClient:
    def __init__(self):
        self.queued = []
        self.interrupted = 0

    def queue(self, prompt):
        self.queued.append(prompt)
        return f"prompt-{len(self.queued)}"

    def interrupt(self):
        self.interrupted += 1


class FakeMidiOut:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append((message.note, message.velocity, message.channel))


def note_on(note, channel=0, velocity=127):
    return SimpleNamespace(type="note_on", note=note, channel=channel, velocity=velocity)


def control_change(control, value, channel=0):
    return SimpleNamespace(type="control_change", control=control, value=value, channel=channel)


def make_bridge(source=None):
    skin = Skin.load(KLEIN_SKIN)
    client = FakeClient()
    out = FakeMidiOut()
    bridge = Bridge(skin, client, out, apc40.MK2, source_image=source)
    return bridge, client, out


def test_knob_then_pad_queues_a_prompt_with_the_knob_value():
    bridge, client, out = make_bridge(source="photo.png")
    bridge.handle("midi", control_change(16, 127))          # device knob 1 -> steps max
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(0, 0)))
    assert len(client.queued) == 1
    prompt = client.queued[0]
    assert get_target(prompt, "sampler.steps") == 32
    assert get_target(prompt, "prompt.text") == bridge.skin.pads[(0, 0)].prompt
    assert get_target(prompt, "reference.image") == "photo.png"
    assert bridge.in_flight == {"prompt-1": (0, 0)}
    # Pad lit yellow, blinking, while it renders.
    assert out.sent[-1] == apc40.led_message(apc40.MK2, 0, 0, "yellow", blink=True)


def test_chain_feeds_last_output_into_next_edit():
    bridge, client, out = make_bridge(source="photo.png")
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(2, 1)))
    executed = {"type": "executed", "data": {"prompt_id": "prompt-1", "node": "save", "output": {
        "images": [{"filename": "klein_00001_.png", "subfolder": "apc40", "type": "output"}]}}}
    bridge.handle("comfy", executed)
    bridge.handle("comfy", {"type": "execution_success", "data": {"prompt_id": "prompt-1"}})
    assert bridge.last_output == "apc40/klein_00001_.png [output]"
    assert bridge.in_flight == {}
    assert out.sent[-1] == apc40.led_message(apc40.MK2, 2, 1, "green")

    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(3, 1)))
    assert get_target(client.queued[1], "reference.image") == "apc40/klein_00001_.png [output]"

    bridge.press_button("scene_1")                            # reset_source
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(3, 1)))
    assert get_target(client.queued[2], "reference.image") == "photo.png"


def test_no_source_runs_text_to_image():
    bridge, client, _ = make_bridge(source=None)
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(0, 2)))
    prompt = client.queued[0]
    assert "reference" not in prompt
    assert prompt["sampler"]["inputs"]["positive"] == ["prompt", 0]


def test_error_event_lights_pad_red_and_clears_flight():
    bridge, client, out = make_bridge()
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(7, 4)))
    bridge.handle("comfy", {"type": "execution_error", "data": {"prompt_id": "prompt-1", "exception_message": "boom"}})
    assert bridge.in_flight == {}
    assert out.sent[-1] == apc40.led_message(apc40.MK2, 7, 4, "red")


def test_buttons_interrupt_and_repeat_and_seed_lock():
    bridge, client, _ = make_bridge()
    bridge.handle("midi", note_on(91))                        # play with nothing to repeat
    assert client.queued == []
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(1, 0)))
    first_seed = get_target(client.queued[0], "sampler.seed")
    bridge.press_button("scene_4")                            # lock_seed
    bridge.handle("midi", note_on(91))                        # repeat
    assert get_target(client.queued[1], "sampler.seed") == first_seed
    bridge.handle("midi", note_on(apc40.MK2.scene_base_note + 4))   # scene 5 -> interrupt
    assert client.interrupted == 1


def test_unmapped_pad_and_note_off_are_ignored():
    bridge, client, _ = make_bridge()
    bridge.skin.pads.pop((0, 0))
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(0, 0)))
    bridge.handle("midi", note_on(*apc40.MK2.note_for_pad(1, 0), velocity=0))
    assert client.queued == []


def test_idle_lighting_colours_every_mapped_pad():
    bridge, _, out = make_bridge()
    bridge.light_idle()
    assert len(out.sent) == apc40.PAD_COLS * apc40.PAD_ROWS
    lit = [velocity for _note, velocity, _channel in out.sent if velocity]
    assert len(lit) == len(bridge.skin.pads)
