"""A skin is a JSON file that lays an APC40 over one API-format workflow.

It names the workflow file, says which node input holds the prompt, the seed
and the source image, and binds knobs to numeric inputs and pads to prompt
presets. Everything about the workflow is addressed as ``node.input``, where
``node`` is the API node id or the node's ``_meta.title``.

Load one with ``Skin.load(path)``; apply it to a workflow with the helpers
below. Nothing in here talks to MIDI or to ComfyUI.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional


class SkinError(ValueError):
    pass


@dataclass
class Knob:
    target: str
    low: float = 0.0
    high: float = 1.0
    kind: str = "float"              # float | int | choice
    choices: list = field(default_factory=list)
    label: str = ""

    def value_for(self, midi_value: int) -> Any:
        fraction = max(0, min(127, int(midi_value))) / 127.0
        if self.kind == "choice":
            if not self.choices:
                raise SkinError(f"knob {self.target} is a choice knob with no choices")
            index = min(len(self.choices) - 1, int(fraction * len(self.choices)))
            return self.choices[index]
        value = self.low + (self.high - self.low) * fraction
        return int(round(value)) if self.kind == "int" else round(value, 4)


@dataclass
class Pad:
    label: str
    prompt: str = ""
    colour: str = "blue"
    set: dict = field(default_factory=dict)   # extra target -> value overrides


@dataclass
class Skin:
    name: str
    workflow_path: str
    workflow: dict
    prompt_target: str
    seed_target: Optional[str] = None
    source_image_target: Optional[str] = None
    base_prompt: str = ""
    prompt_join: str = ", "
    knobs: dict = field(default_factory=dict)        # control name -> Knob
    pads: dict = field(default_factory=dict)         # (col, row) -> Pad
    buttons: dict = field(default_factory=dict)      # button name -> action
    reference_nodes: list = field(default_factory=list)
    without_reference: dict = field(default_factory=dict)  # target -> link

    @classmethod
    def load(cls, path: str) -> "Skin":
        with open(path, "r", encoding="utf-8") as handle:
            spec = json.load(handle)
        base_dir = os.path.dirname(os.path.abspath(path))
        workflow_path = spec.get("workflow")
        if not workflow_path:
            raise SkinError(f"{path}: skin has no 'workflow'")
        if not os.path.isabs(workflow_path):
            workflow_path = os.path.normpath(os.path.join(base_dir, workflow_path))
        with open(workflow_path, "r", encoding="utf-8") as handle:
            workflow = json.load(handle)
        if not isinstance(workflow, dict) or any("class_type" not in v for v in workflow.values()):
            raise SkinError(f"{workflow_path}: not an API-format workflow "
                            "(export it with Workflow > Export (API) in ComfyUI)")

        knobs = {}
        for control, raw in (spec.get("knobs") or {}).items():
            knobs[control] = Knob(
                target=raw["target"],
                low=float(raw.get("min", 0.0)),
                high=float(raw.get("max", 1.0)),
                kind=raw.get("kind", "float"),
                choices=list(raw.get("choices") or []),
                label=raw.get("label", ""),
            )
        pads = {}
        for key, raw in (spec.get("pads") or {}).items():
            col, row = (int(part) for part in key.split(","))
            pads[(col, row)] = Pad(
                label=raw.get("label", key),
                prompt=raw.get("prompt", ""),
                colour=raw.get("colour", raw.get("color", "blue")),
                set=dict(raw.get("set") or {}),
            )
        skin = cls(
            name=spec.get("name", os.path.basename(path)),
            workflow_path=workflow_path,
            workflow=workflow,
            prompt_target=spec["prompt_target"],
            seed_target=spec.get("seed_target"),
            source_image_target=spec.get("source_image_target"),
            base_prompt=spec.get("base_prompt", ""),
            prompt_join=spec.get("prompt_join", ", "),
            knobs=knobs,
            pads=pads,
            buttons=dict(spec.get("buttons") or {}),
            reference_nodes=list(spec.get("reference_nodes") or []),
            without_reference=dict(spec.get("without_reference") or {}),
        )
        skin.validate()
        return skin

    def validate(self) -> None:
        """Every target must resolve against the workflow, now, not at the
        first pad press."""
        targets = [self.prompt_target] + [k.target for k in self.knobs.values()]
        targets += [t for t in (self.seed_target, self.source_image_target) if t]
        targets += list(self.without_reference)
        for pad in self.pads.values():
            targets += list(pad.set)
        for target in targets:
            resolve_target(self.workflow, target)
        for node in self.reference_nodes:
            if node not in self.workflow:
                raise SkinError(f"reference node '{node}' is not in the workflow")


def resolve_target(workflow: dict, target: str):
    """Return (node_id, input_name) for ``node.input``. The node part matches
    an API id first, then a ``_meta.title``."""
    if "." not in target:
        raise SkinError(f"target '{target}' must look like node.input")
    node_part, input_name = target.rsplit(".", 1)
    node_id = node_part if node_part in workflow else None
    if node_id is None:
        for candidate, node in workflow.items():
            if (node.get("_meta") or {}).get("title") == node_part:
                node_id = candidate
                break
    if node_id is None:
        raise SkinError(f"target '{target}': no node with id or title '{node_part}'")
    if input_name not in workflow[node_id].get("inputs", {}):
        raise SkinError(f"target '{target}': node '{node_part}' has no input '{input_name}'")
    return node_id, input_name


def set_target(workflow: dict, target: str, value: Any) -> None:
    node_id, input_name = resolve_target(workflow, target)
    workflow[node_id]["inputs"][input_name] = value


def get_target(workflow: dict, target: str) -> Any:
    node_id, input_name = resolve_target(workflow, target)
    return workflow[node_id]["inputs"][input_name]


def strip_reference(skin: Skin, workflow: dict) -> None:
    """Remove the reference-image chain so the graph runs as plain
    text-to-image when there is no source image yet."""
    for target, link in skin.without_reference.items():
        set_target(workflow, target, list(link))
    for node in skin.reference_nodes:
        workflow.pop(node, None)


def build_prompt(skin: Skin, pad: Pad, knob_values: dict, seed: int,
                 source_image: Optional[str]) -> dict:
    """Return a fresh workflow with the pad, knobs, seed and source applied.
    ``knob_values`` maps target -> already-scaled value."""
    workflow = copy.deepcopy(skin.workflow)
    for target, value in knob_values.items():
        set_target(workflow, target, value)
    for target, value in pad.set.items():
        set_target(workflow, target, value)
    parts = [part for part in (skin.base_prompt, pad.prompt) if part]
    set_target(workflow, skin.prompt_target, skin.prompt_join.join(parts))
    if skin.seed_target:
        set_target(workflow, skin.seed_target, int(seed))
    if skin.source_image_target:
        if source_image:
            set_target(workflow, skin.source_image_target, source_image)
        else:
            strip_reference(skin, workflow)
    return workflow
