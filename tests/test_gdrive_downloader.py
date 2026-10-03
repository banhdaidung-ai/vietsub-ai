"""
tests/test_gdrive_downloader.py — Unit tests cho module tải Google Drive trực tiếp
"""

import os
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest

from core.gdrive_downloader import (
    GDriveDownloader,
    format_bytes,
    is_image_file,
    parse_gdrive_url,
)


def test_parse_gdrive_url_folder():
    urls = [
        "https://drive.google.com/drive/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
        "https://drive.google.com/drive/u/0/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
        "https://drive.google.com/drive/u/2/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P?usp=sharing",
        "https://drive.google.com/drive/mobile/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
    ]
    for url in urls:
        item_id, item_type = parse_gdrive_url(url)
        assert item_id == "1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P"
        assert item_type == "folder"


def test_parse_gdrive_url_file():
    urls = [
        "https://drive.google.com/file/d/1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M/view?usp=sharing",
        "https://drive.google.com/file/u/1/d/1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M/view",
        "https://docs.google.com/document/d/1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M/edit",
        "https://docs.google.com/spreadsheets/d/1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M/edit",
    ]
    for url in urls:
        item_id, item_type = parse_gdrive_url(url)
        assert item_id == "1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M"
        assert item_type == "file"


def test_parse_gdrive_url_plain_id_and_invalid():
    plain_id = "1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P"
    item_id, item_type = parse_gdrive_url(plain_id)
    assert item_id == plain_id

    # Invalid
    item_id, item_type = parse_gdrive_url("https://example.com/not-drive")
    assert item_id is None
    assert item_type == "unknown"


def test_is_image_file():
    assert is_image_file("photo.jpg") is True
    assert is_image_file("photo.JPEG") is True
    assert is_image_file("banner.png") is True
    assert is_image_file("design.psd") is True
    assert is_image_file("camera.RAW") is True
    assert is_image_file("vector.svg") is True
    assert is_image_file("image.webp") is True
    assert is_image_file("video.mp4") is False
    assert is_image_file("document.pdf") is False
    assert is_image_file("audio.mp3") is False


def test_format_bytes():
    assert format_bytes(500) == "500 B"
    assert "KB" in format_bytes(2048)
    assert "MB" in format_bytes(10 * 1024 * 1024)
    assert "GB" in format_bytes(2 * 1024 * 1024 * 1024)


def test_gdrive_downloader_skip_existing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Giả lập file đã tồn tại
        existing_file = os.path.join(tmp_dir, "img1.jpg")
        with open(existing_file, "w") as f:
            f.write("content")

        downloader = GDriveDownloader(max_workers=2)

        # Mock scan_folder
        mock_items = [
            {
                "id": "file_id_1",
                "rel_path": "img1.jpg",
                "local_path": existing_file,
                "name": "img1.jpg",
                "is_image": True,
            },
            {
                "id": "file_id_2",
                "rel_path": "img2.jpg",
                "local_path": os.path.join(tmp_dir, "img2.jpg"),
                "name": "img2.jpg",
                "is_image": True,
            },
        ]

        def fake_download(*args, **kwargs):
            out = kwargs.get("output")
            if out:
                with open(out, "w") as f:
                    f.write("downloaded")
            return out

        with patch.object(downloader, "scan_folder", return_value=mock_items):
            with patch("gdown.download", side_effect=fake_download) as mock_dl:
                stats = downloader.download(
                    url_or_id="https://drive.google.com/drive/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
                    output_dir=tmp_dir,
                    images_only=True,
                    skip_existing=True,
                )

                assert stats["total"] == 2
                assert stats["skipped"] == 1
                assert stats["success"] == 1
                assert mock_dl.call_count == 1


