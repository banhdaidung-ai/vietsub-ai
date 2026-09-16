"""
core/ffmpeg_processor.py — Ghép video cuối cùng: burn subtitle + mix/replace audio
"""

import subprocess
from typing import Callable, Optional


from utils.ffmpeg_check import get_ffmpeg_path


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

        audio_mode:
            "mix"     — Giữ nhạc nền gốc (original_volume) + giọng Việt (tts_volume)
            "replace" — Xóa tiếng gốc, chỉ dùng giọng Việt
        """
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        self._report(0.1, "Đang encode video (có thể mất vài phút)...")

        # Escape đường dẫn SRT cho FFmpeg subtitles filter
        escaped_srt = srt_path.replace("\\", "/")
        if ":" in escaped_srt and not escaped_srt.startswith("/"):
            escaped_srt = escaped_srt.replace(":", "\\:")

        subtitle_style = (
            "Fontname=Arial,"
            f"FontSize={subtitle_font_size},"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"   # Text trắng sáng rõ nét
            "OutlineColour=&H00000000,"   # Viền đen sắc nét
            "BackColour=&H00000000,"      # Trong suốt không bị hộp đen thô
            "Outline=0.8,"                # Viền mảnh sắc nét cho chữ nhỏ
            "Shadow=0.4,"                 # Đổ bóng nhẹ
            f"MarginV={subtitle_margin_v},"  # Cách mép đáy (mặc định 8 để nằm dưới phụ đề gốc)
            "Alignment=2"                  # Căn giữa dưới
        )

        def run_render(mode: str) -> subprocess.CompletedProcess:
            if mode == "replace":
                cmd = [
                    ffmpeg, "-y",
                    "-i", video_path,
                    "-i", tts_audio_path,
                    "-vf", f"subtitles='{escaped_srt}':force_style='{subtitle_style}'",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264",
                    "-crf", "23",
                    "-preset", "medium",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    output_path,
                ]
            else:
                filter_complex = (
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
                    "-i", video_path,
                    "-i", tts_audio_path,
                    "-filter_complex", filter_complex,
                    "-vf", f"subtitles='{escaped_srt}':force_style='{subtitle_style}'",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "libx264",
                    "-crf", "23",
                    "-preset", "medium",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    output_path,
                ]
        # Chế độ chỉ gắn phụ đề, giữ nguyên âm thanh gốc
        if sub_only or not tts_audio_path:
            self._report(0.2, "Đang gắn phụ đề vào video (giữ nguyên 100% âm thanh gốc)...")
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
                "-vf", f"subtitles='{escaped_srt}':force_style='{subtitle_style}'",
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
                "-c:a", "copy",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            # Nếu -c:a copy lỗi (ví dụ định dạng âm thanh gốc không tương thích mp4), fallback sang re-encode aac
            if result.returncode != 0:
                self._report(0.4, "Đang re-encode âm thanh chuẩn AAC...")
                cmd_fallback = [
                    ffmpeg, "-y",
                    "-i", video_path,
                    "-vf", f"subtitles='{escaped_srt}':force_style='{subtitle_style}'",
                    "-c:v", "libx264",
                    "-crf", "23",
                    "-preset", "medium",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    output_path,
                ]
                result = subprocess.run(cmd_fallback, capture_output=True, text=True)

            if result.returncode != 0:
                stderr_tail = result.stderr[-1200:] if result.stderr else "Không có thông tin lỗi"
                raise RuntimeError(f"FFmpeg lỗi khi gắn phụ đề vào video:\n{stderr_tail}")

            self._report(1.0, "Gắn phụ đề hoàn tất!")
            return

        result = run_render(audio_mode)

        # Nếu mix thất bại do video gốc không có luồng audio (matches no streams) -> fallback sang replace
        if result.returncode != 0 and audio_mode == "mix" and ("matches no streams" in result.stderr or "Stream specifier" in result.stderr):
            self._report(0.3, "Video gốc không có âm thanh, tự động chuyển sang chế độ lồng tiếng hoàn toàn...")
            result = run_render("replace")

        if result.returncode != 0:
            stderr_tail = result.stderr[-1200:] if result.stderr else "Không có thông tin lỗi"
            raise RuntimeError(f"FFmpeg lỗi khi render video:\n{stderr_tail}")

        self._report(1.0, "Ghép video hoàn tất!")

