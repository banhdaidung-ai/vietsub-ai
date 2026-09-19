import os
import sys
import shutil
import tempfile
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.downloader import VideoDownloader


def test_clean_artlist_stream_title():
    """Kiểm tra tính năng giải mã và làm sạch tên bài hát từ link CDN base64 của Artlist."""
    # 1. Base64 URL chứa đường dẫn: content/music/aac/5000_260414_260414_01_-_Migration_-_Master_-16-44.1-.aac
    url1 = "https://cms-public-artifacts.artlist.io/Y29udGVudC9tdXNpYy9hYWMvNTAwMF8yNjA0MTRfMjYwNDE0XzAxXy1fTWlncmF0aW9uXy1fTWFzdGVyXy0xNi00NC4xLS5hYWM"
    title1 = VideoDownloader._clean_artlist_stream_title(url1)
    assert "Migration" in title1

    # 2. URL thường
    url2 = "https://example.com/audio.mp3"
    title2 = VideoDownloader._clean_artlist_stream_title(url2, "Default_Title")
    assert title2 == "Default_Title"


def test_artlist_live_download_song_url():
    """Kiểm tra tải nhạc thật từ liên kết bài hát Artlist và chuyển đổi sang MP3 320k."""
    test_url = "https://artlist.io/royalty-free-music/song/migration/5000"
    temp_dir = tempfile.mkdtemp(prefix="test_artlist_")

    try:
        reports = []
        def on_progress(pct, msg):
            reports.append((pct, msg))

        downloader = VideoDownloader(progress_callback=on_progress)
        out_path = downloader.download_audio(
            url=test_url,
            output_dir=temp_dir,
            audio_format="mp3",
            bitrate="320k"
        )

        assert out_path is not None
        file_p = Path(out_path)
        assert file_p.exists(), "File âm thanh tải về phải tồn tại trên ổ đĩa"
        assert file_p.stat().st_size > 500_000, "File MP3 320k của bài Migration phải lớn hơn 500KB"
        assert file_p.suffix.lower() == ".mp3"
        assert "Migration" in file_p.name, f"Tên file phải chứa tên bài hát: {file_p.name}"

        # Kiểm tra các mốc tiến trình
        assert any(pct >= 0.9 for pct, _ in reports), "Tiến trình phải đạt mốc xử lý >= 90%"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_artlist_live_download_direct_stream_url():
    """Kiểm tra tải nhạc thật từ liên kết stream trực tiếp của Artlist (không bị 403 Forbidden)."""
    stream_url = "https://cms-public-artifacts.artlist.io/Y29udGVudC9tdXNpYy9hYWMvNTAwMF8yNjA0MTRfMjYwNDE0XzAxXy1fTWlncmF0aW9uXy1fTWFzdGVyXy0xNi00NC4xLS5hYWM"
    temp_dir = tempfile.mkdtemp(prefix="test_artlist_stream_")

    try:
        downloader = VideoDownloader()
        out_path = downloader.download_audio(
            url=stream_url,
            output_dir=temp_dir,
            audio_format="mp3",
            bitrate="320k"
        )

        assert out_path is not None
        file_p = Path(out_path)
        assert file_p.exists()
        assert file_p.stat().st_size > 500_000
        assert file_p.suffix.lower() == ".mp3"
        assert "Migration" in file_p.name
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_artlist_live_download_short_song_url():
    """Kiểm tra tải nhạc Artlist với định dạng link ngắn: artlist.io/song/.../id."""
    short_url = "https://artlist.io/song/frosty/99999"
    temp_dir = tempfile.mkdtemp(prefix="test_artlist_short_")

    try:
        downloader = VideoDownloader()
        out_path = downloader.download_audio(
            url=short_url,
            output_dir=temp_dir,
            audio_format="mp3",
            bitrate="320k"
        )

        assert out_path is not None
        file_p = Path(out_path)
        assert file_p.exists()
        assert file_p.stat().st_size > 100_000
        assert file_p.suffix.lower() == ".mp3"
        assert "Frosty" in file_p.name or "Less Gravity" in file_p.name
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

