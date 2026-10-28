"""ComfyUI entry point: registers the APC40 Knob and APC40 Pad nodes.

The rest of the package (the headless pad bridge) is a normal Python
package and does not need ComfyUI.
"""
try:
    from .faderface.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
except ImportError:
    # Loaded as a plain module (pytest, a tool importing the repo root)
    # rather than as ComfyUI's custom-node package.
    from faderface.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Browser side: web/faderface_queue.js queues one run per knob move.
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
