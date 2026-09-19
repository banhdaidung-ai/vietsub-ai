"""
main.py — Điểm bắt đầu (Entry point) của ứng dụng Vietsub AI
"""

import os
import sys
from pathlib import Path

# Bảo vệ sys.stdout và sys.stderr khi đóng gói dạng GUI không có console trên Windows
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

# Cấu hình chứng chỉ SSL (certifi) cho Windows và frozen bundles để tải mạng không bị lỗi CERTIFICATE_VERIFY_FAILED
try:
    import certifi
    ca_bundle = certifi.where()
    if ca_bundle and os.path.exists(ca_bundle):
        os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
        os.environ.setdefault("CURL_CA_BUNDLE", ca_bundle)
except Exception:
    pass

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

