"""
utils/srt_parser.py — Parse và xử lý file phụ đề SRT
"""

import re
from dataclasses import dataclass
from typing import List


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
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
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


def parse_srt(srt_content: str) -> List[SRTSegment]:
    """Parse nội dung SRT thành danh sách SRTSegment."""
    segments: List[SRTSegment] = []
    content = srt_content.strip().replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n+", content)

    for block in blocks:
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            continue

        # Tìm dòng chứa timestamp (-->)
        ts_idx = -1
        ts_match = None
        for idx, line in enumerate(lines):
            m = re.search(
                r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})",
                line,
            )
            if m:
                ts_idx = idx
                ts_match = m
                break

        if ts_idx == -1 or not ts_match:
            continue

        start_str = ts_match.group(1).replace(".", ",")
        end_str = ts_match.group(2).replace(".", ",")

        # Index
        index = len(segments) + 1
        if ts_idx > 0:
            digits = re.sub(r"\D", "", lines[ts_idx - 1])
            if digits:
                try:
                    index = int(digits)
                except ValueError:
                    pass

        # Text nội dung
        text = "\n".join(lines[ts_idx + 1:]).strip()
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
        if re.match(r"^\s*\d+\s*$", line) or "-->" in line:
            start_idx = i
            break

    return "\n".join(lines[start_idx:]).strip()

