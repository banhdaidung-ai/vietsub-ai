import base64
import json
import os
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

from utils.platform_helper import run_hidden_subprocess

# Vá lỗi PackageNotFoundError cho curl_cffi khi chạy trong môi trường PyInstaller trên Windows
try:
    import importlib.metadata as _meta
    _orig_meta = _meta.metadata
    _orig_ver = _meta.version

    def _safe_metadata(name: str):
        try:
            return _orig_meta(name)
        except _meta.PackageNotFoundError:
            if name and name.lower().replace("-", "_") == "curl_cffi":
                return {"Summary": "curl_cffi", "Version": "0.16.3", "Name": "curl_cffi"}
            raise

    def _safe_version(name: str):
        try:
            return _orig_ver(name)
        except _meta.PackageNotFoundError:
            if name and name.lower().replace("-", "_") == "curl_cffi":
                return "0.16.3"
            raise

    _meta.metadata = _safe_metadata
    _meta.version = _safe_version
except Exception:
    pass

import yt_dlp

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path


def extract_universal_url(text: str) -> Optional[str]:
    """
    Trích xuất đường dẫn URL (HTTP / HTTPS) hợp lệ từ chuỗi văn bản người dùng dán vào,
    xử lý các trường hợp người dùng copy kèm tiêu đề hoặc văn bản chia sẻ từ TikTok, Douyin, YouTube, Facebook...
    """
    if not text:
        return None
    text_clean = text.strip()
    m = re.search(r"https?://[^\s\"'<>]+", text_clean)
    if m:
        url = m.group(0).rstrip(".,;:!?)>]\"'")
        return url
    return None


def _ensure_ffmpeg_in_path():
    """Đảm bảo thư mục chứa binary ffmpeg và ffprobe được đưa vào os.environ['PATH']."""
    try:
        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            p_dir = str(Path(ffmpeg_path).resolve().parent)
            current_path = os.environ.get("PATH", "")
            if p_dir not in current_path:
                os.environ["PATH"] = p_dir + os.pathsep + current_path
    except Exception:
        pass


