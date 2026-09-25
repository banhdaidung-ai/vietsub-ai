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

# Vá lỗi PackageNotFoundError cho curl_cffi khi đóng gói PyInstaller trên Windows
try:
    import importlib.metadata as _meta
    _orig_meta = _meta.metadata
    _orig_ver = _meta.version

    def _safe_metadata(name: str):
        try:
            return _orig_meta(name)
        except _meta.PackageNotFoundError:
            if name and name.lower().replace("-", "_") == "curl_cffi":
                return {"Summary": "curl_cffi", "Version": "0.16.3", "Name": "curl_cffi"}
            raise

    def _safe_version(name: str):
        try:
            return _orig_ver(name)
        except _meta.PackageNotFoundError:
            if name and name.lower().replace("-", "_") == "curl_cffi":
                return "0.16.3"
            raise

    _meta.metadata = _safe_metadata
    _meta.version = _safe_version
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

# Cấu hình đường dẫn trình duyệt cho Playwright (đặc biệt quan trọng khi đóng gói PyInstaller)
# Tránh bị Playwright ép PLAYWRIGHT_BROWSERS_PATH=0 gây lỗi không tìm thấy Chromium trong app bundle
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    if sys.platform == "darwin":
        _pw_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    elif sys.platform == "win32":
        _local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        _pw_cache = Path(_local) / "ms-playwright"
    else:
        _pw_cache = Path.home() / ".cache" / "ms-playwright"
    try:
        _pw_cache.mkdir(parents=True, exist_ok=True)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_pw_cache)
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
    if len(sys.argv) > 1 and sys.argv[1] == "--test-douyin":
        import traceback
        test_url = sys.argv[2] if len(sys.argv) > 2 else "https://v.douyin.com/iy0w9aEkDFM/"
        print(f"Testing Douyin download in environment for: {test_url}")
        try:
            from core.downloader import VideoDownloader
            dl = VideoDownloader(progress_callback=lambda p, s: print(f"[{p*100:.1f}%] {s}"))
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                res = dl.download(test_url, td)
                print("SUCCESSFULLY DOWNLOADED TO:", res)
        except Exception as e:
            print("ERROR CAUGHT:")
            traceback.print_exc()
        sys.exit(0)

    app = AppWindow()
    app.mainloop()


