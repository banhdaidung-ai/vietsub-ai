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

# Prompt dịch từ Tiếng Trung sang Tiếng Việt
PROMPT_TRANSLATE_ZH_TO_VI = """Bạn là chuyên gia dịch phụ đề từ tiếng Trung sang tiếng Việt.

NHIỆM VỤ: Nghe tất cả lời thoại tiếng Trung trong video này và tạo phụ đề tiếng Việt chính xác theo định dạng SRT.

YÊU CẦU DỊCH THUẬT:
- Dịch sang tiếng Việt tự nhiên, linh hoạt, đúng ngữ cảnh — không dịch từng chữ máy móc
- Giữ nguyên tên người, địa danh (dùng phiên âm Hán Việt hoặc tên thông dụng nếu có)
- TỐC ĐỘ & ĐỘ DÀI: Câu dịch cần súc tích, ngắn gọn, tương đương độ dài và nhịp điệu của câu nói gốc trong video để khi đọc bằng giọng nói (TTS) không bị quá nhanh hay dồn chữ
- Bao gồm TẤT CẢ lời thoại, không bỏ sót câu nào
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng
- Timestamp phải khớp chính xác với thời điểm nói trong video

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown (không dùng ```srt), không có giải thích, không có text ngoài SRT.

Ví dụ format đúng:
1
00:00:01,000 --> 00:00:04,500
Xin chào các bạn!

2
00:00:05,200 --> 00:00:08,000
Hôm nay chúng ta sẽ tìm hiểu về...

BẮT ĐẦU XUẤT SRT NGAY:"""

# Prompt dịch từ Tiếng Anh sang Tiếng Việt
PROMPT_TRANSLATE_EN_TO_VI = """Bạn là chuyên gia dịch phụ đề chuyên nghiệp từ tiếng Anh (English) sang tiếng Việt.

NHIỆM VỤ: Nghe tất cả lời thoại tiếng Anh trong video này và tạo phụ đề tiếng Việt chuẩn xác theo định dạng SRT.

YÊU CẦU DỊCH THUẬT:
- Dịch sang tiếng Việt tự nhiên, gãy gọn, chuẩn văn phong đời sống hoặc chuyên ngành — không dịch word-by-word máy móc.
- Dịch chuẩn các thành ngữ (idioms), tiếng lóng (slang), khẩu ngữ giao tiếp theo cách diễn đạt tự nhiên của người Việt.
- Giữ nguyên tên riêng, địa danh quốc tế, thương hiệu hoặc thuật ngữ chuyên ngành phổ biến khi cần thiết.
- TỐC ĐỘ & ĐỘ DÀI: Câu dịch cần súc tích, cô đọng, độ dài tương xứng với thời lượng nói của câu gốc trong video để khi tạo giọng đọc (TTS) không bị quá nhanh hoặc dồn dập chữ.
- Bao gồm TẤT CẢ lời thoại, không bỏ sót bất kỳ câu nào.
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng để người xem kịp đọc và vừa vặn khung hình.
- Timestamp phải khớp chính xác từng mili-giây với thời điểm người nói phát âm trong video.

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown (không dùng ```srt), không có giải thích, không có text ngoài SRT.

Ví dụ format đúng:
1
00:00:01,200 --> 00:00:04,800
Chào mừng mọi người đã quay trở lại!

2
00:00:05,100 --> 00:00:08,400
Trong video này, chúng ta sẽ cùng khám phá bí quyết...

BẮT ĐẦU XUẤT SRT NGAY:"""

