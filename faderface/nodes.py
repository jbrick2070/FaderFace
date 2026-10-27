"""ComfyUI nodes that read an Akai APC40 by control name.

They sit downstream of ``MIDI Device Loader @ vrch.ai`` (comfyui-web-viewer),
which reads the controller in the browser through Web MIDI and outputs the
current CC and note state as 128-entry lists. These nodes pick one control
out of those lists so a workflow says "device knob 3", not "index 18".

The loader keys CC by number only, so the eight faders (all CC 7, one per
channel) collapse into one slot. Knobs, the master fader and the crossfader
are distinct numbers and work.
"""
from __future__ import annotations

from .apc40 import CC_NAMES, MK2, PAD_COLS, PAD_ROWS

CATEGORY = "APC40"

# Control name -> CC number, channel 0 only (the loader cannot see channels).
KNOB_CC = {name: cc for (cc, channel), name in CC_NAMES.items() if channel == 0}
KNOB_LABELS = {
    **{f"device_{i}": f"device knob {i} (CC {15 + i})" for i in range(1, 9)},
    **{f"track_{i}": f"track knob {i} (CC {47 + i})" for i in range(1, 9)},
    "master": "master fader (CC 14)",
    "crossfader": "crossfader (CC 15)",
}
KNOB_CHOICES = [KNOB_LABELS[name] for name in KNOB_LABELS if name in KNOB_CC]
LABEL_TO_CC = {KNOB_LABELS[name]: cc for name, cc in KNOB_CC.items() if name in KNOB_LABELS}

PAD_CHOICES = [f"pad col {col + 1} row {row + 1}" for row in range(PAD_ROWS) for col in range(PAD_COLS)]
PAD_TO_NOTE = {
    f"pad col {col + 1} row {row + 1}": MK2.note_for_pad(col, row)[0]
    for row in range(PAD_ROWS) for col in range(PAD_COLS)
}
SCENE_CHOICES = [f"scene launch {i + 1}" for i in range(PAD_ROWS)]
SCENE_TO_NOTE = {f"scene launch {i + 1}": MK2.scene_base_note + i for i in range(PAD_ROWS)}


def _entry(values, index: int, default):
    """Pull one entry from the loader's list; anything unexpected gives the
    default rather than an exception in the middle of a performance."""
    try:
        return values[index]
    except (TypeError, IndexError, KeyError):
        return default


class APC40Knob:
    """One knob or fader of the APC40 as a float in your own range."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cc_values": ("FLOAT", {"forceInput": True,
                                        "tooltip": "FLOAT_CC_VALUES from MIDI Device Loader @ vrch.ai"}),
                "control": (KNOB_CHOICES, {"default": KNOB_CHOICES[0]}),
                "output_min": ("FLOAT", {"default": 0.0, "min": -999999.0, "max": 999999.0, "step": 0.01}),
                "output_max": ("FLOAT", {"default": 1.0, "min": -999999.0, "max": 999999.0, "step": 0.01}),
                "resting": ("FLOAT", {"default": 0.0, "min": -999999.0, "max": 999999.0, "step": 0.01,
                                      "tooltip": "Value used until the knob is first moved"}),
            }
        }

    RETURN_TYPES = ("FLOAT", "INT")
    RETURN_NAMES = ("value", "raw_cc")
    FUNCTION = "read"
    CATEGORY = CATEGORY

    def read(self, cc_values, control, output_min, output_max, resting):
        cc = LABEL_TO_CC[control]
        fraction = _entry(cc_values, cc, None)
        if fraction is None:
            return (float(resting), 0)
        fraction = max(0.0, min(1.0, float(fraction)))
        raw = int(round(fraction * 127))
        if raw == 0:
            # The loader reports 0.0 both for "never touched" and "turned to
            # zero"; the resting value wins so a fresh graph starts neutral.
            return (float(resting), 0)
        return (float(output_min) + (float(output_max) - float(output_min)) * fraction, raw)


class APC40Pad:
    """One clip-launch pad or scene button of the APC40 as a boolean."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "note_values": ("BOOL", {"forceInput": True,
                                         "tooltip": "BOOLEAN_NOTE_VALUES from MIDI Device Loader @ vrch.ai"}),
                "button": (PAD_CHOICES + SCENE_CHOICES, {"default": PAD_CHOICES[0]}),
            }
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("pressed",)
    FUNCTION = "read"
    CATEGORY = CATEGORY

    def read(self, note_values, button):
        note = PAD_TO_NOTE.get(button, SCENE_TO_NOTE.get(button))
        return (bool(_entry(note_values, note, False)),)


NODE_CLASS_MAPPINGS = {
    "APC40Knob": APC40Knob,
    "APC40Pad": APC40Pad,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "APC40Knob": "APC40 Knob",
    "APC40Pad": "APC40 Pad",
}
