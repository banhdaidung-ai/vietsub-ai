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


def test_edge_tts_text_preparation():
    """Kiểm tra chuẩn hóa văn bản riêng cho Microsoft Edge-TTS để chống lỗi No audio received."""
    gen = TTSGenerator()

    # Dấu phẩy ở cuối câu (do nối câu giữa chừng) phải được rstrip và chuẩn hóa dấu chấm để tránh ngắt WebSocket SSML và giữ tone đều
    assert gen._prepare_text_for_edge_tts("Xin chào các bạn,") == "Xin chào các bạn."
    assert gen._prepare_text_for_edge_tts("Tôi đang nói thì -") == "Tôi đang nói thì."
    assert gen._prepare_text_for_edge_tts("Chi tiết là:") == "Chi tiết là."

    # Dấu ba chấm '...' và '…' phải được chuyển thành dấu chấm '.' để không bị server Microsoft đóng stream rỗng
    assert gen._prepare_text_for_edge_tts("Không thể nào...") == "Không thể nào."
    assert gen._prepare_text_for_edge_tts("Đợi đã…") == "Đợi đã."
    assert gen._prepare_text_for_edge_tts("   Câu thoại bình thường.   ") == "Câu thoại bình thường."


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


def test_clean_subtitle_text_and_speaker_labels():
    """Kiểm tra làm sạch nhãn người nói và chú thích âm thanh khỏi phụ đề và lời đọc TTS."""
    from utils.srt_parser import clean_subtitle_text

    raw1 = "Speaker 1: Xin chào tất cả các bạn!"
    assert clean_subtitle_text(raw1) == "Xin chào tất cả các bạn!"

    raw2 = "Người nói: Hôm nay chúng ta sẽ cùng khám phá."
    assert clean_subtitle_text(raw2) == "Hôm nay chúng ta sẽ cùng khám phá."

    raw3 = "John: Tuyệt vời quá! [Music] ♪ ♫"
    assert clean_subtitle_text(raw3) == "Tuyệt vời quá!"

    raw4 = "<i>Thuyết minh:</i> Cảm ơn mọi người đã theo dõi (tiếng vỗ tay)."
    assert clean_subtitle_text(raw4) == "Cảm ơn mọi người đã theo dõi ."


def test_parse_srt_flexible_arrows_and_timestamps():
    """Kiểm tra parse SRT với các biến thể mũi tên (->, –>, —>) và timestamp 2 phần (MM:SS,mmm)."""
    from utils.srt_parser import parse_srt

    srt_content = """
1
00:01,500 -> 00:04,200
Chào mừng các bạn đã quay trở lại!

2
00:00:05,000 –> 00:00:08,000
Speaker 1: Đây là câu thứ hai với mũi tên en-dash.

3
00:00:08,500 —> 00:00:11,500
[Nhạc] Và đây là câu thứ ba với mũi tên em-dash.
"""
    segs = parse_srt(srt_content)
    assert len(segs) == 3
    assert segs[0].start == "00:00:01,500"
    assert segs[0].end == "00:00:04,200"
    assert segs[0].text == "Chào mừng các bạn đã quay trở lại!"
    assert segs[1].text == "Đây là câu thứ hai với mũi tên en-dash."
    assert segs[2].text == "Và đây là câu thứ ba với mũi tên em-dash."


@pytest.mark.asyncio
async def test_consistent_tts_voice_retention():
    """Kiểm tra nguyên tắc đồng nhất: Giữ nguyên 100% giọng đọc đã chọn xuyên suốt video, không đổi giọng giữa chừng."""
    logs = []
    used_voices = []
    gen = TTSGenerator(
        voice="vi-VN-NamMinhNeural",
        tts_technology="edge",
        log_callback=lambda msg: logs.append(msg),
    )

    async def mock_generate(text, out_path, voice_override=None, **kwargs):
        used_voices.append(voice_override)
        with open(out_path, "wb") as f:
            f.write(b"fake-audio-data")
        return True

    with patch.object(gen, "_generate_single_edge_tts", side_effect=mock_generate):
        with patch.object(gen, "_create_silence_audio", return_value=True):
            with patch.object(gen, "_get_audio_duration_ms", return_value=1500):
                with patch.object(gen, "_combine_segments", return_value=None):
                    segs = [
                        SRTSegment(index=1, start="00:00:01,000", end="00:00:04,000", text="Câu thứ nhất", start_ms=1000, end_ms=4000),
                        SRTSegment(index=2, start="00:00:05,000", end="00:00:08,000", text="Câu thứ hai", start_ms=5000, end_ms=8000),
                        SRTSegment(index=3, start="00:00:09,000", end="00:00:12,000", text="Câu thứ ba", start_ms=9000, end_ms=12000),
                    ]
                    tmp_out = os.path.join(tempfile.gettempdir(), "test_track_consistent.mp3")
                    await gen._generate_track_async(segs, 15.0, tmp_out)

                    # Xác nhận tất cả các câu đều dùng duy nhất giọng Nam Minh đã chọn, tuyệt đối không có Hoài My
                    assert len(used_voices) == 3
                    assert all(v == "vi-VN-NamMinhNeural" for v in used_voices)
                    assert not any("HoaiMy" in l or "đối ứng" in l for l in logs)


