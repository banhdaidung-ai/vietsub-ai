"""
core/audio_separator.py — Tách giọng hát (Vocal / Acapella) và nhạc nền (Beat / Karaoke)
sử dụng mô hình AI Demucs v4 (Meta AI Research).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path


def _ensure_ffmpeg_ffprobe_in_path():
    """Đảm bảo thư mục chứa ffmpeg và ffprobe được đưa vào os.environ['PATH'] để Demucs gọi thành công."""
    paths_to_add = []

    ffmpeg_p = get_ffmpeg_path()
    if ffmpeg_p and os.path.isfile(ffmpeg_p):
        paths_to_add.append(str(Path(ffmpeg_p).parent))

    ffprobe_p = get_ffprobe_path()
    if ffprobe_p and os.path.isfile(ffprobe_p):
        paths_to_add.append(str(Path(ffprobe_p).parent))

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        paths_to_add.extend([
            str(exe_dir),
            str(exe_dir.parent / "MacOS"),
            str(exe_dir.parent / "Frameworks"),
            str(exe_dir.parent / "Resources"),
            str(exe_dir / "_internal"),
            str(exe_dir / "bin"),
        ])
    else:
        project_root = Path(__file__).resolve().parent.parent
        paths_to_add.extend([
            str(project_root / "bin"),
            str(project_root),
        ])

    candidate_system_dirs = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local/bin"),
        str(Path.home() / ".gemini/antigravity-ide/bin"),
        "/usr/bin",
    ]
    paths_to_add.extend(candidate_system_dirs)

    curr_path = os.environ.get("PATH", "")
    existing_parts = curr_path.split(os.pathsep)
    new_parts = []
    for p in paths_to_add:
        if p and os.path.isdir(p) and p not in existing_parts and p not in new_parts:
            new_parts.append(p)
    if new_parts:
        os.environ["PATH"] = os.pathsep.join(new_parts) + os.pathsep + curr_path


def check_demucs_installed() -> Tuple[bool, str]:
    """Kiểm tra xem thư viện demucs và torch đã sẵn sàng chưa."""
    _ensure_ffmpeg_ffprobe_in_path()
    try:
        import torch  # noqa: F401
        import demucs  # noqa: F401
        from demucs.api import Separator  # noqa: F401
        return True, "Demucs AI sẵn sàng."
    except Exception as e:
        return False, f"Chưa cài đặt thư viện Demucs AI: {e}"


def get_optimal_device() -> str:
    """Xác định thiết bị phần cứng tối ưu (Apple Silicon MPS / CUDA GPU / CPU)."""
    try:
        import torch
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _clean_stem_name(filename: str) -> str:
    """Lấy tên file gốc sạch sẽ, bỏ đuôi mở rộng."""
    stem = Path(filename).stem
    return stem


def separate_audio_stems(
    input_path: str,
    output_dir: str,
    mode: str = "both",               # "both" (cả 2), "instrumental" (nhạc beat), "vocals" (lời hát)
    audio_format: str = "mp3",         # "mp3" hoặc "wav"
    bitrate: str = "320k",
    device: Optional[str] = None,      # "mps", "cuda", "cpu" hoặc None (tự nhận diện)
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, str]:
    """
    Tách nguồn âm thanh bằng Demucs (2 stems: vocals + no_vocals / instrumental).
    Sử dụng trực tiếp Python API demucs.api.Separator & save_audio chuẩn mực.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {input_path}")

    _ensure_ffmpeg_ffprobe_in_path()

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base_stem = _clean_stem_name(input_path)
    fmt = audio_format.lower().strip(".")
    if fmt not in ("mp3", "wav"):
        fmt = "mp3"

    bitrate_int = int(re.sub(r"[^\d]", "", bitrate) or "320")

    if device is None:
        device = get_optimal_device()

    if progress_callback:
        dev_label = "Apple GPU (MPS)" if device == "mps" else ("Nvidia GPU (CUDA)" if device == "cuda" else "CPU")
        progress_callback(0.05, f"Chuẩn bị tách âm thanh (Thiết bị: {dev_label})...")

    temp_work_dir = tempfile.mkdtemp(prefix="vietsub_demucs_")

    try:
        audio_input_path = input_path
        video_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v"}
        is_video = Path(input_path).suffix.lower() in video_exts

        if is_video:
            if progress_callback:
                progress_callback(0.10, "Trích xuất luồng âm thanh gốc từ video...")
            ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
            temp_wav = os.path.join(temp_work_dir, "source_audio.wav")
            cmd_extract = [
                ffmpeg_bin, "-y", "-i", input_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                temp_wav
            ]
            res = subprocess.run(cmd_extract, capture_output=True, text=True, errors="replace")
            if res.returncode == 0 and os.path.exists(temp_wav):
                audio_input_path = temp_wav

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Người dùng đã hủy tác vụ.")

        if progress_callback:
            progress_callback(0.20, "Đang nạp mô hình AI Demucs v4...")

        from demucs.api import Separator, save_audio

        def _demucs_cb(info: dict):
            if cancel_event and cancel_event.is_set():
                raise KeyboardInterrupt("Người dùng đã hủy tác vụ.")
            if progress_callback and "segment_offset" in info and "audio_length" in info:
                total = info["audio_length"]
                if total > 0:
                    cur = info["segment_offset"]
                    frac = min(1.0, max(0.0, cur / float(total)))
                    pct = 0.25 + frac * 0.65
                    val_pct = int(frac * 100)
                    progress_callback(pct, f"Đang tách âm thanh bằng AI Demucs: {val_pct}%...")

        try:
            separator = Separator(
                model="htdemucs",
                device=device,
                callback=_demucs_cb,
            )
            origin, separated = separator.separate_audio_file(audio_input_path)
        except KeyboardInterrupt:
            raise RuntimeError("Người dùng đã hủy tác vụ tách âm thanh.")
        except Exception as e:
            if device == "mps":
                if progress_callback:
                    progress_callback(0.25, "MPS không hỗ trợ toán tử này, đang chuyển sang CPU...")
                return separate_audio_stems(
                    input_path=input_path,
                    output_dir=output_dir,
                    mode=mode,
                    audio_format=audio_format,
                    bitrate=bitrate,
                    device="cpu",
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                )
            raise RuntimeError(f"Lỗi khi tách âm thanh bằng Demucs AI: {e}")

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Người dùng đã hủy tác vụ.")

        if progress_callback:
            progress_callback(0.92, "Đang lưu và hoàn tất các luồng âm thanh...")

        vocal_tensor = separated.get("vocals")
        if vocal_tensor is None:
            raise RuntimeError("Mô hình không tạo được luồng âm thanh vocals.")

        # Tạo luồng instrumental (nhạc beat): tổng các stem còn lại hoặc origin - vocal
        other_stems = [tensor for name, tensor in separated.items() if name != "vocals"]
        if other_stems:
            inst_tensor = sum(other_stems)
        else:
            inst_tensor = origin - vocal_tensor

        result_files: Dict[str, str] = {}

        def _get_unique_dest(base_label: str) -> str:
            dest = os.path.join(output_dir, f"{base_stem}_{base_label}.{fmt}")
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(output_dir, f"{base_stem}_{base_label} ({counter}).{fmt}")
                counter += 1
            return dest

        # Lưu Vocal
        if mode in ("both", "vocals"):
            target_vocal = _get_unique_dest("[Vocal_Loi]")
            if fmt == "mp3":
                save_audio(vocal_tensor, target_vocal, samplerate=separator.samplerate, bitrate=bitrate_int)
            else:
                save_audio(vocal_tensor, target_vocal, samplerate=separator.samplerate)
            result_files["vocals"] = target_vocal

        # Lưu Instrumental / Beat
        if mode in ("both", "instrumental"):
            target_inst = _get_unique_dest("[Beat_Karaoke]")
            if fmt == "mp3":
                save_audio(inst_tensor, target_inst, samplerate=separator.samplerate, bitrate=bitrate_int)
            else:
                save_audio(inst_tensor, target_inst, samplerate=separator.samplerate)
            result_files["instrumental"] = target_inst

        if not result_files:
            raise RuntimeError("Không có file âm thanh nào được tạo ra.")

        if progress_callback:
            progress_callback(1.0, "Tách giọng hát và nhạc beat thành công!")

        return result_files

    finally:
        try:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
        except Exception:
            pass
