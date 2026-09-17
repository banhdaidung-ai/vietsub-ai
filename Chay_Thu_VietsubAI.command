#!/usr/bin/env bash
cd "$(dirname "$0")"

# Chạy ứng dụng bằng Python trong môi trường ảo (.venv)
if [ -f ".venv/bin/python" ]; then
    .venv/bin/python main.py
elif which python3 >/dev/null 2>&1; then
    python3 main.py
else
    python main.py
fi
