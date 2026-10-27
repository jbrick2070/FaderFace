"""The repo root doubles as a ComfyUI node pack (it has an __init__.py), and
its folder name has a hyphen, so pytest cannot import it as a package. Put
the root on sys.path so ``import faderface`` works from anywhere."""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
