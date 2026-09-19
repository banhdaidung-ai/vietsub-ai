"""
core/gemini_processor.py — Phiên âm tiếng Trung + Dịch sang tiếng Việt via Gemini AI
"""

import os
import shutil
import tempfile
import time
from typing import Callable, Optional

from google import genai
from google.genai import types

from utils.srt_parser import clean_srt_response

# Prompt dịch từ Tiếng Trung sang Tiếng Việt
PROMPT_TRANSLATE_ZH_TO_VI = """Bạn là chuyên gia dịch thuật phụ đề phim và video chuyên nghiệp từ tiếng Trung (Chinese) sang tiếng Việt kiêm đạo diễn lồng tiếng hàng đầu.

NHIỆM VỤ: Lắng nghe toàn bộ âm thanh lời thoại tiếng Trung trong video và tạo phụ đề tiếng Việt chuẩn xác 100% theo định dạng SRT chuẩn.

YÊU CẦU DỊCH THUẬT & LỒNG TIẾNG CHUẨN MỰC (CỰC KỲ QUAN TRỌNG):
1. BẮT TRỌN 100% CÂU TỪ, TUYỆT ĐỐI KHÔNG BỎ SÓT:
- Dịch đầy đủ 100% tất cả lời thoại có trong video, từ đầu đến cuối, không được bỏ qua bất kỳ câu nào, dù là câu ngắn, câu cảm thán, lời thoại nền hay thì thầm.
- NGHIÊM CẤM TỰ Ý TÓM TẮT HOẶC CẮT BỚT Ý: Toàn bộ nội dung thông điệp của người nói phải được chuyển ngữ trọn vẹn, chân thực.

2. TONE GIỌNG TỰ NHIÊN, MẠCH LẠC & CHUẨN DẤU CÂU PHÁT THANH VIÊN:
- Dịch sang tiếng Việt tự nhiên, linh hoạt, chuẩn văn phong đời sống hoặc bối cảnh phim ảnh — tuyệt đối không dịch máy tính word-by-word khô cứng.
- Bản dịch mang tính khẩu ngữ sinh động của người Việt, dùng từ ngữ khí tự nhiên theo cảm xúc nhân vật (nhé, nhỉ, nè, trời ơi, thật sao, cơ chứ, hả...).
- NGỮ ĐIỆU & DẤU CÂU ĐỒNG NHẤT ĐỂ GIỌNG ĐỌC AI KHÔNG NHẢY TONE:
  * Giữ phong thái thuyết minh/phát thanh viên chuẩn mực, đĩnh đạc, đầm ấm và ổn định xuyên suốt toàn bộ video.
  * Nếu câu nói đang dở dang và tiếp tục ở phân đoạn sau: BẮT BUỘC kết thúc bằng dấu phẩy (,) để giọng đọc AI giữ cao độ tự nhiên, liền mạch.
  * Kết thúc một câu hoàn chỉnh: Dùng dấu chấm (.).
  * HẠN CHẾ LẠM DỤNG dấu chấm than (!) và dấu ba chấm (...). Tuyệt đối không dùng dấu ngã (~) hay dấu câu kép (!!, ??). Chỉ dùng dấu hỏi (?) cho câu hỏi thực sự.

3. GỘP CÂU HỢP LÝ & PHÙ HỢP LỒNG TIẾNG:
- Tránh ngắt vụn từng từ dưới 1.5 giây. Gộp các cụm từ ngắn thành câu hoàn chỉnh đủ ý (thời lượng mỗi phân đoạn lý tưởng từ 2.0s đến 5.0s) để người nghe dễ theo dõi và giọng đọc phát âm tròn vành rõ chữ.
- Nếu là bài hát / ca từ tiếng Trung: Dịch mượt mà, bay bổng đúng giai điệu và ca từ.
- Tách bạch giọng nói khỏi tiếng nhạc nền (BGM) và hiệu ứng âm thanh (SFX).
- Giữ nguyên tên người, địa danh (dùng phiên âm Hán Việt hoặc tên thông dụng quen thuộc).
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng.
- Timestamp phải khớp chính xác từng mili-giây với thời điểm nói trong video.
- BẮT BUỘC định dạng thời gian 3 phần: Giờ:Phút:Giây,mili-giây (HH:MM:SS,mmm). VÍ DỤ: 00:00:01,000 --> 00:00:04,500. TUYỆT ĐỐI KHÔNG bỏ phần giờ 00:.

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown (không dùng ```srt), không có giải thích, không có text ngoài SRT.

BẮT ĐẦU XUẤT SRT NGAY:"""

