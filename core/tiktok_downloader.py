"""
core/tiktok_downloader.py — Bộ nạp và tải video / âm thanh TikTok chuyên dụng
- Tải trực tiếp video TikTok chất lượng cao nhất (Full HD / 1080p gốc), không dính watermark (logo).
- Tự động nhận diện và xử lý mọi định dạng link: link web, link rút gọn (vt.tiktok.com, vm.tiktok.com).
- Hỗ trợ báo cáo tiến trình theo thời gian thực (tỷ lệ %, tốc độ MB/s) và hủy tiến trình an toàn.
"""

import json
import os
import re
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from utils.ffmpeg_check import get_ffmpeg_path


def _get_requests():
    try:
        from curl_cffi import requests as cffi_requests
        return cffi_requests
    except Exception:
        import requests as std_requests
        return std_requests


class _RequestsProxy:
    def __getattr__(self, name):
        req = _get_requests()
        return getattr(req, name)


requests = _RequestsProxy()


def _safe_filename(name: str, max_len: int = 80) -> str:
    """Tạo tên file an toàn cho hệ điều hành từ tiêu đề video."""
    if not name:
        return "TikTok_Video"
    clean = re.sub(r'[\\/*?:"<>|#\r\n\t]', " ", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = clean.strip("._- ")
    return clean[:max_len].strip() or "TikTok_Video"


class TikTokDownloader:
    """
    Trình bóc tách và tải video / âm thanh từ TikTok.
    - Sử dụng Engine chuyên dụng bóc tách trực tiếp luồng video không logo (No Watermark / HD).
    - Vượt qua các lớp tường lửa và chặn bot của TikTok Web.
    - Hỗ trợ tải âm thanh gốc MP3 cho tính năng lồng tiếng / dịch thuật.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )

    API_ENDPOINT = "https://www.tikwm.com/api/"

    @classmethod
    def is_tiktok_url(cls, text: str) -> bool:
        """Kiểm tra xem chuỗi có phải là liên kết TikTok hay không."""
        if not text:
            return False
        lower = text.lower()
        return "tiktok.com" in lower

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        """Trích xuất URL TikTok từ chuỗi văn bản người dùng dán vào."""
        if not text:
            return None
        m = re.search(r"https?://[^\s\"'<>]+", text.strip())
        if m:
            candidate = m.group(0).rstrip(".,;:!?)]\"'>")
            if cls.is_tiktok_url(candidate):
                return candidate
        return None

    @classmethod
    def resolve_tiktok_url(cls, raw_input: str) -> str:
        """
        Phân giải liên kết TikTok, theo dõi chuyển hướng (redirect) cho các link rút gọn
        như vt.tiktok.com, vm.tiktok.com hoặc link app chia sẻ.
        """
        if not raw_input:
            return raw_input

        text = raw_input.strip()
        url = cls.extract_url(text) or text

        # Nếu là link rút gọn vt.tiktok.com hoặc vm.tiktok.com
        if any(short_domain in url.lower() for short_domain in ("vt.tiktok.com", "vm.tiktok.com", "tiktok.com/t/")):
            try:
                headers = {"User-Agent": cls.USER_AGENT}
                resp = requests.head(url, headers=headers, allow_redirects=True, timeout=8)
                if resp and resp.url:
                    return resp.url
            except Exception:
                try:
                    resp = requests.get(url, headers=headers, allow_redirects=True, timeout=8)
                    if resp and resp.url:
                        return resp.url
                except Exception:
                    pass

        return url

    def fetch_video_info(self, url: str) -> Dict:
        """
        Gửi yêu cầu bóc tách thông tin video TikTok qua Engine chuyên biệt.
        Trả về dict chứa: title, video_url, music_url, cover_url, duration, images...
        """
        target_url = self.resolve_tiktok_url(url)

        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }

        # Gọi API với POST hoặc GET params để đảm bảo chuẩn hóa URL
        try:
            resp = requests.post(
                self.API_ENDPOINT,
                data={"url": target_url, "hd": 1},
                headers=headers,
                timeout=15,
            )
            data = resp.json()
        except Exception:
            try:
                resp = requests.get(
                    self.API_ENDPOINT,
                    params={"url": target_url, "hd": 1},
                    headers=headers,
                    timeout=15,
                )
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"Không thể kết nối đến máy chủ giải mã TikTok: {e}")

        if not isinstance(data, dict) or data.get("code") != 0:
            msg = data.get("msg") if isinstance(data, dict) else "Lỗi không xác định"
            raise RuntimeError(f"Máy chủ TikTok phản hồi: {msg}")

        item_data = data.get("data") or {}
        title = item_data.get("title") or "TikTok_Video"

        # Lấy luồng video chất lượng cao nhất không logo
        # Thứ tự ưu tiên: hdplay (1080p no-watermark) -> play (gốc no-watermark) -> wmplay
        video_url = item_data.get("hdplay") or item_data.get("play") or item_data.get("wmplay")
        music_url = item_data.get("music")
        images = item_data.get("images") or []

        return {
            "id": item_data.get("id"),
            "title": title,
            "video_url": video_url,
            "music_url": music_url,
            "cover_url": item_data.get("cover"),
            "duration": item_data.get("duration", 0),
            "images": images,
            "resolved_url": target_url,
        }

    def _stream_download(
        self,
        url: str,
        target_file: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        content_name: str = "video",
    ) -> str:
        """Tải dữ liệu từ URL dạng stream, báo cáo tiến trình theo % và MB/s."""
        temp_file = target_file.with_suffix(target_file.suffix + ".part")
        target_file.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": self.USER_AGENT,
            "Referer": "https://www.tiktok.com/",
            "Accept": "*/*",
        }

        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=20)
            if resp.status_code not in (200, 206):
                raise RuntimeError(f"Máy chủ CDN trả về mã trạng thái {resp.status_code}")

            total_bytes = int(resp.headers.get("content-length") or 0)
            downloaded = 0
            start_time = time.time()
            last_report_time = 0.0

            with open(temp_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if is_cancelled and is_cancelled():
                        raise InterruptedError("Tiến trình tải đã bị hủy.")

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if progress_callback and (now - last_report_time >= 0.2 or downloaded == total_bytes):
                            elapsed = now - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            speed_str = f" - {speed / 1048576:.1f}MB/s" if speed > 0 else ""

                            if total_bytes > 0:
                                pct = min(downloaded / total_bytes, 0.98)
                                size_str = f"{downloaded / 1048576:.1f}MB/{total_bytes / 1048576:.1f}MB"
                                progress_callback(pct, f"Đang tải {content_name}: {pct * 100:.0f}% ({size_str}{speed_str})")
                            else:
                                mb = downloaded / 1048576
                                progress_callback(0.5, f"Đang tải {content_name}: {mb:.1f}MB{speed_str}")

                            last_report_time = now

            if temp_file.exists():
                if target_file.exists():
                    try:
                        target_file.unlink()
                    except Exception:
                        pass
                temp_file.rename(target_file)

            if progress_callback:
                progress_callback(1.0, f"Đã tải xong {content_name}!")

            return str(target_file)

        except (InterruptedError, KeyboardInterrupt):
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise InterruptedError("Tiến trình tải đã bị hủy.")
        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise RuntimeError(f"Lỗi khi lưu file {content_name}: {e}")

    def download_video(
        self,
        raw_url: str,
        output_dir: str,
        quality: str = "best",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Tải video TikTok gốc không dính logo watermark.
        Trả về đường dẫn tuyệt đối đến file MP4 đã tải.
        """
        def _report(pct: float, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        _report(0.02, "Đang kết nối đến hệ thống TikTok...")
        info = self.fetch_video_info(raw_url)

        title = info.get("title") or "TikTok_Video"
        clean_title = _safe_filename(title, max_len=60)
        video_id = info.get("id") or str(int(time.time()))
        filename = f"{clean_title} [{video_id}].mp4"
        target_path = Path(output_dir) / filename

        video_url = info.get("video_url")
        if not video_url:
            # Kiểm tra nếu là dạng bài đăng album ảnh (slideshow)
            if info.get("images"):
                raise RuntimeError(
                    "Link này là bài đăng album ảnh dạng slide của TikTok, không phải video.\n"
                    "💡 Bạn có thể dùng tính năng 'Tải Riêng Nhạc/Âm Thanh' để lấy bài hát nền."
                )
            raise RuntimeError("Không tìm thấy luồng video khả dụng cho link TikTok này.")

        _report(0.08, "Đã lấy được luồng video gốc (không logo), bắt đầu tải...")

        # Thử tải từ link video
        try:
            return self._stream_download(
                url=video_url,
                target_file=target_path,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
                content_name="video TikTok",
            )
        except Exception as err:
            # Nếu link hdplay bị lỗi, thử fallback sang play thường nếu có
            if info.get("play") and info.get("play") != video_url:
                _report(0.1, "Đang thử luồng video dự phòng...")
                return self._stream_download(
                    url=info["play"],
                    target_file=target_path,
                    progress_callback=progress_callback,
                    is_cancelled=is_cancelled,
                    content_name="video TikTok (dự phòng)",
                )
            raise

    def download_audio(
        self,
        raw_url: str,
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Tải riêng file âm thanh/nhạc nền gốc từ TikTok (.mp3).
        Trả về đường dẫn tuyệt đối đến file MP3 đã tải.
        """
        def _report(pct: float, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        _report(0.02, "Đang trích xuất bài nhạc nền từ TikTok...")
        info = self.fetch_video_info(raw_url)

        title = info.get("title") or "TikTok_Audio"
        clean_title = _safe_filename(title, max_len=60)
        video_id = info.get("id") or str(int(time.time()))
        filename = f"{clean_title} [{video_id}].mp3"
        target_path = Path(output_dir) / filename

        music_url = info.get("music_url")
        if not music_url:
            raise RuntimeError("Không tìm thấy luồng âm thanh cho bài đăng TikTok này.")

        _report(0.1, "Bắt đầu tải file âm thanh MP3...")
        return self._stream_download(
            url=music_url,
            target_file=target_path,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            content_name="âm thanh TikTok",
        )
