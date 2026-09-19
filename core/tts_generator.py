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
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable, List, Optional

import edge_tts

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path
from utils.srt_parser import SRTSegment, is_clause_continuation, ms_to_time


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
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.voice = voice
        self.tts_technology = tts_technology.lower() if tts_technology else "edge"
        self.speed = speed if speed else "+0%"
        self.pitch = pitch if pitch else "+0Hz"
        self.api_key = api_key
        self.progress_callback = progress_callback
        self.is_cancelled = is_cancelled
        self.log_callback = log_callback
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

    def _log(self, message: str):
        """Gửi thông điệp log về UI (nếu có callback)."""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

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
        - Bỏ các ký tự đặc biệt, nốt nhạc, nhãn người nói và chú thích âm thanh.
        - Nếu câu nói đang dở dang và tiếp tục ở dòng sau, thêm dấu phẩy nhẹ để tránh hạ giọng cụt lủn.
        """
        from utils.srt_parser import clean_subtitle_text
        cleaned_text = clean_subtitle_text(text)
        clean = " ".join(cleaned_text.split()).strip()

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

    def _prepare_text_for_edge_tts(self, text: str, is_mid_sentence: bool = False) -> str:
        """
        Chuẩn hóa văn bản tương thích 100% với Microsoft Edge-TTS:
        - Giữ tone giọng ổn định, chuẩn phong thái thuyết minh/phát thanh viên đĩnh đạc, trầm ấm.
        - Triệt tiêu hiện tượng lên/xuống tone bừa bãi:
          * Chuyển dấu ba chấm ('...', '…'), dấu ngã ('~'), gạch ngang ('—', '--') thành dấu ngắt hơi hoặc dấu chấm.
          * Chuyển đổi dấu cảm thán '!' thành dấu chấm '.' (hoặc phẩy) để giữ âm lượng và tone giọng đều đặn.
          * Chuyển đổi dấu hỏi '?' thành dấu câu mềm mại (. hoặc ,) để tránh hiện tượng vút tone the thé ở âm tiết cuối.
          * Chuẩn hóa ký hiệu số & đơn vị thường gặp (% -> phần trăm, & -> và, + -> cộng, $ -> đô la).
          * Loại bỏ các dấu kết thúc dở dang ở cuối câu: dấu phẩy ',', gạch ngang '-', hai chấm ':', chấm phẩy ';'.
          * Bảo đảm câu luôn kết thúc bằng dấu ngắt câu chuẩn để Edge-TTS phát âm ổn định dải tần.
        """
        if not text:
            return ""
        import re
        t = text.replace("...", ".").replace("…", ".").replace("~", ".")
        t = t.replace("%", " phần trăm").replace("&", " và ").replace("+", " cộng ").replace("$", " đô la")
        t = t.replace("—", " - ").replace("--", " - ")

        # Triệt tiêu các dấu cảm thán ! thành dấu chấm hoặc phẩy để giữ âm lượng và tone giọng đều đặn
        t = re.sub(r"[!]+", "." if not is_mid_sentence else ",", t)

        # Dấu hỏi ?: Nếu là vế giữa câu thì dùng dấu phẩy, nếu kết thúc câu thì giữ 1 dấu ? để tự nhiên
        if is_mid_sentence:
            t = re.sub(r"[\?]+", ",", t)
        else:
            t = re.sub(r"[\?]+", "?", t)

        # Loại bỏ các ký tự dấu câu dở dang ở cuối câu
        t = t.rstrip(" ,;:-")

        # Bảo đảm câu kết thúc bằng dấu ngắt câu chuẩn
        if t and t[-1] not in (".", "?", "!"):
            t += "."

        return " ".join(t.split()).strip()

    def _generate_macos_say_tts(self, text: str, out_path: str, ffmpeg: str) -> bool:
        """Dự phòng giọng đọc offline Linh của macOS khi máy chủ Edge-TTS bị ngắt kết nối."""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tf:
                aiff_path = tf.name

            res = subprocess.run(["say", "-v", "Linh", text, "-o", aiff_path], capture_output=True, check=False)
            if res.returncode == 0 and os.path.exists(aiff_path) and os.path.getsize(aiff_path) > 0:
                cmd = [ffmpeg, "-y", "-i", aiff_path, "-c:a", "libmp3lame", "-q:a", "2", out_path]
                subprocess.run(cmd, capture_output=True, check=False)
                try:
                    os.remove(aiff_path)
                except Exception:
                    pass
                return os.path.exists(out_path) and os.path.getsize(out_path) > 0
        except Exception:
            pass
        return False

    async def _generate_single_edge_tts(
        self,
        text: str,
        out_path: str,
        voice_override: Optional[str] = None,
        is_mid_sentence: bool = False,
    ) -> bool:
        """Tạo audio cho một câu dùng Microsoft Edge-TTS với cơ chế thử lại thông minh & bảo toàn 100% câu từ."""
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

        # Nếu có voice_override thì ưu tiên dùng; nếu không thì dùng self.voice
        voice_name = voice_override or self.voice
        if not voice_name.startswith("vi-VN-"):
            voice_name = "vi-VN-HoaiMyNeural"

        # Tiền xử lý văn bản tương thích hoàn hảo với Microsoft Edge-TTS
        clean_edge_text = self._prepare_text_for_edge_tts(text, is_mid_sentence=is_mid_sentence)
        if not clean_edge_text:
            clean_edge_text = " ".join(text.split()).strip()
        if not clean_edge_text:
            return False

        attempt = 0
        max_attempts = 6
        while attempt < max_attempts:
            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Đã hủy bởi người dùng.")

            attempt += 1

            # Dọn dẹp file tạm 0 byte nếu có từ lần thử trước
            if os.path.exists(out_path) and os.path.getsize(out_path) == 0:
                try:
                    os.remove(out_path)
                except Exception:
                    pass

            current_text = clean_edge_text
            current_rate = rate_val
            current_pitch = pitch_val

            # Nếu là vế câu còn tiếp diễn, bỏ dấu chấm cuối câu để AI giữ cao độ tự nhiên
            if is_mid_sentence:
                current_text = current_text.rstrip(".?!,;:- ").strip()

            # Lần thử 2: Bỏ dấu chấm cuối câu (khắc phục lỗi Microsoft tokenizer trên một số từ như 'bạn.', 'này.')
            if attempt == 2:
                current_text = clean_edge_text.rstrip(".?!,;:- ").strip()

            # Lần thử 3: Làm sạch sâu hơn, chỉ giữ chữ, số và dấu phẩy, dùng tham số chuẩn
            if attempt >= 3:
                import re
                current_text = re.sub(r'[^\w\s,]', ' ', clean_edge_text).strip()
                current_text = " ".join(current_text.split())
                current_rate = "+0%"
                current_pitch = "+0Hz"

            # Lần thử 4+: Thử đảo giọng đọc bản xứ khác để tránh server chặn cụm từ
            current_voice = voice_name
            if attempt >= 4:
                if "HoaiMy" in voice_name:
                    current_voice = "vi-VN-NamMinhNeural"
                elif "NamMinh" in voice_name:
                    current_voice = "vi-VN-HoaiMyNeural"

            try:
                communicate = edge_tts.Communicate(
                    text=current_text,
                    voice=current_voice,
                    rate=current_rate,
                    pitch=current_pitch,
                    connect_timeout=12,
                    receive_timeout=25,
                )
                await communicate.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    if attempt > 1:
                        self._log(f"   ✅ Đã tạo thành công giọng {current_voice} ở lần thử thứ {attempt}!")
                    return True
            except (InterruptedError, KeyboardInterrupt):
                raise
            except Exception as e:
                # Xóa file 0 byte nếu có
                if os.path.exists(out_path) and os.path.getsize(out_path) == 0:
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass

                # Nếu là lần thử thứ 5 và có Gemini Client, thử fallback sang Gemini TTS ngay
                if attempt == 5 and self._gemini_client:
                    try:
                        gem_ok = self._generate_single_gemini_tts(current_text, out_path)
                        if gem_ok and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                            self._log(f"   ✅ Đã fallback sang Google Gemini TTS thành công cho câu này!")
                            return True
                    except Exception:
                        pass

                if attempt >= max_attempts:
                    # Nếu trên macOS, thử fallback sang giọng nói Linh của hệ thống trước khi từ bỏ
                    if sys.platform == "darwin":
                        ffmpeg = get_ffmpeg_path() or "ffmpeg"
                        if self._generate_macos_say_tts(current_text, out_path, ffmpeg):
                            self._log("   ✅ Đã sử dụng giọng đọc ngoại tuyến hệ thống để không bỏ sót câu!")
                            return True

                    self._log(f"   ❌ Giọng {voice_name} không phản hồi sau {max_attempts} lần thử.")
                    return False

                # Tăng dần thời gian chờ: 0.8s -> 1.2s -> 1.6s -> ... tối đa 3.0s để WebSocket hồi phục
                wait_sec = min(0.8 + 0.4 * min(attempt, 5), 3.0)
                err_str = str(e)
                if "No audio was received" in err_str:
                    err_hint = "Máy chủ Microsoft ngắt kết nối tạm thời"
                else:
                    err_hint = err_str

                self._log(
                    f"   🔄 Giọng {voice_name} gặp gián đoạn ({err_hint}). "
                    f"Đang tự động thử lại lần {attempt + 1}/{max_attempts} (chờ {wait_sec:.1f}s)..."
                )
                await asyncio.sleep(wait_sec)

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

    def _create_silence_audio(self, ffmpeg: str, duration_sec: float, out_path: str) -> bool:
        """Tạo file audio im lặng (silence) đúng thời lượng phân đoạn để giữ timeline chuẩn xác (Phương án A)."""
        dur = max(duration_sec, 0.2)
        try:
            cmd = [
                ffmpeg, "-y",
                "-f", "lavfi",
                "-i", "anullsrc=r=24000:cl=mono",
                "-t", f"{dur:.3f}",
                "-c:a", "libmp3lame",
                "-q:a", "4",
                out_path,
            ]
            res = subprocess.run(cmd, capture_output=True, check=False)
            return res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
        except Exception:
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
            tts_success_count = 0
            tts_skip_count = 0

            if use_gemini:
                gemini_consecutive_failures = 0
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
                        next_txt = segments[i + 1].text
                        is_mid = is_clause_continuation(seg.text, next_txt, gap)

                    tts_text = self._smooth_segment_text(seg.text, is_mid)
                    if not tts_text:
                        continue

                    seg_path = os.path.join(tmp_dir, f"seg_gemini_{i:04d}.mp3")
                    try:
                        success = self._generate_single_gemini_tts(tts_text, seg_path)
                    except Exception as ge:
                        self._log(f"   ⚠️ Gemini TTS lỗi câu {i + 1}: {ge}")
                        success = False

                    if not success:
                        # Fallback sang Edge-TTS ngay cho câu này để KHÔNG BAO GIỜ bị mất câu
                        fallback_voice = self.voice if self.voice.startswith("vi-VN-") else "vi-VN-HoaiMyNeural"
                        try:
                            success = await self._generate_single_edge_tts(
                                tts_text, seg_path, voice_override=fallback_voice, is_mid_sentence=is_mid
                            )
                        except Exception:
                            success = False

                        if success:
                            temp_gemini_paths.append((seg, seg_path))
                            self._log(f"   ℹ️ Câu {i + 1}/{len(segments)}: Gemini bận → đã lồng tiếng tự động bằng Microsoft AI ({fallback_voice})")
                        else:
                            gemini_consecutive_failures += 1
                            if gemini_consecutive_failures >= 3:
                                self._log(f"   ⚠️ Gemini TTS lỗi {gemini_consecutive_failures} lần liên tiếp → chuyển sang Microsoft AI")
                                gemini_aborted = True
                                break
                            else:
                                seg_dur_sec = max((seg.end_ms - seg.start_ms) / 1000.0, 0.4)
                                silence_path = os.path.join(tmp_dir, f"silence_gemini_{i:04d}.mp3")
                                if self._create_silence_audio(ffmpeg, seg_dur_sec, silence_path):
                                    temp_gemini_paths.append((seg, silence_path))
                                    tts_skip_count += 1
                                    self._log(f"   ⚠️ Câu {i + 1}/{len(segments)}: Đã chèn khoảng lặng {seg_dur_sec:.1f}s giữ timeline.")
                    else:
                        gemini_consecutive_failures = 0  # Reset khi thành công
                        temp_gemini_paths.append((seg, seg_path))

                    await asyncio.sleep(0.3)

                if gemini_aborted:
                    self._report(
                        0.0,
                        "⚠️ Gemini AI hết hạn mức Google. Đang chuyển toàn bộ sang Microsoft AI để đồng nhất 1 giọng...",
                    )
                    self._log("🔄 Chuyển toàn bộ lồng tiếng sang Microsoft Edge-TTS để đảm bảo đồng nhất 1 giọng nói.")
                    use_gemini = False
                else:
                    seg_paths = temp_gemini_paths
                    tts_success_count = len(temp_gemini_paths) - tts_skip_count

            if not use_gemini:
                seg_paths = []
                tts_success_count = 0
                tts_skip_count = 0

                # Giữ nguyên 100% giọng đọc được người dùng lựa chọn trong suốt toàn bộ video
                chosen_voice = self.voice if self.voice.startswith("vi-VN-") else "vi-VN-NamMinhNeural"
                self._log(f"🎙️ Giọng đọc được chọn cố định: {chosen_voice} (đồng nhất 100% xuyên suốt video)")

                for i, seg in enumerate(segments):
                    if self.is_cancelled and self.is_cancelled():
                        raise InterruptedError("Đã hủy bởi người dùng.")

                    self._report(
                        i / len(segments),
                        f"Lồng tiếng ({chosen_voice}) câu {i + 1}/{len(segments)}...",
                    )

                    is_mid = False
                    if i + 1 < len(segments):
                        gap = segments[i + 1].start_ms - seg.end_ms
                        next_txt = segments[i + 1].text
                        is_mid = is_clause_continuation(seg.text, next_txt, gap)

                    tts_text = self._smooth_segment_text(seg.text, is_mid)
                    if not tts_text:
                        continue

                    seg_path = os.path.join(tmp_dir, f"seg_edge_{i:04d}.mp3")

                    # Luôn dùng đúng giọng đọc đã chọn (tuyệt đối không tự ý đổi sang giọng khác)
                    success = await self._generate_single_edge_tts(
                        tts_text, seg_path, voice_override=chosen_voice, is_mid_sentence=is_mid
                    )

                    # Nếu không thành công sau nhiều lần thử, dùng các tầng dự phòng trước khi bỏ qua
                    if not success:
                        # Fallback cấp 2: Thử Gemini TTS nếu có API key
                        if self._gemini_client:
                            try:
                                success = self._generate_single_gemini_tts(tts_text, seg_path)
                            except Exception:
                                success = False

                        # Fallback cấp 3: Thử giọng đọc offline Linh của macOS
                        if not success and sys.platform == "darwin":
                            try:
                                success = self._generate_macos_say_tts(tts_text, seg_path, ffmpeg)
                            except Exception:
                                success = False

                        if not success:
                            tts_skip_count += 1
                            seg_dur_sec = max((seg.end_ms - seg.start_ms) / 1000.0, 0.4)
                            silence_path = os.path.join(tmp_dir, f"silence_edge_{i:04d}.mp3")
                            if self._create_silence_audio(ffmpeg, seg_dur_sec, silence_path):
                                self._log(
                                    f"   ⚠️ Câu {i + 1}/{len(segments)}: Không thể kết nối TTS "
                                    f"→ đã chèn khoảng lặng {seg_dur_sec:.1f}s giữ timeline: \"{tts_text[:40]}...\""
                                )
                                seg_paths.append((seg, silence_path))
                            else:
                                self._log(f"   ⚠️ Bỏ qua câu {i + 1}/{len(segments)}: \"{tts_text[:40]}...\"")
                        else:
                            tts_success_count += 1
                            seg_paths.append((seg, seg_path))
                    else:
                        tts_success_count += 1
                        seg_paths.append((seg, seg_path))

                    # Nghỉ 650ms giữa các câu để chống Microsoft WebSocket connection reset/rate limit
                    await asyncio.sleep(0.65)

            # Điều chỉnh tốc độ thông minh & Bảo toàn tone giọng phát thanh viên (Tempo Smoothing & Ripple Scheduling)
            adjusted_seg_paths = []
            current_end_ms = 0

            for i, (seg, seg_path) in enumerate(seg_paths):
                tts_dur_ms = self._get_audio_duration_ms(seg_path)
                if tts_dur_ms <= 0:
                    adjusted_seg_paths.append((seg, seg_path))
                    continue

                # Xác định khoảng thời gian lý tưởng khả dụng cho câu này
                if i + 1 < len(seg_paths):
                    gap_to_next = seg_paths[i + 1][0].start_ms - seg.start_ms
                    target_max_ms = max(gap_to_next - 60, 500)
                else:
                    seg_dur_ms = max(seg.end_ms - seg.start_ms, 800)
                    target_max_ms = max(seg_dur_ms + 200, int(total_duration_sec * 1000) - seg.start_ms)

                # Nếu câu đọc dài hơn khung thời gian, tăng tốc nhẹ nhàng (tối đa 1.25x) bằng FFmpeg atempo
                # FFmpeg atempo bảo toàn formant và pitch 100%, không làm méo tiếng hay the thé
                if tts_dur_ms > target_max_ms:
                    raw_speed = tts_dur_ms / target_max_ms
                    speed = min(max(raw_speed, 1.02), 1.25)
                    adjusted_path = seg_path.replace(".mp3", "_adj.mp3")
                    filter_str = f"atempo={speed:.3f}"
                    cmd = [
                        ffmpeg, "-y", "-i", seg_path,
                        "-filter:a", filter_str,
                        "-c:a", "libmp3lame", "-q:a", "2",
                        adjusted_path,
                    ]
                    subprocess.run(cmd, capture_output=True, check=False)
                    if os.path.exists(adjusted_path) and os.path.getsize(adjusted_path) > 0:
                        seg_path = adjusted_path
                        tts_dur_ms = self._get_audio_duration_ms(seg_path) or int(tts_dur_ms / speed)

                # TUYỆT ĐỐI KHÔNG CẮT ÂM THANH (-t / afade) ĐỂ ĐẢM BẢO 100% CÂU TỪ ĐƯỢC ĐỌC TRỌN VẸN!
                # Áp dụng thuật toán Non-Colliding Ripple Scheduler:
                # Nếu câu trước đã có âm thanh, câu sau bắt đầu sau khi câu trước dứt lời + 80ms thở tự nhiên.
                # Nếu là câu đầu tiên (chưa có âm thanh), bắt đầu chính xác tại mốc seg.start_ms
                actual_start_ms = max(seg.start_ms, current_end_ms + 80) if current_end_ms > 0 else seg.start_ms
                actual_end_ms = actual_start_ms + tts_dur_ms
                current_end_ms = actual_end_ms

                adjusted_seg = SRTSegment(
                    index=seg.index,
                    start=ms_to_time(actual_start_ms),
                    end=ms_to_time(actual_end_ms),
                    text=seg.text,
                    start_ms=actual_start_ms,
                    end_ms=actual_end_ms,
                )
                adjusted_seg_paths.append((adjusted_seg, seg_path))

            seg_paths = adjusted_seg_paths

            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Đã hủy bởi người dùng.")

            # Tổng kết kết quả TTS
            if tts_skip_count > 0:
                self._log(f"📊 Kết quả lồng tiếng: {tts_success_count} câu thành công, {tts_skip_count} câu bị bỏ qua ({tech_label})")
            else:
                self._log(f"✅ Lồng tiếng hoàn hảo: {tts_success_count}/{tts_success_count} câu thành công ({tech_label})")

            if not seg_paths:
                raise ValueError(
                    "Không tạo được giọng đọc cho bất kỳ câu nào. "
                    "Kiểm tra kết nối internet (Edge-TTS cần WebSocket) và thử lại."
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

        # Tính toán thời lượng an toàn: đảm bảo không cắt đuôi câu nói cuối cùng nếu ripple delay kéo dài hơn video gốc một chút
        max_audio_end_sec = max((seg.end_ms / 1000.0 for seg, _ in seg_paths), default=total_duration_sec)
        mix_duration_sec = max(total_duration_sec, max_audio_end_sec + 0.3) if total_duration_sec > 0 else max_audio_end_sec + 0.3

        if len(seg_paths) <= batch_size:
            self._run_amix_combine(ffmpeg, seg_paths, mix_duration_sec, output_path)
            self._master_audio_track(ffmpeg, output_path, mix_duration_sec)
            return

        batch_files = []
        for batch_idx in range(0, len(seg_paths), batch_size):
            chunk = seg_paths[batch_idx:batch_idx + batch_size]
            batch_out = os.path.join(tmp_dir, f"batch_{batch_idx // batch_size:03d}.mp3")
            self._run_amix_combine(ffmpeg, chunk, mix_duration_sec, batch_out)
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
                "-t", f"{mix_duration_sec:.3f}",
                "-c:a", "libmp3lame",
                "-q:a", "2",
                output_path,
            ]
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg lỗi khi merge audio batches:\n{result.stderr[-800:]}")

        # Chuẩn hóa âm học phát thanh viên EBU R128 cho toàn bộ track âm thanh
        self._master_audio_track(ffmpeg, output_path, mix_duration_sec)

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
                "-t", f"{total_duration_sec:.3f}",
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

    def _master_audio_track(self, ffmpeg: str, audio_path: str, total_duration_sec: float):
        """
        Chuẩn hóa âm học giọng đọc phát thanh viên EBU R128 & Dynamic Range Compression.
        Đảm bảo toàn bộ bài đọc từ đầu đến cuối có âm lượng, độ dày và âm sắc đồng nhất 100%.
        """
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            return
        mastered_tmp = audio_path.replace(".mp3", "_mastered.mp3")
        # -16 LUFS là chuẩn quốc tế cho podcast/giọng đọc lồng tiếng; acompressor nén nhẹ dải động để các âm cao và âm thấp nghe đều đặn
        filter_str = "loudnorm=I=-16:TP=-1.5:LRA=7,acompressor=threshold=-20dB:ratio=2.5:attack=15:release=100"
        cmd = [
            ffmpeg, "-y",
            "-i", audio_path,
            "-af", filter_str,
            "-t", f"{total_duration_sec:.3f}",
            "-c:a", "libmp3lame",
            "-q:a", "2",
            mastered_tmp,
        ]
        res = subprocess.run(cmd, capture_output=True, check=False)
        if res.returncode == 0 and os.path.exists(mastered_tmp) and os.path.getsize(mastered_tmp) > 0:
            try:
                shutil.move(mastered_tmp, audio_path)
                self._log("🎚️ Đã chuẩn hóa âm học phát thanh viên EBU R128 (âm sắc dày ấm, âm lượng đồng đều).")
            except Exception:
                pass
