"""
utils/config.py — Quản lý cài đặt ứng dụng Vietsub AI
"""

import json
import re
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".vietsub_ai"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "auto",  # "auto" (Tự động ưu tiên 3.8 -> 3.7 -> 3.6 -> 2.5) | "gemini-3.8-flash" | "gemini-3.7-flash" | "gemini-3.6-flash" | "gemini-2.5-flash"
    "tts_technology": "edge",     # "edge" (Microsoft AI Chuẩn Việt) | "gemini" (Google Gemini AI Biểu Cảm)
    "tts_voice": "vi-VN-HoaiMyNeural",
    "tts_voice_gemini": "Aoede",  # "Aoede" | "Kore" | "Charon" | "Fenrir" | "Puck"
    "tts_speed": "+0%",           # Tốc độ đọc (+0%, +10%, -10%...)
    "tts_pitch": "+0Hz",          # Cao độ giọng (+0Hz, -5Hz, +5Hz...)
    "audio_mode": "mix",          # "mix" | "replace"
    "original_volume": 0.3,       # Âm lượng tiếng gốc khi mix
    "tts_volume": 1.0,            # Âm lượng giọng TTS
    "output_dir": str(Path.home() / "Desktop"),
    "source_language": "zh",      # "zh" (Trung) | "en" (Anh) | "vi" (Việt)
    "target_language": "vi",      # "vi" (Việt) | "en" (Anh)
    "enable_tts": True,           # Có tạo giọng đọc AI hay không
    "subtitle_font_size": 10,     # Cỡ chữ phụ đề nhỏ gọn tầm 10 (mặc định 10)
    "subtitle_margin_v": 8,       # Khoảng cách đáy (mặc định 8 để nằm dưới phụ đề gốc)
    "download_quality": "best",   # "best" (Gốc/Cao nhất) | "1080p" | "720p" | "480p"
    "url_action_mode": "download_only",  # "download_only" | "download_audio" | "download_and_sub" | "download_and_separate"
    "audio_format": "mp3",        # "mp3" (320kbps) | "m4a" | "wav"
    "audio_bitrate": "320k",      # "320k" | "256k" | "192k"
    "export_srt": True,           # Có xuất file phụ đề .srt rời hay không
    "export_txt": True,           # Có xuất file văn bản .txt rời hay không
    "review_subtitles": False,    # Duyệt và chỉnh sửa phụ đề trước khi ghép video
    "subtitle_style_preset": "capcut_yellow",  # Mẫu kiểu chữ CapCut: "capcut_yellow" | "capcut_white" | "capcut_blackbox" | "capcut_cyan" | "capcut_orange" | "capcut_minimal"
}


def get_output_dir(config: dict) -> str:
    """
    Trả về thư mục xuất hợp lệ từ cấu hình.
    Tự động fallback về Desktop nếu rỗng, sai định dạng hoặc không thể ghi.
    """
    out = (config.get("output_dir") or "").strip()
    if not out:
        out = str(Path.home() / "Desktop")
    try:
        Path(out).mkdir(parents=True, exist_ok=True)
    except Exception:
        out = str(Path.home() / "Desktop")
        Path(out).mkdir(parents=True, exist_ok=True)
    return out


def load_config() -> dict:
    """Đọc cài đặt từ file JSON. Tạo mới nếu chưa có."""
    CONFIG_DIR.mkdir(exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Tự động nâng cấp model cũ 3.8 sang chế độ auto theo yêu cầu
            if saved.get("gemini_model") == "gemini-3.8-flash":
                saved["gemini_model"] = "auto"
            # Đảm bảo output_dir không rỗng
            if not saved.get("output_dir") or not str(saved.get("output_dir")).strip():
                saved["output_dir"] = str(Path.home() / "Desktop")
            # Merge với default để đảm bảo các key mới luôn có
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    """Ghi cài đặt vào file JSON."""
    CONFIG_DIR.mkdir(exist_ok=True)
    # Đảm bảo output_dir không rỗng khi lưu
    if not config.get("output_dir") or not str(config.get("output_dir")).strip():
        config["output_dir"] = str(Path.home() / "Desktop")
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def find_clean_raw_video(path_str: str) -> Optional[str]:
    """
    Tự động truy vết và tìm file video gốc sạch (chưa gắn phụ đề).
    Nếu đường dẫn đầu vào là file phụ đề .srt hoặc video đã được gắn sub (_sub_vi_, _vietsub_, _reburn_),
    hàm sẽ thông minh tìm kiếm video gốc ban đầu trong cùng thư mục hoặc thư mục cha để tránh bị chồng đè 2 lớp chữ.
    """
    if not path_str:
        return None
    p = Path(path_str)
    stem = p.stem
    # Khử bỏ các hậu tố đã gắn sub: _sub_vi_..., _vietsub_..., _reburn_...
    clean_stem = re.sub(r"_(sub_vi|vietsub|reburn)_\d{8}_\d{4,6}$", "", stem).strip()

    # Nếu file đưa vào là video và tên của nó không có hậu tố gắn sub, kiểm tra xem nó có tồn tại không
    if p.suffix.lower() in (".mp4", ".mkv", ".mov", ".webm", ".avi") and clean_stem == stem:
        if p.exists():
            return str(p)

    search_dirs = [p.parent, p.parent.parent] if p.parent else []
    stripped_goc = re.sub(r"^\[Gốc\]\s*", "", clean_stem)
    name_patterns = [clean_stem, stripped_goc, f"[Gốc] {stripped_goc}"]

    for d in search_dirs:
        if not d.exists():
            continue
        for ext in (".mp4", ".mkv", ".mov", ".webm", ".avi"):
            for name in name_patterns:
                candidate = d / f"{name}{ext}"
                if candidate.exists() and not re.search(r"_(sub_vi|vietsub|reburn)_\d{8}_\d{4,6}", candidate.name):
                    return str(candidate)
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".mov", ".webm", ".avi"):
                if not re.search(r"_(sub_vi|vietsub|reburn)_\d{8}_\d{4,6}", f.name):
                    prefix = clean_stem[:25]
                    if prefix and prefix in f.name:
                        return str(f)
    return None

