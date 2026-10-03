"""
gui/gdrive_auth_dialog.py — Hộp thoại xác thực tài khoản Google công ty (Google Workspace)
Cho phép thành viên công ty đăng nhập hoặc dán cookie để tải các thư mục/file nội bộ
chỉ cho phép email nội bộ (@company.com) truy cập.
"""

import os
import threading
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from core.gdrive_auth import (
    clear_cookies,
    has_valid_cookies,
    login_google_via_browser,
    save_cookie_file,
    save_raw_cookie_string,
)

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
APPLE_ORANGE = "#FF9F0A"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_MUTED = "#636366"
# ─────────────────────────────────────────────────────────────────────────────


class GDriveAuthDialog(ctk.CTkToplevel):
    """
    Hộp thoại cấu hình và xác thực tài khoản Google công ty.
    """

    def __init__(self, master, on_auth_changed: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.master = master
        self.on_auth_changed = on_auth_changed

        self.title("🔐 Xác Thực Tài Khoản Google Công Ty")
        self.geometry("560x520")
        self.resizable(False, False)
        self.configure(fg_color=BG_WINDOW)

        self._browser_thread: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()
        self._manual_save_event = threading.Event()

        # Modal attributes
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self._build_ui()
        self.update_idletasks()
        self._center_on_parent(master)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=22, pady=18)

        # ── Header ──
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header,
            text="🔐 Tài Khoản Google Công Ty (Workspace)",
            font=("Arial", 17, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Kết nối tài khoản để tải các thư mục/file nội bộ chỉ chia sẻ cho email công ty.",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        # ── Status Card ──
        status_card = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        status_card.pack(fill="x", pady=(0, 12))

        inner_status = ctk.CTkFrame(status_card, fg_color="transparent")
        inner_status.pack(fill="x", padx=14, pady=10)

        is_authed = has_valid_cookies()
        status_text = "🟢 Đã kết nối phiên đăng nhập công ty" if is_authed else "⚪ Chưa kết nối tài khoản công ty"
        status_color = APPLE_GREEN if is_authed else TEXT_SECONDARY

        self.lbl_auth_status = ctk.CTkLabel(
            inner_status,
            text=status_text,
            font=("Arial", 12, "bold"),
            text_color=status_color,
        )
        self.lbl_auth_status.pack(side="left")

        if is_authed:
            self.btn_logout = ctk.CTkButton(
                inner_status,
                text="Đăng xuất",
                font=("Arial", 11),
                width=80,
                height=26,
                corner_radius=6,
                fg_color=BG_PILL,
                hover_color=BG_PILL_HOVER,
                text_color=APPLE_RED,
                command=self._do_logout,
            )
            self.btn_logout.pack(side="right")

        # ── Tabview Các Phương Thức Xác Thực ──
        self.tabview = ctk.CTkTabview(
            outer,
            height=300,
            corner_radius=10,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_INSET,
            segmented_button_selected_color=APPLE_BLUE,
            segmented_button_selected_hover_color=APPLE_BLUE_HOVER,
            segmented_button_unselected_color=BG_INSET,
            segmented_button_unselected_hover_color=BG_PILL,
            text_color=TEXT_PRIMARY,
        )
        self.tabview.pack(fill="both", expand=True, pady=(0, 12))

        tab_browser = self.tabview.add("🌐 Đăng Nhập Tự Động")
        tab_paste = self.tabview.add("📋 Dán Mã Cookie")
        tab_file = self.tabview.add("📁 Nhập File cookies.txt")

        # ── Tab 1: Browser Login ──
        ctk.CTkLabel(
            tab_browser,
            text="👉 Cách dễ nhất cho nhân viên:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            tab_browser,
            text="Nhấn nút bên dưới để mở cửa sổ trình duyệt và đăng nhập mail công ty.\nKhi vào đến trang Google Drive, hệ thống sẽ tự động lưu phiên làm việc\n(Hoặc Sếp có thể bấm 'Lưu Phiên Ngay' bất cứ khi nào đã vào Drive).",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 12))

        self.lbl_browser_msg = ctk.CTkLabel(
            tab_browser,
            text="Sẵn sàng: Nhấn nút để bắt đầu đăng nhập.",
            font=("Arial", 11),
            text_color=APPLE_BLUE,
        )
        self.lbl_browser_msg.pack(anchor="w", padx=10, pady=(0, 8))

        self.btn_launch_browser = ctk.CTkButton(
            tab_browser,
            text="🚀 Mở Trình Duyệt Đăng Nhập",
            font=("Arial", 12, "bold"),
            height=38,
            corner_radius=8,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            command=self._start_browser_login,
        )
        self.btn_launch_browser.pack(fill="x", padx=10)

        self.btn_manual_save = ctk.CTkButton(
            tab_browser,
            text="✅ Tôi Đã Vào Đến Google Drive (Lưu Phiên Ngay)",
            font=("Arial", 12, "bold"),
            height=36,
            corner_radius=8,
            fg_color=APPLE_GREEN,
            hover_color=APPLE_GREEN_HOVER,
            state="disabled",
            command=self._manual_save_browser_session,
        )
        self.btn_manual_save.pack(fill="x", padx=10, pady=(8, 0))

        # ── Tab 2: Paste Cookie ──
        ctk.CTkLabel(
            tab_paste,
            text="Dán chuỗi Cookie từ trình duyệt Chrome của bạn:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            tab_paste,
            text="1. Mở Google Drive công ty trên Chrome thường dùng.\n"
                 "2. Bấm phím F12 (Inspect) -> Chọn thẻ Network (Mạng) -> F5 tải lại trang.\n"
                 "3. Bấm dòng đầu tiên -> Tại phần Request Headers copy toàn bộ dòng 'Cookie:'\n"
                 "4. Dán vào ô bên dưới và bấm 'Lưu & Kích Hoạt Cookie'.",
            font=("Arial", 10),
            text_color=TEXT_SECONDARY,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 6))

        self.txt_cookie = ctk.CTkTextbox(
            tab_paste,
            height=110,
            corner_radius=8,
            fg_color=BG_INSET,
            border_color=BORDER_INSET,
            border_width=1,
            font=("Consolas", 10),
            text_color=TEXT_PRIMARY,
        )
        self.txt_cookie.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            tab_paste,
            text="💾 Lưu & Kích Hoạt Cookie",
            font=("Arial", 12, "bold"),
            height=36,
            corner_radius=8,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            command=self._save_pasted_cookie,
        ).pack(fill="x", padx=10)

        # ── Tab 3: File cookies.txt ──
        ctk.CTkLabel(
            tab_file,
            text="Sử dụng tệp Netscape cookies.txt:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            tab_file,
            text="Xuất tệp cookies.txt từ tiện ích Chrome mở rộng (ví dụ: 'Get cookies.txt LOCALLY')\nkhi đang mở trang Google Drive công ty, sau đó chọn tệp tại đây:",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 14))

        ctk.CTkButton(
            tab_file,
            text="📂 Chọn Tệp cookies.txt...",
            font=("Arial", 12, "bold"),
            height=38,
            corner_radius=8,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            command=self._browse_cookie_file,
        ).pack(fill="x", padx=10)

        # ── Bottom Close Bar ──
        btn_bar = ctk.CTkFrame(outer, fg_color="transparent")
        btn_bar.pack(fill="x")

        ctk.CTkButton(
            btn_bar,
            text="Đóng",
            font=("Arial", 12),
            height=36,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._on_close,
        ).pack(side="right")

    def _update_status(self, is_authed: bool):
        status_text = "🟢 Đã kết nối phiên đăng nhập công ty" if is_authed else "⚪ Chưa kết nối tài khoản công ty"
        status_color = APPLE_GREEN if is_authed else TEXT_SECONDARY
        self.lbl_auth_status.configure(text=status_text, text_color=status_color)
        if callable(self.on_auth_changed):
            self.on_auth_changed()

    def _do_logout(self):
        clear_cookies()
        self._update_status(False)
        self.lbl_browser_msg.configure(text="Đã đăng xuất. Bạn có thể đăng nhập lại bất kỳ lúc nào.", text_color=TEXT_SECONDARY)

    def _start_browser_login(self):
        self._cancel_event.clear()
        self._manual_save_event.clear()
        self.btn_launch_browser.configure(state="disabled")
        self.btn_manual_save.configure(state="normal")
        self.lbl_browser_msg.configure(text="⏳ Đang mở trình duyệt... Vui lòng kiểm tra cửa sổ mới mở.", text_color=APPLE_BLUE)

        def on_status(msg: str):
            self.after(0, lambda: self.lbl_browser_msg.configure(text=msg))

        def on_success(email: str):
            def handle():
                self.btn_launch_browser.configure(state="normal")
                self.btn_manual_save.configure(state="disabled")
                self.lbl_browser_msg.configure(text="🎉 Đăng nhập và lưu Cookie thành công!", text_color=APPLE_GREEN)
                self._update_status(True)
            self.after(0, handle)

        def on_error(err: str):
            def handle():
                self.btn_launch_browser.configure(state="normal")
                self.btn_manual_save.configure(state="disabled")
                self.lbl_browser_msg.configure(text=f"❌ {err}", text_color=APPLE_RED)
            self.after(0, handle)

        self._browser_thread = threading.Thread(
            target=login_google_via_browser,
            args=(on_status, on_success, on_error, self._cancel_event, self._manual_save_event),
            daemon=True,
        )
        self._browser_thread.start()

    def _manual_save_browser_session(self):
        self._manual_save_event.set()
        self.btn_manual_save.configure(state="disabled")
        self.lbl_browser_msg.configure(text="⏳ Đang trích xuất và lưu phiên làm việc từ trình duyệt...", text_color=APPLE_BLUE)

    def _save_pasted_cookie(self):
        raw = self.txt_cookie.get("1.0", "end").strip()
        if not raw:
            return
        ok = save_raw_cookie_string(raw)
        if ok and has_valid_cookies():
            self._update_status(True)
            self.txt_cookie.delete("1.0", "end")
            self.txt_cookie.insert("1.0", "✅ Đã lưu và kích hoạt Cookie thành công!")
        else:
            self.txt_cookie.insert("end", "\n❌ Cookie không hợp lệ hoặc thiếu thông tin.")

    def _browse_cookie_file(self):
        f = filedialog.askopenfilename(
            parent=self,
            title="Chọn Tệp cookies.txt",
            filetypes=[("Text files", "*.txt"), ("Tất cả tệp", "*.*")],
        )
        if f:
            ok = save_cookie_file(f)
            if ok:
                self._update_status(True)

    def _on_close(self):
        self._cancel_event.set()
        self._manual_save_event.set()
        self.grab_release()
        self.destroy()

    def _center_on_parent(self, master):
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