# Prompt phiên âm tiếng Việt tạo phụ đề
PROMPT_TRANSCRIBE_VI = """Bạn là chuyên gia phiên âm và tạo phụ đề tiếng Việt chuyên nghiệp hàng đầu.

NHIỆM VỤ: Lắng nghe toàn bộ lời thoại tiếng Việt trong video này và tạo phụ đề tiếng Việt chuẩn xác 100% theo định dạng SRT.

YÊU CẦU PHIÊN ÂM:
- Ghi lại trung thực và chính xác từng câu từ mà người nói phát âm trong video sang tiếng Việt có dấu đầy đủ.
- Chuẩn hóa chính tả tiếng Việt, đặt dấu thanh đúng vị trí, sửa các lỗi phát âm sai/nói lắp nhưng vẫn giữ đúng ý nghĩa nguyên bản.
- Ngắt câu hợp lý, gãy gọn theo hơi thở và ý nghĩa diễn đạt của câu nói, tránh dòng quá dài.
- Bao gồm TẤT CẢ lời thoại trong video, không được bỏ qua hoặc tóm tắt bất kỳ đoạn nào.
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng để dễ theo dõi trên màn hình video/Shorts/Reels/TikTok.
- Timestamp phải khớp chính xác tuyệt đối từng mili-giây với lúc nhân vật bắt đầu và kết thúc nói câu đó.

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown (không dùng ```srt), không có giải thích, không có text ngoài SRT.

Ví dụ format đúng:
1
00:00:01,000 --> 00:00:03,800
Xin chào tất cả mọi người!

2
00:00:04,200 --> 00:00:07,500
Ngày hôm nay mình sẽ chia sẻ với các bạn một mẹo cực hay...

BẮT ĐẦU XUẤT SRT NGAY:"""

PROMPTS = {
    "zh": PROMPT_TRANSLATE_ZH_TO_VI,
    "en": PROMPT_TRANSLATE_EN_TO_VI,
    "vi": PROMPT_TRANSCRIBE_VI,
}


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

    def process_video(self, video_path: str, source_lang: str = "zh") -> str:
        """
        Upload video lên Gemini, phiên âm/dịch theo source_lang:
          - "zh": Dịch tiếng Trung sang tiếng Việt
          - "en": Dịch tiếng Anh sang tiếng Việt
          - "vi": Phiên âm tiếng Việt tạo phụ đề
        Trả về nội dung SRT tiếng Việt.
        """
        prompt = PROMPTS.get(source_lang, PROMPT_TRANSLATE_ZH_TO_VI)

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

            # Bước 3: Gọi Gemini để phiên âm / dịch
            if source_lang == "vi":
                status_msg = "Gemini đang lắng nghe và phiên âm phụ đề Tiếng Việt..."
            elif source_lang == "en":
                status_msg = "Gemini đang phiên âm và dịch Tiếng Anh → Tiếng Việt..."
            else:
                status_msg = "Gemini đang phiên âm và dịch Tiếng Trung → Tiếng Việt..."
            self._report(0.5, status_msg)

            models_to_try = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
            response = None
            last_err = None
            for model_name in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[video_file, prompt],
                    )
                    break
                except Exception as e:
                    last_err = e
                    err_msg = str(e)
                    if "404" in err_msg or "NOT_FOUND" in err_msg or "no longer available" in err_msg:
                        continue
                    if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                        raise ValueError("Đã vượt hạn ngạch (quota) của Gemini API. Vui lòng thử lại sau vài phút hoặc dùng key khác.")
                    raise RuntimeError(f"Lỗi khi gọi Gemini xử lý video: {e}")
            if response is None:
                raise RuntimeError(f"Lỗi khi gọi Gemini xử lý video: {last_err}")

            # Dọn dẹp file đã upload trên Gemini
            try:
                self.client.files.delete(name=video_file.name)
            except Exception:
                pass  # Không quan trọng nếu cleanup thất bại

            self._report(0.9, "Đã tạo phụ đề xong, đang chuẩn hóa SRT...")

            # Làm sạch và validate SRT
            srt_content = clean_srt_response(response.text)
            if not srt_content or len(srt_content.strip()) < 20:
                lang_note = {
                    "zh": "Video không có tiếng Trung",
                    "en": "Video không có tiếng Anh",
                    "vi": "Video không có lời thoại tiếng Việt",
                }.get(source_lang, "Video không có lời thoại")
                raise ValueError(
                    "Gemini không tạo được phụ đề.\n"
                    "Có thể do:\n"
                    f"  • {lang_note}\n"
                    "  • Chất lượng âm thanh quá thấp hoặc bị lẫn tạp âm\n"
                    "  • Video quá ngắn (< 1 giây)"
                )

            return srt_content
        finally:
            if clean_temp_file and os.path.exists(clean_temp_file):
                try:
                    os.remove(clean_temp_file)
                except Exception:
                    pass