def test_gdrive_downloader_filter_images_only():
    with tempfile.TemporaryDirectory() as tmp_dir:
        downloader = GDriveDownloader(max_workers=2)

        mock_items = [
            {
                "id": "img1_id",
                "rel_path": "photo.png",
                "local_path": os.path.join(tmp_dir, "photo.png"),
                "name": "photo.png",
                "is_image": True,
            },
            {
                "id": "vid1_id",
                "rel_path": "clip.mp4",
                "local_path": os.path.join(tmp_dir, "clip.mp4"),
                "name": "clip.mp4",
                "is_image": False,
            },
        ]

        def fake_download(*args, **kwargs):
            out = kwargs.get("output")
            if out:
                with open(out, "w") as f:
                    f.write("downloaded")
            return out

        with patch.object(downloader, "scan_folder", return_value=mock_items):
            with patch("gdown.download", side_effect=fake_download):
                # Với images_only=True
                stats = downloader.download(
                    url_or_id="https://drive.google.com/drive/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
                    output_dir=tmp_dir,
                    images_only=True,
                    skip_existing=False,
                )
                assert stats["total"] == 1
                assert stats["success"] == 1


def test_gdrive_downloader_cancellation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        downloader = GDriveDownloader(max_workers=1)
        cancel_event = threading.Event()
        cancel_event.set()  # Đã hủy từ đầu

        mock_items = [
            {
                "id": "img1_id",
                "rel_path": "photo.png",
                "local_path": os.path.join(tmp_dir, "photo.png"),
                "name": "photo.png",
                "is_image": True,
            }
        ]

        with patch.object(downloader, "scan_folder", return_value=mock_items):
            stats = downloader.download(
                url_or_id="https://drive.google.com/drive/folders/1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
                output_dir=tmp_dir,
                cancel_event=cancel_event,
            )
            assert stats["cancelled"] is True
            assert stats["success"] == 0


def test_gdrive_auth_cookie_helpers():
    from core.gdrive_auth import (
        clear_cookies,
        has_valid_cookies,
        save_raw_cookie_string,
        GDRIVE_COOKIES_FILE,
    )
    from pathlib import Path

    # Dọn dẹp trước
    clear_cookies()
    assert has_valid_cookies() is False

    # Lưu cookie chuỗi
    sample_cookie = "SID=test_sid_123; HSID=test_hsid_456; SSID=test_ssid_789"
    ok = save_raw_cookie_string(sample_cookie)
    assert ok is True
    assert GDRIVE_COOKIES_FILE.exists()
    assert has_valid_cookies() is True

    # Dọn dẹp sau test
    clear_cookies()
    assert has_valid_cookies() is False


def test_gdown_monkey_patch_login_redirect():
    import importlib
    import sys
    from unittest.mock import MagicMock
    from gdown.exceptions import DownloadError

    df_mod = sys.modules.get("gdown.download_folder")
    if not df_mod:
        df_mod = importlib.import_module("gdown.download_folder")

    fake_res = MagicMock()
    fake_res.status_code = 200
    fake_res.text = "<html><head><title>Redirecting...</title></head><body></body></html>"

    fake_sess = MagicMock()
    fake_sess.get.return_value = fake_res

    with pytest.raises(DownloadError) as exc_info:
        df_mod._parse_embedded_folder_view(
            sess=fake_sess,
            folder_id="some_id",
            verify=True,
            timeout=5,
        )
    assert "AUTHENTICATION_REQUIRED" in str(exc_info.value)


def test_company_restricted_folder_error():
    from core.gdrive_downloader import GDriveDownloader
    from gdown.exceptions import DownloadError

    downloader = GDriveDownloader()
    with patch.object(downloader, "scan_folder", side_effect=DownloadError("AUTHENTICATION_REQUIRED: Login required")):
        with patch("core.gdrive_downloader.has_valid_cookies", return_value=False):
            stats = downloader.download(
                url_or_id="https://drive.google.com/drive/folders/1HNFupr8h1iWnGFkkSYh4JodtiTDK_oMm",
                output_dir="/tmp/test_dir",
            )
            assert len(stats["errors"]) > 0
            assert "THƯ MỤC NỘI BỘ CÔNG TY" in stats["errors"][0]


