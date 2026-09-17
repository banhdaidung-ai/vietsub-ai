import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from utils.ffmpeg_check import get_ffmpeg_path, get_ffprobe_path


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
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            },
        }

        ffmpeg_bin = get_ffmpeg_path()
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        import shutil
        node_bin = shutil.which("node") or (
            "/usr/local/bin/node" if os.path.exists("/usr/local/bin/node") else None
        )
        if node_bin:
            ydl_opts["js_runtimes"] = {"node": {"path": node_bin}}

        # Chuẩn hóa link nếu là Douyin modal_id
        if "douyin.com" in url and "modal_id=" in url:
            import re
            m = re.search(r"modal_id=(\d+)", url)
            if m:
                url = f"https://www.douyin.com/video/{m.group(1)}"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                if self._downloaded_path is None:
                    self._downloaded_path = ydl.prepare_filename(info)
        except (InterruptedError, KeyboardInterrupt):
            raise InterruptedError("Tiến trình tải đã bị hủy.")
        except Exception as e:
            err_str = str(e)
            if "douyin" in url.lower() or "douyin" in err_str.lower():
                raise RuntimeError(
                    "Douyin chặn tải tự động qua link (yêu cầu xác thực chống bot).\n"
                    "👉 Sếp vui lòng tải video về máy trước (hoặc dùng nút tải của Cốc Cốc/trình duyệt), sau đó chọn file ở tab 'File Video' để dịch mượt mà 100% nhé ạ!"
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
        import re

        clean_title = re.sub(r'[\\/*?:"<>|]', "", title).strip() or "audio_track"
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

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.google.com/",
        }

        r = requests.get(audio_url, stream=True, impersonate="chrome", headers=headers, timeout=20)
        if r.status_code not in (200, 206):
            raise RuntimeError(f"Không thể tải luồng âm thanh: HTTP {r.status_code}")

        total = int(r.headers.get("content-length", 0))
        downloaded = 0

        with open(tmp_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
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

        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
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

        # ── 1. HỖ TRỢ CHUYÊN BIỆT: Epidemic Sound (www.epidemicsound.com) ──
        if "epidemicsound.com" in url_clean.lower() and "audiocdn.epidemicsound.com" not in url_clean:
            import re
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
            import re
            from curl_cffi import requests

            self._report(0.05, "Đang kết nối tới Artlist qua kết nối an toàn...")
            try:
                r = requests.get(url_clean, impersonate="chrome", timeout=15)
                if r.status_code == 200:
                    html = r.text
                    title = "Artlist_Track"
                    m_title = re.search(r"<title>([^<]+)</title>", html)
                    if m_title:
                        raw_title = m_title.group(1)
                        title = raw_title.replace(" - Royalty Free Music | Artlist", "").replace(" | Artlist", "").strip() or "Artlist_Track"

                    m_audio = re.search(r'"sitePlayableFilePath"\s*:\s*"(https://cms-public-artifacts\.artlist\.io/[a-zA-Z0-9_/=+-]+)"', html)
                    if not m_audio:
                        m_audio = re.search(r'sitePlayableFilePath[^:]*:[^h]*(https://cms-public-artifacts\.artlist\.io/[a-zA-Z0-9_/=+-]+)', html)
                    if not m_audio:
                        m_audio = re.search(r'(https://cms-public-artifacts\.artlist\.io/[a-zA-Z0-9_/=+-]+)', html)

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

        # ── 3. HỖ TRỢ TRỰC TIẾP: Link stream audio / CDN (MP3, AAC, M4A, WAV, audiocdn, cms-public-artifacts) ──
        is_direct_audio = any(
            url_clean.lower().split("?")[0].endswith(ext)
            for ext in (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg")
        ) or "audiocdn.epidemicsound.com" in url_clean or "cms-public-artifacts.artlist.io" in url_clean or "cdn.artlist.io" in url_clean

        if is_direct_audio:
            import urllib.parse
            parsed = urllib.parse.urlparse(url_clean)
            raw_filename = Path(parsed.path).stem or "audio_download"
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

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(output_dir) / "%(title).100s.%(ext)s"),
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
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            },
        }

        ffmpeg_bin = get_ffmpeg_path()
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        import shutil
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
            err_str = str(e)
            if "artlist.io" in url_clean.lower():
                raise RuntimeError(
                    "Artlist.io bảo vệ trang web bằng tường lửa Cloudflare và mã hoá phiên duyệt.\n"
                    "👉 Cách tải nhạc Artlist về máy dễ nhất:\n"
                    "1. Mở bài nhạc trên trình duyệt (Cốc Cốc/Chrome) > bấm F12 > chọn tab Network > tìm '.aac' hoặc '.mp3' > copy link đó dán vào đây để app tải và xuất MP3 320kbps!\n"
                    "2. Hoặc tìm tên bài hát trên YouTube / SoundCloud rồi dán link vào đây, app sẽ tải trọn vẹn chất lượng cao nhất cho Sếp ngay lập tức!"
                )
            if "douyin" in url_clean.lower() or "douyin" in err_str.lower():
                raise RuntimeError(
                    "Douyin chặn tải tự động qua link (yêu cầu xác thực chống bot).\n"
                    "👉 Sếp vui lòng tải video về máy trước, sau đó chọn file ở tab 'File Video' và bấm '🎵 Trích Xuất Audio' nhé ạ!"
                )
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



