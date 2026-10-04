"""
tests/test_tiktok_downloader.py — Kiểm tra bộ nạp video & âm thanh TikTok chuyên dụng
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.downloader import VideoDownloader, extract_universal_url
from core.tiktok_downloader import TikTokDownloader, _safe_filename


class TestTikTokDownloader(unittest.TestCase):
    def test_is_tiktok_url(self):
        # Link chuẩn
        self.assertTrue(TikTokDownloader.is_tiktok_url("https://www.tiktok.com/@user/video/1234567890"))
        self.assertTrue(TikTokDownloader.is_tiktok_url("https://tiktok.com/@user/video/1234567890"))
        # Link rút gọn
        self.assertTrue(TikTokDownloader.is_tiktok_url("https://vt.tiktok.com/ZSjabcdef/"))
        self.assertTrue(TikTokDownloader.is_tiktok_url("https://vm.tiktok.com/ZMabcdef/"))
        self.assertTrue(TikTokDownloader.is_tiktok_url("https://www.tiktok.com/t/ZTabcdef/"))
        # Nền tảng khác
        self.assertFalse(TikTokDownloader.is_tiktok_url("https://www.youtube.com/watch?v=123456"))
        self.assertFalse(TikTokDownloader.is_tiktok_url("https://www.douyin.com/video/123456"))
        self.assertFalse(TikTokDownloader.is_tiktok_url(""))

    def test_extract_url(self):
        # Trích xuất từ văn bản chia sẻ chứa chữ tiếng Việt và ký tự @
        text = "Xem video này hay quá https://www.tiktok.com/@tugend.fashion/video/7689323033118461204 cực đẹp!"
        extracted = TikTokDownloader.extract_url(text)
        self.assertEqual(extracted, "https://www.tiktok.com/@tugend.fashion/video/7689323033118461204")

        # Trích xuất từ link rút gọn có dấu chấm cuối câu
        text_short = "Mua ngay: (https://vt.tiktok.com/ZSjabcdef/). Đừng bỏ lỡ!"
        extracted_short = TikTokDownloader.extract_url(text_short)
        self.assertEqual(extracted_short, "https://vt.tiktok.com/ZSjabcdef/")

    def test_safe_filename(self):
        raw = "Băng gối thể thao #banggoithethao #bogoithethao / bảo vệ: đầu gối * ? < > |"
        safe = _safe_filename(raw, max_len=50)
        for char in '\\/*?:"<>|#\r\n\t':
            self.assertNotIn(char, safe)
        self.assertTrue(len(safe) <= 50)

    @patch("core.tiktok_downloader.requests")
    def test_fetch_video_info_success(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "msg": "success",
            "data": {
                "id": "7689323033118461204",
                "title": "Băng gối thể thao",
                "hdplay": "https://cdn.tiktok.com/hd_video.mp4",
                "play": "https://cdn.tiktok.com/normal_video.mp4",
                "music": "https://cdn.tiktok.com/audio.mp3",
                "duration": 14,
            },
        }
        mock_requests.post.return_value = mock_resp

        dl = TikTokDownloader()
        info = dl.fetch_video_info("https://www.tiktok.com/@test/video/7689323033118461204")

        self.assertEqual(info["id"], "7689323033118461204")
        self.assertEqual(info["title"], "Băng gối thể thao")
        self.assertEqual(info["video_url"], "https://cdn.tiktok.com/hd_video.mp4")
        self.assertEqual(info["music_url"], "https://cdn.tiktok.com/audio.mp3")

    @patch("core.tiktok_downloader.TikTokDownloader.download_video")
    def test_video_downloader_routes_to_tiktok_downloader(self, mock_download_video):
        mock_download_video.return_value = "/tmp/test.mp4"

        vd = VideoDownloader()
        result = vd.download(
            url="https://www.tiktok.com/@tugend.fashion/video/7689323033118461204",
            output_dir="/tmp",
            quality="best",
        )
        self.assertEqual(result, "/tmp/test.mp4")
        mock_download_video.assert_called_once()

    @patch("core.tiktok_downloader.TikTokDownloader.download_audio")
    def test_audio_downloader_routes_to_tiktok_downloader(self, mock_download_audio):
        mock_download_audio.return_value = "/tmp/test.mp3"

        vd = VideoDownloader()
        result = vd.download_audio(
            url="https://www.tiktok.com/@tugend.fashion/video/7689323033118461204",
            output_dir="/tmp",
        )
        self.assertEqual(result, "/tmp/test.mp3")
        mock_download_audio.assert_called_once()


if __name__ == "__main__":
    unittest.main()
