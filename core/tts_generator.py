"""
core/tts_generator.py — Tạo giọng đọc tiếng Việt từ SRT dùng edge-tts
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional

import edge_tts

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path
from utils.srt_parser import SRTSegment


class TTSGenerator:
    def __init__(
        self,
        voice: str = "vi-VN-HoaiMyNeural",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ):
        self.voice = voice
        self.progress_callback = progress_callback
        self.is_cancelled = is_cancelled

    def _report(self, pct: float, message: str):
        if self.progress_callback:
            self.progress_callback(pct, message)

    def generate_track(
        self,
        segments: List[SRTSegment],
        total_duration_sec: float,
        output_path: str,
    ):
        """
        Tạo một audio track tiếng Việt hoàn chỉnh, ghép từ các đoạn TTS
        với timing khớp chính xác theo timestamp SRT.
        """
        asyncio.run(
            self._generate_track_async(segments, total_duration_sec, output_path)
        )

    async def _generate_track_async(
        self,
        segments: List[SRTSegment],
        total_duration_sec: float,
        output_path: str,
    ):
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        tmp_dir = tempfile.mkdtemp(prefix="vietsub_tts_")
        try:
            seg_paths: List[tuple] = []  # (segment, audio_path)

            for i, seg in enumerate(segments):
                if self.is_cancelled and self.is_cancelled():
                    raise InterruptedError("Đã hủy bởi người dùng.")

                self._report(
                    i / len(segments),
                    f"Tạo giọng đọc đoạn {i + 1}/{len(segments)}...",
                )

                clean_text = " ".join(seg.text.split()).strip()
                # Loại bỏ ký tự nốt nhạc nếu có để tránh lỗi TTS
                tts_text = clean_text.replace("♪", "").replace("♫", "").replace("♩", "").strip()
                if not tts_text:
                    continue

                seg_path = os.path.join(tmp_dir, f"seg_{i:04d}.mp3")

                # Tạo TTS với edge-tts, hỗ trợ retry tự động
                success = False
                for attempt in range(3):
                    if self.is_cancelled and self.is_cancelled():
                        raise InterruptedError("Đã hủy bởi người dùng.")
                    try:
                        communicate = edge_tts.Communicate(
                            text=tts_text,
                            voice=self.voice,
                            rate="+0%",
                        )
                        await communicate.save(seg_path)
                        if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                            success = True
                            break
                    except Exception:
                        if attempt < 2:
                            await asyncio.sleep(1.0)

                if not success:
                    continue  # Bỏ qua đoạn lỗi để không ngắt toàn bộ tiến trình

                # Điều chỉnh tốc độ nếu TTS dài hơn thời gian phụ đề
                seg_dur_ms = seg.end_ms - seg.start_ms
                if seg_dur_ms > 200:  # Chỉ điều chỉnh nếu segment đủ dài
                    tts_dur_ms = self._get_audio_duration_ms(seg_path)
                    if tts_dur_ms > 0 and tts_dur_ms > seg_dur_ms * 1.15:
                        speed = min(tts_dur_ms / seg_dur_ms, 2.0)
                        adjusted_path = seg_path.replace(".mp3", "_adj.mp3")
                        subprocess.run(
                            [
                                ffmpeg, "-y", "-i", seg_path,
                                "-filter:a", f"atempo={speed:.3f}",
                                adjusted_path,
                            ],
                            capture_output=True,
                            check=False,
                        )
                        if (
                            os.path.exists(adjusted_path)
                            and os.path.getsize(adjusted_path) > 0
                        ):
                            seg_path = adjusted_path

                seg_paths.append((seg, seg_path))

            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Đã hủy bởi người dùng.")

            if not seg_paths:
                raise ValueError(
                    "Không tạo được giọng đọc. "
                    "Kiểm tra kết nối internet và thử lại."
                )

            self._report(0.9, "Đang ghép các đoạn âm thanh...")
            await self._combine_segments(seg_paths, total_duration_sec, output_path, tmp_dir)

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _get_audio_duration_ms(self, audio_path: str) -> int:
        """Lấy thời lượng audio (ms) dùng ffprobe."""
        ffprobe = get_ffprobe_path() or "ffprobe"
        try:
            result = subprocess.run(
                [
                    ffprobe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    audio_path,
                ],
                capture_output=True,
                text=True,
            )
            data = json.loads(result.stdout)
            return int(float(data["format"]["duration"]) * 1000)
        except Exception:
            return 0

    async def _combine_segments(
        self,
        seg_paths: List[tuple],
        total_duration_sec: float,
        output_path: str,
        tmp_dir: str,
    ):
        """
        Ghép các đoạn TTS thành một audio track dùng FFmpeg adelay filter.
        Hỗ trợ chia lô (batching) nếu có nhiều đoạn để tránh lỗi command line length.
        """
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        batch_size = 30

        if len(seg_paths) <= batch_size:
            self._run_amix_combine(ffmpeg, seg_paths, total_duration_sec, output_path)
            return

        # Xử lý theo từng batch nếu số lượng segment lớn
        batch_files = []
        for batch_idx in range(0, len(seg_paths), batch_size):
            chunk = seg_paths[batch_idx:batch_idx + batch_size]
            batch_out = os.path.join(tmp_dir, f"batch_{batch_idx // batch_size:03d}.mp3")
            self._run_amix_combine(ffmpeg, chunk, total_duration_sec, batch_out)
            batch_files.append(batch_out)

        # Trộn các file batch lại với nhau
        inputs = []
        for bf in batch_files:
            inputs.extend(["-i", bf])

        filter_complex = f"amix=inputs={len(batch_files)}:normalize=0[out]"
        cmd = (
            [ffmpeg, "-y"]
            + inputs
            + [
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-t", str(total_duration_sec),
                "-c:a", "libmp3lame",
                "-q:a", "2",
                output_path,
            ]
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg lỗi khi merge audio batches:\n{result.stderr[-800:]}")

    def _run_amix_combine(
        self,
        ffmpeg: str,
        seg_paths: List[tuple],
        total_duration_sec: float,
        output_path: str,
    ):
        inputs: List[str] = []
        filter_parts: List[str] = []

        for i, (seg, path) in enumerate(seg_paths):
            delay_ms = max(0, seg.start_ms)
            inputs.extend(["-i", path])
            filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")

        all_labels = "".join(f"[a{i}]" for i in range(len(seg_paths)))
        filter_parts.append(
            f"{all_labels}amix=inputs={len(seg_paths)}:normalize=0[out]"
        )

        cmd = (
            [ffmpeg, "-y"]
            + inputs
            + [
                "-filter_complex", ";".join(filter_parts),
                "-map", "[out]",
                "-t", str(total_duration_sec),
                "-c:a", "libmp3lame",
                "-q:a", "2",
                output_path,
            ]
        )

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg lỗi khi ghép audio:\n{result.stderr[-800:]}"
            )

