"""
core/xhs_downloader.py — Tải video từ Xiaohongshu (小红书 / XHS)
Hỗ trợ liên kết rút gọn xhslink.com, xhs.link và liên kết đầy đủ xiaohongshu.com/...
Tự động bảo toàn xsec_token để tải trực tiếp video Full HD / 1080p không cần đăng nhập.
"""

import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

import yt_dlp

from utils.ffmpeg_check import get_ffmpeg_path


class XHSDownloader:
    """
    Trình tải video từ Xiaohongshu (小红书).
    - Hỗ trợ link rút gọn xhslink.com/... và link đầy đủ xiaohongshu.com/...
    - Giải mã redirect thông minh, giữ nguyên xsec_token để yt-dlp tải Full HD gốc.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
    MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )

    @classmethod
    def is_xhs_url(cls, text: str) -> bool:
        """Kiểm tra chuỗi có chứa liên kết Xiaohongshu hay không."""
        if not text:
            return False
        lower = text.lower()
        return (
            "xhslink.com" in lower
            or "xiaohongshu.com" in lower
            or "xhs.link" in lower
        )

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        """Trích xuất URL XHS từ chuỗi văn bản người dùng dán vào."""
        if not text:
            return None
        m = re.search(r"https?://[a-zA-Z0-9./?=&#+%_\-]+", text.strip())
        if m:
            candidate = m.group(0).rstrip(".,;:!?)]\"'")
            if cls.is_xhs_url(candidate):
                return candidate
        return None

    @classmethod
    def resolve_xhs_url(cls, raw_input: str) -> str:
        """
        Phân giải và chuẩn hóa mọi loại liên kết Xiaohongshu thành URL đầy đủ
        hợp lệ (chứa discovery/item/... hoặc explore/... kèm query parameters xsec_token).

        Hỗ trợ:
        - Link rút gọn: http://xhslink.com/... hoặc https://xhs.link/...
        - Text copy từ app XHS có kèm liên kết và tiếng Trung
        - Link login kèm redirectPath
        - Link trực tiếp discovery/item hoặc explore
        """
        if not raw_input:
            return raw_input

        text = raw_input.strip()
        url = cls.extract_url(text) or text

        # Trường hợp 1: Link login chứa redirectPath (do redirect quá đà)
        if "xiaohongshu.com/login" in url and "redirectPath=" in url:
            try:
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                if "redirectPath" in qs:
                    target = urllib.parse.unquote(qs["redirectPath"][0])
                    if target.startswith("http://"):
                        target = "https://" + target[7:]
                    if "discovery/item/" in target or "explore/" in target:
                        return target
            except Exception:
                pass

        # Trường hợp 2: Link rút gọn xhslink.com hoặc xhs.link
        if "xhslink.com" in url or "xhs.link" in url:
            resolved_url = None

            class StopAtFirstRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    nonlocal resolved_url
                    # Chặn ngay redirect đầu tiên để lấy URL discovery/item kèm xsec_token,
                    # tránh bị server Xiaohongshu đẩy tiếp sang trang /login
                    if "discovery/item/" in newurl or "explore/" in newurl:
                        resolved_url = newurl
                        return None
                    elif "login" in newurl and "redirectPath=" in newurl:
                        try:
                            parsed = urllib.parse.urlparse(newurl)
                            qs = urllib.parse.parse_qs(parsed.query)
                            if "redirectPath" in qs:
                                target = urllib.parse.unquote(qs["redirectPath"][0])
                                if target.startswith("http://"):
                                    target = "https://" + target[7:]
                                if "discovery/item/" in target or "explore/" in target:
                                    resolved_url = target
                        except Exception:
                            pass
                        return None
                    return super().redirect_request(req, fp, code, msg, headers, newurl)

            opener = urllib.request.build_opener(StopAtFirstRedirect)
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": cls.USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )
            try:
                opener.open(req, timeout=12)
            except Exception:
                pass

            if resolved_url:
                return resolved_url

            # Dự phòng bằng curl_cffi nếu urllib không bắt được
            try:
                from curl_cffi import requests as cffi_req
                r = cffi_req.get(
                    url,
                    headers={"User-Agent": cls.USER_AGENT},
                    allow_redirects=False,
                    impersonate="chrome120",
                    timeout=10,
                )
                loc = r.headers.get("Location") or r.headers.get("location")
                if loc:
                    if "discovery/item/" in loc or "explore/" in loc:
                        return loc
                    if "redirectPath=" in loc:
                        parsed = urllib.parse.urlparse(loc)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if "redirectPath" in qs:
                            target = urllib.parse.unquote(qs["redirectPath"][0])
                            if target.startswith("http://"):
                                target = "https://" + target[7:]
                            if "discovery/item/" in target or "explore/" in target:
                                return target
            except Exception:
                pass

        return url

    @classmethod
    def resolve_note_id(cls, raw_url: str) -> str:
        """
        Lấy note_id (ID bài viết) từ URL XHS hoặc URL rút gọn xhslink.com.
        """
        resolved = cls.resolve_xhs_url(raw_url)
        m = re.search(r"/(?:discovery/item|explore|notes?)/([a-fA-F0-9]{20,30})", resolved)
        if m:
            return m.group(1)

        # Fallback tìm trong raw_url
        m_raw = re.search(r"/(?:discovery/item|explore|notes?)/([a-fA-F0-9]{20,30})", raw_url)
        if m_raw:
            return m_raw.group(1)

        raise RuntimeError(
            f"Không thể trích xuất ID bài viết từ link Xiaohongshu: {raw_url}"
        )

    @classmethod
    def clean_title(cls, title: str, note_id: str) -> str:
        """Làm sạch title để đặt tên file an toàn."""
        clean = re.sub(r'[\\/*?:"<>|#\n\r\t]', " ", title or "").strip()
        clean = re.sub(r"\s+", " ", clean).strip(". ")
        if len(clean) > 80:
            clean = clean[:80].strip(". ")
        return clean or f"xhs_{note_id}"

    def download_video(
        self,
        raw_url: str,
        output_dir: str,
        quality: str = "best",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Tải video từ Xiaohongshu về output_dir với độ nét cao nhất.
        Tự động giải mã redirect và bảo toàn xsec_token.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(0.02, "Đang phân giải liên kết Xiaohongshu...")

        # Bước 1: Chuẩn hóa và giải mã liên kết
        target_url = self.resolve_xhs_url(raw_url)

        if is_cancelled and is_cancelled():
            raise InterruptedError("Tiến trình tải đã bị hủy.")

        if progress_callback:
            progress_callback(0.06, "Đang kết nối tới máy chủ Xiaohongshu...")

        # Bước 2: Tải video bằng yt-dlp với cấu hình chuyên dụng XHS
        def progress_hook(d: dict):
            if is_cancelled and is_cancelled():
                raise InterruptedError("Tiến trình tải đã bị hủy.")
            status = d.get("status", "")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                speed_str = f" - {speed / 1024 / 1024:.1f}MB/s" if speed else ""
                if total > 0:
                    pct = min(0.1 + (downloaded / total) * 0.85, 0.96)
                    size_str = f"{downloaded / 1_048_576:.1f}MB/{total / 1_048_576:.1f}MB"
                    if progress_callback:
                        progress_callback(pct, f"Đang tải XHS: {pct * 100:.0f}% ({size_str}{speed_str})")
                else:
                    mb = downloaded / 1_048_576
                    if progress_callback:
                        progress_callback(0.5, f"Đang tải XHS: {mb:.1f}MB{speed_str}")
            elif status == "finished":
                if progress_callback:
                    progress_callback(0.96, "Đang hoàn thiện file video...")

        # Chọn format theo quality
        if quality == "1080p":
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        elif quality == "720p":
            format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif quality == "480p":
            format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        else:
            format_str = "bestvideo*+bestaudio/bestvideo+bestaudio/best"

        ydl_opts = {
            "format": format_str,
            "merge_output_format": "mp4",
            "outtmpl": str(Path(output_dir) / "%(title).80s.%(ext)s"),
            "windowsfilenames": True,
            "nocheckcertificate": True,
            "progress_hooks": [progress_hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Fetch-Mode": "navigate",
            },
        }

        ffmpeg_bin = get_ffmpeg_path()
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        downloaded_path = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                downloaded_path = ydl.prepare_filename(info)
        except (InterruptedError, KeyboardInterrupt):
            raise InterruptedError("Tiến trình tải đã bị hủy.")
        except Exception as e:
            err_msg = str(e)
            if "No video formats found" in err_msg:
                raise RuntimeError(
                    "Không tìm thấy luồng video trong bài viết Xiaohongshu này.\n\n"
                    "Lý do: Đây là bài viết hình ảnh (album ảnh/Photo Note) hoặc video bị đặt chế độ riêng tư.\n"
                    "👉 Vietsub AI chỉ hỗ trợ các bài viết dạng VIDEO công khai."
                )
            raise RuntimeError(
                f"Không thể tải video từ Xiaohongshu.\n\n"
                f"Chi tiết lỗi: {err_msg}\n\n"
                "👉 Giải pháp thay thế: Tải video từ app Xiaohongshu về máy, sau đó chọn tab 'Chọn File Video Trên Máy' để dịch mượt mà 100% nhé sếp!"
            )

        # Fallback kiểm tra file tồn tại
        if downloaded_path:
            path = Path(downloaded_path)
            if not path.exists():
                for ext in (".mp4", ".mkv", ".webm"):
                    alt = path.with_suffix(ext)
                    if alt.exists():
                        downloaded_path = str(alt)
                        break

        if not downloaded_path or not Path(downloaded_path).exists():
            candidates = [
                p for p in Path(output_dir).glob("*")
                if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi")
            ]
            if candidates:
                candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                downloaded_path = str(candidates[0])

        if progress_callback:
            progress_callback(1.0, f"Đã tải xong: {Path(downloaded_path).name if downloaded_path else 'Video'}")

        return downloaded_path
