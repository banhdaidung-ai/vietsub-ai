"""
core/pipeline.py — Điều phối toàn bộ pipeline dịch video
Chạy trên background thread, gửi progress updates qua queue.Queue
"""

import os
import queue
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.downloader import VideoDownloader
from core.ffmpeg_processor import FFmpegProcessor
from core.gemini_processor import GeminiProcessor
from core.tts_generator import TTSGenerator
from utils.config import get_output_dir
from utils.ffmpeg_check import get_video_duration
from utils.srt_parser import normalize_srt_content, parse_srt, segments_to_srt


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
        output_dir = get_output_dir(config)
        os.makedirs(tmp_dir, exist_ok=True)

        # ── Bước 1: Lấy file video ──────────────────────────────────────────
        if is_url:
            self._log(f"📥 Đang tải video từ:\n   {input_source}")
            downloader = VideoDownloader(
                progress_callback=self._make_progress_cb(0.0, 0.1),
                is_cancelled=lambda: self._cancelled,
            )
            dl_quality = config.get("download_quality", "best")
            video_path = downloader.download(input_source, tmp_dir, quality=dl_quality)
            self._log(f"✅ Tải xong: {Path(video_path).name}")

            # Lưu một bản sao video gốc chất lượng cao vào thư mục xuất
            try:
                raw_filename = f"[Gốc] {Path(video_path).name}"
                raw_out_path = os.path.join(output_dir, raw_filename)
                shutil.copy2(video_path, raw_out_path)
                self._log(f"💾 Đã lưu sẵn video gốc tại: {raw_filename}")
            except Exception:
                pass
        else:
            video_path = input_source
            self._log(f"📂 File input: {Path(video_path).name}")

        self._progress(0.10, "Đã có video")
        if self._cancelled:
            self._log("⚠️ Đã hủy bởi người dùng.")
            return

        source_lang = config.get("source_language", "zh")
        target_lang = config.get("target_language", "vi")
        enable_tts = config.get("enable_tts", True if source_lang != "vi" else False)
        # Khi đầu ra không phải tiếng Việt thì bỏ qua TTS (chưa có giọng nước ngoài)
        if target_lang != "vi":
            enable_tts = False

        # ── Bước 2: Gemini phiên âm / dịch → SRT ──────────────────────────────────────
        src_name_map = {
            "auto": "Tự Động", "zh": "Tiếng Trung", "en": "Tiếng Anh",
            "vi": "Tiếng Việt", "ja": "Tiếng Nhật", "ko": "Tiếng Hàn",
            "th": "Tiếng Thái", "fr": "Tiếng Pháp", "es": "Tiếng Tây Ban Nha", "de": "Tiếng Đức",
        }
        tgt_name_map = {"vi": "Tiếng Việt", "en": "Tiếng Anh"}
        src_label = src_name_map.get(source_lang, source_lang.upper())
        tgt_label = tgt_name_map.get(target_lang, target_lang.upper())

        if source_lang == "auto":
            self._log(f"🤖 Gemini sẽ tự nhận diện ngôn ngữ và tạo phụ đề {tgt_label}...")
        elif source_lang == "vi" and target_lang == "vi":
            self._log("🤖 Đang gửi video lên Gemini AI để phiên âm tạo phụ đề Tiếng Việt...")
        else:
            self._log(f"🤖 Đang gửi video lên Gemini AI để phiên âm và dịch {src_label} → {tgt_label}...")

        gemini = GeminiProcessor(
            api_key=config["gemini_api_key"],
            preferred_model=config.get("gemini_model", "auto"),
            progress_callback=self._make_progress_cb(0.10, 0.50),
        )
        raw_srt = gemini.process_video(
            video_path,
            source_lang=source_lang,
            target_lang=target_lang,
            is_cancelled=lambda: self._cancelled,
        )
        srt_content = normalize_srt_content(raw_srt)

        # Lưu SRT tạm
        srt_tmp = os.path.join(tmp_dir, "subtitles.srt")
        with open(srt_tmp, "w", encoding="utf-8") as f:
            f.write(srt_content)

        segments = parse_srt(srt_content)
        if source_lang == "vi" and target_lang == "vi":
            self._log(f"✅ Phiên âm xong: {len(segments)} đoạn phụ đề tiếng Việt")
            self._progress(0.50, "Phiên âm xong")
        else:
            self._log(f"✅ Dịch xong: {len(segments)} đoạn phụ đề {tgt_label}")
            self._progress(0.50, "Dịch xong")

        # ── Bước 2.5: Duyệt & Chỉnh sửa phụ đề (nếu người dùng bật) ────────
        if config.get("review_subtitles", False):
            self._log("✏️ Đang mở Trình chỉnh sửa phụ đề để Sếp kiểm tra & duyệt...")
            self._progress(0.50, "Đang duyệt phụ đề")
            review_event = threading.Event()
            review_holder = {"segments": segments, "cancelled": False}
            self._put(
                "review_subtitles",
                segments=segments,
                srt_content=srt_content,
                video_path=video_path,
                event=review_event,
                holder=review_holder,
            )
            review_event.wait()

            if review_holder.get("cancelled", False) or self._cancelled:
                self._log("⚠️ Tiến trình đã dừng tại bước duyệt phụ đề.")
                return

            segments = review_holder.get("segments", segments)
            srt_content = segments_to_srt(segments)
            with open(srt_tmp, "w", encoding="utf-8") as f:
                f.write(srt_content)
            self._log(f"✅ Đã cập nhật {len(segments)} đoạn phụ đề sau khi chỉnh sửa.")

        # Tùy chọn lưu file rời ra output folder
        video_stem = Path(video_path).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Đặt suffix theo ngôn ngữ đầu ra
        if target_lang == "en":
            suffix = "sub_en"
        elif source_lang == "vi":
            suffix = "sub_vi"
        else:
            suffix = "vietsub"

        export_srt = config.get("export_srt", True)
        export_txt = config.get("export_txt", True)
        output_srt = None
        output_txt = None

        # Lưu SRT rời ra output folder (nếu được chọn)
        if export_srt:
            output_srt = os.path.join(output_dir, f"{video_stem}_{suffix}_{timestamp}.srt")
            shutil.copy2(srt_tmp, output_srt)
            self._log(f"💾 Đã lưu file phụ đề: {Path(output_srt).name}")

        # Lưu file text (.txt) lời thoại ra output folder (nếu được chọn)
        if export_txt:
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

            tts_tech = config.get("tts_technology", "edge")
            if tts_tech == "gemini":
                chosen_voice = config.get("tts_voice_gemini", "Aoede")
                tech_display = f"Google Gemini AI ({chosen_voice})"
            else:
                chosen_voice = config.get("tts_voice", "vi-VN-HoaiMyNeural")
                tech_display = f"Microsoft AI ({chosen_voice})"

            self._log(f"🗣️ Đang tạo giọng đọc [{tech_display}]...")
            tts_audio = os.path.join(tmp_dir, "tts_track.mp3")

            tts = TTSGenerator(
                voice=chosen_voice,
                tts_technology=tts_tech,
                speed=config.get("tts_speed", "+0%"),
                pitch=config.get("tts_pitch", "+0Hz"),
                api_key=config.get("gemini_api_key", ""),
                progress_callback=self._make_progress_cb(0.50, 0.75),
                is_cancelled=lambda: self._cancelled,
                log_callback=self._log,
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
            subtitle_style_preset=config.get("subtitle_style_preset", "capcut_yellow"),
            is_cancelled=lambda: self._cancelled,
        )

        self._progress(1.0, "Hoàn tất!")
        self._log("─" * 45)
        self._log("🎉 HOÀN TẤT! File đầu ra:")
        self._log(f"   🎬 Video : {Path(output_video).name}")
        if output_srt:
            self._log(f"   📄 Phụ đề: {Path(output_srt).name}")
        if output_txt:
            self._log(f"   📝 Văn bản: {Path(output_txt).name}")
        self._log(f"   📁 Thư mục: {output_dir}")

        self._put("success", video_path=output_video, srt_path=output_srt, txt_path=output_txt)
