"""
utils/config.py — Quản lý cài đặt ứng dụng Vietsub AI
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".vietsub_ai"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "tts_voice": "vi-VN-HoaiMyNeural",
    "audio_mode": "mix",          # "mix" | "replace"
    "original_volume": 0.3,       # Âm lượng tiếng gốc khi mix
    "tts_volume": 1.0,            # Âm lượng giọng TTS
    "output_dir": str(Path.home() / "Desktop"),
}


def load_config() -> dict:
    """Đọc cài đặt từ file JSON. Tạo mới nếu chưa có."""
    CONFIG_DIR.mkdir(exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Merge với default để đảm bảo các key mới luôn có
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    """Ghi cài đặt vào file JSON."""
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