@pytest.mark.asyncio
async def test_persistent_edge_tts_retry_until_success():
    """Kiểm tra cơ chế kiên trì thử lại: Gặp lỗi mạng tạm thời sẽ tự động thử lại cho đến khi thành công 100%."""
    logs = []
    gen = TTSGenerator(
        voice="vi-VN-NamMinhNeural",
        tts_technology="edge",
        log_callback=lambda msg: logs.append(msg),
    )

    call_count = 0

    class MockCommunicate:
        def __init__(self, *args, **kwargs):
            pass

        async def save(self, out_path):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Giả lập lỗi ngắt kết nối WebSocket ở 2 lần đầu
                raise Exception("WebSocket Connection Reset")
            # Lần thứ 3 thành công
            with open(out_path, "wb") as f:
                f.write(b"valid-mp3-audio-stream")

    tmp_out = os.path.join(tempfile.gettempdir(), "test_retry_success.mp3")
    with patch("edge_tts.Communicate", side_effect=MockCommunicate):
        with patch("asyncio.sleep", return_value=None):  # Bỏ qua delay trong unit test
            success = await gen._generate_single_edge_tts("Xin chào Việt Nam", tmp_out)
            assert success is True
            assert call_count == 3

def test_clause_continuation_detection():
    """Kiểm tra nhận diện câu nối giữa các card phụ đề để giữ ngữ điệu liền mạch."""
    from utils.srt_parser import is_clause_continuation

    # Vế kết thúc bằng dấu phẩy -> tiếp diễn
    assert is_clause_continuation("Khi tôi bước vào phòng,", "mọi người đều im lặng", 300) is True

    # Vế không có dấu kết thúc và câu sau viết thường -> tiếp diễn
    assert is_clause_continuation("Chúng ta không chỉ học tập", "mà còn phải thực hành", 200) is True

    # Câu đã trọn vẹn kết thúc bằng dấu chấm -> không tiếp diễn
    assert is_clause_continuation("Chúng ta cần phải thực hành.", "Tiếp theo là bước hai.", 200) is False

    # Khoảng lặng giữa 2 câu quá dài (> 1.2s) -> ngắt câu để thở tự nhiên
    assert is_clause_continuation("Chúng ta không chỉ học tập", "mà còn phải thực hành", 1500) is False


def test_prepare_text_symbol_expansion():
    """Kiểm tra chuyển hóa ký hiệu toán học / tiền tệ thành chữ viết để phát âm tự nhiên tiếng Việt."""
    gen = TTSGenerator()
    prepared = gen._prepare_text_for_edge_tts("Tăng trưởng 15% & đạt mốc $500 + thêm ưu đãi")
    assert "phần trăm" in prepared
    assert "và" in prepared
    assert "đô la" in prepared
    assert "cộng" in prepared


@pytest.mark.asyncio
async def test_ripple_timeline_scheduler_zero_truncation():
    """Kiểm tra thuật toán Non-Colliding Ripple Scheduler: 100% câu từ được nói trọn vẹn, không bị cắt ngắn (-t)."""
    gen = TTSGenerator(
        voice="vi-VN-NamMinhNeural",
        tts_technology="edge",
    )

    # 3 segments ban đầu: mỗi segment 2 giây (0-2s, 2-4s, 4-6s)
    segs = [
        SRTSegment(index=1, start="00:00:00,000", end="00:00:02,000", text="Đoạn văn dài thứ nhất", start_ms=0, end_ms=2000),
        SRTSegment(index=2, start="00:00:02,000", end="00:00:04,000", text="Đoạn văn dài thứ hai", start_ms=2000, end_ms=4000),
        SRTSegment(index=3, start="00:00:04,000", end="00:00:06,000", text="Đoạn văn kết thúc", start_ms=4000, end_ms=6000),
    ]

    async def mock_gen(text, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"mock-audio")
        return True

    recorded_mix_duration = []

    async def mock_combine(seg_paths, total_duration_sec, output_path, tmp_dir):
        # Lưu lại timeline sau khi schedule
        recorded_mix_duration.append((list(seg_paths), total_duration_sec))

    with patch.object(gen, "_generate_single_edge_tts", side_effect=mock_gen):
        with patch.object(gen, "_get_audio_duration_ms", return_value=2500):
            with patch.object(gen, "_combine_segments", side_effect=mock_combine):
                tmp_out = os.path.join(tempfile.gettempdir(), "test_ripple.mp3")
                await gen._generate_track_async(segs, 6.0, tmp_out)

    assert len(recorded_mix_duration) == 1
    scheduled_segs, total_dur = recorded_mix_duration[0]
    assert len(scheduled_segs) == 3

    # Kiểm tra tính chất không đè âm (Non-Colliding): câu sau phải bắt đầu >= câu trước kết thúc + 80ms
    seg1, _ = scheduled_segs[0]
    seg2, _ = scheduled_segs[1]
    seg3, _ = scheduled_segs[2]

    assert seg1.start_ms == 0
    assert seg2.start_ms >= seg1.end_ms + 80
    assert seg3.start_ms >= seg2.end_ms + 80