class VideoDownloader:
    def __init__(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ):
        self.progress_callback = progress_callback
        self.is_cancelled = is_cancelled
        self._downloaded_path: Optional[str] = None

    def _report(self, pct: float, label: str):
        if self.progress_callback:
            self.progress_callback(pct, label)

    def download(self, url: str, output_dir: str, quality: str = "best") -> str:
        """
        Tải video từ URL về output_dir với chất lượng cao nhất.
        Hỗ trợ YouTube, TikTok, Facebook, Bilibili và các trang mạng xã hội khác.
        Trả về đường dẫn file đã tải.
        """
        self._downloaded_path = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        url_clean = url.strip()

        _ensure_ffmpeg_in_path()
        clean_extracted = extract_universal_url(url_clean)
        if clean_extracted:
            url_clean = clean_extracted

        # ── HỖ TRỢ CHUYÊN BIỆT: Douyin (TikTok Trung Quốc) không watermark ──
        if "douyin.com" in url_clean.lower():
            try:
                from core.douyin import DouyinDownloader
                if DouyinDownloader.is_douyin_url(url_clean):
                    douyin_dl = DouyinDownloader()
                    self._downloaded_path = douyin_dl.download_video(
                        raw_url=url_clean,
                        output_dir=output_dir,
                        quality=quality,
                        progress_callback=self.progress_callback,
                        is_cancelled=self.is_cancelled,
                    )
                    return self._downloaded_path
            except Exception as dy_err:
                if isinstance(dy_err, InterruptedError):
                    raise
                pass

        # ── HỖ TRỢ CHUYÊN BIỆT: Xiaohongshu (小红书 / XHS) ──
        from core.xhs_downloader import XHSDownloader
        if XHSDownloader.is_xhs_url(url_clean):
            try:
                self._report(0.02, "Đang giải mã liên kết Xiaohongshu...")
                resolved_xhs = XHSDownloader.resolve_xhs_url(url_clean)
                if resolved_xhs:
                    url_clean = resolved_xhs
                self._report(0.04, "Đã nhận dạng video Xiaohongshu, đang kết nối...")
            except Exception:
                pass


        def progress_hook(d: dict):
            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Tiến trình tải đã bị hủy.")

            status = d.get("status", "")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                speed_str = f" - {speed / 1024 / 1024:.1f}MB/s" if speed else ""
                if total > 0:
                    pct = downloaded / total
                    size_str = (
                        f"{downloaded / 1_048_576:.1f}MB"
                        f"/{total / 1_048_576:.1f}MB"
                    )
                    self._report(pct, f"Đang tải: {pct * 100:.0f}% ({size_str}{speed_str})")
                else:
                    mb = downloaded / 1_048_576
                    self._report(0.5, f"Đang tải: {mb:.1f}MB{speed_str}")
            elif status == "finished":
                self._downloaded_path = d.get("filename") or d.get("_filename")
                self._report(0.95, "Đang hoàn thiện file video...")

        # Cấu hình định dạng tải theo chất lượng yêu cầu
        if quality == "1080p":
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        elif quality == "720p":
            format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif quality == "480p":
            format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        else:
            # Mặc định "best": Lấy chất lượng gốc cao nhất tuyệt đối (4K / 2K / 1080p 60fps, max bitrate)
            format_str = "bestvideo*+bestaudio/bestvideo+bestaudio/best"

        ydl_opts = {
            "format": format_str,
            "merge_output_format": "mp4",
            "outtmpl": str(Path(output_dir) / "%(title).100s.%(ext)s"),
            "windowsfilenames": True,
            "nocheckcertificate": True,
            "restrictfilenames": False,
            "progress_hooks": [progress_hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,vi;q=0.7",
                "Sec-Fetch-Mode": "navigate",
            },
        }

        ffmpeg_bin = get_ffmpeg_path()
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        node_bin = shutil.which("node") or (
            "/usr/local/bin/node" if os.path.exists("/usr/local/bin/node") else None
        )
        if node_bin:
            ydl_opts["js_runtimes"] = {"node": {"path": node_bin}}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_clean, download=True)

                if self._downloaded_path is None:
                    self._downloaded_path = ydl.prepare_filename(info)
        except (InterruptedError, KeyboardInterrupt):
            raise InterruptedError("Tiến trình tải đã bị hủy.")
        except Exception as e:
            err_msg = str(e)

            # ── FALLBACK: Nếu yt-dlp thất bại với XHS URL → thử XHSDownloader chuyên dụng ──
            from core.xhs_downloader import XHSDownloader
            if XHSDownloader.is_xhs_url(url_clean):
                try:
                    self._report(0.05, "Đang thử phương thức tải dự phòng Xiaohongshu...")
                    xhs_dl = XHSDownloader()
                    self._downloaded_path = xhs_dl.download_video(
                        raw_url=url_clean,
                        output_dir=output_dir,
                        quality=quality,
                        progress_callback=self.progress_callback,
                        is_cancelled=self.is_cancelled,
                    )
                    return self._downloaded_path
                except (InterruptedError, KeyboardInterrupt):
                    raise InterruptedError("Tiến trình tải đã bị hủy.")
                except Exception as xhs_err:
                    raise RuntimeError(str(xhs_err))
            elif "Unsupported URL" in err_msg:
                # Trích xuất tên domain để thông báo rõ ràng hơn
                domain_match = re.search(r"https?://([^/\s]+)", err_msg)
                domain = domain_match.group(1) if domain_match else "này"
                raise RuntimeError(
                    f"Nền tảng '{domain}' chưa được hỗ trợ tải trực tiếp.\n"
                    "Hỗ trợ hiện tại: TikTok, Douyin, YouTube, Facebook, Instagram, Bilibili, Xiaohongshu (công khai).\n"
                    "Bạn có thể tải thủ công rồi dùng 'Chọn File Video Trên Máy'."
                )
            raise RuntimeError(f"Không thể tải video từ link: {e}")


        # Fallback: extension có thể đổi sau khi merge
        if self._downloaded_path:
            path = Path(self._downloaded_path)
            if not path.exists():
                for ext in (".mp4", ".mkv", ".webm"):
                    alt = path.with_suffix(ext)
                    if alt.exists():
                        self._downloaded_path = str(alt)
                        break

        # Fallback nếu vẫn chưa thấy file: tìm file video mới nhất trong output_dir
        if not self._downloaded_path or not Path(self._downloaded_path).exists():
            candidates = [
                p for p in Path(output_dir).glob("*")
                if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi")
            ]
            if candidates:
                candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                self._downloaded_path = str(candidates[0])

        return self._downloaded_path

    @staticmethod
    def _clean_artlist_stream_title(audio_url: str, current_title: str = "Artlist_Track") -> str:
        """Trích xuất tên bài hát thân thiện từ URL stream của Artlist (thường là đường dẫn mã hoá base64)."""
        try:
            parsed = urllib.parse.urlparse(audio_url)
            path_part = parsed.path.strip("/")
            if "cms-public-artifacts.artlist.io" in audio_url and path_part:
                b64_candidate = path_part.split("/")[-1]
                pad = len(b64_candidate) % 4
                if pad:
                    b64_candidate += "=" * (4 - pad)
                decoded = base64.b64decode(b64_candidate).decode("utf-8", errors="ignore")
                if "/" in decoded or "." in decoded:
                    stem = Path(decoded).stem
                    parts = stem.split("_-_")
                    if len(parts) >= 2:
                        res = parts[1].replace("_", " ").strip()
                        return re.sub(r"(?i)[_ ]*(?:aac|mp3|wav|m4a)$", "", res).strip() or current_title
                    clean_stem = re.sub(r"^\d+(?:_\d+)*_", "", stem)
                    res = clean_stem.replace("_", " ").strip() or stem
                    return re.sub(r"(?i)[_ ]*(?:aac|mp3|wav|m4a)$", "", res).strip() or current_title
        except Exception:
            pass
        return current_title

    def _download_direct_stream(
        self,
        audio_url: str,
        title: str,
        output_dir: str,
        audio_format: str = "mp3",
        bitrate: str = "320k",
    ) -> str:
        """Tải trực tiếp luồng audio qua HTTP stream và chuyển đổi định dạng bằng FFmpeg."""
        from curl_cffi import requests

        clean_title = re.sub(r'[\\/*?:"<>|]', "", title).strip() or "audio_track"
        if "artlist.io" in audio_url.lower() and (not clean_title or clean_title in ("audio_download", "Artlist_Track") or len(clean_title) > 35):
            clean_title = self._clean_artlist_stream_title(audio_url, clean_title)

        target_ext = audio_format.lower().strip(".")
        if target_ext not in ("mp3", "m4a", "wav"):
            target_ext = "mp3"

        out_path = Path(output_dir) / f"{clean_title}.{target_ext}"
        counter = 1
        while out_path.exists():
            out_path = Path(output_dir) / f"{clean_title} ({counter}).{target_ext}"
            counter += 1

        tmp_file = Path(output_dir) / f"temp_{clean_title}_{counter}.tmp"

        self._report(0.1, f"Đang kết nối tới luồng âm thanh ({clean_title})...")

        # Cấu hình Referer phù hợp theo từng CDN để tránh bị chặn HTTP 403 (đặc biệt là Artlist)
        referer = "https://www.google.com/"
        if "artlist.io" in audio_url.lower():
            referer = "https://artlist.io/"
        elif "epidemicsound.com" in audio_url.lower():
            referer = "https://www.epidemicsound.com/"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Referer": referer,
        }

        r = requests.get(audio_url, stream=True, impersonate="chrome", headers=headers, timeout=20)
        if r.status_code not in (200, 206):
            raise RuntimeError(f"Không thể tải luồng âm thanh: HTTP {r.status_code}")

        total = int(r.headers.get("content-length", 0))
        downloaded = 0

        with open(tmp_file, "wb") as f:
            for chunk in r.iter_content():
                if self.is_cancelled and self.is_cancelled():
                    try:
                        tmp_file.unlink()
                    except Exception:
                        pass
                    raise InterruptedError("Tiến trình tải đã bị hủy.")
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded / total
                        mb_d = downloaded / 1_048_576
                        mb_t = total / 1_048_576
                        self._report(0.1 + pct * 0.75, f"Đang tải nhạc: {pct * 100:.0f}% ({mb_d:.1f}MB/{mb_t:.1f}MB)")
                    else:
                        mb_d = downloaded / 1_048_576
                        self._report(0.5, f"Đang tải nhạc: {mb_d:.1f}MB")

        self._report(0.9, f"Đang hoàn thiện và xuất file {target_ext.upper()} ({bitrate}bps)...")

        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        cmd = [ffmpeg_bin, "-y", "-i", str(tmp_file), "-vn"]
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
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except Exception:
            pass

        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg lỗi khi xuất file audio:\n{res.stderr[-500:]}")

        self._downloaded_path = str(out_path)
        self._report(1.0, f"Đã tải xong: {out_path.name}")
        return str(out_path)

    def download_audio(
        self,
        url: str,
        output_dir: str,
        audio_format: str = "mp3",
        bitrate: str = "320k",
    ) -> str:
        """
        Tải riêng file âm thanh/nhạc từ URL về output_dir.
        Tự động chuyển đổi sang MP3 320kbps (hoặc M4A gốc / WAV lossless) bằng FFmpeg.
        Hỗ trợ Epidemic Sound, YouTube, TikTok, Facebook, Instagram, SoundCloud, Artlist, direct link...
        """
        self._downloaded_path = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        audio_format = audio_format.lower().strip(".")
        if audio_format not in ("mp3", "m4a", "wav"):
            audio_format = "mp3"

        url_clean = url.strip()

        # ── 0. HỖ TRỢ CHUYÊN BIỆT: Douyin (TikTok Trung Quốc) ──
        if "douyin.com" in url_clean.lower():
            try:
                from core.douyin import DouyinDownloader
                if DouyinDownloader.is_douyin_url(url_clean):
                    douyin_dl = DouyinDownloader()
                    self._downloaded_path = douyin_dl.download_audio(
                        raw_url=url_clean,
                        output_dir=output_dir,
                        audio_format=audio_format,
                        bitrate=bitrate,
                        progress_callback=self.progress_callback,
                        is_cancelled=self.is_cancelled,
                    )
                    return self._downloaded_path
            except Exception as dy_err:
                if isinstance(dy_err, InterruptedError):
                    raise
                pass

        # ── 1. HỖ TRỢ CHUYÊN BIỆT: Epidemic Sound (www.epidemicsound.com) ──
        if "epidemicsound.com" in url_clean.lower() and "audiocdn.epidemicsound.com" not in url_clean:
            from curl_cffi import requests

            self._report(0.05, "Đang kết nối tới Epidemic Sound qua kết nối an toàn...")
            try:
                r = requests.get(url_clean, impersonate="chrome", timeout=15)
                if r.status_code == 200:
                    html = r.text
                    title = "Epidemic_Sound_Track"
                    m_title = re.search(r"<title>([^<]+)</title>", html)
                    if m_title:
                        title = m_title.group(1).replace(" | Epidemic Sound", "").strip()

                    m_audio = re.search(r'"lqMp3Url"\s*:\s*"(https://audiocdn\.epidemicsound\.com/[^"]+\.mp3)"', html)
                    if not m_audio:
                        m_audio = re.search(r'(https://audiocdn\.epidemicsound\.com/[a-zA-Z0-9_/.-]+\.mp3)', html)

                    if m_audio:
                        audio_stream_url = m_audio.group(1)
                        return self._download_direct_stream(
                            audio_stream_url,
                            title=title,
                            output_dir=output_dir,
                            audio_format=audio_format,
                            bitrate=bitrate,
                        )
            except Exception as e:
                if isinstance(e, InterruptedError):
                    raise
                pass

        # ── 2. HỖ TRỢ CHUYÊN BIỆT: Artlist.io (artlist.io/royalty-free-music/song/...) ──
        if "artlist.io" in url_clean.lower() and "cms-public-artifacts.artlist.io" not in url_clean and "cdn.artlist.io" not in url_clean:
            from curl_cffi import requests

            self._report(0.05, "Đang kết nối tới Artlist qua kết nối an toàn...")

            # 2.1: Thử lấy dữ liệu bài hát từ Artlist GraphQL API nếu URL có chứa ID
            m_id = re.search(r"/(?:song|track|sfx)/.*?(\d+)(?:[/?#]|$)", url_clean) or re.search(r"/(\d+)(?:[/?#]|$)", url_clean)
            if m_id:
                song_id = m_id.group(1)
                gql_query = """query Songs($ids: [String!]!) {
  songs(ids: $ids) {
    songId
    songName
    artistName
    sitePlayableFilePath
  }
}"""
                try:
                    r_gql = requests.post(
                        "https://search-api.artlist.io/v1/graphql",
                        json={"query": gql_query, "variables": {"ids": [song_id]}},
                        headers={
                            "content-type": "application/json",
                            "referer": "https://artlist.io/",
                        },
                        impersonate="chrome",
                        timeout=10,
                    )
                    if r_gql.status_code == 200:
                        data = r_gql.json()
                        songs = data.get("data", {}).get("songs", [])
                        if songs and songs[0].get("sitePlayableFilePath"):
                            s = songs[0]
                            song_name = s.get("songName", "")
                            artist_name = s.get("artistName", "")
                            track_title = f"{song_name} - {artist_name}".strip(" -") or f"Artlist_{song_id}"
                            audio_stream_url = s.get("sitePlayableFilePath")
                            return self._download_direct_stream(
                                audio_stream_url,
                                title=track_title,
                                output_dir=output_dir,
                                audio_format=audio_format,
                                bitrate=bitrate,
                            )
                except Exception as e:
                    if isinstance(e, InterruptedError):
                        raise

            # 2.2: Fallback phân tích trang HTML của Artlist
            try:
                r = requests.get(url_clean, impersonate="chrome", timeout=15)
                if r.status_code == 200:
                    html = r.text
                    title = "Artlist_Track"
                    m_title = re.search(r"<title>([^<]+)</title>", html)
                    if m_title:
                        raw_title = m_title.group(1)
                        title = raw_title.replace(" - Royalty Free Music | Artlist", "").replace(" | Artlist", "").strip() or "Artlist_Track"

                    # Khớp luồng audio từ JSON state (hỗ trợ cả nháy thường, nháy escape \", và link CDN)
                    m_audio = (
                        re.search(r'sitePlayableFilePath\\?":\\?"(https://cms-public-artifacts\.artlist\.io/[a-zA-Z0-9_/=+-]+)', html)
                        or re.search(r'(https://cms-public-artifacts\.artlist\.io/[a-zA-Z0-9_/=+-]+)', html)
                        or re.search(r'(https://cdn\.artlist\.io/[a-zA-Z0-9_/=+-]+\.(?:mp3|aac|wav|m4a))', html)
                    )

                    if m_audio:
                        audio_stream_url = m_audio.group(1)
                        if title == "Artlist_Track":
                            title = self._clean_artlist_stream_title(audio_stream_url, title)
                        return self._download_direct_stream(
                            audio_stream_url,
                            title=title,
                            output_dir=output_dir,
                            audio_format=audio_format,
                            bitrate=bitrate,
                        )
            except Exception as e:
                if isinstance(e, InterruptedError):
                    raise

            raise RuntimeError(
                "Không thể trích xuất luồng âm thanh từ liên kết Artlist này.\n"
                "Vui lòng kiểm tra lại liên kết bài hát trên Artlist (ví dụ: https://artlist.io/royalty-free-music/song/.../5000) "
                "hoặc dán trực tiếp liên kết phát audio."
            )

        # ── 3. HỖ TRỢ TRỰC TIẾP: Link stream audio / CDN (MP3, AAC, M4A, WAV, audiocdn, cms-public-artifacts) ──
        is_direct_audio = any(
            url_clean.lower().split("?")[0].endswith(ext)
            for ext in (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg")
        ) or "audiocdn.epidemicsound.com" in url_clean or "cms-public-artifacts.artlist.io" in url_clean or "cdn.artlist.io" in url_clean

        if is_direct_audio:
            parsed = urllib.parse.urlparse(url_clean)
            raw_filename = Path(parsed.path).stem or "audio_download"
            if "cms-public-artifacts.artlist.io" in url_clean:
                raw_filename = self._clean_artlist_stream_title(url_clean, raw_filename)
            return self._download_direct_stream(
                url_clean,
                title=raw_filename,
                output_dir=output_dir,
                audio_format=audio_format,
                bitrate=bitrate,
            )

        # ── 4. HỖ TRỢ CÁC NỀN TẢNG VIDEO & NHẠC (YouTube, TikTok, Facebook, SoundCloud...) qua yt-dlp ──
        def progress_hook(d: dict):
            if self.is_cancelled and self.is_cancelled():
                raise InterruptedError("Tiến trình tải đã bị hủy.")

            status = d.get("status", "")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                speed_str = f" - {speed / 1024 / 1024:.1f}MB/s" if speed else ""
                if total > 0:
                    pct = downloaded / total
                    size_str = (
                        f"{downloaded / 1_048_576:.1f}MB"
                        f"/{total / 1_048_576:.1f}MB"
                    )
                    self._report(pct, f"Đang tải nhạc: {pct * 100:.0f}% ({size_str}{speed_str})")
                else:
                    mb = downloaded / 1_048_576
                    self._report(0.5, f"Đang tải nhạc: {mb:.1f}MB{speed_str}")
            elif status == "finished":
                self._downloaded_path = d.get("filename") or d.get("_filename")
                self._report(0.92, f"Đang chuyển đổi sang định dạng {audio_format.upper()} ({bitrate}bps)...")

        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "320" if audio_format == "mp3" else None,
            }
        ]

        _ensure_ffmpeg_in_path()
        clean_extracted = extract_universal_url(url_clean)
        if clean_extracted:
            url_clean = clean_extracted

        # Hỗ trợ Xiaohongshu khi tải chỉ âm thanh
        from core.xhs_downloader import XHSDownloader
        if XHSDownloader.is_xhs_url(url_clean):
            try:
                resolved_xhs = XHSDownloader.resolve_xhs_url(url_clean)
                if resolved_xhs:
                    url_clean = resolved_xhs
            except Exception:
                pass

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(output_dir) / "%(title).100s.%(ext)s"),
            "windowsfilenames": True,
            "nocheckcertificate": True,
            "restrictfilenames": False,
            "progress_hooks": [progress_hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": postprocessors,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,vi;q=0.7",
                "Sec-Fetch-Mode": "navigate",
            },
        }

        ffmpeg_bin = get_ffmpeg_path()
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        node_bin = shutil.which("node") or (
            "/usr/local/bin/node" if os.path.exists("/usr/local/bin/node") else None
        )
        if node_bin:
            ydl_opts["js_runtimes"] = {"node": {"path": node_bin}}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_clean, download=True)
                if self._downloaded_path is None:
                    self._downloaded_path = ydl.prepare_filename(info)
        except (InterruptedError, KeyboardInterrupt):
            raise InterruptedError("Tiến trình tải đã bị hủy.")
        except Exception as e:
            raise RuntimeError(f"Không thể tải âm thanh từ link: {e}")

        # Kiểm tra file với extension đã chuyển đổi
        expected_ext = f".{audio_format}"
        if self._downloaded_path:
            p = Path(self._downloaded_path)
            target = p.with_suffix(expected_ext)
            if target.exists():
                self._downloaded_path = str(target)
            elif not p.exists():
                for alt_ext in (expected_ext, ".mp3", ".m4a", ".wav", ".aac", ".webm"):
                    candidate = p.with_suffix(alt_ext)
                    if candidate.exists():
                        self._downloaded_path = str(candidate)
                        break

        # Fallback: tìm file audio mới nhất trong output_dir
        if not self._downloaded_path or not Path(self._downloaded_path).exists():
            candidates = [
                p for p in Path(output_dir).glob("*")
                if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg")
            ]
            if candidates:
                candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                self._downloaded_path = str(candidates[0])

        return self._downloaded_path