# Prompt dịch từ Tiếng Anh sang Tiếng Việt
PROMPT_TRANSLATE_EN_TO_VI = """Bạn là chuyên gia biên dịch phụ đề và đạo diễn lồng tiếng chuyên nghiệp hàng đầu từ tiếng Anh (English) sang tiếng Việt.

NHIỆM VỤ: Lắng nghe kỹ toàn bộ âm thanh giọng nói tiếng Anh trong video này và tạo phụ đề Tiếng Việt chuẩn xác 100% theo định dạng SRT chuẩn.

YÊU CẦU DỊCH THUẬT & LỒNG TIẾNG TRUYỀN CẢM (CỰC KỲ QUAN TRỌNG):
1. BẮT TRỌN 100% LỜI THOẠI & THUẦN VIỆT 100%:
- Toàn bộ nội dung phụ đề BẮT BUỘC dịch sang Tiếng Việt chuẩn xác, tự nhiên.
- Dịch trọn vẹn 100% tất cả câu từ lời thoại trong video, TUYỆT ĐỐI KHÔNG BỎ SÓT bất kỳ câu nói hay ý nào của nhân vật.
- TUYỆT ĐỐI KHÔNG xuất phụ đề song ngữ (Anh - Việt), KHÔNG để sót nguyên văn câu tiếng Anh trong phụ đề (trừ tên thương hiệu, tên người riêng).
- TUYỆT ĐỐI KHÔNG chèn nhãn người nói (ví dụ: Speaker 1:, John:, Man:, Người nói:) và KHÔNG chèn chú thích âm thanh (ví dụ: [Music], (Laughter), [tiếng cười], ♪, ♫) vào phụ đề.

2. TONE GIỌNG TỰ NHIÊN, MẠCH LẠC & CHUẨN DẤU CÂU PHÁT THANH VIÊN:
- Giữ phong thái thuyết minh/phát thanh viên chuẩn mực, đầm ấm, điềm tĩnh và ổn định xuyên suốt toàn bộ video.
- Dịch thoát ý theo khẩu ngữ giao tiếp sinh động của người Việt, dùng trợ từ ngữ khí tự nhiên theo cảm xúc nhân vật (nhé, nhỉ, nè, trời ơi, thật sao, cơ chứ, hả, nào...).
- Dịch chuẩn các thành ngữ (idioms), tiếng lóng (slang), khẩu ngữ giao tiếp đời thường.
- ĐỒNG NHẤT DẤU CÂU ĐỂ GIỌNG ĐỌC AI KHÔNG NHẢY TONE BỪA BÃI:
  * Nếu phân đoạn là vế câu còn tiếp diễn: BẮT BUỘC dùng dấu phẩy (,) ở cuối phân đoạn để giọng đọc AI giữ cao độ tự nhiên, liền mạch vào câu sau.
  * Chỉ dùng dấu chấm (.) khi kết thúc một câu hoàn chỉnh.
  * HẠN CHẾ dấu chấm than (!) và dấu ba chấm (...). Chỉ dùng dấu hỏi (?) cho câu hỏi thực sự.

3. GỘP CÂU HOÀN CHỈNH & PHÙ HỢP LỒNG TIẾNG:
- Lắng nghe trọn vẹn và GỘP các cụm từ ngắn thành CÂU HOÀN CHỈNH có đầy đủ ý nghĩa (thời lượng mỗi phân đoạn lý tưởng từ 2.0 giây đến 5.0 giây).
- TUYỆT ĐỐI KHÔNG ngắt vụn từng từ hay nửa câu dưới 1.5 giây để phụ đề dễ đọc và giọng đọc AI có đủ thời gian phát âm trọn vẹn, không nuốt chữ.
- Câu dịch cần súc tích, cô đọng, độ dài tương xứng thời lượng nói của video.
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng để vừa vặn khung hình.
- Timestamp phải khớp chính xác từng mili-giây với thời điểm bắt đầu và kết thúc câu nói trong video (HH:MM:SS,mmm).

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown (không dùng ```srt), không có giải thích, không có text ngoài SRT.

BẮT ĐẦU XUẤT SRT NGAY:"""

