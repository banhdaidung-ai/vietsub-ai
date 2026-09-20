"""
core/ffmpeg_processor.py — Ghép video cuối cùng: burn subtitle + mix/replace audio
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional

import re
import threading
from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path, get_video_duration
from utils.platform_helper import get_subprocess_no_window_kwargs, run_hidden_subprocess
from utils.subtitle_styles import build_ffmpeg_subtitle_style


def _run_ffmpeg_cancellable(
    cmd: list,
    cwd: Optional[str] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    total_duration_sec: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """
    Thực thi lệnh FFmpeg có khả năng hủy ngay lập tức và chống deadlock buffer trên Windows:
    - Đọc stream stderr liên tục bằng background thread để tránh đầy pipe buffer (64KB) làm treo FFmpeg.
    - Parse thời gian render `time=HH:MM:SS.ms` để cập nhật tiến trình % thực tế.
    """
    if is_cancelled and is_cancelled():
        raise InterruptedError("Tiến trình đã bị hủy bởi người dùng.")

    popen_kwargs = get_subprocess_no_window_kwargs()

    p = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **popen_kwargs,
    )

    stderr_lines = []
    last_report_time = 0.0

    def reader():
        nonlocal last_report_time
        try:
            for line in p.stderr:
                stderr_lines.append(line)
                if progress_callback and total_duration_sec and total_duration_sec > 0:
                    m = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if m:
                        now = time.time()
                        if now - last_report_time >= 0.4:
                            last_report_time = now
                            h, m_val, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                            cur_sec = h * 3600 + m_val * 60 + s
                            pct = min(cur_sec / total_duration_sec, 0.98)
                            progress_callback(
                                0.1 + pct * 0.88,
                                f"Đang render video: {pct * 100:.0f}% ({int(cur_sec)}s/{int(total_duration_sec)}s)..."
                            )
        except Exception:
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    while p.poll() is None:
        if is_cancelled and is_cancelled():
            try:
                p.kill()
            except Exception:
                pass
            t.join(timeout=1.0)
            raise InterruptedError("Tiến trình đã bị hủy bởi người dùng.")
        time.sleep(0.1)

    t.join(timeout=2.0)
    stderr_text = "".join(stderr_lines)
    return subprocess.CompletedProcess(args=cmd, returncode=p.returncode, stdout="", stderr=stderr_text)


def check_has_audio(video_path: str) -> bool:
    """Kiểm tra video có luồng âm thanh không (hỗ trợ ffmpeg trực tiếp, không cần ffprobe)."""
    try:
        # 1. Thử qua ffprobe nếu có sẵn
        ffprobe = get_ffprobe_path()
        if ffprobe:
            res = run_hidden_subprocess(
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
        res = run_hidden_subprocess(
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
        srt_path: str = "",
        tts_audio_path: Optional[str] = None,
        output_path: str = "",
        audio_mode: str = "mix",
        original_volume: float = 0.3,
        tts_volume: float = 1.0,
        sub_only: bool = False,
        subtitle_font_size: int = 10,
        subtitle_margin_v: int = 8,
        subtitles_path: str = "",
        subtitle_style_preset: str = "capcut_yellow",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ):
        srt_path = srt_path or subtitles_path
        """
        Ghép video cuối cùng:
        - Burn phụ đề SRT tiếng Việt lên video
        - Nếu sub_only=True: giữ nguyên 100% âm thanh gốc, chỉ gắn phụ đề
        - Nếu sub_only=False: Mix âm thanh gốc + TTS, hoặc thay hoàn toàn bằng TTS
        """
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        self._report(0.1, "Đang chuẩn bị render video...")

        abs_video_path = os.path.abspath(video_path)
        abs_output_path = os.path.abspath(output_path)
        abs_tts_path = os.path.abspath(tts_audio_path) if tts_audio_path else None
        out_dir = os.path.dirname(abs_output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Lấy thời lượng video để tính % tiến trình render thực tế
        total_duration = 0.0
        try:
            total_duration = get_video_duration(abs_video_path)
        except Exception:
            pass

        # Tạo file SRT tạm trong tempdir với tên ASCII thuần túy và chuẩn hóa nội dung SRT
        from utils.srt_parser import normalize_srt_content, parse_srt

        temp_dir = tempfile.gettempdir()
        temp_srt_name = f"sub_{int(time.time() * 1000)}.srt"
        temp_srt_path = os.path.join(temp_dir, temp_srt_name)

        try:
            with open(srt_path, "r", encoding="utf-8", errors="replace") as f_in:
                raw_srt = f_in.read()
            clean_srt = normalize_srt_content(raw_srt)
            with open(temp_srt_path, "w", encoding="utf-8") as f_out:
                f_out.write(clean_srt)
            has_subtitles = len(parse_srt(clean_srt)) > 0
        except Exception:
            shutil.copy2(srt_path, temp_srt_path)
            has_subtitles = True

        subtitle_style = build_ffmpeg_subtitle_style(
            preset_id=subtitle_style_preset,
            font_size=subtitle_font_size,
            margin_v=subtitle_margin_v,
            alignment=2,
        )

        # Chạy với cwd=temp_dir để filename là tên file ngắn gọn,
        # triệt tiêu hoàn toàn lỗi ký tự ổ đĩa (C:, F:) và dấu 2 chấm trong filtergraph của FFmpeg trên Windows
        sub_filter = f"subtitles=filename='{temp_srt_name}':force_style='{subtitle_style}'"

        try:
            def run_render(mode: str) -> subprocess.CompletedProcess:
                v_filter = f"[0:v]{sub_filter}[vout]" if has_subtitles else "[0:v]null[vout]"
                if mode == "replace":
                    filter_complex = v_filter
                    cmd = [
                        ffmpeg, "-y",
                        "-i", abs_video_path,
                        "-i", abs_tts_path,
                        "-filter_complex", filter_complex,
                        "-map", "[vout]",
                        "-map", "1:a:0",
                        "-c:v", "libx264",
                        "-crf", "23",
                        "-preset", "fast",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-shortest",
                        abs_output_path,
                    ]
                else:
                    filter_complex = (
                        f"{v_filter};"
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
                        "-preset", "fast",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        abs_output_path,
                    ]
                return _run_ffmpeg_cancellable(
                    cmd,
                    cwd=temp_dir,
                    is_cancelled=is_cancelled,
                    progress_callback=self._report,
                    total_duration_sec=total_duration,
                )

            # Chế độ chỉ gắn phụ đề, giữ nguyên âm thanh gốc
            if sub_only or not abs_tts_path:
                self._report(0.2, "Đang gắn phụ đề vào video (giữ nguyên 100% âm thanh gốc)...")
                cmd = [
                    ffmpeg, "-y",
                    "-i", abs_video_path,
                ]
                if has_subtitles:
                    cmd += ["-vf", sub_filter]
                cmd += [
                    "-c:v", "libx264",
                    "-crf", "23",
                    "-preset", "fast",
                    "-c:a", "copy",
                    abs_output_path,
                ]
                result = _run_ffmpeg_cancellable(
                    cmd,
                    cwd=temp_dir,
                    is_cancelled=is_cancelled,
                    progress_callback=self._report,
                    total_duration_sec=total_duration,
                )
                if result.returncode != 0:
                    self._report(0.4, "Đang re-encode âm thanh chuẩn AAC...")
                    cmd_fallback = [
                        ffmpeg, "-y",
                        "-i", abs_video_path,
                    ]
                    if has_subtitles:
                        cmd_fallback += ["-vf", sub_filter]
                    cmd_fallback += [
                        "-c:v", "libx264",
                        "-crf", "23",
                        "-preset", "fast",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        abs_output_path,
                    ]
                    result = _run_ffmpeg_cancellable(
                        cmd_fallback,
                        cwd=temp_dir,
                        is_cancelled=is_cancelled,
                        progress_callback=self._report,
                        total_duration_sec=total_duration,
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
    is_cancelled: Optional[Callable[[], bool]] = None,
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

    res = _run_ffmpeg_cancellable(
        cmd,
        cwd=output_dir,
        is_cancelled=is_cancelled,
    )

    if res.returncode != 0:
        clean_err = _extract_error(res.stderr)
        raise RuntimeError(f"FFmpeg lỗi khi trích xuất âm thanh:\n{clean_err}")

    if progress_callback:
        progress_callback(1.0, "Trích xuất âm thanh thành công!")

    return out_path

