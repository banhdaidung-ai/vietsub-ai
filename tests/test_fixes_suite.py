import os
import sys
import unittest
from pathlib import Path

from core.downloader import extract_universal_url
from gui.completion_dialog import _reveal_file, _open_file


class TestFixesSuite(unittest.TestCase):
    def test_extract_universal_url_various_formats(self):
        # 1. Direct URL
        self.assertEqual(
            extract_universal_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        # 2. TikTok share text
        tiktok_text = "Check out this amazing video on TikTok! https://vt.tiktok.com/ZSjabcdef/ Let's go!"
        self.assertEqual(
            extract_universal_url(tiktok_text),
            "https://vt.tiktok.com/ZSjabcdef/",
        )

        # 3. Douyin share text
        douyin_text = "7.11 复制打开抖音，看看【小明的作品】 https://v.douyin.com/iABCDEF/ 03/12 l@s.ok"
        self.assertEqual(
            extract_universal_url(douyin_text),
            "https://v.douyin.com/iABCDEF/",
        )

        # 4. Trailing punctuation
        self.assertEqual(
            extract_universal_url("Link: (https://facebook.com/watch/?v=12345)."),
            "https://facebook.com/watch/?v=12345",
        )

        # 5. Empty or invalid
        self.assertIsNone(extract_universal_url(""))
        self.assertIsNone(extract_universal_url("Just plain text without link"))

    def test_completion_dialog_reveal_file_does_not_crash(self):
        # Test with empty path
        _reveal_file("")

        # Test with existing directory
        test_dir = str(Path(__file__).parent)
        _reveal_file(test_dir)

        # Test with existing file
        _reveal_file(__file__)

        # Test _open_file with empty path
        _open_file("")

    def test_ffmpeg_processor_cancellation(self):
        from core.ffmpeg_processor import _run_ffmpeg_cancellable

        # Check immediate cancellation
        with self.assertRaises(InterruptedError):
            _run_ffmpeg_cancellable(["echo", "hello"], is_cancelled=lambda: True)

    def test_tts_prepare_text_prosody_stabilization(self):
        from core.tts_generator import TTSGenerator
        tts = TTSGenerator()

        # 1. Triệt tiêu dấu cảm thán ! thành dấu chấm . để tránh vút cao độ
        self.assertEqual(
            tts._prepare_text_for_edge_tts("Xin chào các bạn!"),
            "Xin chào các bạn."
        )
        self.assertEqual(
            tts._prepare_text_for_edge_tts("Thật là tuyệt vời quá đi!!!"),
            "Thật là tuyệt vời quá đi."
        )

        # 2. Chuyển đổi dấu ba chấm ... thành .
        self.assertEqual(
            tts._prepare_text_for_edge_tts("Ngày xửa ngày xưa..."),
            "Ngày xửa ngày xưa."
        )

        # 3. Giữ nguyên dấu hỏi ?
        self.assertEqual(
            tts._prepare_text_for_edge_tts("Bạn có khỏe không?"),
            "Bạn có khỏe không?"
        )

        # 4. Tự động thêm dấu chấm cho câu trần thuật không dấu
        self.assertEqual(
            tts._prepare_text_for_edge_tts("Hôm nay chúng ta cùng học nấu ăn"),
            "Hôm nay chúng ta cùng học nấu ăn."
        )

        # 5. Loại bỏ dấu kết thúc dở dang ở cuối
        self.assertEqual(
            tts._prepare_text_for_edge_tts("Cụm từ này: "),
            "Cụm từ này."
        )

    def test_tts_master_audio_track_filter(self):
        from core.tts_generator import TTSGenerator
        from utils.ffmpeg_check import get_ffmpeg_path
        import tempfile
        import subprocess

        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            return

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_mp3 = f.name

        try:
            # Tạo 1s âm thanh mẫu
            cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "1.0", "-c:a", "libmp3lame", tmp_mp3]
            subprocess.run(cmd, check=True, capture_output=True)

            tts = TTSGenerator()
            tts._master_audio_track(ffmpeg, tmp_mp3, 1.0)
            self.assertTrue(os.path.exists(tmp_mp3))
            self.assertGreater(os.path.getsize(tmp_mp3), 0)
        finally:
            if os.path.exists(tmp_mp3):
                os.remove(tmp_mp3)

    def test_hidden_subprocess_integration(self):
        from core.tts_generator import run_hidden_subprocess as tts_run_hidden
        from utils.ffmpeg_check import run_hidden_subprocess as check_run_hidden
        from core.ffmpeg_processor import run_hidden_subprocess as proc_run_hidden
        from utils.platform_helper import run_hidden_subprocess

        self.assertIs(tts_run_hidden, run_hidden_subprocess)
        self.assertIs(check_run_hidden, run_hidden_subprocess)
        self.assertIs(proc_run_hidden, run_hidden_subprocess)


if __name__ == "__main__":
    unittest.main()