# Prompt phiên âm tiếng Việt tạo phụ đề
PROMPT_TRANSCRIBE_VI = """Bạn là chuyên gia thẩm âm, phiên âm và tạo phụ đề tiếng Việt chuyên nghiệp hàng đầu.

NHIỆM VỤ: Lắng nghe kỹ toàn bộ lời thoại / bài hát / giọng nói tiếng Việt trong video này và tạo phụ đề tiếng Việt chuẩn xác 100% theo định dạng SRT.

YÊU CẦU PHIÊN ÂM CHÍNH XÁC (QUAN TRỌNG):
1. BẮT TRỌN 100% CA TỪ & LỜI THOẠI, KHÔNG BỎ QUA CÂU NÀO:
- Phiên âm đầy đủ 100% lời nói và bài hát trong video, không bỏ sót bất kỳ câu nào.
- Nếu video chứa bài hát, ca khúc, rap, dân ca, ca dao, nhạc thiếu nhi, nhạc trẻ, nhạc Trung Thu hoặc âm thanh TikTok: Hãy lắng nghe kết hợp đối chiếu với lời gốc chuẩn xác của bài hát để ghi đúng từng từ, tuyệt đối không chép nhầm sang từ vô nghĩa do giai điệu kéo dài hoặc nhạc nền lấn át giọng hát.

2. PHÂN BIỆT RÕ PHỤ ÂM ĐẦU & DẤU THANH DỄ NHẦM:
- Chú ý cao độ các phụ âm dễ nhầm lẫn khi hát hoặc phát âm nhanh: "l" vs "c" ("lốc ca lốc cốc" chứ không phải "cốc ca cốc cốc"), "l" vs "n", "t" vs "đ" ("têm trầu" chứ không phải "tìm trầu"), "s" vs "x", "tr" vs "ch", "d/gi/r".
- Giữ câu từ có nghĩa mạch lạc, chuẩn văn phong và chính tả tiếng Việt có dấu đầy đủ.

3. TÁCH BẠCH GIỌNG NÓI KHỎI NHẠC NỀN & BEAT:
- Tập trung phân tích dải tần giọng người (vocal), loại bỏ ảnh hưởng của tiếng beat, tiếng bass, nhạc cụ đệm hoặc tạp âm xung quanh.
- Nếu câu đang dở dang và tiếp tục ở dòng sau, dùng dấu phẩy (,) để giữ nhịp điệu tự nhiên.

4. ĐỘ DÀI & ĐỊNH DẠNG:
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng để vừa vặn khung hình video.
- Timestamp phải khớp chính xác từng mili-giây với thời điểm bắt đầu và kết thúc câu nói/câu hát.
- BẮT BUỘC định dạng thời gian 3 phần: Giờ:Phút:Giây,mili-giây (HH:MM:SS,mmm). VÍ DỤ: 00:00:01,000 --> 00:00:03,800. TUYỆT ĐỐI KHÔNG bỏ phần giờ 00:.

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown (không dùng ```srt), không có giải thích, không có text ngoài SRT.

BẮT ĐẦU XUẤT SRT NGAY:"""

PROMPTS = {
    ("zh", "vi"): PROMPT_TRANSLATE_ZH_TO_VI,
    ("en", "vi"): PROMPT_TRANSLATE_EN_TO_VI,
    ("vi", "vi"): PROMPT_TRANSCRIBE_VI,
}

