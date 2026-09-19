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

from utils.ffmpeg_check import get_ffmpeg_path


def check_demucs_installed() -> Tuple[bool, str]:
    """Kiểm tra xem thư viện demucs và torch đã sẵn sàng chưa."""
    try:
        import torch  # noqa: F401
        import demucs  # noqa: F401
        return True, "Demucs AI sẵn sàng."
    except ImportError as e:
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
    
    Args:
        input_path: Đường dẫn tới file video hoặc audio.
        output_dir: Thư mục lưu kết quả.
        mode: "both" (tách cả 2), "instrumental" (chỉ lấy nhạc), "vocals" (chỉ lấy lời).
        audio_format: "mp3" hoặc "wav".
        bitrate: Bitrate cho mp3 (mặc định "320k").
        device: Thiết bị tính toán ("mps", "cuda", "cpu").
        progress_callback: Callback(tiến_độ_0_đến_1, nhãn_mô_tả).
        cancel_event: Event báo hiệu hủy tiến trình.
        
    Returns:
        Dict chứa đường dẫn các file đã tạo, ví dụ:
        {"vocals": "/path/..._loi.mp3", "instrumental": "/path/..._beat.mp3"}
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {input_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base_stem = _clean_stem_name(input_path)
    fmt = audio_format.lower().strip(".")
    if fmt not in ("mp3", "wav"):
        fmt = "mp3"

    if device is None:
        device = get_optimal_device()

    if progress_callback:
        dev_label = "Apple GPU (MPS)" if device == "mps" else ("Nvidia GPU (CUDA)" if device == "cuda" else "CPU")
        progress_callback(0.05, f"Chuẩn bị tách âm thanh (Thiết bị: {dev_label})...")

    # Tạo thư mục tạm để làm việc
    temp_work_dir = tempfile.mkdtemp(prefix="vietsub_demucs_")

    try:
        # Bước 1: Nếu là file video, bóc tách audio sang WAV tạm thời bằng FFmpeg để đảm bảo Demucs đọc hoàn hảo
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
            if res.returncode != 0 or not os.path.exists(temp_wav):
                # Fallback: Dùng file gốc trực tiếp nếu ffmpeg bóc tách bị lỗi
                audio_input_path = input_path
            else:
                audio_input_path = temp_wav

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Người dùng đã hủy tác vụ.")

        # Bước 2: Tách âm thanh bằng Demucs AI
        demucs_out_dir = os.path.join(temp_work_dir, "separated")
        os.makedirs(demucs_out_dir, exist_ok=True)

        demucs_opts = [
            "--two-stems=vocals",
            "-n", "htdemucs",
            "-o", demucs_out_dir,
            "-d", device,
        ]

        if fmt == "mp3":
            demucs_opts += ["--mp3", "--mp3-bitrate", bitrate.replace("k", "")]

        demucs_opts.append(audio_input_path)

        if progress_callback:
            progress_callback(0.20, "Đang nạp mô hình AI Demucs v4...")

        is_frozen = getattr(sys, "frozen", False)
        if is_frozen:
            import demucs.separate
            try:
                demucs.separate.main(demucs_opts)
            except SystemExit as se:
                if se.code not in (0, None):
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
                    raise RuntimeError(f"Demucs AI gặp lỗi (mã thoát: {se.code}).")
            if progress_callback:
                progress_callback(0.90, "Đã hoàn tất tách âm thanh bằng Demucs AI.")
        else:
            cmd_demucs = [sys.executable, "-m", "demucs"] + demucs_opts

            # Chạy Demucs với khả năng hủy và đọc tiến trình
            proc = subprocess.Popen(
                cmd_demucs,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            pct_regex = re.compile(r"(\d+)%")
            last_pct = 0.20

            while True:
                if cancel_event and cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise RuntimeError("Người dùng đã hủy tác vụ tách âm thanh.")

                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break

                if line:
                    line_str = line.strip()
                    # Bắt phần trăm tiến trình từ thanh tiến độ của Demucs / tqdm
                    match = pct_regex.search(line_str)
                    if match:
                        val = int(match.group(1))
                        # Map từ 0%..100% của Demucs sang 0.25..0.90 của toàn bộ tác vụ
                        mapped_pct = 0.25 + (val / 100.0) * 0.65
                        if mapped_pct > last_pct:
                            last_pct = mapped_pct
                            if progress_callback:
                                progress_callback(
                                    mapped_pct,
                                    f"Đang tách âm thanh bằng AI: {val}%...",
                                )

            ret_code = proc.wait()
            if ret_code != 0:
                # Nếu chạy bằng MPS bị lỗi (ví dụ một số hàm MPS chưa hỗ trợ), thử fallback về CPU
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
                raise RuntimeError(f"Demucs AI gặp lỗi (mã thoát: {ret_code}).")

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Người dùng đã hủy tác vụ.")

        if progress_callback:
            progress_callback(0.92, "Đang đóng gói và hoàn tất file xuất...")

        # Bước 3: Tìm file xuất từ Demucs và chuyển vào thư mục output của người dùng
        # Demucs lưu tại: demucs_out_dir/htdemucs/<tên_file_input>/
        # Các file gồm: vocals.mp3 (hoặc .wav) và no_vocals.mp3 (hoặc .wav)
        source_stem = Path(audio_input_path).stem
        stems_dir = os.path.join(demucs_out_dir, "htdemucs", source_stem)
        if not os.path.exists(stems_dir):
            # Tìm thư mục con bất kỳ trong htdemucs nếu stem khác biệt
            htdemucs_dir = os.path.join(demucs_out_dir, "htdemucs")
            if os.path.exists(htdemucs_dir):
                subdirs = [os.path.join(htdemucs_dir, d) for d in os.listdir(htdemucs_dir) if os.path.isdir(os.path.join(htdemucs_dir, d))]
                if subdirs:
                    stems_dir = subdirs[0]

        if not os.path.exists(stems_dir):
            raise RuntimeError("Không tìm thấy kết quả tách âm thanh từ Demucs.")

        found_vocals = None
        found_instrumental = None

        for f in os.listdir(stems_dir):
            f_lower = f.lower()
            full_f = os.path.join(stems_dir, f)
            if "vocals" in f_lower and "no_vocals" not in f_lower:
                found_vocals = full_f
            elif "no_vocals" in f_lower or "instrumental" in f_lower:
                found_instrumental = full_f

        result_files: Dict[str, str] = {}

        def _get_unique_dest(base_label: str) -> str:
            dest = os.path.join(output_dir, f"{base_stem}_{base_label}.{fmt}")
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(output_dir, f"{base_stem}_{base_label} ({counter}).{fmt}")
                counter += 1
            return dest

        # Xử lý theo mode
        if mode in ("both", "vocals") and found_vocals and os.path.exists(found_vocals):
            target_vocal = _get_unique_dest("[Vocal_Loi]")
            shutil.move(found_vocals, target_vocal)
            result_files["vocals"] = target_vocal

        if mode in ("both", "instrumental") and found_instrumental and os.path.exists(found_instrumental):
            target_inst = _get_unique_dest("[Beat_Karaoke]")
            shutil.move(found_instrumental, target_inst)
            result_files["instrumental"] = target_inst

        if not result_files:
            raise RuntimeError("Không có file âm thanh nào được tạo ra thành công.")

        if progress_callback:
            progress_callback(1.0, "Tách giọng hát và nhạc beat thành công!")

        return result_files

    finally:
        # Dọn dẹp thư mục tạm
        try:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
        except Exception:
            pass
