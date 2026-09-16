"""
core/gemini_processor.py — Phiên âm tiếng Trung + Dịch sang tiếng Việt via Gemini AI
"""

import os
import shutil
import tempfile
import time
from typing import Callable, Optional

from google import genai

from utils.srt_parser import clean_srt_response

# Prompt dịch thuật được tối ưu cho chất lượng cao
TRANSLATION_PROMPT = """Bạn là chuyên gia dịch phụ đề từ tiếng Trung sang tiếng Việt.

NHIỆM VỤ: Nghe tất cả lời thoại tiếng Trung trong video này và tạo phụ đề tiếng Việt chính xác theo định dạng SRT.

YÊU CẦU DỊCH THUẬT:
- Dịch sang tiếng Việt tự nhiên, linh hoạt — không dịch từng chữ máy móc
- Giữ nguyên tên người, địa danh (dùng phiên âm hoặc tên Việt nếu có)
- Bao gồm TẤT CẢ lời thoại, không bỏ sót câu nào
- Mỗi phụ đề tối đa 2 dòng, tối đa 42 ký tự mỗi dòng
- Timestamp phải khớp chính xác với thời điểm nói trong video

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown, không có giải thích, không có text ngoài SRT.

Ví dụ format đúng:
1
00:00:01,000 --> 00:00:04,500
Xin chào các bạn!

2
00:00:05,200 --> 00:00:08,000
Hôm nay chúng ta sẽ học về...

BẮT ĐẦU XUẤT SRT NGAY:"""


# MIME types được Gemini File API hỗ trợ
MIME_MAP = {
    ".mp4": "video/mp4",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".3gp": "video/3gpp",
    ".mkv": "video/x-matroska",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
}

MAX_FILE_SIZE_GB = 2.0
MAX_WAIT_SECONDS = 600  # 10 phút


class GeminiProcessor:
    def __init__(
        self,
        api_key: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ):
        self.client = genai.Client(api_key=api_key)
        self.progress_callback = progress_callback

    def _report(self, pct: float, message: str):
        if self.progress_callback:
            self.progress_callback(pct, message)

    def process_video(self, video_path: str) -> str:
        """
        Upload video lên Gemini, phiên âm tiếng Trung và dịch sang tiếng Việt.
        Trả về nội dung SRT tiếng Việt.
        """
        # Kiểm tra kích thước file
        file_size_gb = os.path.getsize(video_path) / (1024**3)
        if file_size_gb > MAX_FILE_SIZE_GB:
            raise ValueError(
                f"File video quá lớn ({file_size_gb:.1f}GB). "
                f"Giới hạn Gemini là {MAX_FILE_SIZE_GB}GB.\n"
                "Vui lòng dùng FFmpeg để cắt video thành các phần nhỏ hơn:\n"
                "ffmpeg -i video.mp4 -c copy -t 1800 part1.mp4"
            )

        # Xác định MIME type
        ext = os.path.splitext(video_path)[1].lower()
        mime_type = MIME_MAP.get(ext, "video/mp4")

        # Chuẩn hóa tên file thành ASCII để tránh lỗi HTTP Header trong google-genai
        # (Header 'X-Goog-Upload-File-Name' chỉ chấp nhận ASCII theo chuẩn RFC)
        clean_temp_file = None
        upload_target = video_path
        try:
            os.path.basename(video_path).encode("ascii")
        except UnicodeEncodeError:
            clean_temp_file = os.path.join(tempfile.gettempdir(), f"vietsub_up_{int(time.time())}{ext}")
            if os.path.exists(clean_temp_file):
                try:
                    os.remove(clean_temp_file)
                except Exception:
                    pass
            try:
                os.symlink(os.path.abspath(video_path), clean_temp_file)
            except (OSError, AttributeError):
                shutil.copy2(video_path, clean_temp_file)
            upload_target = clean_temp_file

        try:
            # Bước 1: Upload file lên Gemini File API
            self._report(0.05, "Đang upload video lên Gemini AI...")
            try:
                video_file = self.client.files.upload(
                    file=upload_target,
                    config={"mime_type": mime_type},
                )
            except Exception as e:
                err_msg = str(e)
                if "API_KEY_INVALID" in err_msg or "401" in err_msg or "403" in err_msg:
                    raise ValueError("API Key Gemini không hợp lệ. Vui lòng kiểm tra lại trong phần Cài đặt.")
                raise RuntimeError(f"Lỗi khi upload video lên Gemini: {e}")

            self._report(0.25, "Upload xong. Chờ Gemini xử lý video...")

            # Bước 2: Chờ Gemini xử lý xong (PROCESSING → ACTIVE)
            waited = 0
            while True:
                state_name = getattr(video_file.state, "name", str(video_file.state))
                if state_name != "PROCESSING":
                    break

                time.sleep(5)
                waited += 5
                self._report(
                    min(0.48, 0.25 + (waited / 120) * 0.23),
                    f"Chờ Gemini phân tích video... ({waited}s)",
                )
                video_file = self.client.files.get(name=video_file.name)
                if waited >= MAX_WAIT_SECONDS:
                    try:
                        self.client.files.delete(name=video_file.name)
                    except Exception:
                        pass
                    raise TimeoutError(
                        f"Gemini xử lý quá lâu (>{MAX_WAIT_SECONDS//60} phút). "
                        "Vui lòng thử lại với video ngắn hơn."
                    )

            state_name = getattr(video_file.state, "name", str(video_file.state))
            if state_name == "FAILED":
                raise RuntimeError(
                    "Gemini không thể xử lý file video này.\n"
                    "Hãy thử chuyển sang định dạng MP4 trước:\n"
                    "ffmpeg -i input.mkv -c copy output.mp4"
                )

            # Bước 3: Gọi Gemini để phiên âm + dịch
            self._report(0.5, "Gemini đang phiên âm và dịch tiếng Trung → Việt...")
            models_to_try = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
            response = None
            last_err = None
            for model_name in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[video_file, TRANSLATION_PROMPT],
                    )
                    break
                except Exception as e:
                    last_err = e
                    err_msg = str(e)
                    if "404" in err_msg or "NOT_FOUND" in err_msg or "no longer available" in err_msg:
                        continue
                    if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                        raise ValueError("Đã vượt hạn ngạch (quota) của Gemini API. Vui lòng thử lại sau vài phút hoặc dùng key khác.")
                    raise RuntimeError(f"Lỗi khi gọi Gemini dịch video: {e}")
            if response is None:
                raise RuntimeError(f"Lỗi khi gọi Gemini dịch video: {last_err}")

            # Dọn dẹp file đã upload trên Gemini
            try:
                self.client.files.delete(name=video_file.name)
            except Exception:
                pass  # Không quan trọng nếu cleanup thất bại

            self._report(0.9, "Dịch xong, đang xử lý SRT...")

            # Làm sạch và validate SRT
            srt_content = clean_srt_response(response.text)
            if not srt_content or len(srt_content.strip()) < 20:
                raise ValueError(
                    "Gemini không tạo được phụ đề.\n"
                    "Có thể do:\n"
                    "  • Video không có tiếng Trung\n"
                    "  • Chất lượng âm thanh quá thấp\n"
                    "  • Video quá ngắn (< 1 giây)"
                )

            return srt_content
        finally:
            if clean_temp_file and os.path.exists(clean_temp_file):
                try:
                    os.remove(clean_temp_file)
                except Exception:
                    pass