# ──────────────────────────────────────────────────────────────────────────────
# Prompt: Tự động nhận diện ngôn ngữ → Tiếng Việt
# ──────────────────────────────────────────────────────────────────────────────
PROMPT_AUTO_TO_VI = """Bạn là chuyên gia dịch thuật phụ đề phim và video đa ngôn ngữ kiêm đạo diễn lồng tiếng hàng đầu.

NHIỆM VỤ: Lắng nghe toàn bộ lời thoại trong video, TỰ ĐỘNG NHẬN DIỆN ngôn ngữ gốc, rồi dịch sang phụ đề Tiếng Việt chuẩn xác 100% theo định dạng SRT chuẩn.

QUY TRÌNH & YÊU CẦU DỊCH THUẬT & LỒNG TIẾNG TRUYỀN CẢM:
1. BẮT TRỌN 100% LỜI THOẠI & DỊCH SANG TIẾNG VIỆT THUẦN TÚY:
- Tự động nhận diện ngôn ngữ đang được nói trong video (Anh, Trung, Nhật, Hàn, Thái, Pháp, Tây Ban Nha, Đức, ...).
- Dịch đầy đủ 100% nội dung lời thoại, TUYỆT ĐỐI KHÔNG BỎ QUA bất kỳ câu nào, không tự ý tóm tắt hay cắt bớt câu.
- Dịch thoát ý sang Tiếng Việt tự nhiên, linh hoạt, chuẩn văn phong đời sống hoặc bối cảnh phim ảnh — tuyệt đối không dịch word-by-word máy móc.
- Toàn bộ phụ đề BẮT BUỘC bằng Tiếng Việt 100%, TUYỆT ĐỐI KHÔNG xuất phụ đề song ngữ hay để lẫn tiếng gốc.
- TUYỆT ĐỐI KHÔNG chèn nhãn người nói (Speaker 1:, Người nói:) và KHÔNG chèn chú thích âm thanh ([Music], (Laughter), [tiếng cười], ♪, ♫).

2. GỘP CÂU HOÀN CHỈNH & KHÔNG NGẮT VỤN (TỐI ƯU CHO LỒNG TIẾNG):
- Lắng nghe trọn vẹn và GỘP các cụm từ ngắn dở dang thành CÂU HOÀN CHỈNH có đầy đủ ý nghĩa (thời lượng mỗi phân đoạn lý tưởng từ 2.0s đến 5.0s).
- TUYỆT ĐỐI KHÔNG ngắt vụn từng từ hay nửa câu dưới 1.5 giây để phụ đề dễ đọc và giọng đọc AI có đủ thời gian phát âm trọn vẹn, không bị nuốt chữ.

3. KHẨU NGỮ TỰ NHIÊN & DẤU CÂU ỔN ĐỊNH (CHUẨN LỒNG TIẾNG PHÁT THANH VIÊN):
- Giữ phong thái thuyết minh/phát thanh viên chuẩn mực, đầm ấm và ổn định xuyên suốt toàn bộ video.
- HẠN CHẾ LẠM DỤNG dấu chấm than (!) và dấu ba chấm (...). Các câu trần thuật thông thường BẮT BUỘC kết thúc bằng dấu chấm (.) để giọng đọc AI giữ cao độ chuẩn, không bị giật cục hay the thé bất thường.
- Dùng từ ngữ khí sinh động của người Việt (nhé, nhỉ, nè, trời ơi, thật sao, cơ chứ, hả...).
- Giữ nguyên tên người, địa danh, thương hiệu quen thuộc.

4. TỐC ĐỘ & ĐỘ DÀI:
- Câu dịch súc tích, tương đương độ dài và nhịp điệu câu gốc để lồng tiếng khớp nhịp.
- Bao gồm TẤT CẢ lời thoại, không bỏ sót câu nào.
- Mỗi phụ đề tối đa 2 dòng, tối đa 40 ký tự mỗi dòng.
- Timestamp phải khớp chính xác từng mili-giây với thời điểm bắt đầu và kết thúc câu nói trong video.
- BẮT BUỘC định dạng thời gian 3 phần: HH:MM:SS,mmm. VÍ DỤ: 00:00:01,000 --> 00:00:04,500. TUYỆT ĐỐI KHÔNG bỏ phần giờ 00:.

ĐỊNH DẠNG ĐẦU RA (NGHIÊM NGẶT):
Chỉ xuất nội dung SRT thuần túy, không có markdown, không có giải thích, không có text ngoài SRT.

BẮT ĐẦU XUẤT SRT NGAY:"""

