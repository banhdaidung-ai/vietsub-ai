"""
gui/ffmpeg_download_dialog.py — Hộp thoại tải và cài đặt FFmpeg tự động trực quan
"""

import sys
import threading
from typing import Callable, Optional

import customtkinter as ctk

from utils.ffmpeg_check import check_ffmpeg, download_ffmpeg_binaries, get_platform_key


class FFmpegDownloadDialog(ctk.CTkToplevel):
    def __init__(self, master, on_success: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.title("⚡ Cài Đặt FFmpeg Tự Động")
        self.geometry("480x280")
        self.resizable(False, False)

        # Căn giữa hộp thoại so với cửa sổ cha
        self.update_idletasks()
        try:
            x = master.winfo_x() + (master.winfo_width() // 2) - 240
            y = master.winfo_y() + (master.winfo_height() // 2) - 140
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self.on_success = on_success
        self._is_downloading = False

        self._build_ui()
        self.after(200, self._start_download)

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=24, pady=20)

        # Header Title
        title_box = ctk.CTkFrame(container, fg_color="transparent")
        title_box.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            title_box,
            text="⚡ Tự Động Tải & Cài Đặt FFmpeg",
            font=("Arial", 16, "bold"),
        ).pack(anchor="w")

        platform_name = {
            "win32": "Windows (64-bit)",
            "darwin_arm64": "macOS Apple Silicon (M1/M2/M3/M4)",
            "darwin": "macOS Intel",
            "linux": "Linux (x86_64)",
            "linux_arm64": "Linux (ARM64)",
        }.get(get_platform_key(), sys.platform)

        ctk.CTkLabel(
            title_box,
            text=f"Phiên bản tương thích: {platform_name} (~72 MB)",
            font=("Arial", 12),
            text_color="#94A3B8",
        ).pack(anchor="w", pady=(2, 0))

        # Progress Bar Card
        card = ctk.CTkFrame(container, corner_radius=10, border_width=1, border_color="#334155")
        card.pack(fill="x", pady=10, ipady=8)

        self.lbl_status = ctk.CTkLabel(
            card,
            text="Đang khởi tạo kết nối...",
            font=("Arial", 12),
            text_color="#E2E8F0",
        )
        self.lbl_status.pack(anchor="w", padx=16, pady=(8, 6))

        self.prog_bar = ctk.CTkProgressBar(
            card,
            height=12,
            corner_radius=6,
            progress_color="#10B981",
        )
        self.prog_bar.pack(fill="x", padx=16, pady=(0, 8))
        self.prog_bar.set(0.0)

        self.lbl_detail = ctk.CTkLabel(
            card,
            text="Quá trình tải về và cấu hình diễn ra hoàn toàn tự động.",
            font=("Arial", 11),
            text_color="#94A3B8",
        )
        self.lbl_detail.pack(anchor="w", padx=16, pady=(0, 4))

        # Footer Button
        self.btn_action = ctk.CTkButton(
            container,
            text="Đang xử lý...",
            state="disabled",
            height=34,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=self.destroy,
        )
        self.btn_action.pack(side="right", pady=(10, 0))

    def _start_download(self):
        if self._is_downloading:
            return
        self._is_downloading = True
        self.btn_action.configure(state="disabled", text="Đang tải về...")

        def run_thread():
            def progress_callback(pct, downloaded, total, msg):
                self.after(0, self._update_progress, pct, msg)

            success, message = download_ffmpeg_binaries(progress_callback)
            self.after(0, self._on_finish, success, message)

        t = threading.Thread(target=run_thread, daemon=True)
        t.start()

    def _update_progress(self, pct: float, msg: str):
        try:
            self.prog_bar.set(max(0.0, min(1.0, pct)))
            self.lbl_status.configure(text=msg)
        except Exception:
            pass

    def _on_finish(self, success: bool, message: str):
        self._is_downloading = False
        if success:
            self.prog_bar.set(1.0)
            self.lbl_status.configure(
                text="✅ Đã cài đặt FFmpeg thành công!", text_color="#34D399"
            )
            self.lbl_detail.configure(
                text="Hệ thống đã sẵn sàng xử lý video và phụ đề.", text_color="#A7F3D0"
            )
            self.btn_action.configure(
                state="normal",
                text="Đóng & Sử Dụng",
                fg_color="#065F46",
                hover_color="#047857",
            )
            if self.on_success:
                try:
                    self.on_success()
                except Exception:
                    pass
        else:
            self.lbl_status.configure(
                text="❌ Tải FFmpeg thất bại", text_color="#FCA5A5"
            )
            self.lbl_detail.configure(text=message[:150], text_color="#F87171")
            self.btn_action.configure(
                state="normal",
                text="Đóng",
                fg_color="#7F1D1D",
                hover_color="#991B1B",
            )
