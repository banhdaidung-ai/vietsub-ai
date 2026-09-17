"""
gui/audio_separator_dialog.py — Hộp thoại tùy chọn Tách Lời & Tách Nhạc AI (Demucs v4)
Giao diện macOS Sequoia / Sonoma Dark Mode cao cấp.
"""

import os
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from core.audio_separator import get_optimal_device

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
APPLE_PURPLE = "#AF52DE"
APPLE_PURPLE_HOVER = "#9333EA"
APPLE_ORANGE = "#FF9F0A"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_MUTED = "#636366"
# ─────────────────────────────────────────────────────────────────────────────


class AudioSeparatorDialog(ctk.CTkToplevel):
    """
    Hộp thoại cấu hình tách giọng hát (Vocal) và nhạc nền (Beat Karaoke) bằng AI.
    """

    def __init__(
        self,
        master,
        input_file: str,
        on_start: Callable[[str, str, str], None],
    ):
        super().__init__(master)
        self.input_file = input_file
        self.on_start = on_start

        self.title("🎤 Tách Lời & Nhạc Nền AI — Demucs")
        self.geometry("520x520")
        self.resizable(False, False)
        self.configure(fg_color=BG_WINDOW)

        # Modal behavior
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self._build_ui()
        self.update_idletasks()
        self._center_on_parent(master)

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=20)

        # ── Header ──
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            header,
            text="🎤 Tách Lời & Nhạc Beat (AI)",
            font=("Arial", 18, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Sử dụng mạng nơ-ron Demucs v4 để bóc tách giọng ca sĩ và nhạc nền riêng biệt.",
            font=("Arial", 12),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        # ── Card File Nguồn ──
        card_file = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card_file.pack(fill="x", pady=(0, 14), ipady=4)

        file_inner = ctk.CTkFrame(card_file, fg_color="transparent")
        file_inner.pack(fill="x", padx=14, pady=10)

        fn = Path(self.input_file).name if self.input_file else "Chưa chọn tệp"
        ctk.CTkLabel(
            file_inner,
            text="📁 Tệp nguồn:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            file_inner,
            text=fn,
            font=("Arial", 12, "bold"),
            text_color=APPLE_BLUE,
            wraplength=360,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # ── Card Chế độ Tách ──
        card_mode = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card_mode.pack(fill="x", pady=(0, 14))

        mode_header = ctk.CTkFrame(card_mode, fg_color="transparent")
        mode_header.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            mode_header,
            text="🎯 Chọn kết quả bạn muốn lấy:",
            font=("Arial", 13, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")

        self.mode_var = ctk.StringVar(value="both")

        # Option 1: Cả hai
        r1 = ctk.CTkRadioButton(
            card_mode,
            text="✨ Tách cả 2 (Lời riêng & Nhạc Beat riêng) — Khuyến nghị",
            variable=self.mode_var,
            value="both",
            font=("Arial", 12),
            text_color=TEXT_PRIMARY,
            fg_color=APPLE_PURPLE,
            hover_color=APPLE_PURPLE_HOVER,
        )
        r1.pack(anchor="w", padx=18, pady=(4, 6))

        # Option 2: Beat Karaoke
        r2 = ctk.CTkRadioButton(
            card_mode,
            text="🎸 Chỉ lấy Nhạc Beat (Tắt giọng ca sĩ / Làm Karaoke)",
            variable=self.mode_var,
            value="instrumental",
            font=("Arial", 12),
            text_color=TEXT_PRIMARY,
            fg_color=APPLE_PURPLE,
            hover_color=APPLE_PURPLE_HOVER,
        )
        r2.pack(anchor="w", padx=18, pady=4)

        # Option 3: Vocal Acapella
        r3 = ctk.CTkRadioButton(
            card_mode,
            text="🎤 Chỉ lấy Giọng hát (Tắt nhạc nền / Acapella)",
            variable=self.mode_var,
            value="vocals",
            font=("Arial", 12),
            text_color=TEXT_PRIMARY,
            fg_color=APPLE_PURPLE,
            hover_color=APPLE_PURPLE_HOVER,
        )
        r3.pack(anchor="w", padx=18, pady=(4, 12))

        # ── Card Định dạng & Thiết bị ──
        card_opts = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card_opts.pack(fill="x", pady=(0, 18))

        row_fmt = ctk.CTkFrame(card_opts, fg_color="transparent")
        row_fmt.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(
            row_fmt,
            text="🎵 Định dạng âm thanh:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 10))

        self.fmt_var = ctk.StringVar(value="MP3 (320kbps Studio)")
        fmt_menu = ctk.CTkOptionMenu(
            row_fmt,
            values=["MP3 (320kbps Studio)", "WAV (Lossless 44.1kHz)"],
            variable=self.fmt_var,
            width=190,
            height=30,
            corner_radius=6,
            fg_color=BG_INSET,
            button_color=BG_PILL,
            button_hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
        )
        fmt_menu.pack(side="left")

        # Hardware badge
        opt_dev = get_optimal_device()
        dev_text = "⚡ Apple Silicon GPU" if opt_dev == "mps" else ("⚡ Nvidia GPU" if opt_dev == "cuda" else "🖥️ CPU Multi-core")
        ctk.CTkLabel(
            row_fmt,
            text=dev_text,
            font=("Arial", 11, "bold"),
            text_color=APPLE_GREEN if opt_dev in ("mps", "cuda") else TEXT_SECONDARY,
        ).pack(side="right")

        # ── Action Buttons ──
        btn_bar = ctk.CTkFrame(outer, fg_color="transparent")
        btn_bar.pack(fill="x")
        btn_bar.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_bar,
            text="🚀 Bắt Đầu Tách",
            font=("Arial", 13, "bold"),
            fg_color=APPLE_PURPLE,
            hover_color=APPLE_PURPLE_HOVER,
            text_color="#FFFFFF",
            height=42,
            corner_radius=10,
            command=self._on_start_clicked,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            btn_bar,
            text="Đóng",
            font=("Arial", 13),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            height=42,
            corner_radius=10,
            command=self.destroy,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _on_start_clicked(self):
        mode = self.mode_var.get()
        fmt_str = self.fmt_var.get()
        audio_fmt = "wav" if "WAV" in fmt_str else "mp3"
        bitrate = "320k"

        self.destroy()
        if callable(self.on_start):
            self.on_start(mode, audio_fmt, bitrate)

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