# ──────────────────────────────────────────────────────────────────────────────
# Prompt: Tự động nhận diện ngôn ngữ → Tiếng Anh
# ──────────────────────────────────────────────────────────────────────────────
PROMPT_AUTO_TO_EN = """You are a professional multilingual subtitle translator.

TASK: Listen to all speech in this video, AUTO-DETECT the source language, then translate to accurate English subtitles in SRT format.

PROCESS:
1. Identify the spoken language(s) in the video (Vietnamese, Chinese, Japanese, Korean, Thai, French, Spanish, German, etc.)
2. Translate to natural, fluent English — never word-by-word machine translation.
3. If the video contains multiple languages, translate all to English.

TRANSLATION REQUIREMENTS:
- Natural, idiomatic English that reads well as subtitles.
- Preserve proper names, place names, brand names.
- TIMING & LENGTH: Keep subtitles concise, matching the pacing of the original speech.
- Include ALL spoken lines — do not skip any.
- Maximum 2 lines per subtitle, maximum 42 characters per line.
- Timestamps must precisely match the moment of speech in the video.
- REQUIRED time format: HH:MM:SS,mmm (e.g. 00:00:01,000 --> 00:00:04,500). NEVER omit the 00: hour part.

OUTPUT FORMAT (STRICT):
Output only pure SRT content — no markdown, no explanations, no text outside SRT.

BEGIN SRT OUTPUT NOW:"""

# ──────────────────────────────────────────────────────────────────────────────
# Prompt: Tiếng Việt → Tiếng Anh (phiên âm + dịch)
# ──────────────────────────────────────────────────────────────────────────────
PROMPT_VI_TO_EN = """You are a professional Vietnamese-to-English subtitle translator.

TASK: Listen to all Vietnamese speech in this video and create accurate English subtitles in SRT format.

TRANSLATION REQUIREMENTS:
- Translate to natural, fluent, idiomatic English — never literal word-by-word translation.
- Capture Vietnamese idioms, slang, and colloquial expressions in their natural English equivalents.
- Preserve proper names, place names, Vietnamese brand names as appropriate.
- TIMING & LENGTH: Keep subtitles concise, matching the original speech pacing so they are comfortable to read.
- Include ALL spoken lines — do not omit anything.
- Maximum 2 lines per subtitle, maximum 42 characters per line.
- Timestamps must precisely match the moment of speech in the video.
- REQUIRED time format: HH:MM:SS,mmm (e.g. 00:00:01,000 --> 00:00:04,500). NEVER omit the 00: hour part.

OUTPUT FORMAT (STRICT):
Output only pure SRT content — no markdown, no explanations, no text outside SRT.

BEGIN SRT OUTPUT NOW:"""

# ──────────────────────────────────────────────────────────────────────────────
# Prompt: Tiếng Trung → Tiếng Anh
# ──────────────────────────────────────────────────────────────────────────────
PROMPT_ZH_TO_EN = """You are a professional Chinese-to-English subtitle translator.

TASK: Listen to all Chinese (Mandarin/Cantonese) speech in this video and create accurate English subtitles in SRT format.

TRANSLATION REQUIREMENTS:
- Translate to natural, fluent English — never word-by-word translation.
- Preserve Chinese names using their common English/Pinyin equivalents as appropriate.
- TIMING & LENGTH: Subtitles should be concise and match the original speech pacing.
- Include ALL spoken lines — do not skip any.
- Maximum 2 lines per subtitle, maximum 42 characters per line.
- Timestamps must precisely match the moment of speech.
- REQUIRED time format: HH:MM:SS,mmm (e.g. 00:00:01,000 --> 00:00:04,500). NEVER omit the 00: hour part.

OUTPUT FORMAT (STRICT):
Output only pure SRT content — no markdown, no explanations, no text outside SRT.

BEGIN SRT OUTPUT NOW:"""

