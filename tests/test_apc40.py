from faderface import apc40


def test_mk2_pad_numbering_starts_bottom_left():
    assert apc40.MK2.pad_from_note(0, 0) == (0, 4)      # bottom-left pad
    assert apc40.MK2.pad_from_note(39, 0) == (7, 0)     # top-right pad
    assert apc40.MK2.pad_from_note(32, 0) == (0, 0)     # top-left pad


def test_mk2_pad_roundtrip_every_pad():
    for col in range(apc40.PAD_COLS):
        for row in range(apc40.PAD_ROWS):
            note, channel = apc40.MK2.note_for_pad(col, row)
            assert apc40.MK2.pad_from_note(note, channel) == (col, row)


def test_mk1_pads_use_channel_for_column():
    note, channel = apc40.MK1.note_for_pad(3, 2)
    assert (note, channel) == (55, 3)
    assert apc40.MK1.pad_from_note(55, 3) == (3, 2)
    assert apc40.MK1.pad_from_note(55, 9) is None


def test_non_pad_notes_are_not_pads():
    assert apc40.MK2.pad_from_note(40, 0) is None
    assert apc40.MK2.pad_from_note(5, 1) is None
    assert apc40.MK2.scene_from_note(84, 0) == 2
    assert apc40.MK2.button_from_note(91, 0) == "play"
    assert apc40.MK2.button_from_note(52, 3) == "clip_stop_4"


def test_cc_names_cover_knobs_and_faders():
    assert apc40.cc_name(16, 0) == "device_1"
    assert apc40.cc_name(55, 0) == "track_8"
    assert apc40.cc_name(7, 2) == "fader_3"
    assert apc40.cc_name(14, 0) == "master"
    assert apc40.cc_name(99, 0) is None


def test_led_message_mk2_blink_uses_blink_channel():
    note, velocity, channel = apc40.led_message(apc40.MK2, 0, 0, "yellow", blink=True)
    assert note == 32 and velocity == apc40.MK2.led["yellow"] and channel == apc40.MK2.blink_channel
    note, velocity, channel = apc40.led_message(apc40.MK2, 0, 0, "off")
    assert velocity == 0 and channel == 0


def test_led_message_mk1_blink_is_a_velocity():
    note, velocity, channel = apc40.led_message(apc40.MK1, 1, 0, "green", blink=True)
    assert (note, velocity, channel) == (53, 2, 1)


def test_layout_for_port():
    assert apc40.layout_for_port("APC40 mkII 0") is apc40.MK2
    assert apc40.layout_for_port("Akai APC40 1") is apc40.MK1
    assert apc40.layout_for_port("loopMIDI Port 1") is apc40.MK2


def test_mode_sysex_carries_product_id():
    assert apc40.MK2.mode_sysex()[2] == 0x29
    assert apc40.MK1.mode_sysex()[2] == 0x73
