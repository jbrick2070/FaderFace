"""Akai APC40 layout: which note or CC each control sends, how pads are
numbered, the SysEx that puts the unit in host-controlled mode, and the LED
colour codes.

The mk2 is the unit on this desk and is the layout that has been exercised;
the mk1 table is carried from Akai's protocol document so a skin written for
one works on the other without edits.

Pad coordinates are (col, row) with col 0 on the left and row 0 on the TOP,
which is how a person reads the grid. The mk2 numbers its notes from the
bottom-left, so the conversion lives here and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PAD_COLS = 8
PAD_ROWS = 5


@dataclass(frozen=True)
class Layout:
    name: str
    product_id: int
    # Pads: mk2 puts the whole grid on one channel; mk1 puts each column on
    # its own channel and uses the note for the row.
    pads_on_one_channel: bool
    pad_base_note: int
    scene_base_note: int          # five scene-launch buttons, top to bottom
    named_notes: dict = field(default_factory=dict)   # name -> (note, channel)
    led: dict = field(default_factory=dict)           # colour name -> velocity
    blink_channel: int = 0        # mk2: note-on channel that selects blinking

    def pad_from_note(self, note: int, channel: int):
        """Return (col, row) for a pad note, or None if the note is not a pad."""
        if self.pads_on_one_channel:
            if channel != 0 or not (self.pad_base_note <= note < self.pad_base_note + PAD_COLS * PAD_ROWS):
                return None
            index = note - self.pad_base_note
            col, row_from_bottom = index % PAD_COLS, index // PAD_COLS
            return col, PAD_ROWS - 1 - row_from_bottom
        if not (0 <= channel < PAD_COLS):
            return None
        row = note - self.pad_base_note
        if not (0 <= row < PAD_ROWS):
            return None
        return channel, row

    def note_for_pad(self, col: int, row: int):
        """Return (note, channel) that lights or identifies pad (col, row)."""
        if not (0 <= col < PAD_COLS and 0 <= row < PAD_ROWS):
            raise ValueError(f"pad out of range: col={col} row={row}")
        if self.pads_on_one_channel:
            return self.pad_base_note + (PAD_ROWS - 1 - row) * PAD_COLS + col, 0
        return self.pad_base_note + row, col

    def scene_from_note(self, note: int, channel: int):
        """Return scene index 0..4 (top to bottom) or None."""
        if channel == 0 and self.scene_base_note <= note < self.scene_base_note + PAD_ROWS:
            return note - self.scene_base_note
        return None

    def button_from_note(self, note: int, channel: int):
        """Return the name of a non-pad button, or None."""
        for name, (n, ch) in self.named_notes.items():
            if n == note and (ch is None or ch == channel):
                return name if ch is not None else f"{name}_{channel + 1}"
        return None

    def mode_sysex(self) -> list:
        """Data bytes (without F0/F7) that switch the unit to the mode where the
        host owns every LED. Mode 0x42 on both generations."""
        return [0x47, 0x7F, self.product_id, 0x60, 0x00, 0x04, 0x42, 0x09, 0x01, 0x01]


# Continuous controls are the same numbers on both generations.
CC_NAMES = {}
for _i in range(8):
    CC_NAMES[(16 + _i, 0)] = f"device_{_i + 1}"   # the eight knobs above the display
    CC_NAMES[(48 + _i, 0)] = f"track_{_i + 1}"    # the eight knobs above the faders
    CC_NAMES[(7, _i)] = f"fader_{_i + 1}"         # one fader per track channel
CC_NAMES[(14, 0)] = "master"
CC_NAMES[(15, 0)] = "crossfader"
CC_NAMES[(47, 0)] = "cue_level"                  # relative encoder, 1 = up, 127 = down


def cc_name(control: int, channel: int):
    return CC_NAMES.get((control, channel))


_PER_TRACK_BUTTONS = {
    "clip_stop": 52, "track_select": 51, "activator": 50, "solo": 49, "arm": 48,
}
_GLOBAL_BUTTONS_MK2 = {
    "play": 91, "record": 93, "session": 102, "shift": 98, "stop_all": 81,
    "bank_up": 94, "bank_down": 95, "bank_right": 96, "bank_left": 97,
    "nudge_minus": 100, "nudge_plus": 101, "tap_tempo": 99, "metronome": 90,
    "pan": 87, "sends": 88, "user": 89, "device_left": 58, "device_right": 59,
    "bank_left_device": 60, "bank_right_device": 61, "device_on": 62,
    "device_lock": 63, "clip_dev_view": 64, "detail_view": 65,
}
_GLOBAL_BUTTONS_MK1 = {
    "play": 91, "stop": 92, "record": 93, "shift": 98, "stop_all": 81,
    "bank_up": 94, "bank_down": 95, "bank_right": 96, "bank_left": 97,
    "nudge_minus": 100, "nudge_plus": 101, "tap_tempo": 99,
    "pan": 87, "send_a": 88, "send_b": 89, "send_c": 90,
}


def _named(global_buttons):
    names = {k: (v, 0) for k, v in global_buttons.items()}
    names.update({k: (v, None) for k, v in _PER_TRACK_BUTTONS.items()})
    return names


MK2 = Layout(
    name="mk2",
    product_id=0x29,
    pads_on_one_channel=True,
    pad_base_note=0,
    scene_base_note=82,
    named_notes=_named(_GLOBAL_BUTTONS_MK2),
    # Velocity picks a colour from the mk2's 128-entry palette. These indexes
    # are the clean primaries; tune by eye if a shade looks off on your unit.
    led={"off": 0, "white": 3, "red": 5, "orange": 9, "yellow": 13, "green": 21,
         "cyan": 37, "blue": 45, "purple": 49, "pink": 57},
    blink_channel=11,   # blink at 1/8 note; channel 0 is solid
)

MK1 = Layout(
    name="mk1",
    product_id=0x73,
    pads_on_one_channel=False,
    pad_base_note=53,
    scene_base_note=82,
    named_notes=_named(_GLOBAL_BUTTONS_MK1),
    # The mk1 pads are three-colour: green, red, yellow, each solid or blinking.
    led={"off": 0, "green": 1, "green_blink": 2, "red": 3, "red_blink": 4,
         "yellow": 5, "yellow_blink": 6,
         # Fallbacks so a skin written in mk2 colours still lights something.
         "white": 5, "orange": 5, "cyan": 1, "blue": 1, "purple": 3, "pink": 3},
    blink_channel=0,
)

LAYOUTS = {"mk2": MK2, "mk1": MK1}


def layout_for_port(port_name: str) -> Layout:
    """Pick the layout from the MIDI port name. Anything that is not an APC40
    (a loopMIDI port, for instance) is driven as an mk2."""
    lowered = port_name.lower()
    if "apc40" in lowered and "mkii" not in lowered and "mk2" not in lowered:
        return MK1
    return MK2


def led_message(layout: Layout, col: int, row: int, colour: str, blink: bool = False):
    """Build the (note, velocity, channel) triple that lights one pad."""
    note, channel = layout.note_for_pad(col, row)
    if layout.name == "mk1":
        key = f"{colour}_blink" if blink and f"{colour}_blink" in layout.led else colour
        return note, layout.led.get(key, layout.led["off"]), channel
    velocity = layout.led.get(colour, layout.led["off"])
    return note, velocity, (layout.blink_channel if blink and velocity else channel)
