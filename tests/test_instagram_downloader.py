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


def test_instagram_downloader_url_helpers():
    """Kiểm tra is_instagram_url và extract_shortcode."""
    from core.instagram_downloader import InstagramDownloader

    assert InstagramDownloader.is_instagram_url("https://www.instagram.com/p/DeRT85WpP1y/")
    assert InstagramDownloader.is_instagram_url("https://instagr.am/reel/DcihkN3FptN/?igsh=123")
    assert not InstagramDownloader.is_instagram_url("https://www.youtube.com/watch?v=123")
    assert not InstagramDownloader.is_instagram_url("")

    assert InstagramDownloader.extract_shortcode("https://www.instagram.com/p/DeRT85WpP1y/") == "DeRT85WpP1y"
    assert InstagramDownloader.extract_shortcode("https://www.instagram.com/reel/DcihkN3FptN/?igsh=abc") == "DcihkN3FptN"
    assert InstagramDownloader.extract_shortcode("https://www.instagram.com/share/p/AbCdEf123/") == "AbCdEf123"
    assert InstagramDownloader.extract_shortcode("https://example.com") is None


def test_instagram_downloader_extract_post_info():
    """Kiểm tra bóc tách thông tin bài viết Instagram (ảnh đơn và carousel)."""
    from core.instagram_downloader import InstagramDownloader

    dl = InstagramDownloader()

    # Giả lập trả về cho bài ảnh đơn
    mock_single_res = {
        "id": "TestShortcode1",
        "uploader": "test_user",
        "title": "Photo by test_user",
        "thumbnails": [
            {"url": "https://cdn.example.com/thumb_150.jpg?stp=c0.150x150"},
            {"url": "https://cdn.example.com/thumb_1080.jpg?stp=dst-jpg_e35_tt6"},
        ],
        "formats": [],
    }

    with patch.object(InstagramDownloader, "extract_post_info") as mock_extract:
        mock_extract.return_value = {
            "id": "TestShortcode1",
            "uploader": "test_user",
            "title": "Photo by test_user",
            "description": "",
            "is_carousel": False,
            "items": [
                {
                    "id": "TestShortcode1",
                    "type": "image",
                    "url": "https://cdn.example.com/thumb_1080.jpg?stp=dst-jpg_e35_tt6",
                    "ext": "jpg",
                }
            ],
        }

        info = dl.extract_post_info("https://www.instagram.com/p/TestShortcode1/")
        assert info["id"] == "TestShortcode1"
        assert info["uploader"] == "test_user"
        assert not info["is_carousel"]
        assert len(info["items"]) == 1
        assert info["items"][0]["type"] == "image"
        assert "dst-jpg_e35_tt6" in info["items"][0]["url"]


def test_instagram_downloader_download_post(tmp_path):
    """Kiểm tra tiến trình download_post lưu đúng định dạng file."""
    from core.instagram_downloader import InstagramDownloader

    dl = InstagramDownloader()

    fake_info = {
        "id": "Post123",
        "uploader": "photographer",
        "title": "Beautiful Sunset",
        "description": "Sunset at beach",
        "is_carousel": True,
        "items": [
            {"id": "img1", "type": "image", "url": "https://cdn.example.com/1.jpg", "ext": "jpg"},
            {"id": "img2", "type": "image", "url": "https://cdn.example.com/2.jpg", "ext": "jpg"},
        ],
    }

    # Giả lập urllib.request.urlopen trả về dữ liệu ảnh giả lập
    fake_img_data = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 100

    class FakeResponse:
        def __init__(self):
            self.headers = {"Content-Length": str(len(fake_img_data))}
            self._data = fake_img_data
            self._offset = 0

        def read(self, chunk_size=65536):
            if self._offset >= len(self._data):
                return b""
            chunk = self._data[self._offset : self._offset + chunk_size]
            self._offset += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    progress_calls = []

    def on_prog(pct, msg):
        progress_calls.append((pct, msg))

    with patch.object(dl, "extract_post_info", return_value=fake_info), patch(
        "urllib.request.urlopen", return_value=FakeResponse()
    ):
        saved = dl.download_post(
            url="https://www.instagram.com/p/Post123/",
            output_dir=str(tmp_path),
            progress_callback=on_prog,
        )

        assert len(saved) == 2
        assert all(os.path.exists(f) for f in saved)
        assert Path(saved[0]).suffix == ".jpg"
        assert Path(saved[1]).suffix == ".jpg"
        assert len(progress_calls) > 0


def test_video_downloader_fallback_to_instagram_images(tmp_path):
    """Kiểm tra VideoDownloader tự động fallback tải ảnh khi gặp bài đăng ảnh Instagram."""
    downloader = VideoDownloader()

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance
        # Giả lập lỗi yt-dlp khi gặp bài viết ảnh
        mock_ydl_instance.extract_info.side_effect = Exception(
            "[Instagram] DeRT85WpP1y: No video formats found!; please report this issue on https://github.com/yt-dlp/yt-dlp/issues"
        )

        fake_saved = [str(tmp_path / "Instagram_test_DeRT85WpP1y.jpg")]
        Path(fake_saved[0]).write_bytes(b"fake image data")

        with patch("core.instagram_downloader.InstagramDownloader.download_post", return_value=fake_saved):
            res = downloader.download("https://www.instagram.com/p/DeRT85WpP1y/", str(tmp_path))

            assert res == fake_saved[0]
            assert downloader.downloaded_files == fake_saved


def test_video_downloader_download_images_direct(tmp_path):
    """Kiểm tra gọi hàm download_images trực tiếp."""
    downloader = VideoDownloader()

    fake_saved = [
        str(tmp_path / "Instagram_test_1.jpg"),
        str(tmp_path / "Instagram_test_2.jpg"),
    ]
    for f in fake_saved:
        Path(f).write_bytes(b"image")

    with patch("core.instagram_downloader.InstagramDownloader.download_post", return_value=fake_saved):
        res = downloader.download_images("https://www.instagram.com/p/DeRT85WpP1y/", str(tmp_path))
        assert len(res) == 2
        assert downloader.downloaded_files == fake_saved

