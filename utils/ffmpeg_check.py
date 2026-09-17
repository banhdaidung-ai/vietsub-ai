"""
utils/ffmpeg_check.py — Kiểm tra và tự động cấu hình FFmpeg cho hệ thống
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple

FFMPEG_DOWNLOAD_URLS = {
    "win32": "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/win32.zip",
    "darwin_arm64": "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/darwin_arm64.zip",
    "darwin": "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/darwin.zip",
    "linux": "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip",
    "linux_arm64": "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux_arm64.zip",
}


def get_platform_key() -> str:
    """Trả về định danh nền tảng OS để tải binary phù hợp."""
    if sys.platform == "win32":
        return "win32"
    elif sys.platform == "darwin":
        mach = platform.machine().lower()
        return "darwin_arm64" if mach in ("arm64", "aarch64") else "darwin"
    elif sys.platform.startswith("linux"):
        mach = platform.machine().lower()
        return "linux_arm64" if mach in ("arm64", "aarch64") else "linux"
    return "win32" if os.name == "nt" else "linux"


def get_app_bin_dir() -> Path:
    """Trả về thư mục lưu file nhị phân ffmpeg của ứng dụng."""
    # 1. Thử ghi ngay cạnh file thực thi hoặc thư mục gốc ứng dụng nếu có quyền ghi
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent.parent

    # Nếu không phải macOS .app bundle và thư mục ghi được, ưu tiên bin ngay trong thư mục app
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        try:
            local_bin = base_dir / "bin"
            local_bin.mkdir(parents=True, exist_ok=True)
            test_file = local_bin / ".write_test"
            test_file.touch()
            test_file.unlink()
            return local_bin
        except Exception:
            pass

    # 2. Thư mục dữ liệu người dùng (AppData / Application Support / .local)
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        app_dir = Path(local_app_data) / "VietsubAI" / "bin"
    elif sys.platform == "darwin":
        app_dir = Path.home() / "Library" / "Application Support" / "VietsubAI" / "bin"
    else:
        app_dir = Path.home() / ".local" / "share" / "VietsubAI" / "bin"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _resolve_binary(name: str) -> Optional[str]:
    """Tìm kiếm file thực thi (ffmpeg/ffprobe) trên toàn bộ hệ thống."""
    exts = [".exe", ""] if os.name == "nt" else [""]

    # 0. Kiểm tra trong bundle PyInstaller hoặc bên cạnh file thực thi
    check_dirs = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        check_dirs.extend([
            exe_dir,
            exe_dir / "_internal",
            exe_dir / "bin",
            exe_dir / "ffmpeg",
            exe_dir.parent / "Resources",
            exe_dir.parent / "MacOS",
            exe_dir.parent / "Frameworks",
        ])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            check_dirs.extend([
                Path(meipass),
                Path(meipass) / "_internal",
                Path(meipass) / "bin",
                Path(meipass) / "Frameworks",
            ])
    else:
        project_root = Path(__file__).resolve().parent.parent
        check_dirs.extend([
            project_root,
            project_root / "bin",
            project_root / "assets" / "bin",
        ])

    # Thư mục app bin của người dùng (nơi download_ffmpeg_binaries lưu trữ)
    try:
        check_dirs.append(get_app_bin_dir())
    except Exception:
        pass

    for directory in check_dirs:
        for ext in exts:
            target = directory / f"{name}{ext}"
            if target.is_file() and (os.name == "nt" or os.access(target, os.X_OK)):
                return str(target)

    # 1. Kiểm tra trong PATH hiện tại
    path = shutil.which(name)
    if path:
        return path

    # 2. Thử dùng static-ffmpeg an toàn (bảo vệ tránh crash khi console=False)
    try:
        import static_ffmpeg
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        try:
            static_ffmpeg.add_paths()
            path = shutil.which(name)
            if path:
                return path
        finally:
            if old_stdout is None:
                sys.stdout = None
            if old_stderr is None:
                sys.stderr = None
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
        app_data = os.environ.get("APPDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        program_data = os.environ.get("ProgramData", "")

        candidate_dirs.extend([
            r"C:\ffmpeg\bin",
            r"C:\ffmpeg",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files\ffmpeg",
            r"C:\Program Files (x86)\ffmpeg\bin",
            r"D:\ffmpeg\bin",
            r"D:\ffmpeg",
            str(Path(local_app_data) / "VietsubAI" / "bin") if local_app_data else "",
            str(Path(app_data) / "VietsubAI" / "bin") if app_data else "",
            str(Path(local_app_data) / "Microsoft" / "WinGet" / "Links") if local_app_data else "",
            str(Path(user_profile) / "scoop" / "shims") if user_profile else "",
            str(Path(user_profile) / "scoop" / "apps" / "ffmpeg" / "current" / "bin") if user_profile else "",
            str(Path(program_data) / "chocolatey" / "bin") if program_data else "",
        ])

        # WinGet Packages scan
        if local_app_data:
            winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.exists():
                try:
                    for p in winget_pkgs.glob("**/ffmpeg.exe"):
                        if p.is_file():
                            return str(p) if name == "ffmpeg" else str(p.parent / f"{name}.exe")
                except Exception:
                    pass

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


def download_ffmpeg_binaries(
    progress_callback: Optional[Callable[[float, int, int, str], None]] = None
) -> Tuple[bool, str]:
    """
    Tự động tải bộ giải mã FFmpeg tĩnh cho hệ điều hành hiện tại và giải nén vào thư mục ứng dụng.
    progress_callback(fraction, downloaded_bytes, total_bytes, message)
    Returns: (thành_công, thông_báo)
    """
    platform_key = get_platform_key()
    url = FFMPEG_DOWNLOAD_URLS.get(platform_key)
    if not url:
        return False, f"Hệ điều hành ({sys.platform}) chưa được hỗ trợ tải tự động."

    bin_dir = get_app_bin_dir()
    temp_zip = bin_dir / f"ffmpeg_download_{int(time.time())}.zip"

    def _report(pct: float, cur: int, total: int, msg: str):
        if progress_callback:
            try:
                progress_callback(pct, cur, total, msg)
            except Exception:
                pass

    try:
        _report(0.02, 0, 0, "Đang kết nối máy chủ tải FFmpeg...")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "VietsubAI/1.0 (Desktop; ModernVideoTranslation)"},
        )

        with urllib.request.urlopen(req, timeout=30) as response, open(temp_zip, "wb") as out_file:
            content_length = response.headers.get("Content-Length")
            total_bytes = int(content_length) if content_length and content_length.isdigit() else 75 * 1024 * 1024
            downloaded = 0
            chunk_size = 256 * 1024

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                pct = min(0.90, (downloaded / total_bytes) * 0.90) if total_bytes > 0 else 0.5
                mb_down = downloaded / (1024 * 1024)
                mb_total = total_bytes / (1024 * 1024)
                _report(
                    pct,
                    downloaded,
                    total_bytes,
                    f"Đang tải FFmpeg: {mb_down:.1f} MB / {mb_total:.1f} MB ({int((downloaded / total_bytes) * 100 if total_bytes > 0 else 0)}%)...",
                )

        _report(0.92, total_bytes, total_bytes, "Đang giải nén bộ giải mã FFmpeg...")
        with zipfile.ZipFile(temp_zip, "r") as zf:
            for member in zf.namelist():
                fname = os.path.basename(member)
                if fname.lower() in ("ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe"):
                    target_path = bin_dir / fname
                    with zf.open(member) as source, open(target_path, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                    if os.name != "nt":
                        try:
                            os.chmod(target_path, 0o755)
                        except Exception:
                            pass

        # Dọn dẹp file zip tạm
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass

        _report(0.98, total_bytes, total_bytes, "Đang kiểm tra khởi động FFmpeg...")
        ok, msg = check_ffmpeg()
        if ok:
            _report(1.0, total_bytes, total_bytes, "Cài đặt FFmpeg thành công!")
            return True, "Cài đặt FFmpeg thành công và sẵn sàng sử dụng!"
        return False, f"Tải hoàn tất nhưng kiểm tra FFmpeg thất bại: {msg}"

    except Exception as e:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass
        return False, f"Lỗi trong quá trình tải FFmpeg: {e}"


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
            "  Windows: Bấm '⚡ Tải FFmpeg' ở góc phải hoặc chạy 'winget install ffmpeg'\n"
            "  Mac:     brew install ffmpeg\n"
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
    """
    Lấy thời lượng video (giây).
    Ưu tiên đọc trực tiếp và siêu tốc qua FFmpeg -i (không cần ffprobe).
    Fallback sang ffprobe nếu có sẵn.
    """
    # 1. Đọc thời lượng trực tiếp qua FFmpeg -i (nhanh, chuẩn và không cần thêm file ffprobe)
    ffmpeg = get_ffmpeg_path() or "ffmpeg"
    try:
        res = subprocess.run(
            [ffmpeg, "-i", video_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
        if m:
            h, mn, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
            return h * 3600 + mn * 60 + s
    except Exception:
        pass

    # 2. Fallback sang ffprobe nếu trên máy có sẵn
    ffprobe = get_ffprobe_path()
    if ffprobe:
        try:
            result = subprocess.run(
                [
                    ffprobe, "-v", "error",
                    "-show_entries", "format=duration:stream=duration",
                    "-of", "json",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                if "format" in data and "duration" in data["format"]:
                    return float(data["format"]["duration"])
                for st in data.get("streams", []):
                    if "duration" in st:
                        return float(st["duration"])
        except Exception:
            pass

        try:
            result_simple = subprocess.run(
                [
                    ffprobe, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result_simple.returncode == 0 and result_simple.stdout.strip():
                return float(result_simple.stdout.strip())
        except Exception:
            pass

    raise RuntimeError("Không thể xác định thời lượng video qua FFmpeg.")