# ──────────────────────────────────────────────────────────────────────────────
# Prompt lookup: (source_lang, target_lang) → prompt
# source "auto" = AI tự nhận diện; source cụ thể = ngôn ngữ gốc được chỉ định
# ──────────────────────────────────────────────────────────────────────────────
PROMPTS.update({
    # → Tiếng Việt
    ("auto", "vi"): PROMPT_AUTO_TO_VI,
    ("ja",   "vi"): PROMPT_AUTO_TO_VI,   # các ngôn ngữ chưa có prompt riêng → dùng auto
    ("ko",   "vi"): PROMPT_AUTO_TO_VI,
    ("th",   "vi"): PROMPT_AUTO_TO_VI,
    ("fr",   "vi"): PROMPT_AUTO_TO_VI,
    ("es",   "vi"): PROMPT_AUTO_TO_VI,
    ("de",   "vi"): PROMPT_AUTO_TO_VI,
    # → Tiếng Anh
    ("auto", "en"): PROMPT_AUTO_TO_EN,
    ("vi",   "en"): PROMPT_VI_TO_EN,
    ("zh",   "en"): PROMPT_ZH_TO_EN,
    ("en",   "en"): PROMPT_AUTO_TO_EN,   # Anh→Anh (phiên âm thuần)
    ("ja",   "en"): PROMPT_AUTO_TO_EN,
    ("ko",   "en"): PROMPT_AUTO_TO_EN,
    ("th",   "en"): PROMPT_AUTO_TO_EN,
    ("fr",   "en"): PROMPT_AUTO_TO_EN,
    ("es",   "en"): PROMPT_AUTO_TO_EN,
    ("de",   "en"): PROMPT_AUTO_TO_EN,
})


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
        preferred_model: Optional[str] = "gemini-3.8-flash",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ):
        self.client = genai.Client(api_key=api_key)
        self.preferred_model = preferred_model or "gemini-3.8-flash"
        self.progress_callback = progress_callback

    def _report(self, pct: float, message: str):
        if self.progress_callback:
            self.progress_callback(pct, message)

    def process_video(
        self,
        video_path: str,
        source_lang: str = "zh",
        target_lang: str = "vi",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Upload video lên Gemini, phiên âm/dịch theo source_lang → target_lang.
          source_lang: "auto"|"zh"|"en"|"vi"|"ja"|"ko"|"th"|"fr"|"es"|"de"
          target_lang:  "vi" (Tiếng Việt) | "en" (Tiếng Anh)
        Trả về nội dung SRT theo target_lang.
        """
        if is_cancelled and is_cancelled():
            raise InterruptedError("Tiến trình đã bị hủy bởi người dùng.")

        # Tra cứu prompt theo (source, target); fallback về auto → vi
        prompt = PROMPTS.get(
            (source_lang, target_lang),
            PROMPTS.get(("auto", target_lang), PROMPT_AUTO_TO_VI),
        )

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

        video_file = None
        try:
            # Bước 1: Upload file lên Gemini File API
            self._report(0.05, "Đang upload video lên Gemini AI...")
            if is_cancelled and is_cancelled():
                raise InterruptedError("Tiến trình đã bị hủy bởi người dùng.")
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
                if is_cancelled and is_cancelled():
                    raise InterruptedError("Tiến trình đã bị hủy bởi người dùng.")

                state_name = getattr(video_file.state, "name", str(video_file.state))
                if state_name != "PROCESSING":
                    break

                # Ngủ từng nhịp 0.5s để phát hiện hủy ngay lập tức
                for _ in range(10):
                    if is_cancelled and is_cancelled():
                        raise InterruptedError("Tiến trình đã bị hủy bởi người dùng.")
                    time.sleep(0.5)

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
            target_label = "Tiếng Anh" if target_lang == "en" else "Tiếng Việt"
            if source_lang == "auto":
                status_msg = f"Gemini đang tự nhận diện ngôn ngữ và tạo phụ đề {target_label}..."
            elif source_lang == "vi" and target_lang == "en":
                status_msg = "Gemini đang phiên âm và dịch Tiếng Việt → Tiếng Anh..."
            elif source_lang == "vi":
                status_msg = "Gemini đang lắng nghe và phiên âm phụ đề Tiếng Việt..."
            elif source_lang == "en" and target_lang == "vi":
                status_msg = "Gemini đang phiên âm và dịch Tiếng Anh → Tiếng Việt..."
            elif source_lang == "zh" and target_lang == "en":
                status_msg = "Gemini đang phiên âm và dịch Tiếng Trung → Tiếng Anh..."
            else:
                status_msg = f"Gemini đang phiên âm và dịch sang {target_label}..."
            self._report(0.5, status_msg)

            # Danh sách model theo thứ tự ưu tiên: Ưu tiên Gemini 3.8 Flash mới nhất, thông minh nhất
            all_candidate_models = [
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.6-flash",
                "gemini-3.5-flash",
                "gemini-flash-latest",
            ]
            pref = getattr(self, "preferred_model", "gemini-3.8-flash")
            if pref and pref != "auto" and pref in all_candidate_models:
                models_to_try = [pref] + [m for m in all_candidate_models if m != pref]
            else:
                models_to_try = all_candidate_models

            response = None
            last_err = None

            for m_idx, model_name in enumerate(models_to_try):
                # Thử tối đa 2 lần cho mỗi model nếu gặp 503 / 429
                for attempt in range(2):
                    try:
                        self._report(
                            min(0.85, 0.50 + (m_idx * 0.08) + (attempt * 0.04)),
                            f"Đang phiên âm & dịch với AI ({model_name})...",
                        )
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=[video_file, prompt],
                            config=types.GenerateContentConfig(
                                temperature=0.0,
                            ),
                        )
                        if response and response.text:
                            break
                    except Exception as e:
                        last_err = e
                        err_str = str(e)

                        # Nếu API key sai thì ngắt ngay
                        if "API_KEY_INVALID" in err_str or "401" in err_str or "403" in err_str:
                            raise ValueError("API Key Gemini không hợp lệ. Vui lòng kiểm tra lại trong phần Cài đặt.")

                        # Nếu lỗi quá tải (503 UNAVAILABLE / 429 / 500), chờ 2s rồi retry 1 lần
                        is_overloaded = any(
                            x in err_str
                            for x in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "504", "DEADLINE_EXCEEDED"]
                        )
                        if is_overloaded and attempt == 0:
                            self._report(
                                0.55,
                                f"Model {model_name} đang tải cao (503/429), chờ 2s thử lại...",
                            )
                            time.sleep(2)
                            continue

                        # Nếu hết lượt của model này mà còn model khác, thông báo chuyển model
                        if m_idx < len(models_to_try) - 1:
                            next_model = models_to_try[m_idx + 1]
                            self._report(
                                0.58,
                                f"Model {model_name} đang bận, tự động chuyển sang {next_model}...",
                            )
                        break

                if response and response.text:
                    break

            # Dọn dẹp file đã upload trên Gemini
            try:
                self.client.files.delete(name=video_file.name)
            except Exception:
                pass  # Không quan trọng nếu cleanup thất bại

            if response is None or not getattr(response, "text", None):
                raise RuntimeError(
                    f"Máy chủ Gemini đang quá tải tạm thời (503/Demand Spike): {last_err}.\n"
                    "Hệ thống đã tự động thử các model dự phòng. "
                    "Sếp vui lòng nhấn 'BẮT ĐẦU DỊCH' thử lại sau vài giây hoặc kiểm tra lại kết nối mạng."
                )

            self._report(0.9, "Đã tạo phụ đề xong, đang chuẩn hóa SRT...")

            # Làm sạch và validate SRT
            srt_content = clean_srt_response(response.text)
            if not srt_content or len(srt_content.strip()) < 20:
                target_label = "Tiếng Anh" if target_lang == "en" else "Tiếng Việt"
                if source_lang == "auto":
                    lang_note = "Video không có lời thoại rõ ràng"
                elif source_lang == "vi" and target_lang == "vi":
                    lang_note = "Video không có lời thoại tiếng Việt"
                elif source_lang == "en":
                    lang_note = "Video không có tiếng Anh"
                elif source_lang == "zh":
                    lang_note = "Video không có tiếng Trung"
                else:
                    lang_note = f"Video không có lời thoại ngôn ngữ đã chọn"
                raise ValueError(
                    f"Gemini không tạo được phụ đề {target_label}.\n"
                    "Có thể do:\n"
                    f"  • {lang_note}\n"
                    "  • Chất lượng âm thanh quá thấp hoặc bị lẫn tạp âm\n"
                    "  • Video quá ngắn (< 1 giây)"
                )

            return srt_content

        finally:
            if video_file:
                try:
                    self.client.files.delete(name=video_file.name)
                except Exception:
                    pass
            if clean_temp_file and os.path.exists(clean_temp_file):
                try:
                    os.remove(clean_temp_file)
                except Exception:
                    pass

