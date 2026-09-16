"""
core/pipeline.py — Điều phối toàn bộ pipeline dịch video
Chạy trên background thread, gửi progress updates qua queue.Queue
"""

import os
import queue
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.downloader import VideoDownloader
from core.ffmpeg_processor import FFmpegProcessor
from core.gemini_processor import GeminiProcessor
from core.tts_generator import TTSGenerator
from utils.ffmpeg_check import get_video_duration
from utils.srt_parser import parse_srt


class Pipeline:
    """
    Orchestrator cho toàn bộ quá trình dịch video.
    
    Tất cả các bước nặng chạy trong background thread.
    Tiến độ được gửi qua task_queue với các message types:
      - {"type": "log", "message": str}
      - {"type": "progress", "value": float, "label": str}
      - {"type": "success", "video_path": str, "srt_path": str}
      - {"type": "error", "message": str}
      - {"type": "done"}
    """

    def __init__(self, task_queue: queue.Queue):
        self.task_queue = task_queue
        self._cancelled = False

    def cancel(self):
        """Yêu cầu dừng pipeline (sẽ dừng ở checkpoint tiếp theo)."""
        self._cancelled = True

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _put(self, msg_type: str, **kwargs):
        self.task_queue.put({"type": msg_type, **kwargs})

    def _log(self, message: str):
        self._put("log", message=message)

    def _progress(self, value: float, label: str):
        self._put("progress", value=min(value, 1.0), label=label)

    def _make_progress_cb(
        self, start: float, end: float
    ) -> Callable[[float, str], None]:
        """Tạo callback ánh xạ [0, 1] → [start, end] của progress bar."""
        def cb(pct: float, label: str):
            mapped = start + (end - start) * pct
            self._progress(mapped, label)
        return cb

    # ─── Main entry point ───────────────────────────────────────────────────

    def run(self, config: dict, input_source: str, is_url: bool):
        """Chạy toàn bộ pipeline. Gọi trong background thread."""
        tmp_dir = tempfile.mkdtemp(prefix="vietsub_")
        try:
            self._run_impl(config, input_source, is_url, tmp_dir)
        except (InterruptedError, KeyboardInterrupt):
            self._log("⚠️ Tiến trình đã được hủy.")
            self._progress(0.0, "Đã hủy")
        except Exception as exc:
            if self._cancelled:
                self._log("⚠️ Tiến trình đã được hủy.")
                self._progress(0.0, "Đã hủy")
            else:
                self._log(f"❌ Lỗi: {exc}")
                self._progress(0.0, "Thất bại")
                self._put("error", message=str(exc))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            self._put("done")

    # ─── Pipeline steps ─────────────────────────────────────────────────────

    def _run_impl(
        self, config: dict, input_source: str, is_url: bool, tmp_dir: str
    ):
        output_dir = config.get("output_dir", str(Path.home() / "Desktop"))
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(tmp_dir, exist_ok=True)

        # ── Bước 1: Lấy file video ──────────────────────────────────────────
        if is_url:
            self._log(f"📥 Đang tải video từ:\n   {input_source}")
            downloader = VideoDownloader(
                progress_callback=self._make_progress_cb(0.0, 0.1),
                is_cancelled=lambda: self._cancelled,
            )
            video_path = downloader.download(input_source, tmp_dir)
            self._log(f"✅ Tải xong: {Path(video_path).name}")
        else:
            video_path = input_source
            self._log(f"📂 File input: {Path(video_path).name}")

        self._progress(0.10, "Đã có video")
        if self._cancelled:
            self._log("⚠️ Đã hủy bởi người dùng.")
            return

        source_lang = config.get("source_language", "zh")
        enable_tts = config.get("enable_tts", True if source_lang != "vi" else False)

        # ── Bước 2: Gemini phiên âm / dịch → SRT ───────────────────────────
        if source_lang == "vi":
            self._log("🤖 Đang gửi video lên Gemini AI để phiên âm tạo phụ đề Tiếng Việt...")
        elif source_lang == "en":
            self._log("🤖 Đang gửi video lên Gemini AI để phiên âm và dịch Tiếng Anh → Việt...")
        else:
            self._log("🤖 Đang gửi video lên Gemini AI để phiên âm và dịch Tiếng Trung → Việt...")

        gemini = GeminiProcessor(
            api_key=config["gemini_api_key"],
            progress_callback=self._make_progress_cb(0.10, 0.50),
        )
        srt_content = gemini.process_video(video_path, source_lang=source_lang)

        # Lưu SRT tạm
        srt_tmp = os.path.join(tmp_dir, "subtitles.srt")
        with open(srt_tmp, "w", encoding="utf-8") as f:
            f.write(srt_content)

        segments = parse_srt(srt_content)
        if source_lang == "vi":
            self._log(f"✅ Phiên âm xong: {len(segments)} đoạn phụ đề tiếng Việt")
            self._progress(0.50, "Phiên âm xong")
        else:
            self._log(f"✅ Dịch xong: {len(segments)} đoạn phụ đề tiếng Việt")
            self._progress(0.50, "Dịch xong")

        # Lưu SRT ra output folder
        video_stem = Path(video_path).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "sub_vi" if source_lang == "vi" else "vietsub"
        output_srt = os.path.join(output_dir, f"{video_stem}_{suffix}_{timestamp}.srt")
        shutil.copy2(srt_tmp, output_srt)
        self._log(f"💾 Đã lưu phụ đề: {Path(output_srt).name}")

        # Lưu file text (.txt) lời thoại ra output folder
        output_txt = os.path.join(output_dir, f"{video_stem}_{suffix}_{timestamp}.txt")
        txt_lines = []
        for seg in segments:
            clean_line = " ".join(seg.text.split()).strip()
            if clean_line:
                txt_lines.append(clean_line)
        with open(output_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines) + "\n")
        self._log(f"📝 Đã lưu file text: {Path(output_txt).name}")

        if self._cancelled:
            self._log("⚠️ Đã hủy bởi người dùng.")
            return

        # ── Bước 3 & 4: TTS tạo giọng đọc tiếng Việt (nếu được bật) ────────
        tts_audio = None
        if enable_tts:
            try:
                total_duration = get_video_duration(video_path)
                self._log(f"⏱️ Thời lượng video: {total_duration:.1f}s")
            except Exception:
                # Fallback: dùng end_ms của segment cuối + 5s buffer
                total_duration = (segments[-1].end_ms / 1000 + 5) if segments else 3600.0

            self._log(f"🗣️ Đang tạo giọng đọc ({config.get('tts_voice', 'vi-VN-HoaiMyNeural')})...")
            tts_audio = os.path.join(tmp_dir, "tts_track.mp3")

            tts = TTSGenerator(
                voice=config.get("tts_voice", "vi-VN-HoaiMyNeural"),
                progress_callback=self._make_progress_cb(0.50, 0.75),
                is_cancelled=lambda: self._cancelled,
            )
            tts.generate_track(segments, total_duration, tts_audio)
            self._log("✅ Tạo giọng đọc xong")
            self._progress(0.75, "Tạo giọng xong")
        else:
            self._log("⏩ Bỏ qua lồng tiếng AI — Giữ nguyên 100% âm thanh gốc của video.")
            self._progress(0.75, "Bỏ qua TTS")

        if self._cancelled:
            self._log("⚠️ Đã hủy bởi người dùng.")
            return

        # ── Bước 5: FFmpeg ghép video cuối cùng ─────────────────────────────
        output_video = os.path.join(
            output_dir, f"{video_stem}_{suffix}_{timestamp}.mp4"
        )
        audio_mode = config.get("audio_mode", "mix")
        if not enable_tts:
            mode_label = "gắn phụ đề chữ, giữ âm thanh gốc"
        else:
            mode_label = "mix âm thanh" if audio_mode == "mix" else "thay hoàn toàn"
        self._log(f"🎬 Đang render video ({mode_label})...")

        ffmpeg = FFmpegProcessor(
            progress_callback=self._make_progress_cb(0.75, 1.0),
        )
        ffmpeg.process_video(
            video_path=video_path,
            srt_path=srt_tmp,
            tts_audio_path=tts_audio,
            output_path=output_video,
            audio_mode=audio_mode,
            original_volume=config.get("original_volume", 0.3),
            tts_volume=config.get("tts_volume", 1.0),
            sub_only=not enable_tts,
            subtitle_font_size=int(config.get("subtitle_font_size", 10)),
            subtitle_margin_v=int(config.get("subtitle_margin_v", 8)),
        )

        self._progress(1.0, "Hoàn tất!")
        self._log("─" * 45)
        self._log("🎉 HOÀN TẤT! File đầu ra:")
        self._log(f"   🎬 Video : {Path(output_video).name}")
        self._log(f"   📄 Phụ đề: {Path(output_srt).name}")
        self._log(f"   📝 Văn bản: {Path(output_txt).name}")
        self._log(f"   📁 Thư mục: {output_dir}")

        self._put("success", video_path=output_video, srt_path=output_srt, txt_path=output_txt)
