@echo off
rem Starts ComfyUI with the Documents custom_nodes folder (FaderFace, ControlFreak,
rem Web Viewer, AnimateDiff, IPAdapter, ...) on http://127.0.0.1:8000
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HF_HOME=C:\ComfyUI-Models\huggingface
C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py --port 8000 --listen 127.0.0.1 --base-directory C:\Users\jeffr\Documents\ComfyUI
pause
