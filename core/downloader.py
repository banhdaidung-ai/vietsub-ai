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

    def download(self, url: str, output_dir: str) -> str:
        """
        Tải video từ URL về output_dir.
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
                self._report(0.95, "Đang kiểm tra định dạng tương thích...")

        ydl_opts = {
            # Ưu tiên MP4 codec H.264 (avc1) 1080p trở xuống để tương thích 100% QuickTime/macOS/Windows
            "format": (
                "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]"
                "/bestvideo[vcodec^=h264][height<=1080]+bestaudio[ext=m4a]"
                "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
                "/bestvideo[vcodec^=h264]+bestaudio[ext=m4a]"
                "/bestvideo[height<=1080]+bestaudio"
                "/bestvideo+bestaudio"
                "/best[ext=mp4]/best"
            ),
            "merge_output_format": "mp4",
            "outtmpl": str(Path(output_dir) / "%(title).80s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
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

        # Đảm bảo video dùng codec H.264 (AVC1) chuẩn để QuickTime/macOS luôn phát được mượt mà
        if self._downloaded_path and Path(self._downloaded_path).exists():
            self._ensure_compatible_codec(self._downloaded_path)

        return self._downloaded_path

    def _ensure_compatible_codec(self, video_path: str):
        """
        Đảm bảo video có video codec H.264 (avc1) và pix_fmt yuv420p.
        Các nền tảng như Facebook, YouTube thường nén bằng AV1 hoặc VP9,
        khiến macOS QuickTime Player, QuickLook và DaVinci Resolve không thể mở được.
        Hàm này tự động phát hiện và chuyển đổi sang H.264 nếu cần.
        """
        ffprobe = get_ffprobe_path()
        ffmpeg = get_ffmpeg_path()
        if not ffprobe or not ffmpeg:
            return

        try:
            res = subprocess.run(
                [
                    ffprobe, "-v", "quiet", "-print_format", "json",
                    "-show_streams", video_path,
                ],
                capture_output=True,
                text=True,
            )
            data = json.loads(res.stdout)
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                None,
            )
            if not video_stream:
                return

            codec = video_stream.get("codec_name", "").lower()
            pix_fmt = video_stream.get("pix_fmt", "").lower()

            # Nếu codec không phải h264 (ví dụ av1, vp9) hoặc pix_fmt không phải yuv420p
            if codec != "h264" or pix_fmt != "yuv420p":
                self._report(0.96, f"Đang chuẩn hóa chuẩn H.264 ({codec} → h264 để QuickTime phát được)...")
                temp_converted = video_path + ".h264_tmp.mp4"
                cmd = [
                    ffmpeg, "-y", "-i", video_path,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "192k",
                    temp_converted,
                ]
                conv_res = subprocess.run(cmd, capture_output=True, text=True)
                if (
                    conv_res.returncode == 0
                    and os.path.exists(temp_converted)
                    and os.path.getsize(temp_converted) > 0
                ):
                    os.replace(temp_converted, video_path)
                else:
                    if os.path.exists(temp_converted):
                        os.remove(temp_converted)
        except Exception:
            pass

