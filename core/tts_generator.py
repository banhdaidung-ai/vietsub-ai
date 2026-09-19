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

    def _prepare_text_for_edge_tts(self, text: str) -> str:
        """
        Chuẩn hóa văn bản tương thích 100% với Microsoft Edge-TTS:
        - Giữ tone giọng ổn định, chuẩn phong thái thuyết minh/phát thanh viên.
        - Chuyển dấu ba chấm ('...', '…') thành dấu chấm '.' (tránh ngắt kết nối WebSocket).
        - Chuyển đổi dấu cảm thán '!' thành dấu chấm '.' để triệt tiêu hiện tượng vút tone/thét cao độ thất thường.
        - Loại bỏ các dấu kết thúc dở dang ở cuối câu: dấu phẩy ',', gạch ngang '-', hai chấm ':', chấm phẩy ';'
          (tránh Edge-TTS báo lỗi 'No audio was received' do cụm từ chưa kết thúc SSML).
        - Bảo đảm câu luôn kết thúc bằng dấu câu hợp lệ (. hoặc ?) để Edge-TTS phát âm ổn định dải tần.
        """
        if not text:
            return ""
        import re
        t = text.replace("...", ".").replace("…", ".").replace("~", ".")
        # Triệt tiêu các dấu cảm thán ! thành dấu chấm . để giữ âm lượng và tone giọng đều đặn
        t = re.sub(r"[!]+", ".", t)
        # Loại bỏ các ký tự dấu câu dở dang ở cuối câu
        t = t.rstrip(" ,;:-")
        # Bảo đảm câu kết thúc bằng dấu ngắt câu chuẩn
        if t and t[-1] not in (".", "?"):
            t += "."
        return " ".join(t.split()).strip()

    async def _generate_single_edge_tts(
        self, text: str, out_path: str, voice_override: Optional[str] = None
    ) -> bool:
        """Tạo audio cho một câu dùng Microsoft Edge-TTS (hỗ trợ voice override và tự động dọn dẹp file lỗi)."""
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
        clean_edge_text = self._prepare_text_for_edge_tts(text)
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

            # Nếu thử lại từ lần 3 trở đi, làm sạch sâu hơn và dùng tham số chuẩn
            if attempt >= 3:
                import re
                current_text = re.sub(r'[^\w\s.,?]', '', clean_edge_text).strip()
                current_text = self._prepare_text_for_edge_tts(current_text) or clean_edge_text
                current_rate = "+0%"
                current_pitch = "+0Hz"

            try:
                communicate = edge_tts.Communicate(
                    text=current_text,
                    voice=voice_name,
                    rate=current_rate,
                    pitch=current_pitch,
                    connect_timeout=12,
                    receive_timeout=25,
                )
                await communicate.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    if attempt > 1:
                        self._log(f"   ✅ Đã tạo thành công giọng {voice_name} ở lần thử thứ {attempt}!")
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

                if attempt >= max_attempts:
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
                        if gap < 450:
                            is_mid = True

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
                        gemini_consecutive_failures += 1
                        # Cho phép chịu đựng tối đa 3 lỗi liên tiếp trước khi abort toàn bộ sang Edge-TTS
                        if gemini_consecutive_failures >= 3:
                            self._log(f"   ⚠️ Gemini TTS lỗi {gemini_consecutive_failures} lần liên tiếp → chuyển sang Microsoft AI")
                            gemini_aborted = True
                            break
                        else:
                            # Chèn khoảng lặng chuẩn timeline cho câu này để giữ nguyên tính đồng nhất của giọng nói
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
                        if gap < 450:
                            is_mid = True

                    tts_text = self._smooth_segment_text(seg.text, is_mid)
                    if not tts_text:
                        continue

                    seg_path = os.path.join(tmp_dir, f"seg_edge_{i:04d}.mp3")

                    # Luôn dùng đúng giọng đọc đã chọn (tuyệt đối không tự ý đổi sang giọng khác)
                    success = await self._generate_single_edge_tts(tts_text, seg_path, voice_override=chosen_voice)

                    # Nếu không thành công sau nhiều lần thử, chèn khoảng lặng giữ timeline để bảo toàn tính đồng nhất của giọng nói
                    if not success:
                        tts_skip_count += 1
                        seg_dur_sec = max((seg.end_ms - seg.start_ms) / 1000.0, 0.4)
                        silence_path = os.path.join(tmp_dir, f"silence_edge_{i:04d}.mp3")
                        if self._create_silence_audio(ffmpeg, seg_dur_sec, silence_path):
                            self._log(
                                f"   ⚠️ Câu {i + 1}/{len(segments)}: Giọng {chosen_voice} mất kết nối sau nhiều lần thử "
                                f"→ đã chèn khoảng lặng {seg_dur_sec:.1f}s giữ timeline (bảo toàn giọng đã chọn): \"{tts_text[:40]}...\""
                            )
                            seg_paths.append((seg, silence_path))
                        else:
                            self._log(f"   ⚠️ Bỏ qua câu {i + 1}/{len(segments)}: \"{tts_text[:40]}...\"")
                    else:
                        tts_success_count += 1
                        seg_paths.append((seg, seg_path))

                    # Nghỉ 350ms giữa các câu để chống Microsoft WebSocket connection reset/rate limit
                    await asyncio.sleep(0.35)

            # Điều chỉnh tốc độ thông minh & Bảo toàn tone giọng phát thanh viên (Tempo Smoothing)
            adjusted_seg_paths = []
            for i, (seg, seg_path) in enumerate(seg_paths):
                # Xác định thời gian tối đa được phép phát trước khi câu tiếp theo bắt đầu
                if i + 1 < len(seg_paths):
                    next_start_ms = seg_paths[i + 1][0].start_ms
                    # Chừa khoảng đệm tự nhiên (lead-out buffer 120ms) để câu đọc tròn vành rõ chữ
                    gap_ms = next_start_ms - seg.start_ms
                    max_allowed_ms = max(gap_ms + 120, 600)
                else:
                    seg_dur_ms = max(seg.end_ms - seg.start_ms, 800)
                    max_allowed_ms = max(seg_dur_ms + 200, int(total_duration_sec * 1000) - seg.start_ms)

                tts_dur_ms = self._get_audio_duration_ms(seg_path)
                if tts_dur_ms > max_allowed_ms:
                    raw_speed = tts_dur_ms / max_allowed_ms
                    # KHỐNG CHẾ TRẦN TỐC ĐỘ TỐI ĐA 1.20x ĐỂ GIỮ TONE GIỌNG CHUẨN XUYÊN SUỐT:
                    # Ngưỡng 1.03x - 1.20x giữ trọn vẹn chất giọng tự nhiên, tuyệt đối không bị the thé hay đổi tone
                    speed = min(max(raw_speed, 1.03), 1.20)
                    adjusted_path = seg_path.replace(".mp3", "_adj.mp3")
                    new_dur_ms = tts_dur_ms / speed

                    filter_str = f"atempo={speed:.3f}"
                    # Nếu sau khi điều chỉnh tốc độ vẫn còn dài hơn khoảng đệm quá 250ms, fade out nhẹ ở đuôi
                    if new_dur_ms > max_allowed_ms + 250 and i + 1 < len(seg_paths):
                        max_sec = (max_allowed_ms + 200) / 1000.0
                        fade_st = max(0.0, max_sec - 0.10)
                        filter_str = f"atempo={speed:.3f},afade=t=out:st={fade_st:.3f}:d=0.10"
                        cmd = [
                            ffmpeg, "-y", "-i", seg_path,
                            "-filter:a", filter_str,
                            "-t", f"{max_sec:.3f}",
                            "-c:a", "libmp3lame", "-q:a", "2",
                            adjusted_path,
                        ]
                    else:
                        cmd = [
                            ffmpeg, "-y", "-i", seg_path,
                            "-filter:a", filter_str,
                            "-c:a", "libmp3lame", "-q:a", "2",
                            adjusted_path,
                        ]

                    subprocess.run(cmd, capture_output=True, check=False)
                    if os.path.exists(adjusted_path) and os.path.getsize(adjusted_path) > 0:
                        seg_path = adjusted_path

                adjusted_seg_paths.append((seg, seg_path))

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

        if len(seg_paths) <= batch_size:
            self._run_amix_combine(ffmpeg, seg_paths, total_duration_sec, output_path)
            self._master_audio_track(ffmpeg, output_path, total_duration_sec)
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

        # Chuẩn hóa âm học phát thanh viên EBU R128 cho toàn bộ track âm thanh
        self._master_audio_track(ffmpeg, output_path, total_duration_sec)

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
            "-t", str(total_duration_sec),
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
