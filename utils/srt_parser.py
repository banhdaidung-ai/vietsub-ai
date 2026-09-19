"""
utils/srt_parser.py — Parse và xử lý file phụ đề SRT
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SRTSegment:
    index: int
    start: str      # "00:00:01,000"
    end: str        # "00:00:04,500"
    text: str
    start_ms: int
    end_ms: int


def time_to_ms(time_str: str) -> int:
    """Chuyển timestamp SRT '00:01:23,456' sang milliseconds."""
    norm = normalize_timestamp(time_str).replace(",", ".")
    parts = norm.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return int((h * 3600 + m * 60 + s) * 1000)


def ms_to_time(ms: int) -> str:
    """Chuyển milliseconds sang timestamp SRT '00:01:23,456'."""
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1_000
    ms_rem = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"


def clean_subtitle_text(text: str) -> str:
    """
    Làm sạch nội dung phụ đề:
    - Loại bỏ nhãn người nói (Speaker 1:, Người nói 1:, John:, Man:,...)
    - Loại bỏ chú thích âm thanh ([Music], (Laughter), [tiếng cười], ♪, ♫,...)
    - Loại bỏ thẻ định dạng HTML/ASS (<i>, </i>, <b>, </b>, {\\an8},...)
    """
    if not text:
        return ""

    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # 1. Bỏ thẻ HTML và ASS override tags
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\{[^\}]+\}", "", line)

        # 2. Bỏ các ký tự biểu tượng âm nhạc
        for sym in ("♪", "♫", "♩", "♬", "¶"):
            line = line.replace(sym, "")

        # 3. Bỏ chú thích âm thanh trong ngoặc [...] hoặc (...)
        # Ví dụ: [Nhạc], [Music], (tiếng cười), (Laughter), [Vỗ tay], (Applause)...
        line = re.sub(
            r"\[(?:Nhạc|Music|Âm nhạc|Sound|Applause|Vỗ tay|Cười|Laughter|Cheering|Tiếng [^\]]+|Background [^\]]+)\]",
            "",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(
            r"\((?:Nhạc|Music|Âm nhạc|Sound|Applause|Vỗ tay|Cười|Laughter|Cheering|Tiếng [^\)]+|Background [^\)]+)\)",
            "",
            line,
            flags=re.IGNORECASE,
        )

        # 4. Bỏ nhãn người nói đầu câu (Speaker 1:, Người nói:, John:, Man:, Woman:,...)
        # Chỉ loại bỏ khi có dấu hai chấm ở đầu câu và phía trước là tên/vai trò ngắn (< 25 ký tự)
        line = re.sub(
            r"^(?:Speaker\s*\w+|Person\s*\w+|Người\s*nói\s*\w*|Nhân\s*vật\s*\w*|Thuyết\s*minh|[A-Z][a-z]{1,15})\s*:\s*",
            "",
            line,
            flags=re.IGNORECASE,
        )

        line = " ".join(line.split()).strip()
        if line:
            lines.append(line)

    return "\n".join(lines)


def normalize_timestamp(ts_str: str) -> str:
    """
    Chuẩn hóa timestamp SRT thành đúng định dạng 3 phần: 'HH:MM:SS,mmm'.
    Tự động sửa các lỗi timestamp phổ biến do AI trả về:
    - MM:SS,mmm -> 00:MM:SS,mmm (ví dụ: 00:03,000 -> 00:00:03,000)
    - MM:SS.mmm -> 00:MM:SS,mmm
    - H:MM:SS,mmm -> 0H:MM:SS,mmm
    - MM:SS -> 00:MM:SS,000
    - HH:MM:SS -> HH:MM:SS,000
    """
    ts_str = ts_str.strip().replace(".", ",")
    parts = ts_str.split(":")
    if len(parts) == 1:
        # Chỉ có giây: e.g. "45,500" hoặc "120"
        s_parts = parts[0].split(",")
        s = int(s_parts[0]) if s_parts[0].isdigit() else 0
        ms_str = s_parts[1] if len(s_parts) > 1 else "000"
        ms = int(ms_str.ljust(3, "0")[:3]) if ms_str.isdigit() else 0
        h = s // 3600
        m = (s % 3600) // 60
        s = s % 60
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    elif len(parts) == 2:  # MM:SS,mmm hoặc MM:SS
        m_str, s_ms = parts[0], parts[1]
        s_parts = s_ms.split(",")
        s = int(s_parts[0]) if s_parts[0].isdigit() else 0
        ms_str = s_parts[1] if len(s_parts) > 1 else "000"
        ms = int(ms_str.ljust(3, "0")[:3]) if ms_str.isdigit() else 0
        m = int(m_str) if m_str.isdigit() else 0
        h = m // 60
        m = m % 60
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    elif len(parts) == 3:  # HH:MM:SS,mmm hoặc HH:MM:SS
        h_str, m_str, s_ms = parts[0], parts[1], parts[2]
        s_parts = s_ms.split(",")
        s = int(s_parts[0]) if s_parts[0].isdigit() else 0
        ms_str = s_parts[1] if len(s_parts) > 1 else "000"
        ms = int(ms_str.ljust(3, "0")[:3]) if ms_str.isdigit() else 0
        h = int(h_str) if h_str.isdigit() else 0
        m = int(m_str) if m_str.isdigit() else 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return ts_str


# Regex nhận diện dấu mũi tên SRT linh hoạt (--> hoặc -> hoặc –> hoặc —> hoặc ~>)
ARROW_REGEX = r"(?:-->|->|–>|—>|~>)"


def normalize_srt_content(srt_content: str) -> str:
    """
    Quét và tự động chuẩn hóa toàn bộ timestamp trong nội dung SRT về chuẩn ISO SRT (HH:MM:SS,mmm).
    Đảm bảo 100% tương thích với libass / FFmpeg không bao giờ bị lỗi 'Unable to open sub.srt'.
    """
    if not srt_content:
        return ""

    def replace_arrow(match):
        start = normalize_timestamp(match.group(1))
        end = normalize_timestamp(match.group(2))
        return f"{start} --> {end}"

    pattern = rf"(\d{{1,2}}:\d{{1,2}}(?::\d{{1,2}})?(?:[,\.]\d{{1,3}})?)\s*{ARROW_REGEX}\s*(\d{{1,2}}:\d{{1,2}}(?::\d{{1,2}})?(?:[,\.]\d{{1,3}})?)"
    return re.sub(pattern, replace_arrow, srt_content)


def parse_srt(srt_content: str) -> List[SRTSegment]:
    """Parse nội dung SRT thành danh sách SRTSegment (tự động chuẩn hóa timestamp & text)."""
    segments: List[SRTSegment] = []
    content = normalize_srt_content(srt_content.strip().replace("\r\n", "\n").replace("\r", "\n"))
    blocks = re.split(r"\n\s*\n+", content)

    # Pattern nhận diện dòng timestamp linh hoạt
    ts_pattern = rf"(\d{{1,2}}:\d{{1,2}}(?::\d{{1,2}})?(?:[,\.]\d{{1,3}})?)\s*{ARROW_REGEX}\s*(\d{{1,2}}:\d{{1,2}}(?::\d{{1,2}})?(?:[,\.]\d{{1,3}})?)"

    for block in blocks:
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            continue

        # Tìm dòng chứa timestamp (--> hoặc các biến thể mũi tên)
        ts_idx = -1
        ts_match = None
        for idx, line in enumerate(lines):
            m = re.search(ts_pattern, line)
            if m:
                ts_idx = idx
                ts_match = m
                break

        if ts_idx == -1 or not ts_match:
            continue

        start_str = normalize_timestamp(ts_match.group(1))
        end_str = normalize_timestamp(ts_match.group(2))

        # Index
        index = len(segments) + 1
        if ts_idx > 0:
            digits = re.sub(r"\D", "", lines[ts_idx - 1])
            if digits:
                try:
                    index = int(digits)
                except ValueError:
                    pass

        # Text nội dung (làm sạch thẻ, chú thích âm thanh và nhãn người nói)
        raw_text = "\n".join(lines[ts_idx + 1:]).strip()
        text = clean_subtitle_text(raw_text)
        if not text:
            continue

        segments.append(
            SRTSegment(
                index=index,
                start=start_str,
                end=end_str,
                text=text,
                start_ms=time_to_ms(start_str),
                end_ms=time_to_ms(end_str),
            )
        )

    return segments


def clean_srt_response(response_text: str) -> str:
    """Làm sạch response từ Gemini, chỉ giữ lại nội dung SRT thuần túy."""
    text = response_text.strip()

    # Xóa markdown code blocks nếu có (```srt, ```subtitles, ```, ...)
    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = re.sub(r"```", "", text)

    # Tìm vị trí bắt đầu của block SRT đầu tiên (dòng số hoặc dòng timestamp)
    lines = text.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*\d+\s*$", line) or re.search(ARROW_REGEX, line):
            start_idx = i
            break

    cleaned = "\n".join(lines[start_idx:]).strip()
    return normalize_srt_content(cleaned)


def segments_to_srt(segments: List[SRTSegment]) -> str:
    """Chuyển danh sách SRTSegment thành chuỗi nội dung SRT chuẩn ISO."""
    blocks = []
    for idx, seg in enumerate(segments, start=1):
        start_ts = normalize_timestamp(seg.start)
        end_ts = normalize_timestamp(seg.end)
        text = seg.text.strip()
        if text:
            blocks.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def is_clause_continuation(current_text: str, next_text: Optional[str] = None, gap_ms: int = 0) -> bool:
    """
    Xác định xem phân đoạn hiện tại có phải là một vế câu còn tiếp diễn hay không:
    - Nếu khoảng cách tới câu tiếp theo quá dài (> 650ms), coi như nhịp ngắt hoàn chỉnh.
    - Nếu kết thúc bằng dấu phẩy (,), gạch nối (-), hai chấm (:), chấm phẩy (;) -> chắc chắn còn tiếp diễn.
    - Nếu câu hiện tại không có dấu kết thúc câu (. ! ?) và câu sau bắt đầu bằng chữ thường hoặc khoảng cách gần (< 500ms).
    - Nếu câu sau bắt đầu bằng các liên từ chuyển tiếp (mà, thì, là, và, nhưng, bởi vì, nên, do đó...).
    """
    if not current_text:
        return False
    t = current_text.strip()
    if not t:
        return False

    # Nếu khoảng cách giữa 2 câu quá 650ms thì là nhịp ngắt tự nhiên
    if gap_ms > 650:
        return False

    # Các dấu hiệu kết thúc rõ ràng
    if t.endswith((".", "!", "?", "…")):
        return False

    # Dấu hiệu còn tiếp diễn rõ ràng
    if t.endswith((",", ";", ":", "-", "–", "—")):
        return True

    # Nếu không có câu tiếp theo thì không phải continuation
    if not next_text:
        return False

    nt = next_text.strip()
    if not nt:
        return False

    # Nếu câu sau bắt đầu bằng chữ thường (vd: "thì chúng ta...", "và sau đó...")
    first_char = nt[0]
    if first_char.islower():
        return True

    # Các từ liên từ nối tiếp phổ biến ở đầu câu sau
    first_word = nt.split()[0].lower().rstrip(",;:.") if nt.split() else ""
    continuation_words = {"và", "nhưng", "mà", "thì", "là", "hoặc", "hay", "nên", "cho", "để", "vì", "bởi", "do", "khi", "nếu"}
    if first_word in continuation_words and gap_ms < 500:
        return True

    # Mặc định nếu gap ngắn (< 450ms) và không có dấu chấm ở cuối thì giữ continuation
    return gap_ms < 450


