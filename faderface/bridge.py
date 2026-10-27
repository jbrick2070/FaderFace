"""The bridge: MIDI in from the APC40, prompts out to ComfyUI, LEDs back.

Everything arrives on one queue (MIDI messages from the port callback,
JSON events from the WebSocket thread) and is handled on the main thread,
so there is no locking anywhere in here.

State the bridge keeps between presses:
  * knob values, scaled per the skin, applied to every prompt;
  * the source image (uploaded at start) and the last output, so an edit
    can chain on the previous result (the pedalboard idea);
  * which pad each in-flight prompt belongs to, for the LED feedback.
"""
from __future__ import annotations

import logging
import queue
import random
import time
from typing import Optional

from . import apc40
from .comfy_client import output_image_name
from .skin import Skin, build_prompt

log = logging.getLogger("faderface")

# Button actions a skin may bind.
ACTIONS = {
    "repeat": "queue the last pad again with a fresh seed",
    "reset_source": "forget the chained output; next edit starts from the source image",
    "toggle_chain": "flip whether each edit starts from the previous output",
    "new_seed": "pick a new random seed (edits otherwise reuse the seed)",
    "interrupt": "ask ComfyUI to stop the running prompt",
    "lock_seed": "keep the current seed for every following press",
}


class Bridge:
    def __init__(self, skin: Skin, client, midi_out, layout: apc40.Layout,
                 source_image: Optional[str] = None, chain: bool = True):
        self.skin = skin
        self.client = client
        self.midi_out = midi_out
        self.layout = layout
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.knob_values: dict = {}
        self.source_image = source_image
        self.last_output: Optional[str] = None
        self.chain = chain
        self.seed = random.randrange(0, 2**32)
        self.seed_locked = False
        self.in_flight: dict = {}          # prompt_id -> (col, row)
        self.last_pad: Optional[tuple] = None
        self._running = False

    # ---------------------------------------------------------------- inputs
    def on_midi(self, message) -> None:
        """Port callback. Runs on the MIDI thread; only enqueues."""
        self.events.put(("midi", message))

    def on_comfy_event(self, event: dict) -> None:
        """WebSocket callback. Runs on the socket thread; only enqueues."""
        self.events.put(("comfy", event))

    # ------------------------------------------------------------------ loop
    def start(self) -> None:
        self._running = True
        self.light_idle()

    def stop(self) -> None:
        self._running = False
        self.blackout()

    def run_forever(self) -> None:
        self.start()
        try:
            while self._running:
                try:
                    kind, payload = self.events.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.handle(kind, payload)
        finally:
            self.stop()

    def handle(self, kind: str, payload) -> None:
        if kind == "midi":
            self._handle_midi(payload)
        elif kind == "comfy":
            self._handle_comfy(payload)

    # ------------------------------------------------------------------ MIDI
    def _handle_midi(self, message) -> None:
        if message.type == "control_change":
            name = apc40.cc_name(message.control, message.channel)
            if name and name in self.skin.knobs:
                knob = self.skin.knobs[name]
                self.knob_values[knob.target] = knob.value_for(message.value)
                log.info("%s -> %s = %s", name, knob.target, self.knob_values[knob.target])
            return
        if message.type != "note_on" or message.velocity == 0:
            return
        pad = self.layout.pad_from_note(message.note, message.channel)
        if pad is not None:
            self.press_pad(pad)
            return
        scene = self.layout.scene_from_note(message.note, message.channel)
        if scene is not None:
            self.press_button(f"scene_{scene + 1}")
            return
        button = self.layout.button_from_note(message.note, message.channel)
        if button:
            self.press_button(button)

    def press_pad(self, pad_key: tuple) -> None:
        pad = self.skin.pads.get(pad_key)
        if pad is None:
            log.debug("pad %s is unmapped", pad_key)
            return
        if not self.seed_locked:
            self.seed = random.randrange(0, 2**32)
        source = self.last_output if (self.chain and self.last_output) else self.source_image
        prompt = build_prompt(self.skin, pad, self.knob_values, self.seed, source)
        try:
            prompt_id = self.client.queue(prompt)
        except Exception as error:
            log.error("pad %s (%s) refused: %s", pad_key, pad.label, error)
            self.light_pad(pad_key, "red")
            return
        self.in_flight[prompt_id] = pad_key
        self.last_pad = pad_key
        self.light_pad(pad_key, "yellow", blink=True)
        log.info("pad %s '%s' queued as %s (seed %d, from %s)",
                 pad_key, pad.label, prompt_id, self.seed, source or "scratch")

    def press_button(self, name: str) -> None:
        action = self.skin.buttons.get(name)
        if not action:
            return
        log.info("%s -> %s", name, action)
        if action == "repeat" and self.last_pad is not None:
            self.press_pad(self.last_pad)
        elif action == "reset_source":
            self.last_output = None
        elif action == "toggle_chain":
            self.chain = not self.chain
            log.info("chain is %s", "on" if self.chain else "off")
        elif action == "new_seed":
            self.seed = random.randrange(0, 2**32)
            self.seed_locked = True
        elif action == "lock_seed":
            self.seed_locked = not self.seed_locked
            log.info("seed %d is %s", self.seed, "locked" if self.seed_locked else "free")
        elif action == "interrupt":
            try:
                self.client.interrupt()
            except Exception as error:
                log.error("interrupt failed: %s", error)

    # --------------------------------------------------------------- ComfyUI
    def _handle_comfy(self, event: dict) -> None:
        kind = event.get("type")
        data = event.get("data") or {}
        prompt_id = data.get("prompt_id")
        if prompt_id not in self.in_flight:
            return
        pad_key = self.in_flight[prompt_id]
        if kind == "executed":
            name = output_image_name(event)
            if name:
                self.last_output = name
                log.info("pad %s finished -> %s", pad_key, name)
        elif kind == "execution_success":
            self.in_flight.pop(prompt_id, None)
            self.light_pad(pad_key, "green")
        elif kind in ("execution_error", "execution_interrupted"):
            self.in_flight.pop(prompt_id, None)
            self.light_pad(pad_key, "red")
            if kind == "execution_error":
                log.error("pad %s failed: %s", pad_key, data.get("exception_message", "")[:300])

    # ------------------------------------------------------------------ LEDs
    def _send_led(self, note: int, velocity: int, channel: int) -> None:
        if self.midi_out is None:
            return
        import mido
        self.midi_out.send(mido.Message("note_on", note=note, velocity=velocity, channel=channel))

    def light_pad(self, pad_key: tuple, colour: str, blink: bool = False) -> None:
        col, row = pad_key
        self._send_led(*apc40.led_message(self.layout, col, row, colour, blink))

    def light_idle(self) -> None:
        """Mapped pads show their skin colour; everything else goes dark."""
        for col in range(apc40.PAD_COLS):
            for row in range(apc40.PAD_ROWS):
                pad = self.skin.pads.get((col, row))
                self.light_pad((col, row), pad.colour if pad else "off")

    def blackout(self) -> None:
        for col in range(apc40.PAD_COLS):
            for row in range(apc40.PAD_ROWS):
                self.light_pad((col, row), "off")
        time.sleep(0.05)
