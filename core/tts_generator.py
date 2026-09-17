"""
core/tts_generator.py — Tạo giọng đọc lồng tiếng hỗ trợ 2 công nghệ:
1. Microsoft Edge-TTS (Chuẩn giọng Việt bản xứ 100%, tốc độ cao, miễn phí)
2. Google Gemini AI Voice (Biểu cảm điện ảnh theo ngữ cảnh, dùng Gemini API)
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable, List, Optional

import edge_tts

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path
from utils.srt_parser import SRTSegment


class TTSGenerator:
    def __init__(
        self,
        voice: str = "vi-VN-HoaiMyNeural",
        tts_technology: str = "edge",          # "edge" hoặc "gemini"
        speed: str = "+0%",                    # Ví dụ: "+0%", "+10%", "-10%"
        pitch: str = "+0Hz",                   # Ví dụ: "+0Hz", "-5Hz", "+5Hz"
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ):
        self.voice = voice
        self.tts_technology = tts_technology.lower() if tts_technology else "edge"
        self.speed = speed if speed else "+0%"
        self.pitch = pitch if pitch else "+0Hz"
        self.api_key = api_key
        self.progress_callback = progress_callback
        self.is_cancelled = is_cancelled
        self._gemini_client = None

        if self.tts_technology == "gemini" and self.api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Không thể khởi tạo Google GenAI Client cho TTS: {e}")

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
        Tạo một audio track hoàn chỉnh, ghép từ các đoạn TTS
        với timing khớp chính xác theo timestamp SRT.
        """
        asyncio.run(
            self._generate_track_async(segments, total_duration_sec, output_path)
        )

    def _smooth_segment_text(self, text: str, is_mid_sentence: bool = False) -> str:
        """
        Làm mượt văn bản để AI đọc có hồn và tự nhiên:
        - Bỏ các ký tự đặc biệt / nốt nhạc.
        - Nếu câu nói đang dở dang và tiếp tục ở dòng sau, thêm dấu phẩy nhẹ để tránh hạ giọng cụt lủn.
        """
        clean = " ".join(text.split()).strip()
        for sym in ("♪", "♫", "♩", "♬", "[Nhạc]", "[Âm nhạc]"):
            clean = clean.replace(sym, "").strip()

        if not clean:
            return ""

        # Nếu dòng này không có dấu câu kết thúc và câu còn tiếp diễn, thêm dấu phẩy để AI giữ ngữ điệu
        if is_mid_sentence and clean[-1] not in (".", "!", "?", "…", ",", ";", ":", "-"):
            clean += ","

        return clean

    def generate_single_segment(self, text: str, out_path: str, is_mid_sentence: bool = False) -> bool:
        """Tạo audio cho 1 phân đoạn đơn lẻ (hỗ trợ cả Edge-TTS và Gemini AI với tự động fallback)."""
        tts_text = self._smooth_segment_text(text, is_mid_sentence)
        if not tts_text:
            return False

        if self.tts_technology == "gemini":
            try:
                success = self._generate_single_gemini_tts(tts_text, out_path)
                if success:
                    return True
            except Exception:
                pass
            # Fallback sang Edge-TTS
            return asyncio.run(self._generate_single_edge_tts(tts_text, out_path))
        else:
            return asyncio.run(self._generate_single_edge_tts(tts_text, out_path))

    async def _generate_single_edge_tts(self, text: str, out_path: str) -> bool:
        """Tạo audio cho một câu dùng Microsoft Edge-TTS."""
        # Chuẩn hóa rate và pitch
        rate_val = self.speed
        if not rate_val.startswith(("+", "-")):
            rate_val = f"+{rate_val}"
        if not rate_val.endswith("%"):
            rate_val = f"{rate_val}%"

        pitch_val = self.pitch
        if not pitch_val.startswith(("+", "-")):
            pitch_val = f"+{pitch_val}"
        if not pitch_val.endswith("Hz"):
            pitch_val = f"{pitch_val}Hz"

        # Nếu voice được truyền là voice của Gemini (do người dùng chuyển chế độ), fallback về Hoài My
        voice_name = self.voice
        if not voice_name.startswith("vi-VN-"):
            voice_name = "vi-VN-HoaiMyNeural"

        for attempt in range(3):
            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Đã hủy bởi người dùng.")
            try:
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=voice_name,
                    rate=rate_val,
                    pitch=pitch_val,
                )
                await communicate.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    return True
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.8)
        return False

    def _generate_single_gemini_tts(self, text: str, out_path: str) -> bool:
        """Tạo audio cho một câu dùng Google Gemini TTS."""
        if not self._gemini_client:
            return False

        from google.genai import types

        # Danh sách giọng hợp lệ của Gemini
        gemini_voice = self.voice
        valid_voices = {"Aoede", "Charon", "Fenrir", "Kore", "Puck"}
        if gemini_voice not in valid_voices:
            gemini_voice = "Aoede"

        for attempt in range(3):
            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Đã hủy bởi người dùng.")
            try:
                prompt = (
                    f"Bạn là phát thanh viên lồng tiếng chuyên nghiệp. "
                    f"Hãy đọc câu sau bằng tiếng Việt với giọng đọc chuẩn, tông giọng đều đặn, "
                    f"nhịp điệu ổn định và tự nhiên, không thay đổi cao độ đột ngột: {text}"
                )
                resp = self._gemini_client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=gemini_voice)
                            )
                        ),
                    ),
                )
                if resp and resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
                    for part in resp.candidates[0].content.parts:
                        if getattr(part, "inline_data", None) and part.inline_data.data:
                            pcm_data = part.inline_data.data
                            # Lưu dữ liệu PCM 24kHz 16-bit Mono thành file WAV
                            temp_wav = out_path.replace(".mp3", ".wav")
                            with wave.open(temp_wav, "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
                                wf.writeframes(pcm_data)

                            # Chuyển WAV sang MP3 chất lượng cao
                            ffmpeg = get_ffmpeg_path() or "ffmpeg"
                            subprocess.run(
                                [ffmpeg, "-y", "-i", temp_wav, "-c:a", "libmp3lame", "-q:a", "2", out_path],
                                capture_output=True,
                                check=False,
                            )
                            try:
                                os.remove(temp_wav)
                            except Exception:
                                pass

                            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                                return True
            except (InterruptedError, KeyboardInterrupt):
                raise
            except Exception as e:
                err_str = str(e)
                print(f"Gemini TTS retry {attempt + 1}: {err_str}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    # Gặp hạn ngạch giới hạn Free Tier (3 req/phút của Google)
                    # Lập tức fallback về Edge-TTS để không làm gián đoạn hay bắt người dùng chờ lâu
                    return False
                time.sleep(1.0 * (attempt + 1))
        return False

    async def _generate_track_async(
        self,
        segments: List[SRTSegment],
        total_duration_sec: float,
        output_path: str,
    ):
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        tmp_dir = tempfile.mkdtemp(prefix="vietsub_tts_")
        tech_label = "Google Gemini AI" if self.tts_technology == "gemini" else "Microsoft AI"

        try:
            seg_paths: List[tuple] = []
            use_gemini = (self.tts_technology == "gemini")

            if use_gemini:
                gemini_aborted = False
                temp_gemini_paths = []
                for i, seg in enumerate(segments):
                    if self.is_cancelled and self.is_cancelled():
                        raise InterruptedError("Đã hủy bởi người dùng.")

                    self._report(
                        i / len(segments),
                        f"Lồng tiếng (Google Gemini AI) câu {i + 1}/{len(segments)}...",
                    )

                    is_mid = False
                    if i + 1 < len(segments):
                        gap = segments[i + 1].start_ms - seg.end_ms
                        if gap < 450:
                            is_mid = True

                    tts_text = self._smooth_segment_text(seg.text, is_mid)
                    if not tts_text:
                        continue

                    seg_path = os.path.join(tmp_dir, f"seg_gemini_{i:04d}.mp3")
                    try:
                        success = self._generate_single_gemini_tts(tts_text, seg_path)
                    except Exception as ge:
                        print(f"Gemini TTS exception: {ge}")
                        success = False

                    if not success:
                        # Gemini hết quota (429/10 reqs per day của Google Free Tier)
                        # Để tránh video bị 2 giọng lẫn lộn, hủy và chuyển TOÀN BỘ sang Microsoft Edge-TTS
                        gemini_aborted = True
                        break

                    temp_gemini_paths.append((seg, seg_path))
                    await asyncio.sleep(0.3)

                if gemini_aborted:
                    self._report(
                        0.0,
                        "⚠️ Gemini AI hết hạn mức Google. Đang chuyển toàn bộ sang Microsoft AI để đồng nhất 1 giọng...",
                    )
                    use_gemini = False
                else:
                    seg_paths = temp_gemini_paths

            if not use_gemini:
                seg_paths = []
                for i, seg in enumerate(segments):
                    if self.is_cancelled and self.is_cancelled():
                        raise InterruptedError("Đã hủy bởi người dùng.")

                    self._report(
                        i / len(segments),
                        f"Lồng tiếng (Microsoft AI) câu {i + 1}/{len(segments)}...",
                    )

                    is_mid = False
                    if i + 1 < len(segments):
                        gap = segments[i + 1].start_ms - seg.end_ms
                        if gap < 450:
                            is_mid = True

                    tts_text = self._smooth_segment_text(seg.text, is_mid)
                    if not tts_text:
                        continue

                    seg_path = os.path.join(tmp_dir, f"seg_edge_{i:04d}.mp3")
                    success = await self._generate_single_edge_tts(tts_text, seg_path)
                    if not success:
                        continue
                    seg_paths.append((seg, seg_path))

            # Điều chỉnh tốc độ thông minh & Chống đè tiếng tuyệt đối (Anti-overlap Protection)
            adjusted_seg_paths = []
            for i, (seg, seg_path) in enumerate(seg_paths):
                # Xác định thời gian tối đa được phép phát trước khi câu tiếp theo bắt đầu
                if i + 1 < len(seg_paths):
                    next_start_ms = seg_paths[i + 1][0].start_ms
                    # Luôn chừa tối thiểu 80ms nghỉ trước khi câu sau phát
                    max_allowed_ms = max(next_start_ms - seg.start_ms - 80, 400)
                else:
                    seg_dur_ms = max(seg.end_ms - seg.start_ms, 600)
                    max_allowed_ms = max(seg_dur_ms, int(total_duration_sec * 1000) - seg.start_ms - 80)

                tts_dur_ms = self._get_audio_duration_ms(seg_path)
                if tts_dur_ms > max_allowed_ms:
                    raw_speed = tts_dur_ms / max_allowed_ms
                    # Tăng tốc độ mượt mà tối đa lên 1.45x
                    speed = min(max(raw_speed, 1.05), 1.45)
                    adjusted_path = seg_path.replace(".mp3", "_adj.mp3")
                    max_sec = max_allowed_ms / 1000.0
                    fade_st = max(0.0, max_sec - 0.05)

                    filter_str = f"atempo={speed:.3f},afade=t=out:st={fade_st:.3f}:d=0.05"
                    subprocess.run(
                        [
                            ffmpeg, "-y", "-i", seg_path,
                            "-filter:a", filter_str,
                            "-t", f"{max_sec:.3f}",
                            "-c:a", "libmp3lame", "-q:a", "2",
                            adjusted_path,
                        ],
                        capture_output=True,
                        check=False,
                    )
                    if os.path.exists(adjusted_path) and os.path.getsize(adjusted_path) > 0:
                        seg_path = adjusted_path

                adjusted_seg_paths.append((seg, seg_path))

            seg_paths = adjusted_seg_paths

            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Đã hủy bởi người dùng.")

            if not seg_paths:
                raise ValueError(
                    "Không tạo được giọng đọc. "
                    "Kiểm tra kết nối internet và thử lại."
                )

            self._report(0.9, "Đang hòa trộn các đoạn giọng nói theo mốc thời gian...")
            await self._combine_segments(seg_paths, total_duration_sec, output_path, tmp_dir)

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _get_audio_duration_ms(self, audio_path: str) -> int:
        """Lấy thời lượng audio (ms) dùng ffprobe hoặc FFmpeg."""
        try:
            from utils.ffmpeg_check import get_video_duration
            sec = get_video_duration(audio_path)
            return int(sec * 1000)
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

        batch_files = []
        for batch_idx in range(0, len(seg_paths), batch_size):
            chunk = seg_paths[batch_idx:batch_idx + batch_size]
            batch_out = os.path.join(tmp_dir, f"batch_{batch_idx // batch_size:03d}.mp3")
            self._run_amix_combine(ffmpeg, chunk, total_duration_sec, batch_out)
            batch_files.append(batch_out)

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
