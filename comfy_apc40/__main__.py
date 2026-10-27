"""Command line entry: ``python -m comfy_apc40 --skin mappings/<skin>.json``."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from . import apc40
from .bridge import Bridge
from .comfy_client import ComfyClient
from .skin import Skin, build_prompt

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SKIN = os.path.normpath(os.path.join(HERE, "..", "mappings", "flux3_klein_edit.json"))


def find_port(names, wanted: str):
    matches = [name for name in names if wanted.lower() in name.lower()]
    if not matches:
        raise SystemExit(f"no MIDI port matches '{wanted}'. Ports: {names}")
    return matches[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="comfy_apc40", description="Play ComfyUI from an Akai APC40.")
    parser.add_argument("--skin", default=DEFAULT_SKIN, help="skin JSON (default: the Flux 3 Klein edit pedalboard)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8188, help="ComfyUI port (8188 desktop, 8000 headless)")
    parser.add_argument("--midi-in", default="APC40", help="substring of the MIDI input port name")
    parser.add_argument("--midi-out", default=None, help="substring of the MIDI output port (default: same as --midi-in)")
    parser.add_argument("--layout", choices=sorted(apc40.LAYOUTS), default=None, help="force mk1 or mk2 (default: from the port name)")
    parser.add_argument("--source", default=None, help="image to edit; uploaded to ComfyUI's input folder at start")
    parser.add_argument("--no-chain", action="store_true", help="every edit starts from --source instead of the last output")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--dry-run", metavar="COL,ROW", help="print the prompt one pad would send, then exit; no MIDI, no server")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    if args.list_ports:
        import mido
        print("inputs: ", mido.get_input_names())
        print("outputs:", mido.get_output_names())
        return 0

    skin = Skin.load(args.skin)
    logging.info("skin '%s' over %s (%d pads, %d knobs)", skin.name, os.path.basename(skin.workflow_path),
                 len(skin.pads), len(skin.knobs))

    if args.dry_run:
        col, row = (int(part) for part in args.dry_run.split(","))
        pad = skin.pads.get((col, row))
        if pad is None:
            raise SystemExit(f"pad {col},{row} is not mapped in this skin")
        prompt = build_prompt(skin, pad, {}, seed=1, source_image=args.source)
        print(json.dumps(prompt, indent=2))
        return 0

    import mido

    in_name = find_port(mido.get_input_names(), args.midi_in)
    out_name = find_port(mido.get_output_names(), args.midi_out or args.midi_in)
    layout = apc40.LAYOUTS[args.layout] if args.layout else apc40.layout_for_port(in_name)
    logging.info("MIDI in '%s', out '%s', layout %s", in_name, out_name, layout.name)

    client = ComfyClient(args.host, args.port)
    if not client.alive():
        raise SystemExit(f"ComfyUI is not answering at {client.base}")

    source = client.upload_image(args.source) if args.source else None
    if source:
        logging.info("source image uploaded as %s", source)

    bridge = Bridge(skin, client, None, layout, source_image=source, chain=not args.no_chain)
    with mido.open_output(out_name) as midi_out, mido.open_input(in_name, callback=bridge.on_midi):
        bridge.midi_out = midi_out
        midi_out.send(mido.Message("sysex", data=layout.mode_sysex()))
        client.listen(bridge.on_comfy_event)
        logging.info("ready. pads launch edits; Ctrl+C to quit")
        try:
            bridge.run_forever()
        except KeyboardInterrupt:
            bridge.stop()
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
