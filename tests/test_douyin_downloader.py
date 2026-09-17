"""
tests/test_douyin_downloader.py — Kiểm thử tự động tính năng Tải Video & Âm Thanh Douyin
"""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.douyin import DouyinDownloader
from core.downloader import VideoDownloader


TEST_DOUYIN_URL = "https://v.douyin.com/fbylW_3sgAE/"
TEST_SHARE_TEXT = (
    "7.20 复制打开抖音，看看【柏敬礼的作品】五分钟唠明白怎么去营造氛围感的旅拍画面 "
    "https://v.douyin.com/fbylW_3sgAE/ 12/02 o@b.sk :0pm"
)


def test_douyin_url_detection_and_extraction():
    """Kiểm tra nhận diện và bóc tách URL Douyin từ văn bản thô."""
    assert DouyinDownloader.is_douyin_url(TEST_DOUYIN_URL) is True
    assert DouyinDownloader.is_douyin_url("https://www.douyin.com/video/7598819713975668011") is True
    assert DouyinDownloader.is_douyin_url("https://www.youtube.com/watch?v=123") is False

    extracted = DouyinDownloader.extract_url(TEST_SHARE_TEXT)
    assert extracted is not None
    assert "v.douyin.com/fbylW_3sgAE/" in extracted


def test_douyin_ttwid_cookie():
    """Kiểm tra lấy cookie ttwid tự động từ ByteDance."""
    ttwid = DouyinDownloader.get_ttwid()
    assert ttwid is not None
    assert len(ttwid) > 10
    assert "ttwid" in ttwid or "%7C" in ttwid or "1" in ttwid


def test_douyin_resolve_aweme_id():
    """Kiểm tra giải mã aweme_id từ link rút gọn v.douyin.com."""
    aweme_id = DouyinDownloader.resolve_aweme_id(TEST_DOUYIN_URL)
    assert aweme_id == "7598819713975668011"


def test_douyin_aweme_detail():
    """Kiểm tra lấy thông tin video từ Douyin API."""
    detail = DouyinDownloader.get_aweme_detail("7598819713975668011")
    assert "desc" in detail
    assert "video" in detail
    assert "play_addr" in detail["video"]
    assert len(detail["video"]["play_addr"]["url_list"]) > 0


def test_douyin_video_download():
    """Kiểm tra tải video chất lượng cao 1080p Full HD từ link Douyin."""
    dl = DouyinDownloader()
    progress_records = []

    def on_prog(pct, label):
        progress_records.append((pct, label))

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_file = dl.download_video(
            raw_url=TEST_DOUYIN_URL,
            output_dir=tmp_dir,
            quality="best",
            progress_callback=on_prog,
        )
        assert os.path.exists(out_file)
        file_size = os.path.getsize(out_file)
        # Video 1080p phải đạt dung lượng Full HD chuẩn (~35.9MB)
        assert file_size > 25_000_000, f"File video 1080p phải lớn hơn 25MB, thực tế: {file_size}"
        assert out_file.endswith(".mp4")
        assert len(progress_records) > 0


def test_video_downloader_central_integration():
    """Kiểm tra tích hợp Douyin vào VideoDownloader trung tâm của ứng dụng."""
    downloader = VideoDownloader()
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = downloader.download(TEST_DOUYIN_URL, tmp_dir, quality="720p")
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 1_000_000
