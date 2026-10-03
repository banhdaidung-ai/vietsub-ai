"""
gui/gdrive_download_dialog.py — Hộp thoại tải tệp và thư mục Google Drive trực tiếp (Không Zip)
Giao diện macOS Sequoia / Sonoma Dark Mode cao cấp, đồng bộ với toàn bộ ứng dụng Vietsub AI.
"""

import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from core.gdrive_downloader import GDriveDownloader, format_bytes, parse_gdrive_url
from core.gdrive_auth import has_valid_cookies
from gui.gdrive_auth_dialog import GDriveAuthDialog
from utils.config import get_output_dir, load_config

# ─── Design Tokens ────────────────────────────────────────────────────────────
BG_WINDOW = "#141518"
BG_CARD = "#1C1F27"
BG_INSET = "#121419"
BORDER_CARD = "#2E3342"
BORDER_INSET = "#252834"
BG_PILL = "#272B37"
BG_PILL_HOVER = "#343949"

APPLE_BLUE = "#0A84FF"
APPLE_BLUE_HOVER = "#0071E3"
APPLE_GREEN = "#30D158"
APPLE_GREEN_HOVER = "#28B84C"
APPLE_RED = "#FF453A"
APPLE_RED_HOVER = "#D73327"
APPLE_ORANGE = "#FF9F0A"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_MUTED = "#636366"
# ─────────────────────────────────────────────────────────────────────────────


def _open_folder(path: str) -> None:
    """Mở thư mục bằng trình quản lý tệp mặc định của hệ điều hành."""
    try:
        if not path or not os.path.exists(path):
            return
        p = Path(path).resolve()
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        elif sys.platform == "win32":
            os.startfile(os.path.normpath(str(p)))
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception:
        pass


