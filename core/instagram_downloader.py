"""
core/instagram_downloader.py — Trình tải hình ảnh & video chuyên dụng từ Instagram.
Hỗ trợ tải toàn bộ ảnh chất lượng gốc (Full HD / 2K / 4K), album carousel và video Reels.
Tự động nạp cookies nếu có và báo cáo tiến trình theo thời gian thực.
"""

import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

import yt_dlp
from yt_dlp.extractor.instagram import InstagramIE


def _safe_filename(text: str, max_len: int = 60) -> str:
    """Loại bỏ ký tự đặc biệt không hợp lệ trên Windows và macOS/Linux."""
    if not text:
        return "Instagram_Media"
    clean = re.sub(r'[\\/*?:"<>|]', "", text)
    clean = re.sub(r"[\r\n\t]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = clean.strip(". ")
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip(". ")
    return clean or "Instagram_Media"


class InstagramDownloader:
    """
    Trình bóc tách và tải hình ảnh & video từ Instagram.
    - Hỗ trợ ảnh đơn lẻ (Single Photo), album bộ sưu tập (Carousel / Slideshow).
    - Hỗ trợ bài đăng hỗn hợp (vừa có ảnh vừa có clip video ngắn).
    - Giữ nguyên độ phân giải gốc cao nhất từ máy chủ CDN Meta.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )

    @classmethod
    def is_instagram_url(cls, text: str) -> bool:
        """Kiểm tra chuỗi có chứa liên kết Instagram hay không."""
        if not text:
            return False
        lower = text.lower()
        return "instagram.com" in lower or "instagr.am" in lower

    @classmethod
    def extract_shortcode(cls, url: str) -> Optional[str]:
        """Trích xuất mã shortcode của bài viết Instagram."""
        if not url:
            return None
        m = re.search(r"/(?:p|reel|reels|tv|share/p|share/reel)/([A-Za-z0-9_-]+)", url)
        if m:
            return m.group(1)
        return None

    @classmethod
    def get_cookie_file(cls) -> Optional[str]:
        """Tìm file cookie Instagram nếu người dùng đã cung cấp."""
        for cf in (
            Path.home() / ".vietsub_ai" / "cookies.txt",
            Path.home() / ".vietsub_ai" / "instagram_cookies.txt",
            Path.home() / ".vietsub_ai" / "youtube_cookies.txt",
        ):
            if cf.exists():
                return str(cf)
        return None

    def _report(
        self,
        progress_callback: Optional[Callable[[float, str], None]],
        pct: float,
        msg: str,
    ):
        if progress_callback:
            progress_callback(min(max(pct, 0.0), 1.0), msg)

    def extract_post_info(self, url: str) -> Dict[str, Any]:
        """
        Bóc tách siêu dữ liệu và danh sách media (ảnh, video) của bài viết Instagram.
        Trả về dict chứa:
          - id: shortcode
          - title: tiêu đề/mô tả
          - uploader: người đăng
          - items: danh sách các phần tử media ({type, url, width, height, ext})
        """
        url_clean = url.strip()
        cookie_file = self.get_cookie_file()

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extractor_args": {
                "instagram": {
                    "app_id": ["ios"],
                }
            },
            "http_headers": {
                "User-Agent": self.USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            },
        }
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        ydl = yt_dlp.YoutubeDL(ydl_opts)
        ie = InstagramIE(ydl)
        try:
            ie.initialize()
        except Exception:
            pass

        # Chặn bắt hàm raise_no_formats để giữ lại toàn bộ metadata ảnh khi không có video
        ie.raise_no_formats = lambda msg, expected=True: None

        try:
            res = ie._real_extract(url_clean)
        except Exception as e:
            err_str = str(e)
            if any(k in err_str.lower() for k in ("login", "rate-limit", "redirect", "empty media", "restricted", "private")):
                raise RuntimeError(
                    "Bài viết Instagram này yêu cầu đăng nhập hoặc bị giới hạn truy cập ẩn danh.\n"
                    f"Chi tiết kỹ thuật: {err_str}\n\n"
                    "💡 Bạn có thể xuất file cookies.txt từ trình duyệt và đặt vào ~/.vietsub_ai/cookies.txt để tải bình thường."
                )
            raise RuntimeError(f"Không thể bóc tách thông tin Instagram: {e}")

        if not res or not isinstance(res, dict):
            raise RuntimeError("Không tìm thấy dữ liệu media nào khả dụng cho bài viết Instagram này.")

        shortcode = res.get("id") or self.extract_shortcode(url_clean) or str(int(time.time()))
        uploader = res.get("channel") or res.get("uploader") or "Instagram"
        raw_title = res.get("title") or f"Instagram by {uploader}"
        description = res.get("description") or ""

        def _pick_best_image_url(thumbs: List[Dict[str, Any]]) -> Optional[str]:
            if not thumbs:
                return None
            # Ưu tiên các ảnh không bị crop vuông (không chứa 'stp=c')
            non_cropped = [t for t in thumbs if "stp=c" not in t.get("url", "")]
            candidates = non_cropped if non_cropped else thumbs
            # Tìm candidate có độ phân giải gốc cao nhất (thường nằm ở cuối mảng do yt-dlp đảo ngược)
            # Hoặc candidate có stp=dst-jpg_e35_tt6
            for t in reversed(candidates):
                u = t.get("url", "")
                if "dst-jpg_e35_tt6" in u:
                    return u
            return candidates[-1].get("url")

        def _pick_best_video_url(formats: List[Dict[str, Any]]) -> Optional[str]:
            if not formats:
                return None
            # Lọc các formats có video url và sắp xếp theo độ phân giải / tbr
            valid = [f for f in formats if f.get("url")]
            if not valid:
                return None
            # Sắp xếp theo chiều cao (height) hoặc bitrate
            valid.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
            return valid[0].get("url")

        items: List[Dict[str, Any]] = []

        is_playlist = res.get("_type") == "playlist" or bool(res.get("entries"))
        entries = res.get("entries") or []

        if is_playlist and entries:
            for idx, entry in enumerate(entries):
                e_id = entry.get("id") or f"{shortcode}_{idx+1}"
                v_formats = entry.get("formats") or []
                v_url = _pick_best_video_url(v_formats)

                if v_url:
                    items.append({
                        "id": e_id,
                        "type": "video",
                        "url": v_url,
                        "ext": "mp4",
                    })
                else:
                    e_thumbs = entry.get("thumbnails") or []
                    i_url = _pick_best_image_url(e_thumbs)
                    if i_url:
                        items.append({
                            "id": e_id,
                            "type": "image",
                            "url": i_url,
                            "ext": "jpg",
                        })
        else:
            # Bài đăng đơn lẻ (Single post)
            v_formats = res.get("formats") or []
            v_url = _pick_best_video_url(v_formats)

            if v_url:
                items.append({
                    "id": shortcode,
                    "type": "video",
                    "url": v_url,
                    "ext": "mp4",
                })
            else:
                thumbs = res.get("thumbnails") or []
                i_url = _pick_best_image_url(thumbs)
                if i_url:
                    items.append({
                        "id": shortcode,
                        "type": "image",
                        "url": i_url,
                        "ext": "jpg",
                    })

        if not items:
            raise RuntimeError("Bài viết Instagram này không chứa bất kỳ hình ảnh hoặc video nào có thể tải về.")

        return {
            "id": shortcode,
            "uploader": uploader,
            "title": raw_title,
            "description": description,
            "is_carousel": len(items) > 1,
            "items": items,
        }

    def download_post(
        self,
        url: str,
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[str]:
        """
        Bóc tách và tải toàn bộ ảnh / video của bài viết Instagram về output_dir.
        Trả về danh sách đường dẫn tuyệt đối của các file đã tải thành công.
        """
        os.makedirs(output_dir, exist_ok=True)
        self._report(progress_callback, 0.05, "Đang kết nối và phân tích bài viết Instagram...")

        info = self.extract_post_info(url)
        items = info["items"]
        total = len(items)
        uploader = info["uploader"]
        shortcode = info["id"]

        safe_uploader = _safe_filename(uploader, max_len=30)
        base_prefix = f"Instagram_{safe_uploader}_{shortcode}"

        saved_files: List[str] = []

        for idx, item in enumerate(items):
            if is_cancelled and is_cancelled():
                raise InterruptedError("Tiến trình tải Instagram đã bị hủy.")

            item_type = item["type"]
            media_url = item["url"]
            ext = item["ext"]

            if total == 1:
                filename = f"{base_prefix}.{ext}"
            else:
                filename = f"{base_prefix}_{idx+1:02d}.{ext}"

            dest_path = Path(output_dir) / filename
            counter = 1
            while dest_path.exists():
                if total == 1:
                    filename = f"{base_prefix} ({counter}).{ext}"
                else:
                    filename = f"{base_prefix}_{idx+1:02d} ({counter}).{ext}"
                dest_path = Path(output_dir) / filename
                counter += 1

            type_label = "ảnh" if item_type == "image" else "video"
            step_base = idx / total
            step_span = 1.0 / total

            self._report(
                progress_callback,
                step_base + step_span * 0.1,
                f"Đang tải {type_label} ({idx+1}/{total})...",
            )

            # Tải file trực tiếp qua luồng stream
            temp_path = dest_path.with_suffix(f".{ext}.part")
            try:
                req = urllib.request.Request(
                    media_url,
                    headers={
                        "User-Agent": self.USER_AGENT,
                        "Referer": "https://www.instagram.com/",
                    },
                )
                with urllib.request.urlopen(req, timeout=30) as resp, open(temp_path, "wb") as f:
                    content_length = resp.headers.get("Content-Length")
                    total_bytes = int(content_length) if content_length and content_length.isdigit() else 0
                    downloaded_bytes = 0
                    chunk_size = 64 * 1024

                    while True:
                        if is_cancelled and is_cancelled():
                            raise InterruptedError("Tiến trình tải Instagram đã bị hủy.")

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_bytes += len(chunk)

                        if total_bytes > 0:
                            sub_pct = downloaded_bytes / total_bytes
                            pct = step_base + step_span * sub_pct
                            kb_done = downloaded_bytes // 1024
                            kb_total = total_bytes // 1024
                            self._report(
                                progress_callback,
                                pct,
                                f"Đang tải {type_label} ({idx+1}/{total}): {kb_done}/{kb_total} KB",
                            )

                # Hoàn tất ghi file
                if temp_path.exists():
                    temp_path.rename(dest_path)
                    saved_files.append(str(dest_path))

            except (InterruptedError, KeyboardInterrupt):
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise InterruptedError("Tiến trình tải Instagram đã bị hủy.")
            except Exception as e:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise RuntimeError(f"Lỗi khi tải {type_label} #{idx+1} ({filename}): {e}")

        self._report(progress_callback, 1.0, f"✅ Đã tải thành công {len(saved_files)} file Instagram!")
        return saved_files
