"""
tests/test_instagram_downloader.py — Bộ kiểm thử tính năng tải Instagram Reels / Video
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.downloader import VideoDownloader, _find_cookie_file


def test_find_cookie_file(tmp_path):
    """Kiểm tra logic tự động dò tìm file cookies.txt."""
    # Không có file
    assert _find_cookie_file(str(tmp_path)) is None

    # Tạo file rỗng -> không nhận
    empty_cookie = tmp_path / "cookies.txt"
    empty_cookie.write_text("")
    assert _find_cookie_file(str(tmp_path)) is None

    # Tạo file có nội dung -> nhận diện đúng
    empty_cookie.write_text("# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t12345\n")
    assert _find_cookie_file(str(tmp_path)) == str(empty_cookie)


def test_downloader_ydl_opts_instagram_config():
    """Kiểm tra VideoDownloader cấu hình đúng extractor_args cho Instagram."""
    downloader = VideoDownloader()

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.extract_info.return_value = {"id": "test_id", "title": "Test Title"}
        mock_ydl_instance.prepare_filename.return_value = "/tmp/fake_video.mp4"

        # Giả lập file tồn tại
        with patch.object(Path, "exists", return_value=True):
            res = downloader.download("https://www.instagram.com/reel/DcihkN3FptN/", "/tmp")

        # Kiểm tra options truyền cho yt_dlp
        call_args = mock_ydl_cls.call_args[0][0]
        assert "extractor_args" in call_args
        assert "instagram" in call_args["extractor_args"]
        assert call_args["extractor_args"]["instagram"].get("app_id") == ["ios"]


def test_downloader_audio_only_instagram_config():
    """Kiểm tra download_audio_only cũng cấu hình đúng extractor_args cho Instagram."""
    downloader = VideoDownloader()

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.extract_info.return_value = {"id": "test_id", "title": "Test Title"}
        mock_ydl_instance.prepare_filename.return_value = "/tmp/fake_audio.mp3"

        with patch.object(Path, "exists", return_value=True):
            res = downloader.download_audio("https://www.instagram.com/reel/DcihkN3FptN/", "/tmp")

        call_args = mock_ydl_cls.call_args[0][0]
        assert "extractor_args" in call_args
        assert "instagram" in call_args["extractor_args"]
        assert call_args["extractor_args"]["instagram"].get("app_id") == ["ios"]


def test_instagram_friendly_error_message():
    """Kiểm tra thông báo lỗi thân thiện khi Instagram yêu cầu đăng nhập."""
    downloader = VideoDownloader()

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.extract_info.side_effect = Exception("The webpage request was redirected to the login page. You have exceeded the rate-limit for accessing posts anonymously.")

        with pytest.raises(RuntimeError) as exc_info:
            downloader.download("https://www.instagram.com/reel/DcihkN3FptN/", "/tmp")

        err_text = str(exc_info.value)
        assert "Video Instagram này không thể tải do bị giới hạn truy cập ẩn danh" in err_text
        assert "cookies.txt" in err_text
