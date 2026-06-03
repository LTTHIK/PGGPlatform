@echo off
cd /d %~dp0
.\.venv\Scripts\python realtime_gui.py --model-dir .\paraformer_model

