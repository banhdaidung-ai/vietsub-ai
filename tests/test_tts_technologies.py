"""
tests/test_tts_technologies.py — Kiểm tra tích hợp 2 Công nghệ lồng tiếng AI:
1. Microsoft AI (Chuẩn Việt - Tốc độ & Cao độ)
2. Google Gemini AI (Biểu cảm điện ảnh & Fallback tự động)
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.tts_generator import TTSGenerator
from utils.config import DEFAULT_CONFIG, load_config, save_config
from utils.srt_parser import SRTSegment


def test_config_dual_tts_keys():
    """Kiểm tra các trường cấu hình lồng tiếng mới."""
    cfg = load_config()
    assert "tts_technology" in cfg
    assert "tts_voice_gemini" in cfg
    assert "tts_speed" in cfg
    assert "tts_pitch" in cfg
    assert cfg["tts_technology"] in ["edge", "gemini"]


def test_text_smoothing_logic():
    """Kiểm tra làm mượt câu thoại tránh hụt hơi / ngắt quãng giữa câu."""
    gen = TTSGenerator()
    
    # Đoạn giữa câu không có dấu kết thúc -> nối dấu phẩy để giữ cao độ
    smoothed = gen._smooth_segment_text("Xin chào các bạn", is_mid_sentence=True)
    assert smoothed == "Xin chào các bạn,"
    
    # Đoạn cuối câu hoặc có dấu kết thúc tự nhiên -> giữ nguyên
    assert gen._smooth_segment_text("Xin chào các bạn", is_mid_sentence=False) == "Xin chào các bạn"
    assert gen._smooth_segment_text("Thật tuyệt vời!", is_mid_sentence=True) == "Thật tuyệt vời!"
    assert gen._smooth_segment_text("Bạn có khỏe không?", is_mid_sentence=True) == "Bạn có khỏe không?"
    assert gen._smooth_segment_text("Tôi đang đi học...", is_mid_sentence=True) == "Tôi đang đi học..."


def test_tts_generator_init_edge():
    """Kiểm tra khởi tạo công nghệ Microsoft AI với tốc độ & cao độ tùy chỉnh."""
    gen = TTSGenerator(
        voice="vi-VN-NamMinhNeural",
        tts_technology="edge",
        speed="+10%",
        pitch="-2Hz",
    )
    assert gen.tts_technology == "edge"
    assert gen.voice == "vi-VN-NamMinhNeural"
    assert gen.speed == "+10%"
    assert gen.pitch == "-2Hz"


def test_tts_generator_init_gemini():
    """Kiểm tra khởi tạo công nghệ Google Gemini AI."""
    gen = TTSGenerator(
        voice="Charon",
        tts_technology="gemini",
        api_key="fake-test-key-12345",
    )
    assert gen.tts_technology == "gemini"
    assert gen.voice == "Charon"
    assert gen.api_key == "fake-test-key-12345"


def test_gemini_fallback_to_edge_on_error():
    """Kiểm tra cơ chế tự động chuyển đổi sang Microsoft AI khi Gemini gặp sự cố."""
    gen = TTSGenerator(
        voice="Aoede",
        tts_technology="gemini",
        api_key="invalid-key",
    )
    
    # Mock _generate_single_gemini_tts để giả lập ném ra lỗi (quota/mạng)
    with patch.object(gen, "_generate_single_gemini_tts", side_effect=Exception("429 Quota Exceeded")):
        with patch.object(gen, "_generate_single_edge_tts", return_value=True) as mock_edge:
            out_file = os.path.join(tempfile.gettempdir(), "test_fallback.mp3")
            success = gen.generate_single_segment("Xin chào Sếp", out_file)
            
            assert success is True
            # Kiểm tra xem có tự động gọi sang Edge-TTS không
            mock_edge.assert_called_once()


def test_settings_dialog_ui_switch():
    """Kiểm tra logic giao diện SettingsDialog khi chuyển đổi qua lại giữa 2 công nghệ."""
    import customtkinter as ctk
    from gui.settings_dialog import SettingsDialog
    
    root = ctk.CTk()
    root.withdraw()
    
    test_config = {
        "gemini_api_key": "test_key",
        "gemini_model": "auto",
        "tts_technology": "edge",
        "tts_voice": "vi-VN-HoaiMyNeural",
        "tts_voice_gemini": "Aoede",
        "tts_speed": "+0%",
        "tts_pitch": "+0Hz",
        "audio_mode": "mix",
        "original_volume": 0.3,
        "tts_volume": 1.0,
        "subtitle_font_size": 24,
        "subtitle_margin_v": 30,
        "output_dir": "",
        "export_srt": True,
        "export_txt": False,
        "review_subtitles": False,
    }
    
    saved_config = {}
    def on_save(cfg):
        nonlocal saved_config
        saved_config = cfg
        
    dialog = SettingsDialog(root, test_config, on_save)
    
    # Ban đầu là edge
    assert dialog.tts_tech_var.get() == "edge"
    assert "Microsoft Edge" in dialog.lbl_voice_title.cget("text")
    assert "vi-VN-HoaiMyNeural" in dialog.voice_display_var.get()
    
    # Chuyển sang Gemini AI
    dialog._on_tts_tech_change("🎭 Google Gemini AI (Biểu Cảm)")
    assert dialog.tts_tech_var.get() == "gemini"
    assert "Gemini" in dialog.lbl_voice_title.cget("text")
    assert "Aoede" in dialog.voice_display_var.get()
    
    # Đổi giọng Gemini sang Charon
    dialog.voice_display_var.set("Charon (Nam - Trầm sâu, điện ảnh)")
    
    # Lưu cấu hình (mock save_config để không ghi đè cấu hình thực của máy)
    with patch("gui.settings_dialog.save_config"):
        dialog._save()
    assert saved_config["tts_technology"] == "gemini"
    assert saved_config["tts_voice_gemini"] == "Charon"
    
    root.destroy()


def test_tts_silence_insertion_on_all_retries_failure():
    """Kiểm tra Phương án A: Khi tất cả retry đều thất bại, hệ thống chèn file im lặng (silence) để giữ timeline."""
    import shutil
    from utils.srt_parser import SRTSegment
    from utils.ffmpeg_check import get_ffmpeg_path

    logs = []
    def log_cb(msg):
        logs.append(msg)

    gen = TTSGenerator(
        voice="vi-VN-HoaiMyNeural",
        tts_technology="edge",
        log_callback=log_cb,
    )

    ffmpeg = get_ffmpeg_path() or "ffmpeg"
    tmp_dir = tempfile.mkdtemp()
    try:
        silence_file = os.path.join(tmp_dir, "silence_test.mp3")
        ok = gen._create_silence_audio(ffmpeg, 1.2, silence_file)
        assert ok is True
        assert os.path.exists(silence_file)
        assert os.path.getsize(silence_file) > 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_check_ffmpeg_caching():
    """Kiểm tra chức năng bộ nhớ đệm FFmpeg phản hồi siêu tốc."""
    from utils.ffmpeg_check import check_ffmpeg, clear_ffmpeg_cache

    clear_ffmpeg_cache()
    ok1, msg1 = check_ffmpeg()
    assert ok1 is True

    # Lần 2 lấy từ cache
    ok2, msg2 = check_ffmpeg()
    assert ok2 is True
    assert msg1 == msg2

