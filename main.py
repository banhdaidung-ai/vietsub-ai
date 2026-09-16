"""
main.py — Điểm bắt đầu (Entry point) của ứng dụng Vietsub AI
"""

import os
import sys
from pathlib import Path

# Kiểm tra nếu đang chạy bằng Python cũ của macOS (Tk 8.5 gây lỗi màn hình trắng trong CustomTkinter)
# Tự động chuyển hướng sang môi trường Python hiện đại trong .venv (Tk 9.0)
if not getattr(sys, "frozen", False):
    _venv_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if _venv_python.exists() and sys.executable != str(_venv_python):
        try:
            import tkinter
            if getattr(tkinter, "TkVersion", 0) < 8.6:
                os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)
        except Exception:
            pass

from gui.app_window import AppWindow

if __name__ == "__main__":
    app = AppWindow()
    app.mainloop()

