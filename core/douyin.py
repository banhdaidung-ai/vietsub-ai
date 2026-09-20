import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from utils.platform_helper import run_hidden_subprocess

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

from utils.ffmpeg_check import get_ffmpeg_path


class DouyinDownloader:
    """
    Trình bóc tách và tải video / âm thanh từ Douyin (TikTok Trung Quốc).
    - Vượt bảo vệ chống bot của Douyin bằng cách tự động đăng ký cookie `ttwid` qua ByteDance.
    - Dùng curl_cffi giả lập trình duyệt Chrome (vượt kiểm tra TLS fingerprint/JA3).
    - Tải trực tiếp luồng video chất lượng gốc không watermark (không dính logo).
    - Hỗ trợ đầy đủ báo cáo tiến trình theo thời gian thực và ngắt tiến trình (cancel).
    """

    _cached_ttwid: Optional[str] = None
    _ttwid_timestamp: float = 0.0

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
    MOBILE_USER_AGENT = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    )

    @classmethod
    def is_douyin_url(cls, text: str) -> bool:
        """Kiểm tra chuỗi đầu vào có chứa link Douyin hay không."""
        if not text:
            return False
        lower = text.lower()
        return "douyin.com" in lower or "iesdouyin.com" in lower

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        """
        Trích xuất URL Douyin từ văn bản người dùng nhập/dán
        (xử lý trường hợp người dùng copy nguyên cả đoạn text chia sẻ từ app Douyin).
        """
        if not text:
            return None
        m = re.search(r"https?://[a-zA-Z0-9./?=&#%_+-]+", text.strip())
        if m:
            candidate = m.group(0)
            if cls.is_douyin_url(candidate):
                return candidate
        return None

    @classmethod
    def get_ttwid(cls, force_refresh: bool = False) -> str:
        """
        Lấy cookie ttwid từ máy chủ ByteDance.
        Cookie này có hiệu lực dài và được cache trong bộ nhớ để tái sử dụng.
        """
        now = time.time()
        # Cache ttwid trong 6 giờ
        if not force_refresh and cls._cached_ttwid and (now - cls._ttwid_timestamp < 21600):
            return cls._cached_ttwid

        url = "https://ttwid.bytedance.com/ttwid/union/register/"
        payload = {
            "region": "cn",
            "aid": 1768,
            "needFid": "false",
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https",
            "union": "true",
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": cls.USER_AGENT,
        }

        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            ttwid = r.cookies.get("ttwid")
            if ttwid:
                cls._cached_ttwid = ttwid
                cls._ttwid_timestamp = now
                return ttwid
        except Exception:
            pass

        # Fallback: Nếu không lấy được qua ixigua aid, thử gọi root douyin
        try:
            r_dy = requests.get("https://www.douyin.com/", impersonate="chrome120", timeout=10)
            ttwid = r_dy.cookies.get("ttwid")
            if ttwid:
                cls._cached_ttwid = ttwid
                cls._ttwid_timestamp = now
                return ttwid
        except Exception:
            pass

        # Nếu không lấy được, dùng fallback cookie ttwid mặc định dự phòng
        if cls._cached_ttwid:
            return cls._cached_ttwid
        return "1%7Cfallback_ttwid"

    @classmethod
    def resolve_aweme_id(cls, raw_input: str) -> str:
        """
        Giải mã URL ngắn (v.douyin.com) hoặc URL web để lấy ID video (aweme_id).
        """
        url = cls.extract_url(raw_input) or raw_input.strip()

        # Kiểm tra nếu đã có sẵn số ID trong link (modal_id=xxx hoặc /video/xxx)
        m_modal = re.search(r"modal_id=(\d+)", url)
        if m_modal:
            return m_modal.group(1)

        m_direct = re.search(r"/(?:video|note|share/video)/(\d+)", url)
        if m_direct:
            return m_direct.group(1)

        # Nếu là link rút gọn v.douyin.com, cần theo dõi chuyển hướng (redirect)
        headers = {
            "User-Agent": cls.MOBILE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        final_url = url
        try:
            r = requests.get(url, headers=headers, impersonate="chrome120", timeout=10)
            final_url = r.url
        except Exception:
            # Fallback dùng requests thường nếu curl_cffi gặp lỗi mạng tạm thời
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": cls.MOBILE_USER_AGENT})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    final_url = resp.geturl()
            except Exception:
                pass

        m_vid = re.search(r"/(?:video|note|share/video)/(\d+)", final_url)
        if m_vid:
            return m_vid.group(1)

        m_id = re.search(r"itemId=(\d+)", final_url)
        if m_id:
            return m_id.group(1)

        m_any = re.search(r"/(\d{15,25})", final_url)
        if m_any:
            return m_any.group(1)

        # Nếu không tìm thấy trong URL, tìm trong nội dung HTML phản hồi
        if "r" in locals() and hasattr(r, "text"):
            m_html = re.search(r'["\']itemId["\']\s*:\s*["\'](\d+)["\']', r.text)
            if m_html:
                return m_html.group(1)
            m_html2 = re.search(r'["\']aweme_id["\']\s*:\s*["\'](\d+)["\']', r.text)
            if m_html2:
                return m_html2.group(1)

        raise RuntimeError(f"Không thể trích xuất mã ID video từ liên kết Douyin:\n{url}")

    @classmethod
    def get_aweme_detail(cls, aweme_id: str) -> dict:
        """
        Gọi Douyin Aweme Detail Web API để lấy toàn bộ thông tin video và link tải không watermark.
        """
        api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}"
        ttwid = cls.get_ttwid()

        headers = {
            "User-Agent": cls.USER_AGENT,
            "Referer": "https://www.douyin.com/",
            "Cookie": f"ttwid={ttwid};",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        r = requests.get(api_url, headers=headers, impersonate="chrome120", timeout=15)
        if r.status_code != 200 or len(r.text.strip()) == 0:
            # Thử làm mới ttwid và gọi lại 1 lần
            ttwid = cls.get_ttwid(force_refresh=True)
            headers["Cookie"] = f"ttwid={ttwid};"
            r = requests.get(api_url, headers=headers, impersonate="chrome120", timeout=15)

        if r.status_code != 200 or len(r.text.strip()) == 0:
            raise RuntimeError(
                f"Không thể lấy thông tin video Douyin (HTTP {r.status_code}).\n"
                "Có thể video đã bị ẩn/xóa hoặc máy chủ Douyin tạm thời giới hạn."
            )

        try:
            data = r.json()
        except Exception as e:
            raise RuntimeError(f"Lỗi phản hồi dữ liệu từ Douyin: {e}")

        aweme_detail = data.get("aweme_detail")
        if not aweme_detail:
            filter_reason = data.get("filter_detail", {}).get("notice_name", "")
            msg = f" ({filter_reason})" if filter_reason else ""
            raise RuntimeError(f"Không tìm thấy chi tiết video Douyin{msg}. Có thể video riêng tư hoặc đã bị xóa.")

        return aweme_detail

    @classmethod
    def clean_title(cls, title: str, aweme_id: str) -> str:
        """Làm sạch tiêu đề video để đặt tên file an toàn trên Windows và macOS."""
        clean = re.sub(r'[\\/*?:"<>|#\n\r\t]', " ", title or "").strip()
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = clean.strip(". ")
        if len(clean) > 80:
            clean = clean[:80].strip(". ")
        if not clean:
            clean = f"douyin_{aweme_id}"
        return clean

    def download_video(
        self,
        raw_url: str,
        output_dir: str,
        quality: str = "best",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Tải video Douyin trực tiếp chất lượng gốc (không logo watermark).
        Hỗ trợ các độ phân giải: best, 1080p, 720p, 480p.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(0.02, "Đang giải mã liên kết Douyin...")

        aweme_id = self.resolve_aweme_id(raw_url)

        if is_cancelled and is_cancelled():
            raise InterruptedError("Tiến trình tải đã bị hủy.")

        if progress_callback:
            progress_callback(0.05, "Đang kết nối máy chủ Douyin & lấy luồng video gốc...")

        aweme = self.get_aweme_detail(aweme_id)
        raw_desc = aweme.get("desc", "")
        title = self.clean_title(raw_desc, aweme_id)

        video = aweme.get("video", {})
        bit_rates = video.get("bit_rate", [])

        # 1. Trích xuất mã định danh luồng video_id (uri của play_addr)
        video_id = (
            video.get("play_addr", {}).get("uri")
            or video.get("play_addr_h264", {}).get("uri")
            or video.get("play_addr_265", {}).get("uri")
        )
        if not video_id and "download_addr" in video:
            video_id = video.get("download_addr", {}).get("uri")

        selected_urls: List[str] = []
        quality_lower = str(quality).lower().strip()

        # 2. Xây dựng danh sách URL tải chất lượng cao (ưu tiên Full HD 1080p gốc không watermark)
        if quality_lower in ("best", "1080p", "4k", "2k"):
            if video_id:
                # Gateway CDN cao cấp nhất của ByteDance (1080p Full HD)
                selected_urls.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0")
                selected_urls.append(f"https://api.amemv.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0")
                selected_urls.append(f"https://api-play.amemv.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0")
                selected_urls.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=default&line=0")

            # Luồng H.264 chất lượng cao (bitrate cao)
            for u in video.get("play_addr_h264", {}).get("url_list", []):
                if u not in selected_urls:
                    selected_urls.append(u)

        elif quality_lower == "720p":
            # Ưu tiên luồng H.264 720p bitrate cao
            for u in video.get("play_addr_h264", {}).get("url_list", []):
                if u not in selected_urls:
                    selected_urls.append(u)

            if video_id:
                selected_urls.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=720p&line=0")
                selected_urls.append(f"https://api.amemv.com/aweme/v1/play/?video_id={video_id}&ratio=720p&line=0")

        elif quality_lower == "480p":
            if video_id:
                selected_urls.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=540p&line=0")
                selected_urls.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=480p&line=0")

            for b in bit_rates:
                gear = str(b.get("gear_name", "")).lower()
                if "540" in gear or "480" in gear:
                    for u in b.get("play_addr", {}).get("url_list", []):
                        if u not in selected_urls:
                            selected_urls.append(u)

        # 3. Dự phòng các luồng từ bit_rate (sắp xếp theo bitrate cao nhất) và play_addr
        if bit_rates:
            sorted_rates = sorted(bit_rates, key=lambda x: x.get("bit_rate", 0), reverse=True)
            for b in sorted_rates:
                for u in b.get("play_addr", {}).get("url_list", []):
                    if u not in selected_urls:
                        selected_urls.append(u)

        for u in video.get("play_addr", {}).get("url_list", []):
            if u not in selected_urls:
                selected_urls.append(u)

        if not selected_urls:
            images = aweme.get("images", [])
            if images:
                raise RuntimeError("Liên kết này là bài đăng bộ ảnh Douyin (không phải video).")
            raise RuntimeError("Không tìm thấy luồng tải video khả dụng cho bài đăng Douyin này.")

        # Chuẩn bị file xuất
        out_file = Path(output_dir) / f"{title}.mp4"
        counter = 1
        while out_file.exists():
            out_file = Path(output_dir) / f"{title} ({counter}).mp4"
            counter += 1

        tmp_file = Path(output_dir) / f"temp_{title}_{int(time.time())}.tmp"

        headers = {
            "User-Agent": self.USER_AGENT,
            "Referer": "https://www.douyin.com/",
        }

        # Thử tải từ danh sách CDN URLs của Douyin
        last_err = None
        for stream_url in selected_urls:
            if is_cancelled and is_cancelled():
                raise InterruptedError("Tiến trình tải đã bị hủy.")

            try:
                r = requests.get(
                    stream_url,
                    headers=headers,
                    stream=True,
                    impersonate="chrome120",
                    timeout=20,
                )
                if r.status_code not in (200, 206):
                    continue

                total_bytes = int(r.headers.get("content-length", 0))
                downloaded = 0
                start_time = time.time()
                last_report_time = 0.0
                last_reported_pct = -1.0

                with open(tmp_file, "wb") as f:
                    for chunk in r.iter_content():
                        if is_cancelled and is_cancelled():
                            try:
                                tmp_file.unlink()
                            except Exception:
                                pass
                            raise InterruptedError("Tiến trình tải đã bị hủy.")

                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            elapsed = max(now - start_time, 0.001)
                            speed = downloaded / elapsed
                            speed_str = f" - {speed / 1048576:.1f}MB/s" if speed > 0 else ""

                            if progress_callback:
                                if total_bytes > 0:
                                    pct = min(0.08 + (downloaded / total_bytes) * 0.88, 0.98)
                                    if (pct - last_reported_pct >= 0.01) or (now - last_report_time >= 0.25):
                                        last_reported_pct = pct
                                        last_report_time = now
                                        mb_d = downloaded / 1048576
                                        mb_t = total_bytes / 1048576
                                        progress_callback(
                                            pct,
                                            f"Đang tải video Douyin: {pct * 100:.0f}% ({mb_d:.1f}MB/{mb_t:.1f}MB{speed_str})"
                                        )
                                else:
                                    if now - last_report_time >= 0.25:
                                        last_report_time = now
                                        mb_d = downloaded / 1048576
                                        progress_callback(
                                            0.5,
                                            f"Đang tải video Douyin: {mb_d:.1f}MB{speed_str}"
                                        )

                # Kiểm tra dung lượng file đã tải
                if tmp_file.exists() and tmp_file.stat().st_size > 50000:
                    for _attempt in range(5):
                        try:
                            if out_file.exists():
                                out_file.unlink()
                            shutil.move(str(tmp_file), str(out_file))
                            break
                        except Exception:
                            time.sleep(0.2)
                    else:
                        tmp_file.replace(out_file)

                    if progress_callback:
                        progress_callback(1.0, f"Đã tải xong: {out_file.name}")
                    return str(out_file)
            except Exception as e:
                last_err = e
                if isinstance(e, InterruptedError):
                    raise
                continue

        # Dọn dẹp nếu có lỗi
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except Exception:
                pass

        raise RuntimeError(f"Không thể tải video Douyin: {last_err or 'Các máy chủ CDN không phản hồi'}")

    def download_audio(
        self,
        raw_url: str,
        output_dir: str,
        audio_format: str = "mp3",
        bitrate: str = "320k",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Tải riêng file âm thanh / nhạc nền từ video Douyin.
        Tự động trích xuất sang MP3 320kbps / M4A / WAV bằng FFmpeg.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        target_ext = audio_format.lower().strip(".")
        if target_ext not in ("mp3", "m4a", "wav"):
            target_ext = "mp3"

        if progress_callback:
            progress_callback(0.02, "Đang giải mã liên kết Douyin...")

        aweme_id = self.resolve_aweme_id(raw_url)

        if is_cancelled and is_cancelled():
            raise InterruptedError("Tiến trình tải đã bị hủy.")

        if progress_callback:
            progress_callback(0.05, "Đang kết nối lấy thông tin âm thanh Douyin...")

        aweme = self.get_aweme_detail(aweme_id)
        music = aweme.get("music", {})
        music_urls = music.get("play_url", {}).get("url_list", [])
        raw_title = music.get("title") or aweme.get("desc") or f"douyin_{aweme_id}"
        title = self.clean_title(raw_title, aweme_id)

        out_path = Path(output_dir) / f"{title}.{target_ext}"
        counter = 1
        while out_path.exists():
            out_path = Path(output_dir) / f"{title} ({counter}).{target_ext}"
            counter += 1

        tmp_audio = Path(output_dir) / f"temp_{title}_{int(time.time())}.tmp"

        headers = {
            "User-Agent": self.USER_AGENT,
            "Referer": "https://www.douyin.com/",
        }

        downloaded_stream = False
        if music_urls:
            for m_url in music_urls:
                if is_cancelled and is_cancelled():
                    raise InterruptedError("Tiến trình tải đã bị hủy.")
                try:
                    r = requests.get(m_url, headers=headers, stream=True, impersonate="chrome120", timeout=15)
                    if r.status_code in (200, 206):
                        total = int(r.headers.get("content-length", 0))
                        downloaded = 0
                        last_audio_report = 0.0
                        with open(tmp_audio, "wb") as f:
                            for chunk in r.iter_content():
                                if is_cancelled and is_cancelled():
                                    try:
                                        tmp_audio.unlink()
                                    except Exception:
                                        pass
                                    raise InterruptedError("Tiến trình tải đã bị hủy.")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    now = time.time()
                                    if progress_callback and (now - last_audio_report >= 0.25):
                                        last_audio_report = now
                                        pct = 0.05 + (downloaded / max(total, 1)) * 0.80
                                        progress_callback(pct, f"Đang tải nhạc Douyin: {pct * 100:.0f}%")
                        if tmp_audio.exists() and tmp_audio.stat().st_size > 10000:
                            downloaded_stream = True
                            break
                except Exception:
                    continue

        # Nếu không tải được luồng nhạc riêng, tải luồng video và trích xuất audio
        if not downloaded_stream:
            if progress_callback:
                progress_callback(0.2, "Đang trích xuất âm thanh từ luồng video Douyin...")
            tmp_video = self.download_video(
                raw_url,
                output_dir=output_dir,
                quality="480p",
                progress_callback=lambda p, l: progress_callback(p * 0.8, f"[Âm thanh] {l}") if progress_callback else None,
                is_cancelled=is_cancelled,
            )
            input_media = tmp_video
            remove_input = True
        else:
            input_media = str(tmp_audio)
            remove_input = True

        if progress_callback:
            progress_callback(0.9, f"Đang hoàn thiện định dạng {target_ext.upper()} ({bitrate}bps)...")

        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        cmd = [ffmpeg_bin, "-y", "-i", input_media, "-vn"]
        if target_ext == "mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
        elif target_ext == "m4a":
            cmd += ["-c:a", "aac", "-b:a", bitrate]
        elif target_ext == "wav":
            cmd += ["-c:a", "pcm_s16le"]
        else:
            cmd += ["-c:a", "libmp3lame", "-b:a", "320k"]
        cmd.append(str(out_path))

        res = run_hidden_subprocess(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

        if remove_input and os.path.exists(input_media):
            try:
                os.remove(input_media)
            except Exception:
                pass

        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg lỗi khi xuất file audio:\n{res.stderr[-500:]}")

        if progress_callback:
            progress_callback(1.0, f"Đã tải xong nhạc: {out_path.name}")

        return str(out_path)
