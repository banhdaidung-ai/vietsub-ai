"""
utils/ffmpeg_check.py — Kiểm tra FFmpeg đã cài đặt chưa
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


def _resolve_binary(name: str) -> Optional[str]:
    # 0. Kiểm tra trong bundle PyInstaller hoặc bên cạnh file thực thi
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        bundle_candidates = [
            exe_dir / name,
            exe_dir / f"{name}.exe",
            exe_dir.parent / "Resources" / name,
            Path(getattr(sys, "_MEIPASS", "")) / name,
            Path(getattr(sys, "_MEIPASS", "")) / f"{name}.exe",
        ]
        for c in bundle_candidates:
            if c.is_file() and (os.name == "nt" or os.access(c, os.X_OK)):
                return str(c)

    # 1. Kiểm tra trong PATH hiện tại
    path = shutil.which(name)
    if path:
        return path

    # 2. Thử dùng static-ffmpeg nếu đã cài
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        path = shutil.which(name)
        if path:
            return path
    except Exception:
        pass

    # 3. Kiểm tra các thư mục cài đặt phổ biến (macOS / Linux / Windows)
    candidate_dirs = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local/bin"),
        str(Path.home() / ".gemini/antigravity-ide/bin"),
        "/usr/bin",
    ]
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate_dirs.extend([
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files (x86)\ffmpeg\bin",
            str(Path(local_app_data) / "Microsoft" / "WinGet" / "Links") if local_app_data else "",
        ])

    for d in candidate_dirs:
        if not d:
            continue
        bin_path = shutil.which(name, path=d) or os.path.join(d, name)
        if os.name == "nt" and not bin_path.lower().endswith(".exe"):
            bin_path_exe = f"{bin_path}.exe"
            if os.path.isfile(bin_path_exe):
                return bin_path_exe
        if os.path.isfile(bin_path) and (os.name == "nt" or os.access(bin_path, os.X_OK)):
            return bin_path

    return None


def get_ffmpeg_path() -> Optional[str]:
    """Trả về đường dẫn ffmpeg nếu tìm thấy, ngược lại None."""
    return _resolve_binary("ffmpeg")


def get_ffprobe_path() -> Optional[str]:
    """Trả về đường dẫn ffprobe nếu tìm thấy, ngược lại None."""
    return _resolve_binary("ffprobe")


def check_ffmpeg() -> Tuple[bool, str]:
    """
    Kiểm tra FFmpeg đã cài đặt và hoạt động.
    Returns: (thành_công, thông_báo)
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False, (
            "FFmpeg không tìm thấy trên hệ thống.\n\n"
            "Cài đặt:\n"
            "  Mac:     brew install ffmpeg (hoặc pip install static-ffmpeg)\n"
            "  Windows: winget install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg"
        )

    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            return True, f"FFmpeg OK: {version_line}"
        return False, "FFmpeg lỗi khi chạy."
    except Exception as e:
        return False, f"FFmpeg lỗi: {e}"


def get_video_duration(video_path: str) -> float:
    """Lấy thời lượng video (giây) dùng ffprobe."""
    ffprobe = get_ffprobe_path() or "ffprobe"
    result = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration:stream=duration",
            "-of", "json",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        try:
            data = json.loads(result.stdout)
            if "format" in data and "duration" in data["format"]:
                return float(data["format"]["duration"])
            for st in data.get("streams", []):
                if "duration" in st:
                    return float(st["duration"])
        except Exception:
            pass

    # Fallback trực tiếp nếu output format json không đủ trường
    result_simple = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    if result_simple.returncode == 0 and result_simple.stdout.strip():
        try:
            return float(result_simple.stdout.strip())
        except ValueError:
            pass

    raise RuntimeError("Không thể xác định thời lượng video qua ffprobe.")