def test_gdrive_modals_ui():
    """Kiểm tra khởi tạo thành công 2 modal thông báo Google Drive: Completion & Auth Success."""
    import customtkinter as ctk
    from gui.gdrive_download_dialog import GDriveCompletionModal
    from gui.gdrive_auth_dialog import GDriveAuthSuccessModal

    root = ctk.CTk()
    root.withdraw()

    # 1. Test GDriveCompletionModal
    modal_comp = GDriveCompletionModal(
        root,
        success_count=5,
        total_count=7,
        skipped_count=2,
        failed_count=0,
        out_dir="/tmp/fake_dir",
        elapsed_str="12.5s",
    )
    assert modal_comp is not None
    assert modal_comp.out_dir == "/tmp/fake_dir"
    modal_comp.destroy()

    # 2. Test GDriveAuthSuccessModal
    closed = []
    modal_auth = GDriveAuthSuccessModal(
        root,
        on_confirm=lambda: closed.append(True),
    )
    assert modal_auth is not None
    root.destroy()


def test_browser_login_pages_detection_and_singleton():
    """Kiểm tra nhận diện tab Drive trong đa trang (context.pages) và cơ chế Singleton."""
    from core.gdrive_auth import is_browser_login_running, login_google_via_browser
    from unittest.mock import MagicMock, patch

    # 1. Test check running status
    assert not is_browser_login_running()

    # 2. Test Playwright multi-page detection logic
    mock_page1 = MagicMock()
    mock_page1.url = "https://accounts.google.com/signin/v2/challenge/pwd"

    mock_page2 = MagicMock()
    mock_page2.url = "https://drive.google.com/drive/home"

    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page1, mock_page2]
    mock_ctx.cookies.return_value = [
        {"name": "OSID", "value": "secret_osid_cookie_123456", "domain": "drive.google.com"},
        {"name": "SID", "value": "secret_sid_cookie_123456", "domain": ".google.com"},
    ]

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_ctx
    mock_ctx.new_page.return_value = mock_page1

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_sync_pw = MagicMock()
    mock_sync_pw.return_value.__enter__.return_value = mock_p

    success_called = []
    error_called = []

    with patch.dict("sys.modules", {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)}):
        with patch("core.gdrive_auth.has_valid_cookies", return_value=True):
            with patch("core.gdrive_auth.cookies_dict_to_netscape", return_value=True):
                login_google_via_browser(
                    on_status=None,
                    on_success=lambda email: success_called.append(email),
                    on_error=lambda err: error_called.append(err),
                )

    assert len(success_called) == 1
    assert len(error_called) == 0
    assert not is_browser_login_running()


def test_cookies_dict_to_netscape_with_none_expires(tmp_path):
    """Kiểm tra cookies_dict_to_netscape xử lý an toàn tuyệt đối khi expires là None, float, âm hoặc rỗng."""
    from core.gdrive_auth import cookies_dict_to_netscape, has_valid_cookies

    test_cookies = [
        {"name": "OSID", "value": "test_osid_val_1234567890", "domain": "drive.google.com", "expires": None},
        {"name": "SID", "value": "test_sid_val_1234567890", "domain": ".google.com", "expires": -1},
        {"name": "COMPASS", "value": "test_compass_val_1234567890", "domain": "drive.google.com", "expires": 1899999999.5},
        {"name": "SSID", "value": "test_ssid_val_1234567890", "domain": ".google.com", "expires": "1999999999"},
    ]

    target = tmp_path / "test_cookies.txt"
    res = cookies_dict_to_netscape(test_cookies, target)
    assert res is True
    assert target.exists()

    content = target.read_text(encoding="utf-8")
    assert "OSID" in content
    assert "SID" in content
    assert "COMPASS" in content
    assert "SSID" in content

    # Kiểm tra has_valid_cookies nhận diện được file vừa tạo
    with patch("core.gdrive_auth.get_cookies_path", return_value=str(target)):
        assert has_valid_cookies() is True



