"""
core/ffmpeg_processor.py — Ghép video cuối cùng: burn subtitle + mix/replace audio
"""

import os
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Optional

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path


def check_has_audio(video_path: str) -> bool:
    """Kiểm tra video có luồng âm thanh không (hỗ trợ ffmpeg trực tiếp, không cần ffprobe)."""
    try:
        # 1. Thử qua ffprobe nếu có sẵn
        ffprobe = get_ffprobe_path()
        if ffprobe:
            res = subprocess.run(
                [
                    ffprobe, "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0:
                return "audio" in res.stdout.lower()

        # 2. Hoặc kiểm tra trực tiếp qua ffmpeg -i
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        res = subprocess.run(
            [ffmpeg, "-i", video_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return "Audio:" in res.stderr
    except Exception:
        return True


class FFmpegProcessor:
    def __init__(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ):
        self.progress_callback = progress_callback

    def _report(self, pct: float, message: str):
        if self.progress_callback:
            self.progress_callback(pct, message)

    def process_video(
        self,
        video_path: str,
        srt_path: str,
        tts_audio_path: Optional[str] = None,
        output_path: str = "",
        audio_mode: str = "mix",
        original_volume: float = 0.3,
        tts_volume: float = 1.0,
        sub_only: bool = False,
        subtitle_font_size: int = 10,
        subtitle_margin_v: int = 8,
    ):
        """
        Ghép video cuối cùng:
        - Burn phụ đề SRT tiếng Việt lên video
        - Nếu sub_only=True: giữ nguyên 100% âm thanh gốc, chỉ gắn phụ đề
        - Nếu sub_only=False: Mix âm thanh gốc + TTS, hoặc thay hoàn toàn bằng TTS
        """
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        self._report(0.1, "Đang encode video (có thể mất vài phút)...")

        abs_video_path = os.path.abspath(video_path)
        abs_output_path = os.path.abspath(output_path)
        abs_tts_path = os.path.abspath(tts_audio_path) if tts_audio_path else None
        out_dir = os.path.dirname(abs_output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Tạo file SRT tạm trong tempdir với tên ASCII thuần túy
        temp_dir = tempfile.gettempdir()
        temp_srt_name = f"sub_{int(time.time() * 1000)}.srt"
        temp_srt_path = os.path.join(temp_dir, temp_srt_name)
        shutil.copy2(srt_path, temp_srt_path)

        subtitle_style = (
            "Fontname=Arial,"
            f"FontSize={subtitle_font_size},"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"   # Text trắng sáng rõ nét
            "OutlineColour=&H00000000,"   # Viền đen sắc nét
            "BackColour=&H00000000,"      # Trong suốt không bị hộp đen thô
            "Outline=0.8,"                # Viền mảnh sắc nét cho chữ nhỏ
            "Shadow=0.4,"                 # Đổ bóng nhẹ
            f"MarginV={subtitle_margin_v},"  # Cách mép đáy
            "Alignment=2"                  # Căn giữa dưới
        )

        # Chạy với cwd=temp_dir để filename là tên file ngắn gọn,
        # triệt tiêu hoàn toàn lỗi ký tự ổ đĩa (C:, F:) và dấu 2 chấm trong filtergraph của FFmpeg trên Windows
        sub_filter = f"subtitles=filename='{temp_srt_name}':force_style='{subtitle_style}'"

        def _extract_error(stderr: str) -> str:
            if not stderr:
                return "Không có thông tin chi tiết."
            filtered = []
            for line in stderr.splitlines():
                line_s = line.strip()
                if not line_s:
                    continue
                if any(line_s.startswith(p) for p in [
                    "--enable-", "configuration:", "built with", "libav", "libsw", "libpostproc",
                    "Input #", "Stream #", "Output #", "Metadata:", "Duration:"
                ]):
                    continue
                filtered.append(line_s)
            return "\n".join(filtered[-8:]) if filtered else stderr[-400:]

        try:
            def run_render(mode: str) -> subprocess.CompletedProcess:
                if mode == "replace":
                    filter_complex = f"[0:v]{sub_filter}[vout]"
                    cmd = [
                        ffmpeg, "-y",
                        "-i", abs_video_path,
                        "-i", abs_tts_path,
                        "-filter_complex", filter_complex,
                        "-map", "[vout]",
                        "-map", "1:a:0",
                        "-c:v", "libx264",
                        "-crf", "23",
                        "-preset", "medium",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-shortest",
                        abs_output_path,
                    ]
                else:
                    filter_complex = (
                        f"[0:v]{sub_filter}[vout];"
                        f"[0:a]"
                        f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                        f"volume={original_volume}[orig];"
                        f"[1:a]"
                        f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                        f"volume={tts_volume}[tts];"
                        "[orig][tts]amix=inputs=2:duration=first:normalize=0[aout]"
                    )
                    cmd = [
                        ffmpeg, "-y",
                        "-i", abs_video_path,
                        "-i", abs_tts_path,
                        "-filter_complex", filter_complex,
                        "-map", "[vout]",
                        "-map", "[aout]",
                        "-c:v", "libx264",
                        "-crf", "23",
                        "-preset", "medium",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        abs_output_path,
                    ]
                return subprocess.run(
                    cmd,
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            # Chế độ chỉ gắn phụ đề, giữ nguyên âm thanh gốc
            if sub_only or not abs_tts_path:
                self._report(0.2, "Đang gắn phụ đề vào video (giữ nguyên 100% âm thanh gốc)...")
                cmd = [
                    ffmpeg, "-y",
                    "-i", abs_video_path,
                    "-vf", sub_filter,
                    "-c:v", "libx264",
                    "-crf", "23",
                    "-preset", "medium",
                    "-c:a", "copy",
                    abs_output_path,
                ]
                result = subprocess.run(
                    cmd,
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.returncode != 0:
                    self._report(0.4, "Đang re-encode âm thanh chuẩn AAC...")
                    cmd_fallback = [
                        ffmpeg, "-y",
                        "-i", abs_video_path,
                        "-vf", sub_filter,
                        "-c:v", "libx264",
                        "-crf", "23",
                        "-preset", "medium",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        abs_output_path,
                    ]
                    result = subprocess.run(
                        cmd_fallback,
                        cwd=temp_dir,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )

                if result.returncode != 0:
                    clean_err = _extract_error(result.stderr)
                    raise RuntimeError(f"FFmpeg lỗi khi gắn phụ đề vào video:\n{clean_err}")

                self._report(1.0, "Gắn phụ đề hoàn tất!")
                return

            # Kiểm tra trước xem video gốc có luồng audio không
            effective_mode = audio_mode
            if effective_mode == "mix" and not check_has_audio(abs_video_path):
                self._report(0.15, "Video gốc không có âm thanh, tự động chuyển sang chế độ lồng tiếng hoàn toàn...")
                effective_mode = "replace"

            result = run_render(effective_mode)

            # Nếu mix vẫn báo thiếu audio stream, fallback sang replace
            if result.returncode != 0 and effective_mode == "mix" and (
                "matches no streams" in result.stderr or "Stream specifier" in result.stderr
            ):
                self._report(0.3, "Không tìm thấy luồng âm thanh gốc, chuyển sang chế độ lồng tiếng...")
                result = run_render("replace")

            if result.returncode != 0:
                clean_err = _extract_error(result.stderr)
                raise RuntimeError(f"FFmpeg lỗi khi render video:\n{clean_err}")

            self._report(1.0, "Ghép video hoàn tất!")

        finally:
            if os.path.exists(temp_srt_path):
                try:
                    os.remove(temp_srt_path)
                except Exception:
                    pass


def extract_audio(
    video_path: str,
    output_dir: str,
    audio_format: str = "mp3",
    bitrate: str = "320k",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Trích xuất âm thanh từ file video sang file audio (MP3 320kbps / M4A / WAV).
    Cực nhanh (1-2s) vì không phải re-encode video.
    """
    from pathlib import Path

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy file video: {video_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base_name = Path(video_path).stem
    ext = audio_format.lower().strip(".")
    if ext not in ("mp3", "m4a", "wav"):
        ext = "mp3"

    out_path = str(Path(output_dir) / f"{base_name}.{ext}")

    # Đảm bảo không trùng tên nếu file đã tồn tại
    counter = 1
    while os.path.exists(out_path):
        out_path = str(Path(output_dir) / f"{base_name} ({counter}).{ext}")
        counter += 1

    ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"

    cmd = [ffmpeg_bin, "-y", "-i", video_path, "-vn"]

    if ext == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif ext == "m4a":
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif ext == "wav":
        cmd += ["-c:a", "pcm_s16le"]
    else:
        cmd += ["-c:a", "libmp3lame", "-b:a", "320k"]

    cmd.append(out_path)

    if progress_callback:
        progress_callback(0.3, "Đang bóc tách luồng âm thanh...")

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if res.returncode != 0:
        clean_err = _extract_error(res.stderr)
        raise RuntimeError(f"FFmpeg lỗi khi trích xuất âm thanh:\n{clean_err}")

    if progress_callback:
        progress_callback(1.0, "Trích xuất âm thanh thành công!")

    return out_path

