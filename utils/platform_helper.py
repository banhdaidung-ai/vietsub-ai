"""
utils/platform_helper.py — Tiện ích đa nền tảng và ẩn hoàn toàn cửa sổ console trên Windows
"""

import subprocess
import sys
from typing import Any, Dict


def get_subprocess_no_window_kwargs() -> Dict[str, Any]:
    """
    Trả về các tham số subprocess ngăn hoàn toàn việc bật/nháy cửa sổ console (cmd.exe)
    trên Windows khi gọi các công cụ dòng lệnh (FFmpeg, FFprobe, yt-dlp, v.v.).

    Bao gồm cả hai tầng bảo vệ tối cao trên Windows:
    1. creationflags = subprocess.CREATE_NO_WINDOW (0x08000000): Không cấp phát console window.
    2. startupinfo = STARTF_USESHOWWINDOW + SW_HIDE: Ẩn tuyệt đối bất kỳ cửa sổ nào có nguy cơ xuất hiện.
    """
    if sys.platform != "win32":
        return {}

    kwargs: Dict[str, Any] = {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    kwargs["creationflags"] = creationflags

    if hasattr(subprocess, "STARTUPINFO"):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = startupinfo
        except Exception:
            pass

    return kwargs


def run_hidden_subprocess(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """
    Wrapper drop-in an toàn thay thế subprocess.run().
    Tự động chèn các cờ ẩn cửa sổ trên Windows nếu người gọi chưa chỉ định.
    """
    no_win = get_subprocess_no_window_kwargs()
    for k, v in no_win.items():
        kwargs.setdefault(k, v)
    return subprocess.run(cmd, **kwargs)
