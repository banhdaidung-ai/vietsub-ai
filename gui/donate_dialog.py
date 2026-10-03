"""
gui/donate_dialog.py — Hộp thoại Donate / Mời tác giả cà phê qua mã QR
Thiết kế theo ngôn ngữ macOS Studio Pro Dark Glassmorphism, tinh tế, trang nhã.
"""

import os
import shutil
import sys
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk
from PIL import Image

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
APPLE_AMBER = "#FF9F0A"
APPLE_AMBER_HOVER = "#E08A00"
APPLE_AMBER_BG = "#2B2115"
APPLE_AMBER_BORDER = "#5E4324"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_MUTED = "#636366"
# ─────────────────────────────────────────────────────────────────────────────


class DonateDialog(ctk.CTkToplevel):
    """Popup hiển thị mã QR ủng hộ / Mời tác giả một ly cà phê."""

    _instance: Optional["DonateDialog"] = None

    @classmethod
    def show_dialog(cls, parent) -> "DonateDialog":
        """Hiển thị hộp thoại Donate, đảm bảo chỉ có tối đa 1 instance duy nhất."""
        if cls._instance is not None:
            try:
                if cls._instance.winfo_exists():
                    cls._instance.deiconify()
                    cls._instance.lift()
                    cls._instance.focus_force()
                    return cls._instance
            except Exception:
                cls._instance = None

        dialog = cls(parent)
        cls._instance = dialog
        return dialog

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Mời Tác Giả Một Ly Cà Phê ☕ — Vietsub AI")
        self.geometry("500x660")
        self.minsize(480, 620)
        self.resizable(False, False)
        self.configure(fg_color=BG_WINDOW)

        self.transient(parent)
        self.grab_set()

        self._qr_image_path = self._get_qr_path()
        self._qr_photo = None

        self._build_ui()
        self._center_window(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _get_qr_path(self) -> Path:
        """Lấy đường dẫn ảnh mã QR tương thích cả môi trường source và frozen bundle."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            p = Path(sys._MEIPASS) / "assets" / "donate_qr.png"
            if p.exists():
                return p
        p = Path(__file__).resolve().parent.parent / "assets" / "donate_qr.png"
        return p

    def _center_window(self, parent):
        """Căn giữa hộp thoại theo cửa sổ cha hoặc màn hình."""
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            w = self.winfo_width()
            h = self.winfo_height()
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        # Container chính dạng Card bo tròn
        main_card = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER_CARD,
        )
        main_card.pack(fill="both", expand=True, padx=16, pady=16)

        # ── 1. Header & Badge ──
        badge_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        badge_frame.pack(anchor="center", pady=(18, 6))

        ctk.CTkLabel(
            badge_frame,
            text="☕ BUY ME A COFFEE • VIETSUB AI STUDIO",
            font=("Arial", 11, "bold"),
            text_color="#FFB340",
            fg_color=APPLE_AMBER_BG,
            corner_radius=12,
            padx=14,
            pady=4,
        ).pack()

        # Headline
        ctk.CTkLabel(
            main_card,
            text="Mời Tác Giả Một Ly Cà Phê ☕",
            font=("Arial", 18, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(4, 6))

        # Thông điệp ấm áp (Lựa chọn A)
        msg_text = (
            "Nếu Vietsub AI giúp công việc sáng tạo video của bạn nhanh hơn,\n"
            "nhàn hơn và tạo ra những thước phim ưng ý, hãy mời tác giả một ly cà phê nhé!\n"
            "Mỗi sự ủng hộ nhỏ từ bạn là nguồn năng lượng to lớn giúp mình\n"
            "tiếp tục duy trì và nâng cấp các tính năng AI mới nhất."
        )
        ctk.CTkLabel(
            main_card,
            text=msg_text,
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
            justify="center",
            wraplength=440,
        ).pack(padx=20, pady=(0, 12))

        # ── 2. Khung hiển thị Mã QR ──
        qr_container = ctk.CTkFrame(
            main_card,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=2,
            border_color=APPLE_AMBER_BORDER,
        )
        qr_container.pack(anchor="center", pady=(0, 12), padx=20)

        # Tải ảnh QR
        try:
            if self._qr_image_path.exists():
                pil_img = Image.open(self._qr_image_path).resize((200, 200), Image.Resampling.LANCZOS)
                self._qr_photo = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(200, 200))
                lbl_qr = ctk.CTkLabel(qr_container, image=self._qr_photo, text="")
                lbl_qr.pack(padx=8, pady=8)
            else:
                lbl_qr = ctk.CTkLabel(
                    qr_container,
                    text="[Mã QR Ngân Hàng VIB]",
                    font=("Arial", 13, "bold"),
                    text_color="#141518",
                    width=200,
                    height=200,
                )
                lbl_qr.pack(padx=8, pady=8)
        except Exception:
            lbl_qr = ctk.CTkLabel(
                qr_container,
                text="[Mã QR Ngân Hàng VIB]",
                font=("Arial", 13, "bold"),
                text_color="#141518",
                width=200,
                height=200,
            )
            lbl_qr.pack(padx=8, pady=8)

        # ── 3. Thông tin tài khoản ngân hàng ──
        bank_info_card = ctk.CTkFrame(
            main_card,
            fg_color=BG_INSET,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_INSET,
        )
        bank_info_card.pack(fill="x", padx=28, pady=(0, 12))

        row1 = ctk.CTkFrame(bank_info_card, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(8, 2))
        ctk.CTkLabel(
            row1,
            text="Ngân hàng:",
            font=("Arial", 11),
            text_color=TEXT_MUTED,
        ).pack(side="left")
        ctk.CTkLabel(
            row1,
            text="VIB (Ngân hàng TMCP Quốc Tế Việt Nam)",
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="right")

        row2 = ctk.CTkFrame(bank_info_card, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(
            row2,
            text="Số tài khoản:",
            font=("Arial", 11),
            text_color=TEXT_MUTED,
        ).pack(side="left")
        self.lbl_stk = ctk.CTkLabel(
            row2,
            text="0982333097",
            font=("Arial", 13, "bold"),
            text_color="#FFB340",
        )
        self.lbl_stk.pack(side="right")

        row3 = ctk.CTkFrame(bank_info_card, fg_color="transparent")
        row3.pack(fill="x", padx=14, pady=(2, 8))
        ctk.CTkLabel(
            row3,
            text="Chủ tài khoản:",
            font=("Arial", 11),
            text_color=TEXT_MUTED,
        ).pack(side="left")
        ctk.CTkLabel(
            row3,
            text="BÀNH ĐẠI DŨNG",
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="right")

        # ── 4. Các nút thao tác ──
        action_row = ctk.CTkFrame(main_card, fg_color="transparent")
        action_row.pack(fill="x", padx=28, pady=(0, 14))

        self.btn_copy_stk = ctk.CTkButton(
            action_row,
            text="📋 Sao Chép Số Tài Khoản",
            font=("Arial", 12, "bold"),
            text_color="#FFFFFF",
            fg_color=APPLE_AMBER,
            hover_color=APPLE_AMBER_HOVER,
            corner_radius=8,
            height=34,
            command=self._on_copy_stk,
        )
        self.btn_copy_stk.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_save_qr = ctk.CTkButton(
            action_row,
            text="💾 Lưu Ảnh QR",
            font=("Arial", 12),
            text_color=TEXT_PRIMARY,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            corner_radius=8,
            height=34,
            command=self._on_save_qr,
        )
        self.btn_save_qr.pack(side="right", fill="x", expand=True, padx=(6, 0))

        # ── 5. Nút đóng / Cảm ơn ──
        ctk.CTkButton(
            main_card,
            text="Cảm Ơn Bạn Rất Nhiều! ❤️",
            font=("Arial", 12),
            text_color=TEXT_MUTED,
            fg_color="transparent",
            hover_color=BG_INSET,
            corner_radius=8,
            height=28,
            command=self._on_close,
        ).pack(pady=(0, 10))

    def _on_copy_stk(self):
        """Sao chép số tài khoản vào clipboard và cập nhật trạng thái nút."""
        try:
            self.clipboard_clear()
            self.clipboard_append("0982333097")
            self.btn_copy_stk.configure(
                text="✅ Đã Sao Chép STK!",
                fg_color=APPLE_GREEN,
                hover_color=APPLE_GREEN_HOVER,
            )
            self.after(2000, self._restore_copy_btn)
        except Exception:
            pass

    def _restore_copy_btn(self):
        """Khôi phục lại giao diện ban đầu của nút copy."""
        try:
            if self.winfo_exists():
                self.btn_copy_stk.configure(
                    text="📋 Sao Chép Số Tài Khoản",
                    fg_color=APPLE_AMBER,
                    hover_color=APPLE_AMBER_HOVER,
                )
        except Exception:
            pass

    def _on_save_qr(self):
        """Lưu ảnh QR về máy theo đường dẫn người dùng chỉ định."""
        try:
            if not self._qr_image_path.exists():
                return
            dest = filedialog.asksaveasfilename(
                title="Lưu ảnh mã QR Donate",
                defaultextension=".png",
                initialfile="VietQR_BanhDaiDung_0982333097.png",
                filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
                parent=self,
            )
            if dest:
                shutil.copyfile(self._qr_image_path, dest)
                self.btn_save_qr.configure(text="✅ Đã Lưu!")
                self.after(2000, lambda: self.btn_save_qr.configure(text="💾 Lưu Ảnh QR") if self.winfo_exists() else None)
        except Exception:
            pass

    def _on_close(self):
        """Đóng hộp thoại an toàn và giải phóng singleton."""
        DonateDialog._instance = None
        self.destroy()