class GDriveDownloadDialog(ctk.CTkToplevel):
    """
    Hộp thoại tải Google Drive trực tiếp không qua nén ZIP.
    Hỗ trợ quét đệ quy, tải đa luồng, lọc ảnh và hiển thị tiến trình thời gian thực.
    """

    def __init__(self, master, default_output_dir: Optional[str] = None):
        super().__init__(master)
        self.master = master

        self.title("📥 Tải Google Drive Trực Tiếp (Không Zip)")
        self.geometry("650x700")
        self.minsize(580, 560)
        self.configure(fg_color=BG_WINDOW)

        # Trạng thái tiến trình
        self._is_downloading = False
        self._cancel_event = threading.Event()
        self._msg_queue: queue.Queue = queue.Queue()
        self._download_thread: Optional[threading.Thread] = None

        # Thiết lập thư mục lưu mặc định
        cfg = load_config()
        base_dir = default_output_dir or get_output_dir(cfg)
        self.target_dir = os.path.join(base_dir, "GDrive_Downloads")

        # Thuộc tính cửa sổ modal
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self._build_ui()
        self.update_idletasks()
        self._center_on_parent(master)

        # Bắt sự kiện đóng cửa sổ và làm mới trạng thái xác thực khi cửa sổ nhận focus
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<FocusIn>", lambda e: self._refresh_auth_status())

        # Bắt đầu vòng lặp đọc hàng đợi giao diện
        self._check_queue()

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── 1. Action Buttons (DOCK ĐÁY CỬA SỔ ĐẦU TIÊN ĐỂ KHÔNG BAO GIỜ BỊ CHE/ẨN) ──
        btn_bar = ctk.CTkFrame(outer, fg_color="transparent")
        btn_bar.pack(side="bottom", fill="x", pady=(10, 0))

        self.btn_start = ctk.CTkButton(
            btn_bar,
            text="🚀 Bắt Đầu Tải",
            font=("Arial", 13, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            text_color="#FFFFFF",
            height=38,
            corner_radius=8,
            command=self._start_download,
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_cancel = ctk.CTkButton(
            btn_bar,
            text="⏹ Dừng",
            font=("Arial", 12, "bold"),
            fg_color=APPLE_RED,
            hover_color=APPLE_RED_HOVER,
            text_color="#FFFFFF",
            width=90,
            height=38,
            corner_radius=8,
            state="disabled",
            command=self._cancel_download,
        )
        self.btn_cancel.pack(side="left", padx=4)

        self.btn_open = ctk.CTkButton(
            btn_bar,
            text="📂 Mở Thư Mục",
            font=("Arial", 12),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            width=115,
            height=38,
            corner_radius=8,
            command=self._open_output_dir,
        )
        self.btn_open.pack(side="left", padx=4)

        self.btn_close = ctk.CTkButton(
            btn_bar,
            text="Đóng",
            font=("Arial", 12),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            width=80,
            height=38,
            corner_radius=8,
            command=self._on_close,
        )
        self.btn_close.pack(side="right", padx=(6, 0))

        # ── 2. Header ──
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(side="top", fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header,
            text="📥 Tải File & Thư Mục Google Drive",
            font=("Arial", 18, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Tải trực tiếp từng ảnh/file nguyên bản, không bị Google nén thành nhiều file zip phân mảnh.",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        # ── 3. Auth Banner Strip (Tài khoản Google Công ty) ──
        self.auth_card = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        self.auth_card.pack(side="top", fill="x", pady=(0, 8))

        inner_auth = ctk.CTkFrame(self.auth_card, fg_color="transparent")
        inner_auth.pack(fill="x", padx=14, pady=8)

        self.lbl_auth_pill = ctk.CTkLabel(
            inner_auth,
            text="",
            font=("Arial", 11, "bold"),
        )
        self.lbl_auth_pill.pack(side="left")

        self.btn_auth_action = ctk.CTkButton(
            inner_auth,
            text="🔐 Đăng Nhập Mail Công Ty",
            font=("Arial", 11, "bold"),
            height=28,
            corner_radius=6,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            command=self._open_auth_dialog,
        )
        self.btn_auth_action.pack(side="right")
        self._refresh_auth_status()

        # ── 4. Card Nhập Liên Kết & Thư Mục Lưu ──
        card_input = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card_input.pack(side="top", fill="x", pady=(0, 8), ipady=4)

        inner_input = ctk.CTkFrame(card_input, fg_color="transparent")
        inner_input.pack(fill="x", padx=14, pady=8)

        # Row URL
        ctk.CTkLabel(
            inner_input,
            text="🔗 Đường dẫn Google Drive (Thư mục hoặc Tệp):",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))

        row_url = ctk.CTkFrame(inner_input, fg_color="transparent")
        row_url.pack(fill="x", pady=(0, 10))

        self.url_var = ctk.StringVar()
        self.entry_url = ctk.CTkEntry(
            row_url,
            textvariable=self.url_var,
            placeholder_text="https://drive.google.com/drive/folders/...",
            height=36,
            corner_radius=8,
            fg_color=BG_INSET,
            border_color=BORDER_INSET,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=("Consolas", 12),
        )
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row_url,
            text="📋 Dán",
            font=("Arial", 11, "bold"),
            width=65,
            height=36,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._paste_clipboard,
        ).pack(side="right")

        ctk.CTkLabel(
            inner_input,
            text="💡 Hỗ trợ tải cả link công khai và link giới hạn nội bộ công ty (Cần đăng nhập mail công ty ở trên).",
            font=("Arial", 11),
            text_color="#FBBF24",
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        # Row Output Dir
        ctk.CTkLabel(
            inner_input,
            text="📂 Thư mục lưu trên máy tính:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))

        row_dir = ctk.CTkFrame(inner_input, fg_color="transparent")
        row_dir.pack(fill="x")

        self.dir_var = ctk.StringVar(value=self.target_dir)
        self.entry_dir = ctk.CTkEntry(
            row_dir,
            textvariable=self.dir_var,
            height=36,
            corner_radius=8,
            fg_color=BG_INSET,
            border_color=BORDER_INSET,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=("Consolas", 11),
        )
        self.entry_dir.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row_dir,
            text="📁 Duyệt...",
            font=("Arial", 11, "bold"),
            width=85,
            height=36,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._browse_directory,
        ).pack(side="right")

        # ── 5. Card Tùy Chọn Tải Thông Minh ──
        card_opts = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card_opts.pack(side="top", fill="x", pady=(0, 8), ipady=2)

        inner_opts = ctk.CTkFrame(card_opts, fg_color="transparent")
        inner_opts.pack(fill="x", padx=14, pady=8)

        self.var_images_only = ctk.BooleanVar(value=True)
        self.chk_images = ctk.CTkCheckBox(
            inner_opts,
            text="Chỉ tải hình ảnh (JPG, PNG, WEBP, PSD, RAW, HEIC...)",
            variable=self.var_images_only,
            font=("Arial", 12),
            text_color=TEXT_PRIMARY,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
        )
        self.chk_images.pack(anchor="w", pady=(2, 6))

        self.var_skip_existing = ctk.BooleanVar(value=True)
        self.chk_skip = ctk.CTkCheckBox(
            inner_opts,
            text="Bỏ qua tệp đã có sẵn trên máy (Tránh tải lại / Hỗ trợ Resume)",
            variable=self.var_skip_existing,
            font=("Arial", 12),
            text_color=TEXT_PRIMARY,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
        )
        self.chk_skip.pack(anchor="w", pady=(0, 6))

        row_threads = ctk.CTkFrame(inner_opts, fg_color="transparent")
        row_threads.pack(fill="x", pady=(2, 0))

        ctk.CTkLabel(
            row_threads,
            text="⚡ Tốc độ tải song song:",
            font=("Arial", 12),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 10))

        self.var_threads = ctk.StringVar(value="3 Luồng")
        self.seg_threads = ctk.CTkSegmentedButton(
            row_threads,
            values=["2 Luồng", "3 Luồng", "5 Luồng"],
            variable=self.var_threads,
            font=("Arial", 11, "bold"),
            selected_color=APPLE_BLUE,
            selected_hover_color=APPLE_BLUE_HOVER,
            unselected_color=BG_INSET,
            unselected_hover_color=BG_PILL,
            text_color=TEXT_PRIMARY,
            height=28,
        )
        self.seg_threads.pack(side="left")

        # ── 6. Card Tiến Trình & Nhật Ký (FILL VÀ CO DÃN THEO KHÔNG GIAN CỬA SỔ) ──
        card_progress = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card_progress.pack(side="top", fill="both", expand=True)

        inner_prog = ctk.CTkFrame(card_progress, fg_color="transparent")
        inner_prog.pack(fill="both", expand=True, padx=14, pady=10)

        # Status text
        self.lbl_status = ctk.CTkLabel(
            inner_prog,
            text="💡 Sẵn sàng: Dán link Google Drive và nhấn 'Bắt Đầu Tải'",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        self.lbl_status.pack(fill="x", pady=(0, 6))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            inner_prog,
            height=8,
            corner_radius=4,
            fg_color=BG_INSET,
            progress_color=APPLE_BLUE,
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(0, 10))

        # Log Terminal
        ctk.CTkLabel(
            inner_prog,
            text="📝 Nhật ký tiến trình:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.log_textbox = ctk.CTkTextbox(
            inner_prog,
            height=100,
            corner_radius=8,
            fg_color=BG_INSET,
            border_color=BORDER_INSET,
            border_width=1,
            font=("Consolas", 11),
            text_color=TEXT_PRIMARY,
            activate_scrollbars=True,
        )
        self.log_textbox.pack(fill="both", expand=True)


    def _refresh_auth_status(self):
        """Cập nhật trạng thái kết nối tài khoản công ty trên giao diện."""
        authed = has_valid_cookies()
        if authed:
            self.lbl_auth_pill.configure(
                text="🟢 Đã kết nối: Tài khoản Google Công Ty (Cookies kích hoạt)",
                text_color=APPLE_GREEN,
            )
            self.btn_auth_action.configure(
                text="⚙️ Quản lý Tài Khoản",
                text_color=TEXT_PRIMARY,
            )
        else:
            self.lbl_auth_pill.configure(
                text="⚪ Chưa đăng nhập: Chỉ tải được link công khai",
                text_color=TEXT_SECONDARY,
            )
            self.btn_auth_action.configure(
                text="🔐 Đăng Nhập Mail Công Ty",
                text_color="#FBBF24",
            )

    def _open_auth_dialog(self):
        """Mở popup cấu hình đăng nhập / cookie tài khoản Google công ty."""
        def on_changed():
            self._refresh_auth_status()
            if has_valid_cookies():
                self._log("🔐 Đã cập nhật phiên làm việc tài khoản Google công ty.")
            else:
                self._log("ℹ️ Đã xóa phiên làm việc tài khoản Google công ty.")

        GDriveAuthDialog(self, on_auth_changed=on_changed)

    def _log(self, text: str):
        """Thêm dòng log kèm dấu thời gian vào hộp nhật ký."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        self.log_textbox.insert("end", line)
        self.log_textbox.see("end")

    def _paste_clipboard(self):
        """Dán nội dung từ clipboard vào ô URL."""
        try:
            cb = self.clipboard_get()
            if cb:
                self.url_var.set(cb.strip())
                self._log(f"📋 Đã dán link từ bộ nhớ tạm: {cb[:60]}...")
        except Exception:
            pass

    def _browse_directory(self):
        """Mở hộp thoại chọn thư mục lưu."""
        cur = self.dir_var.get().strip() or os.path.expanduser("~")
        chosen = filedialog.askdirectory(
            parent=self,
            initialdir=cur,
            title="Chọn Thư Mục Lưu Tệp Tải Về",
        )
        if chosen:
            self.dir_var.set(chosen)
            self._log(f"📂 Đã chọn thư mục lưu: {chosen}")

    def _open_output_dir(self):
        """Mở thư mục tải về trong hệ điều hành."""
        d = self.dir_var.get().strip()
        if os.path.exists(d):
            _open_folder(d)
        else:
            self._log(f"⚠️ Thư mục chưa tồn tại: {d}")

    def _start_download(self):
        """Bắt đầu tiến trình quét và tải."""
        self._refresh_auth_status()
        url = self.url_var.get().strip()
        if not url:
            self._log("❌ Vui lòng nhập hoặc dán đường dẫn Google Drive.")
            self.lbl_status.configure(text="❌ Chưa nhập đường dẫn Google Drive", text_color=APPLE_RED)
            return

        out_dir = self.dir_var.get().strip()
        if not out_dir:
            self._log("❌ Vui lòng chọn thư mục lưu trên máy tính.")
            return

        threads_map = {"2 Luồng": 2, "3 Luồng": 3, "5 Luồng": 5}
        workers = threads_map.get(self.var_threads.get(), 3)
        images_only = self.var_images_only.get()
        skip_existing = self.var_skip_existing.get()

        # Cập nhật trạng thái UI
        self._is_downloading = True
        self._cancel_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_close.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.lbl_status.configure(text="⏳ Đang bắt đầu kết nối...", text_color=APPLE_BLUE)

        self._log(f"🚀 Bắt đầu tiến trình tải (Đa luồng: {workers}, Lọc ảnh: {images_only}, Bỏ qua trùng: {skip_existing})")

        # Khởi chạy trên background thread
        def run_worker():
            downloader = GDriveDownloader(max_workers=workers)
            try:
                stats = downloader.download(
                    url_or_id=url,
                    output_dir=out_dir,
                    images_only=images_only,
                    skip_existing=skip_existing,
                    max_workers=workers,
                    progress_callback=self._msg_queue.put,
                    cancel_event=self._cancel_event,
                )
                self._msg_queue.put({"status": "all_done", "stats": stats})
            except Exception as e:
                self._msg_queue.put({"status": "fatal_error", "error": str(e)})

        self._download_thread = threading.Thread(target=run_worker, daemon=True)
        self._download_thread.start()

    def _cancel_download(self):
        """Gửi tín hiệu dừng tải."""
        if self._is_downloading:
            self._cancel_event.set()
            self._log("⏹ Đang gửi yêu cầu dừng tiến trình... Vui lòng đợi hoàn tất luồng hiện tại.")
            self.btn_cancel.configure(state="disabled")

    def _check_queue(self):
        """Vòng lặp định kỳ đọc hàng đợi từ background thread để update UI an toàn."""
        try:
            while not self._msg_queue.empty():
                msg = self._msg_queue.get_nowait()
                status = msg.get("status")

                if status == "scanning":
                    self.lbl_status.configure(text=msg.get("message", "Đang quét..."), text_color=APPLE_ORANGE)
                    self._log(msg.get("message", ""))

                elif status == "downloading":
                    pct = msg.get("percent", 0) / 100.0
                    self.progress_bar.set(max(0.0, min(1.0, pct)))
                    idx = msg.get("file_index", 0)
                    total = msg.get("total", 0)
                    fn = msg.get("file_name", "")
                    self.lbl_status.configure(
                        text=f"⬇️ Đang tải ({idx}/{total}): {fn} [{int(pct * 100)}%]",
                        text_color=APPLE_BLUE,
                    )
                    self._log(msg.get("message", ""))

                elif status == "completed":
                    self.progress_bar.set(1.0)
                    self.lbl_status.configure(text=msg.get("message", "Hoàn tất!"), text_color=APPLE_GREEN)
                    self._log(msg.get("message", ""))

                elif status == "cancelled":
                    self.lbl_status.configure(text=msg.get("message", "Đã dừng."), text_color=APPLE_RED)
                    self._log(msg.get("message", ""))

                elif status == "error":
                    self.lbl_status.configure(text=msg.get("message", "Lỗi xảy ra."), text_color=APPLE_RED)
                    self._log(msg.get("message", ""))

                elif status == "all_done":
                    stats = msg.get("stats", {})
                    self._is_downloading = False
                    self.btn_start.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    self.btn_close.configure(state="normal")
                    s = stats.get("success", 0)
                    sk = stats.get("skipped", 0)
                    f = stats.get("failed", 0)
                    t = stats.get("total", 0)
                    if stats.get("cancelled"):
                        self._log(f"⏹ Đã dừng: Thành công {s}/{t}, Bỏ qua {sk}, Thất bại {f}.")
                    else:
                        self._log(f"🎉 TỔNG KẾT: Tải thành công {s}/{t} tệp (Bỏ qua: {sk}, Lỗi: {f}).")
                        self.lbl_status.configure(
                            text=f"🎉 Hoàn tất! Đã tải {s}/{t} tệp (Bỏ qua: {sk})",
                            text_color=APPLE_GREEN,
                        )

                elif status == "fatal_error":
                    self._is_downloading = False
                    self.btn_start.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    self.btn_close.configure(state="normal")
                    err = msg.get("error", "Lỗi không xác định")
                    self.lbl_status.configure(text=f"❌ Lỗi nghiêm trọng: {err}", text_color=APPLE_RED)
                    self._log(f"❌ Lỗi nghiêm trọng: {err}")

        except Exception:
            pass

        # Tiếp tục lắng nghe nếu cửa sổ còn tồn tại
        if self.winfo_exists():
            self.after(60, self._check_queue)

    def _on_close(self):
        """Xử lý đóng cửa sổ an toàn."""
        if self._is_downloading:
            self._cancel_event.set()
        self.grab_release()
        self.destroy()

    def _center_on_parent(self, master):
        """Căn giữa cửa sổ trên ứng dụng chính."""
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            px = master.winfo_x()
            py = master.winfo_y()
            pw = master.winfo_width()
            ph = master.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
