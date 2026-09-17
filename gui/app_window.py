"""
gui/app_window.py — Giao diện chính nâng cấp của ứng dụng Vietsub AI
Hiện đại, trực quan, chuyên nghiệp với Pipeline Step Tracker và Studio Terminal
"""

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from core.pipeline import Pipeline
from gui.ffmpeg_download_dialog import FFmpegDownloadDialog
from gui.settings_dialog import SettingsDialog
from gui.subtitle_editor_dialog import SubtitleEditorDialog
from utils.config import load_config, save_config
from utils.ffmpeg_check import check_ffmpeg, get_ffmpeg_path

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ═════════════════════════════════════════════════════════
# APPLE macOS SEQUOIA / SONOMA DESIGN SYSTEM TOKENS
# ═════════════════════════════════════════════════════════
BG_WINDOW = "#141518"          # macOS deep space canvas
BG_HEADER = "#191B22"          # Unified macOS titlebar
BORDER_HEADER = "#292D39"      # Titlebar subtle border
BG_CARD = "#1C1F27"            # Apple surface card
BORDER_CARD = "#2E3342"        # Crisp 1px card border
BG_INSET = "#121419"           # Inset input background
BORDER_INSET = "#252834"       # Inset border
BG_PILL = "#272B37"            # Tool button / elevated pill
BG_PILL_HOVER = "#343949"      # Hover state for pills

APPLE_BLUE = "#0A84FF"         # Apple System Blue
APPLE_BLUE_HOVER = "#0071E3"   # Apple Blue Active
APPLE_GREEN = "#30D158"        # Apple System Green / Mint
APPLE_GREEN_HOVER = "#28B84C"
APPLE_GREEN_BG = "#0D2C1A"     # Subtle green pill bg
APPLE_GREEN_BORDER = "#195935" # Green pill border
APPLE_ORANGE = "#FF9F0A"       # Apple Amber
APPLE_ORANGE_HOVER = "#D98200"
APPLE_ORANGE_BG = "#331E08"    # Subtle amber pill bg
APPLE_ORANGE_BORDER = "#633B11"
APPLE_RED = "#FF453A"          # Apple Crimson
APPLE_RED_HOVER = "#D73327"
APPLE_RED_BG = "#361413"       # Subtle red pill bg
APPLE_RED_BORDER = "#692523"
APPLE_INDIGO = "#5E5CE6"       # Apple Indigo
APPLE_CYAN = "#64D2FF"         # Apple Cyan

TEXT_PRIMARY = "#F5F5F7"       # Apple pure bright text
TEXT_SECONDARY = "#98989F"     # Apple SF muted caption
TEXT_TERTIARY = "#636366"      # Apple subtle placeholder
TEXT_MUTED = "#636366"         # Apple muted gray for inactive steps


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Vietsub AI Studio — macOS Edition")
        self.geometry("920x780")
        self.minsize(860, 720)
        self.configure(fg_color=BG_WINDOW)

        self.config = load_config()
        self.task_queue = queue.Queue()
        self.pipeline: Optional[Pipeline] = None
        self._is_processing = False
        self._download_cancelled = False
        self._current_step = 0

        # Stopwatch / Timer đếm thời gian thực hiện
        self._timer_start_time = None
        self._timer_running = False
        self._timer_after_id = None

        self._set_app_icon()
        self._build_ui()
        self._check_prerequisites()
        self._update_step_labels()
        self._update_action_button()

        # Polling queue định kỳ (100ms) để cập nhật UI từ background thread
        self.after(100, self._process_queue)

    def _set_app_icon(self):
        try:
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                asset_dir = Path(sys._MEIPASS) / "assets"
            else:
                asset_dir = Path(__file__).resolve().parent.parent / "assets"
            ico_file = asset_dir / "icon.ico"
            png_file = asset_dir / "icon.png"
            if os.name == "nt" and ico_file.exists():
                self.iconbitmap(str(ico_file))
            elif png_file.exists():
                icon_img = ImageTk.PhotoImage(Image.open(png_file))
                self.wm_iconphoto(True, icon_img)
        except Exception:
            pass

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ═════════════════════════════════════════════════════════
        # 1. HEADER BAR (macOS UNIFIED TITLEBAR)
        # ═════════════════════════════════════════════════════════
        header_card = ctk.CTkFrame(
            self,
            fg_color=BG_HEADER,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_HEADER,
        )
        header_card.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 8))
        header_card.grid_columnconfigure(1, weight=1)

        # Left: Brand Logo & Title
        brand_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        brand_frame.grid(row=0, column=0, sticky="w", padx=16, pady=10)

        # Load Icon
        try:
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                logo_path = Path(sys._MEIPASS) / "assets" / "icon.png"
            else:
                logo_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
            if logo_path.exists():
                logo_img = ctk.CTkImage(Image.open(logo_path), size=(36, 36))
                lbl_logo = ctk.CTkLabel(brand_frame, image=logo_img, text="")
                lbl_logo.pack(side="left", padx=(0, 10))
        except Exception:
            pass

        title_inner = ctk.CTkFrame(brand_frame, fg_color="transparent")
        title_inner.pack(side="left")

        title_row = ctk.CTkFrame(title_inner, fg_color="transparent")
        title_row.pack(anchor="w")

        ctk.CTkLabel(
            title_row,
            text="Vietsub AI",
            font=("Arial", 20, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            title_row,
            text="PRO STUDIO",
            font=("Arial", 10, "bold"),
            fg_color=APPLE_BLUE,
            text_color="#FFFFFF",
            corner_radius=6,
            width=84,
            height=20,
        ).pack(side="left", padx=8)

        ctk.CTkLabel(
            title_inner,
            text="Studio phụ đề & lồng tiếng AI • Phát triển bởi Bành Đại Dũng - 0982333097",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w")

        # Right: System Health Badges & Controls
        controls_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        controls_frame.grid(row=0, column=2, sticky="e", padx=16, pady=10)

        # Status Badges
        self.badge_ffmpeg = ctk.CTkButton(
            controls_frame,
            text="⚡ FFmpeg: Đang kiểm tra",
            font=("Arial", 11, "bold"),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_SECONDARY,
            corner_radius=14,
            height=28,
            command=self._on_ffmpeg_badge_click,
        )
        self.badge_ffmpeg.pack(side="left", padx=4)

        self.badge_api = ctk.CTkLabel(
            controls_frame,
            text="🤖 Gemini: Tự động",
            font=("Arial", 11, "bold"),
            fg_color=BG_PILL,
            text_color=APPLE_CYAN,
            corner_radius=14,
            padx=12,
            pady=4,
            height=28,
        )
        self.badge_api.pack(side="left", padx=4)

        # Theme toggle button
        self.btn_theme = ctk.CTkButton(
            controls_frame,
            text="🌓",
            width=34,
            height=28,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            command=self._toggle_theme,
        )
        self.btn_theme.pack(side="left", padx=4)

        # Settings button
        ctk.CTkButton(
            controls_frame,
            text="⚙️ Cài đặt",
            font=("Arial", 11, "bold"),
            width=88,
            height=28,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._open_settings,
        ).pack(side="left", padx=(4, 0))

        # ═════════════════════════════════════════════════════════
        # 2. INPUT SECTION (APPLE CARD VIEW)
        # ═════════════════════════════════════════════════════════
        input_card = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        input_card.grid(row=1, column=0, sticky="ew", padx=20, pady=6)

        self.tabview = ctk.CTkTabview(
            input_card,
            height=168,
            corner_radius=10,
            fg_color="transparent",
            segmented_button_fg_color=BG_INSET,
            segmented_button_selected_color=APPLE_BLUE,
            segmented_button_selected_hover_color=APPLE_BLUE_HOVER,
            segmented_button_unselected_color=BG_INSET,
            segmented_button_unselected_hover_color=BG_PILL,
            text_color=TEXT_PRIMARY,
            command=self._on_tab_changed,
        )
        self.tabview.pack(fill="x", padx=14, pady=(6, 10))

        tab_file = self.tabview.add("📂 Chọn File Video Trên Máy")
        tab_url = self.tabview.add("🌐 Dán Link Online (TikTok, YouTube, Facebook...)")

        # ── Tab 1: File Video ──
        self.file_path_var = ctk.StringVar()
        file_box = ctk.CTkFrame(tab_file, fg_color="transparent")
        file_box.pack(fill="x", pady=10)

        self.file_entry = ctk.CTkEntry(
            file_box,
            textvariable=self.file_path_var,
            placeholder_text="Chưa chọn video nào... Nhấp 'Chọn Video' để duyệt tệp",
            state="readonly",
            height=38,
            corner_radius=8,
            fg_color=BG_INSET,
            border_color=BORDER_INSET,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=("Consolas", 12),
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            file_box,
            text="📂 Chọn Video...",
            font=("Arial", 12, "bold"),
            width=135,
            height=38,
            corner_radius=8,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            text_color="#FFFFFF",
            command=self._browse_file,
        ).pack(side="right")

        file_action_bar = ctk.CTkFrame(tab_file, fg_color="transparent")
        file_action_bar.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            file_action_bar,
            text="💡 Hỗ trợ: MP4, MKV, MOV, AVI, WEBM",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(side="left")

        self.btn_extract_audio = ctk.CTkButton(
            file_action_bar,
            text="🎵 Trích Xuất Audio (MP3 320k)",
            font=("Arial", 11, "bold"),
            width=190,
            height=28,
            corner_radius=6,
            fg_color=APPLE_ORANGE_BG,
            hover_color=APPLE_ORANGE_HOVER,
            text_color=APPLE_ORANGE,
            border_width=1,
            border_color=APPLE_ORANGE_BORDER,
            command=self._on_extract_audio_from_file_clicked,
        )
        self.btn_extract_audio.pack(side="right")

        # ── Tab 2: URL Online ──
        self.url_var = ctk.StringVar()
        url_input_box = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_input_box.pack(fill="x", pady=(6, 6))

        self.url_entry = ctk.CTkEntry(
            url_input_box,
            textvariable=self.url_var,
            placeholder_text="Dán link TikTok, YouTube, Facebook, SoundCloud, Artlist hoặc direct audio vào đây...",
            height=38,
            corner_radius=8,
            fg_color=BG_INSET,
            border_color=BORDER_INSET,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=("Consolas", 12),
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            url_input_box,
            text="📋 Dán",
            font=("Arial", 11, "bold"),
            width=65,
            height=38,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._paste_clipboard,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            url_input_box,
            text="✖",
            width=38,
            height=38,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_SECONDARY,
            command=lambda: self.url_var.set(""),
        ).pack(side="right")

        # Dòng 2: Tùy chọn Tác vụ & Độ nét / Định dạng âm thanh khi tải online
        url_controls_bar = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_controls_bar.pack(fill="x", pady=(2, 4))

        # Nhóm lựa chọn chế độ: Chỉ tải gốc vs Chỉ tải nhạc vs Tải & Vietsub luôn
        ctk.CTkLabel(
            url_controls_bar,
            text="🎯 Chế độ:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 6))

        self.url_mode_display_map = {
            "download_only": "⬇️ Video Gốc",
            "download_audio": "🎵 Chỉ Tải Nhạc / Audio",
            "download_and_sub": "⚡ Tải & Vietsub Luôn",
        }
        self.reverse_url_mode_map = {v: k for k, v in self.url_mode_display_map.items()}

        current_url_mode = self.config.get("url_action_mode", "download_only")
        if current_url_mode not in self.url_mode_display_map:
            current_url_mode = "download_only"

        self.url_mode_var = ctk.StringVar(
            value=self.url_mode_display_map.get(current_url_mode, "⬇️ Video Gốc")
        )

        init_color = APPLE_GREEN if current_url_mode == "download_only" else (APPLE_ORANGE if current_url_mode == "download_audio" else APPLE_BLUE)

        self.seg_url_mode = ctk.CTkSegmentedButton(
            url_controls_bar,
            values=["⬇️ Video Gốc", "🎵 Chỉ Tải Nhạc / Audio", "⚡ Tải & Vietsub Luôn"],
            command=self._on_url_mode_changed,
            height=30,
            corner_radius=8,
            selected_color=init_color,
            selected_hover_color=init_color,
            variable=self.url_mode_var,
        )
        self.seg_url_mode.pack(side="left", padx=(0, 14))

        # Nhóm lựa chọn: Độ nét (nếu tải video) hoặc Định dạng (nếu tải audio)
        self.lbl_format_or_quality = ctk.CTkLabel(
            url_controls_bar,
            text="🎵 Định dạng:" if current_url_mode == "download_audio" else "🎬 Độ nét:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        )
        self.lbl_format_or_quality.pack(side="left", padx=(0, 6))

        self.quality_display_map = {
            "best": "🌟 Cao nhất (Gốc 4K/2K/1080p)",
            "1080p": "📺 Full HD (1080p)",
            "720p": "📱 HD (720p)",
        }
        self.reverse_quality_map = {v: k for k, v in self.quality_display_map.items()}

        self.audio_format_display_map = {
            "mp3": "MP3 (320kbps Studio)",
            "m4a": "M4A (Apple AAC)",
            "wav": "WAV (Lossless)",
        }
        self.reverse_audio_format_map = {v: k for k, v in self.audio_format_display_map.items()}

        current_quality = self.config.get("download_quality", "best")
        current_quality_display = self.quality_display_map.get(current_quality, "🌟 Cao nhất (Gốc 4K/2K/1080p)")
        self.download_quality_var = ctk.StringVar(value=current_quality_display)

        current_audio_fmt = self.config.get("audio_format", "mp3")
        current_audio_fmt_display = self.audio_format_display_map.get(current_audio_fmt, "MP3 (320kbps Studio)")
        self.download_audio_format_var = ctk.StringVar(value=current_audio_fmt_display)

        active_menu_values = (
            list(self.audio_format_display_map.values())
            if current_url_mode == "download_audio"
            else list(self.quality_display_map.values())
        )
        active_menu_var = (
            self.download_audio_format_var
            if current_url_mode == "download_audio"
            else self.download_quality_var
        )

        self.quality_menu = ctk.CTkOptionMenu(
            url_controls_bar,
            values=active_menu_values,
            variable=active_menu_var,
            command=self._on_format_or_quality_changed,
            height=30,
            corner_radius=8,
            fg_color=BG_INSET,
            button_color=BG_PILL,
            button_hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
        )
        self.quality_menu.pack(side="left")

        # Dòng 3: Giải thích trực quan & Nền tảng hỗ trợ
        url_hint_bar = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_hint_bar.pack(fill="x", pady=(2, 0))

        self.lbl_url_hint = ctk.CTkLabel(
            url_hint_bar,
            text="",
            font=("Arial", 11),
            text_color=APPLE_GREEN,
        )
        self.lbl_url_hint.pack(side="left")

        ctk.CTkLabel(
            url_hint_bar,
            text="Hỗ trợ: 🎵 TikTok  •  📺 YouTube  •  📘 Facebook  •  ⚡ Bilibili  •  🎧 SoundCloud/Artlist",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(side="right")

        # ── Thanh Tùy Chọn: Ngôn ngữ, Lồng tiếng AI, Cỡ chữ & Tùy chọn xuất file ──
        options_bar = ctk.CTkFrame(
            input_card,
            fg_color=BG_INSET,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_INSET,
        )
        options_bar.pack(fill="x", padx=14, pady=(0, 12))

        # Dòng 1: Ngôn ngữ nguồn (trái) & Lồng tiếng AI (phải)
        opts_row1 = ctk.CTkFrame(options_bar, fg_color="transparent")
        opts_row1.pack(fill="x", padx=12, pady=(8, 4))

        lang_box = ctk.CTkFrame(opts_row1, fg_color="transparent")
        lang_box.pack(side="left")

        ctk.CTkLabel(
            lang_box,
            text="🌐 Ngôn ngữ:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 6))

        self.lang_display_map = {
            "zh": "🇨🇳 Tiếng Trung",
            "en": "🇺🇸 Tiếng Anh",
            "vi": "🇻🇳 Tiếng Việt",
        }
        self.reverse_lang_map = {v: k for k, v in self.lang_display_map.items()}

        current_lang = self.config.get("source_language", "zh")
        self.source_lang_var = ctk.StringVar(value=current_lang)

        self.seg_lang = ctk.CTkSegmentedButton(
            lang_box,
            values=["🇨🇳 Tiếng Trung", "🇺🇸 Tiếng Anh", "🇻🇳 Tiếng Việt"],
            command=self._on_source_lang_change,
            height=30,
            corner_radius=8,
            selected_color=APPLE_BLUE,
            selected_hover_color=APPLE_BLUE_HOVER,
            unselected_color=BG_CARD,
            unselected_hover_color=BG_PILL_HOVER,
        )
        self.seg_lang.set(self.lang_display_map.get(current_lang, "🇨🇳 Tiếng Trung"))
        self.seg_lang.pack(side="left")

        right_top_box = ctk.CTkFrame(opts_row1, fg_color="transparent")
        right_top_box.pack(side="right")

        self.btn_editor = ctk.CTkButton(
            right_top_box,
            text="✏️ Sửa Sub & Ghép Lại",
            font=("Arial", 11, "bold"),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            border_width=1,
            border_color=BORDER_CARD,
            text_color=TEXT_PRIMARY,
            height=30,
            corner_radius=8,
            command=self._open_standalone_editor,
        )
        self.btn_editor.pack(side="left", padx=(0, 14))

        current_enable_tts = self.config.get("enable_tts", True if current_lang != "vi" else False)
        self.enable_tts_var = ctk.BooleanVar(value=current_enable_tts)

        self.switch_tts = ctk.CTkSwitch(
            right_top_box,
            text="🎙️ Lồng tiếng AI",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
            progress_color=APPLE_GREEN,
            command=self._on_tts_toggle,
            variable=self.enable_tts_var,
        )
        self.switch_tts.pack(side="left")

        # Dòng 2: Cỡ chữ sub (trái) & Tùy chọn Duyệt sub & Xuất kèm SRT / TXT (phải)
        opts_row2 = ctk.CTkFrame(options_bar, fg_color="transparent")
        opts_row2.pack(fill="x", padx=12, pady=(4, 8))

        font_box = ctk.CTkFrame(opts_row2, fg_color="transparent")
        font_box.pack(side="left")

        ctk.CTkLabel(
            font_box,
            text="📝 Cỡ chữ sub:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 6))

        current_font_size = self.config.get("subtitle_font_size", 10)
        self.font_slider_main = ctk.CTkSlider(
            font_box,
            from_=8,
            to=24,
            number_of_steps=16,
            width=110,
            command=self._on_main_font_slide,
            progress_color=APPLE_BLUE,
            button_color="#99C7FF",
        )
        self.font_slider_main.set(current_font_size)
        self.font_slider_main.pack(side="left", padx=(0, 6))

        self.lbl_font_main = ctk.CTkLabel(
            font_box,
            text=f"{int(current_font_size)} pt",
            font=("Consolas", 12, "bold"),
            text_color=APPLE_CYAN,
            width=42,
        )
        self.lbl_font_main.pack(side="left")

        export_box = ctk.CTkFrame(opts_row2, fg_color="transparent")
        export_box.pack(side="right")

        self.review_subtitles_var = ctk.BooleanVar(value=self.config.get("review_subtitles", False))
        self.chk_review_sub = ctk.CTkCheckBox(
            export_box,
            text="✏️ Duyệt & sửa sub trước khi ghép",
            variable=self.review_subtitles_var,
            command=self._on_review_sub_toggle,
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
            checkmark_color="#FFFFFF",
            fg_color=APPLE_GREEN,
            hover_color=APPLE_GREEN_HOVER,
            border_color=BORDER_CARD,
            width=18,
            height=18,
            checkbox_width=18,
            checkbox_height=18,
        )
        self.chk_review_sub.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(
            export_box,
            text="📤 Xuất kèm:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self.export_srt_var = ctk.BooleanVar(value=self.config.get("export_srt", True))
        self.chk_export_srt = ctk.CTkCheckBox(
            export_box,
            text="File .SRT",
            variable=self.export_srt_var,
            command=self._on_export_option_change,
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
            checkmark_color="#FFFFFF",
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            border_color=BORDER_CARD,
            width=18,
            height=18,
            checkbox_width=18,
            checkbox_height=18,
        )
        self.chk_export_srt.pack(side="left", padx=(0, 12))

        self.export_txt_var = ctk.BooleanVar(value=self.config.get("export_txt", True))
        self.chk_export_txt = ctk.CTkCheckBox(
            export_box,
            text="File .TXT",
            variable=self.export_txt_var,
            command=self._on_export_option_change,
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
            checkmark_color="#FFFFFF",
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            border_color=BORDER_CARD,
            width=18,
            height=18,
            checkbox_width=18,
            checkbox_height=18,
        )
        self.chk_export_txt.pack(side="left")

        # ═════════════════════════════════════════════════════════
        # 3. PIPELINE STAGE TRACKER (macOS PROGRESS STEPPER)
        # ═════════════════════════════════════════════════════════
        tracker_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        tracker_card.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        tracker_card.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.steps = []
        step_definitions = [
            ("1", "1  📥 Tải / Nhận Video"),
            ("2", "2  🤖 Gemini AI Dịch"),
            ("3", "3  🎙️ Lồng Tiếng AI"),
            ("4", "4  🎬 Ghép Sub & Xuất"),
        ]

        for i, (num, name) in enumerate(step_definitions):
            step_box = ctk.CTkFrame(tracker_card, fg_color="transparent")
            step_box.grid(row=0, column=i, padx=6, pady=8, sticky="ew")

            pill = ctk.CTkLabel(
                step_box,
                text=name,
                font=("Arial", 11, "bold"),
                fg_color=BG_INSET,
                text_color=TEXT_SECONDARY,
                corner_radius=8,
                height=32,
            )
            pill.pack(fill="x")
            self.steps.append(pill)

        # ═════════════════════════════════════════════════════════
        # 4. TERMINAL & LOG CONSOLE CARD (macOS CONSOLE WINDOW)
        # ═════════════════════════════════════════════════════════
        log_card = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        log_card.grid(row=3, column=0, sticky="nsew", padx=20, pady=6)
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        # Terminal Header with macOS Traffic Lights
        term_header = ctk.CTkFrame(log_card, fg_color="transparent")
        term_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))

        traffic_dots = ctk.CTkFrame(term_header, fg_color="transparent")
        traffic_dots.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(traffic_dots, text="●", font=("Arial", 14), text_color="#FF5F56").pack(side="left", padx=2)
        ctk.CTkLabel(traffic_dots, text="●", font=("Arial", 14), text_color="#FFBD2E").pack(side="left", padx=2)
        ctk.CTkLabel(traffic_dots, text="●", font=("Arial", 14), text_color="#27C93F").pack(side="left", padx=2)

        ctk.CTkLabel(
            term_header,
            text="Console — Studio Terminal",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self.pct_badge = ctk.CTkLabel(
            term_header,
            text="0%",
            font=("Consolas", 11, "bold"),
            fg_color=BG_INSET,
            text_color=APPLE_CYAN,
            corner_radius=6,
            width=48,
            height=22,
        )
        self.pct_badge.pack(side="left", padx=(10, 4))

        self.timer_badge = ctk.CTkLabel(
            term_header,
            text="⏱️ 00:00",
            font=("Consolas", 11, "bold"),
            fg_color=BG_INSET,
            text_color=APPLE_ORANGE,
            corner_radius=6,
            width=76,
            height=22,
        )
        self.timer_badge.pack(side="left", padx=4)

        ctk.CTkButton(
            term_header,
            text="🗑️ Xóa Log",
            font=("Arial", 11),
            width=70,
            height=24,
            corner_radius=6,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_SECONDARY,
            command=self._clear_logs,
        ).pack(side="right")

        # Terminal Content Box
        self.log_box = ctk.CTkTextbox(
            log_card,
            font=("Consolas", 12),
            fg_color="#0D0E12",
            text_color="#D8DEE9",
            corner_radius=10,
            border_width=1,
            border_color=BORDER_INSET,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            log_card,
            height=7,
            corner_radius=4,
            progress_color=APPLE_BLUE,
            fg_color=BG_INSET,
        )
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.progress_bar.set(0.0)

        # ═════════════════════════════════════════════════════════
        # 5. BOTTOM ACTION FOOTER
        # ═════════════════════════════════════════════════════════
        footer_card = ctk.CTkFrame(self, fg_color="transparent")
        footer_card.grid(row=4, column=0, sticky="ew", padx=20, pady=(6, 16))
        footer_card.grid_columnconfigure(0, weight=1)

        # Status text left
        self.status_label = ctk.CTkLabel(
            footer_card,
            text="✨ Sẵn sàng thực hiện.",
            font=("Arial", 13),
            text_color="#94A3B8",
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        # Buttons right
        btn_group = ctk.CTkFrame(footer_card, fg_color="transparent")
        btn_group.grid(row=0, column=1, sticky="e")

        self.btn_open_folder = ctk.CTkButton(
            btn_group,
            text="📁 Mở Thư Mục Xuất",
            width=145,
            height=38,
            corner_radius=8,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_CARD,
            font=("Arial", 12, "bold"),
            command=self._open_output_dir,
        )
        self.btn_open_folder.pack(side="left", padx=(0, 10))

        self.btn_cancel = ctk.CTkButton(
            btn_group,
            text="⏹ Hủy",
            width=80,
            height=38,
            corner_radius=8,
            fg_color=APPLE_RED_BG,
            hover_color=APPLE_RED,
            text_color=APPLE_RED,
            state="disabled",
            font=("Arial", 12, "bold"),
            command=self._cancel,
        )
        self.btn_cancel.pack(side="left", padx=(0, 10))

        self.btn_start = ctk.CTkButton(
            btn_group,
            text="🚀 BẮT ĐẦU DỊCH",
            width=185,
            height=38,
            corner_radius=8,
            font=("Arial", 13, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            command=self._on_main_action_clicked,
        )
        self.btn_start.pack(side="left")

        # ═════════════════════════════════════════════════════════
        # 6. AUTHOR & BRANDING BAR (macOS FOOTER STRIP)
        # ═════════════════════════════════════════════════════════
        credit_bar = ctk.CTkFrame(self, fg_color="transparent")
        credit_bar.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 10))
        credit_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            credit_bar,
            text="⭐️ Được phát triển bởi Bành Đại Dũng - 0982333097",
            font=("Arial", 11, "bold"),
            text_color=APPLE_CYAN,
        ).pack(side="left")

        ctk.CTkLabel(
            credit_bar,
            text="Vietsub AI Studio • macOS Edition",
            font=("Arial", 10),
            text_color=TEXT_TERTIARY,
        ).pack(side="right")

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        if current.lower() == "dark":
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("Dark")

    def _paste_clipboard(self):
        try:
            text = self.clipboard_get().strip()
            if text:
                self.url_var.set(text)
        except Exception:
            pass

    def _clear_logs(self):
        self.log_box.delete("1.0", "end")
        if hasattr(self, "timer_badge"):
            self.timer_badge.configure(text="⏱️ 00:00", text_color=APPLE_ORANGE)

    def _start_timer(self):
        """Bắt đầu đếm thời gian thực hiện (stopwatch)."""
        self._timer_start_time = time.time()
        self._timer_running = True
        if hasattr(self, "timer_badge"):
            self.timer_badge.configure(text="⏱️ 00:00", text_color=APPLE_ORANGE)
        self._tick_timer()

    def _tick_timer(self):
        """Cập nhật đồng hồ đếm giây mỗi giây."""
        if not self._timer_running or self._timer_start_time is None:
            return
        elapsed = int(time.time() - self._timer_start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        if hasattr(self, "timer_badge"):
            self.timer_badge.configure(text=f"⏱️ {mins:02d}:{secs:02d}")
        self._timer_after_id = self.after(1000, self._tick_timer)

    def _stop_timer(self, success: bool = True) -> str:
        """Dừng đồng hồ đếm và trả về chuỗi mm:ss."""
        self._timer_running = False
        if self._timer_after_id:
            try:
                self.after_cancel(self._timer_after_id)
            except Exception:
                pass
            self._timer_after_id = None
        if self._timer_start_time is not None:
            elapsed = int(time.time() - self._timer_start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            elapsed_str = f"{mins:02d}:{secs:02d}"
            color = APPLE_GREEN if success else APPLE_RED
            if hasattr(self, "timer_badge"):
                self.timer_badge.configure(text=f"⏱️ {elapsed_str}", text_color=color)
            return elapsed_str
        return "00:00"

    def _set_active_step(self, step_idx: int):
        """Cập nhật giao diện 4 bước của Pipeline: 0=None, 1=Tải, 2=Dịch, 3=TTS, 4=Render"""
        self._current_step = step_idx
        for i, pill in enumerate(self.steps, start=1):
            if i < step_idx:
                # Đã hoàn thành bước trước
                pill.configure(fg_color=APPLE_GREEN_BG, text_color=APPLE_GREEN)
            elif i == step_idx:
                # Đang xử lý bước hiện tại
                pill.configure(fg_color=APPLE_BLUE, text_color="#FFFFFF")
            else:
                # Chưa đến lượt
                pill.configure(fg_color=BG_INSET, text_color=TEXT_MUTED)

    def _reset_steps(self):
        self._set_active_step(0)

    def _on_tab_changed(self):
        """Gọi khi chuyển đổi giữa tab Chọn File và tab Link Online."""
        self._update_action_button()

    def _on_url_mode_changed(self, selected_label: str):
        """Xử lý khi người dùng chọn 'Video Gốc', 'Chỉ Tải Nhạc' hoặc 'Tải & Vietsub luôn'."""
        mode_key = self.reverse_url_mode_map.get(selected_label, "download_only")
        self.config["url_action_mode"] = mode_key
        save_config(self.config)

        if mode_key == "download_only":
            self.seg_url_mode.configure(
                selected_color=APPLE_GREEN,
                selected_hover_color="#248A3D",
            )
            if hasattr(self, "lbl_format_or_quality"):
                self.lbl_format_or_quality.configure(text="🎬 Độ nét:")
            if hasattr(self, "quality_menu"):
                self.quality_menu.configure(
                    values=list(self.quality_display_map.values()),
                    variable=self.download_quality_var,
                )
        elif mode_key == "download_audio":
            self.seg_url_mode.configure(
                selected_color=APPLE_ORANGE,
                selected_hover_color="#CC7A00",
            )
            if hasattr(self, "lbl_format_or_quality"):
                self.lbl_format_or_quality.configure(text="🎵 Định dạng:")
            if hasattr(self, "quality_menu"):
                self.quality_menu.configure(
                    values=list(self.audio_format_display_map.values()),
                    variable=self.download_audio_format_var,
                )
        else:
            self.seg_url_mode.configure(
                selected_color=APPLE_BLUE,
                selected_hover_color=APPLE_BLUE_HOVER,
            )
            if hasattr(self, "lbl_format_or_quality"):
                self.lbl_format_or_quality.configure(text="🎬 Độ nét:")
            if hasattr(self, "quality_menu"):
                self.quality_menu.configure(
                    values=list(self.quality_display_map.values()),
                    variable=self.download_quality_var,
                )
        self._update_action_button()

    def _on_format_or_quality_changed(self, selected_label: str):
        """Xử lý khi người dùng đổi chất lượng video hoặc định dạng audio."""
        mode = self.config.get("url_action_mode", "download_only")
        if mode == "download_audio":
            fmt_key = self.reverse_audio_format_map.get(selected_label, "mp3")
            self.config["audio_format"] = fmt_key
            save_config(self.config)
            self._update_action_button()
        else:
            quality_key = self.reverse_quality_map.get(selected_label, "best")
            self.config["download_quality"] = quality_key
            save_config(self.config)

    def _on_quality_changed(self, selected_label: str):
        # Giữ tương thích ngược
        self._on_format_or_quality_changed(selected_label)

    def _update_action_button(self):
        """Đồng bộ trạng thái, nhãn nút và màu sắc của nút hành động chính ở góc dưới."""
        if not hasattr(self, "tabview") or not hasattr(self, "btn_start"):
            return

        current_tab = self.tabview.get()
        if "🌐" in current_tab:
            mode = self.config.get("url_action_mode", "download_only")
            if mode == "download_only":
                self.btn_start.configure(
                    text="⬇️ TẢI VIDEO GỐC",
                    fg_color=APPLE_GREEN,
                    hover_color="#248A3D",
                )
                if hasattr(self, "lbl_url_hint"):
                    self.lbl_url_hint.configure(
                        text="💡 Tải file gốc chất lượng cao nhất về máy (nguyên bản 100%, không chèn sub).",
                        text_color=APPLE_GREEN,
                    )
            elif mode == "download_audio":
                audio_fmt = self.config.get("audio_format", "mp3").upper()
                self.btn_start.configure(
                    text=f"🎵 TẢI NHẠC / AUDIO ({audio_fmt})",
                    fg_color=APPLE_ORANGE,
                    hover_color="#CC7A00",
                )
                if hasattr(self, "lbl_url_hint"):
                    self.lbl_url_hint.configure(
                        text="💡 Chỉ tải riêng bài nhạc/âm thanh chất lượng 320kbps (YouTube, TikTok, SoundCloud, Artlist...).",
                        text_color=APPLE_ORANGE,
                    )
            else:
                self.btn_start.configure(
                    text="⚡ TẢI & VIETSUB NGAY",
                    fg_color=APPLE_BLUE,
                    hover_color=APPLE_BLUE_HOVER,
                )
                if hasattr(self, "lbl_url_hint"):
                    self.lbl_url_hint.configure(
                        text="💡 Tự động tải video và vietsub luôn. Hệ thống lưu cả 2 file: [Gốc] và [Vietsub]!",
                        text_color=APPLE_CYAN,
                    )
        else:
            source_lang = getattr(self, "source_lang_var", None) and self.source_lang_var.get() or "zh"
            enable_tts = getattr(self, "enable_tts_var", None) and self.enable_tts_var.get()
            if enable_tts is None:
                enable_tts = True

            if source_lang == "vi":
                btn_text = "🚀 TẠO PHỤ ĐỀ VIỆT" if not enable_tts else "🚀 TẠO SUB & LỒNG TIẾNG"
            else:
                btn_text = "🚀 DỊCH & GHÉP SUB" if not enable_tts else "🚀 BẮT ĐẦU DỊCH"

            self.btn_start.configure(
                text=btn_text,
                fg_color=APPLE_BLUE,
                hover_color=APPLE_BLUE_HOVER,
            )

    def _on_main_action_clicked(self):
        """Hành động khi nhấn nút chính ở chân trang: linh hoạt theo tab và chế độ đã chọn."""
        current_tab = self.tabview.get()
        if "🌐" in current_tab:
            mode = self.config.get("url_action_mode", "download_only")
            if mode == "download_only":
                self._start_download_only()
            elif mode == "download_audio":
                self._start_audio_download()
            else:
                self._start()
        else:
            self._start()

    def _update_step_labels(self):
        source_lang = getattr(self, "source_lang_var", None) and self.source_lang_var.get() or "zh"
        enable_tts = getattr(self, "enable_tts_var", None) and self.enable_tts_var.get()
        if enable_tts is None:
            enable_tts = True

        if source_lang == "vi":
            self.steps[1].configure(text="🤖 AI Phiên Âm")
            self.steps[2].configure(text="📝 Xuất Phụ Đề" if not enable_tts else "🎙️ TTS Lồng Tiếng")
        else:
            self.steps[1].configure(text="🤖 AI Dịch Thuật")
            self.steps[2].configure(text="📝 Xuất Phụ Đề" if not enable_tts else "🎙️ TTS Lồng Tiếng")

        self._update_action_button()

    def _on_source_lang_change(self, display_val: str):
        val = self.reverse_lang_map.get(display_val, "zh")
        self.source_lang_var.set(val)
        # Nếu chuyển sang Tiếng Việt -> mặc định tắt TTS để giữ nguyên giọng nói gốc của video
        if val == "vi":
            self.enable_tts_var.set(False)
            self.switch_tts.deselect()
        else:
            self.enable_tts_var.set(True)
            self.switch_tts.select()
        self._update_step_labels()

    def _on_tts_toggle(self):
        self._update_step_labels()

    def _on_export_option_change(self):
        self.config["export_srt"] = self.export_srt_var.get()
        self.config["export_txt"] = self.export_txt_var.get()
        save_config(self.config)

    def _on_review_sub_toggle(self):
        self.config["review_subtitles"] = self.review_subtitles_var.get()
        save_config(self.config)

    def _open_standalone_editor(self):
        """Mở Trình Chỉnh Sửa Phụ Đề độc lập để chỉnh sửa SRT và ghép lại video."""
        try:
            srt_path = ctk.filedialog.askopenfilename(
                title="Chọn file Phụ đề (.srt) cần chỉnh sửa",
                filetypes=[("SRT Subtitles", "*.srt"), ("All Files", "*.*")],
            )
            if not srt_path:
                return
            with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            from utils.config import find_clean_raw_video

            # Tự động tìm file video gốc sạch từ file srt hoặc từ ô nhập video chính
            clean_video = find_clean_raw_video(srt_path)
            if not clean_video:
                curr_input = self.file_path_var.get().strip()
                clean_video = find_clean_raw_video(curr_input) or (curr_input if os.path.exists(curr_input) else None)

            SubtitleEditorDialog(
                self,
                srt_content=content,
                video_path=clean_video,
                mode="standalone",
            )
        except Exception as e:
            self._log_msg(f"❌ Lỗi khi mở file phụ đề: {e}")

    def _on_main_font_slide(self, val: float):
        int_val = int(round(val))
        self.lbl_font_main.configure(text=f"{int_val} pt")
        self.config["subtitle_font_size"] = int_val
        save_config(self.config)

    def _check_prerequisites(self):
        """Kiểm tra FFmpeg và API Key khi khởi động và cập nhật Badges."""
        ok, msg = check_ffmpeg()
        if ok:
            self.badge_ffmpeg.configure(
                text="⚡ FFmpeg: Sẵn sàng",
                fg_color=APPLE_GREEN_BG,
                hover_color=APPLE_GREEN_BG,
                text_color=APPLE_GREEN,
            )
        else:
            self.badge_ffmpeg.configure(
                text="❌ FFmpeg: Thiếu (Bấm tải)",
                fg_color=APPLE_RED_BG,
                hover_color=APPLE_RED_BG,
                text_color=APPLE_RED,
            )
            self._log_msg(f"❌ {msg}")
            self._log_msg("💡 Mẹo: Bấm vào huy hiệu '❌ FFmpeg: Thiếu (Bấm tải)' ở góc trên để tải tự động 1-click!")
            self.btn_start.configure(state="disabled")

        api_key = self.config.get("gemini_api_key", "").strip()
        if api_key:
            self.badge_api.configure(
                text="🔑 Gemini: Đã kết nối",
                fg_color=APPLE_GREEN_BG,
                text_color=APPLE_GREEN,
            )
        else:
            self.badge_api.configure(
                text="⚠️ Gemini: Chưa có Key",
                fg_color=APPLE_ORANGE_BG,
                text_color=APPLE_ORANGE,
            )
            self._log_msg("⚠️ Chưa có Gemini API Key. Vui lòng bấm '⚙️ Cài đặt' để nhập key.")

    def _on_ffmpeg_badge_click(self):
        ok, msg = check_ffmpeg()
        if ok:
            path = get_ffmpeg_path()
            self._log_msg(f"⚡ FFmpeg đã sẵn sàng: {path}")
        else:
            self._open_ffmpeg_download()

    def _open_ffmpeg_download(self):
        def on_download_success():
            self._check_prerequisites()
            ok, _ = check_ffmpeg()
            if ok and self.config.get("gemini_api_key"):
                self.btn_start.configure(state="normal")
            self._log_msg("✅ Đã cài đặt và kích hoạt FFmpeg thành công!")

        FFmpegDownloadDialog(self, on_success=on_download_success)

    def _open_output_dir(self):
        out_dir = self.config.get("output_dir", str(Path.home() / "Desktop"))
        os.makedirs(out_dir, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])
            elif sys.platform == "win32":
                os.startfile(out_dir)
            else:
                subprocess.Popen(["xdg-open", out_dir])
        except Exception as e:
            self._log_msg(f"⚠️ Không thể mở thư mục: {e}")

    def _log_msg(self, text: str):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def _open_settings(self):
        def on_save(new_config):
            self.config = new_config
            self._check_prerequisites()
            ok, _ = check_ffmpeg()
            if ok and self.config.get("gemini_api_key"):
                self.btn_start.configure(state="normal")
            # Đồng bộ thanh trượt cỡ chữ trên màn hình chính
            new_fs = new_config.get("subtitle_font_size", 10)
            self.font_slider_main.set(new_fs)
            self.lbl_font_main.configure(text=f"{int(new_fs)} pt")
            if hasattr(self, "export_srt_var"):
                self.export_srt_var.set(new_config.get("export_srt", True))
            if hasattr(self, "export_txt_var"):
                self.export_txt_var.set(new_config.get("export_txt", True))
            if hasattr(self, "review_subtitles_var"):
                self.review_subtitles_var.set(new_config.get("review_subtitles", False))

        SettingsDialog(self, self.config, on_save)

    def _browse_file(self):
        filepath = ctk.filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.mov *.avi *.webm")]
        )
        if filepath:
            self.file_path_var.set(filepath)

    def _start(self):
        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        if not self.config.get("gemini_api_key"):
            self._log_msg("❌ Lỗi: Chưa có API Key. Vui lòng bấm Cài đặt để thêm key.")
            self._open_settings()
            return

        is_url = self.tabview.get().startswith("🌐")
        source = self.url_var.get().strip() if is_url else self.file_path_var.get().strip()

        if not source:
            self._log_msg("❌ Lỗi: Vui lòng chọn file video hoặc dán link online.")
            return

        # Khóa UI
        self._is_processing = True
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.seg_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "chk_review_sub"):
                self.chk_review_sub.configure(state="disabled")
            if hasattr(self, "chk_export_srt"):
                self.chk_export_srt.configure(state="disabled")
            if hasattr(self, "chk_export_txt"):
                self.chk_export_txt.configure(state="disabled")
            if hasattr(self, "btn_editor"):
                self.btn_editor.configure(state="disabled")
        except Exception:
            pass

        try:
            self.log_box.delete("1.0", "end")
            self.progress_bar.set(0.0)
            self.pct_badge.configure(text="0%")
            self._start_timer()
            self.status_label.configure(text="⏳ Đang khởi động quy trình...")
            self._set_active_step(1 if is_url else 2)

            # Cập nhật cấu hình hiện tại và lưu lại
            self.config["source_language"] = self.source_lang_var.get()
            self.config["enable_tts"] = self.enable_tts_var.get()
            self.config["download_quality"] = self.reverse_quality_map.get(self.download_quality_var.get(), "best")
            self.config["export_srt"] = self.export_srt_var.get()
            self.config["export_txt"] = self.export_txt_var.get()
            self.config["review_subtitles"] = self.review_subtitles_var.get()
            save_config(self.config)

            # Chạy pipeline trên thread riêng
            self.pipeline = Pipeline(self.task_queue)
            thread = threading.Thread(
                target=self.pipeline.run,
                args=(self.config, source, is_url),
                daemon=True,
            )
            thread.start()
        except Exception as e:
            self._is_processing = False
            self._stop_timer(success=False)
            self.btn_start.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
            self.status_label.configure(text="❌ Lỗi khởi động")
            self._log_msg(f"❌ Không thể khởi động tiến trình: {e}")

    def _start_download_only(self):
        url = self.url_var.get().strip()
        if not url:
            self._log_msg("❌ Lỗi: Vui lòng dán link video (TikTok, Facebook, YouTube...) vào ô nhập.")
            return

        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        self._is_processing = True
        self._download_cancelled = False
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.seg_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "chk_export_srt"):
                self.chk_export_srt.configure(state="disabled")
            if hasattr(self, "chk_export_txt"):
                self.chk_export_txt.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang kết nối tới máy chủ video...")
        self._set_active_step(1)

        out_dir = self.config.get("output_dir", str(Path.home() / "Desktop"))
        quality = self.config.get("download_quality", "best")
        quality_label = self.quality_display_map.get(quality, quality.upper())
        self._log_msg(f"📥 Bắt đầu tải video gốc ({quality_label}) từ:\n   {url}")
        self._log_msg(f"📁 Thư mục lưu: {out_dir}")

        def run_dl():
            from core.downloader import VideoDownloader
            try:
                def on_prog(pct, label):
                    self.task_queue.put({"type": "progress", "value": pct, "label": label})

                dl = VideoDownloader(
                    progress_callback=on_prog,
                    is_cancelled=lambda: self._download_cancelled,
                )
                file_path = dl.download(url, out_dir, quality=quality)
                self.task_queue.put({"type": "download_success", "file_path": file_path})
            except (InterruptedError, KeyboardInterrupt):
                self.task_queue.put({"type": "log", "message": "⚠️ Tiến trình tải đã bị hủy."})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Đã hủy"})
            except Exception as e:
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi tải video: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_dl, daemon=True).start()

    def _start_audio_download(self):
        """Tải riêng file âm thanh/nhạc từ link online (YouTube, TikTok, Facebook, SoundCloud, Artlist...)."""
        url = self.url_var.get().strip()
        if not url:
            self._log_msg("❌ Lỗi: Vui lòng dán link video hoặc link bài nhạc vào ô nhập.")
            return

        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        self._is_processing = True
        self._download_cancelled = False
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.seg_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "chk_export_srt"):
                self.chk_export_srt.configure(state="disabled")
            if hasattr(self, "chk_export_txt"):
                self.chk_export_txt.configure(state="disabled")
            if hasattr(self, "btn_extract_audio"):
                self.btn_extract_audio.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang kết nối tải bài nhạc...")
        self._set_active_step(1)

        out_dir = self.config.get("output_dir", str(Path.home() / "Desktop"))
        audio_fmt = self.config.get("audio_format", "mp3")
        bitrate = self.config.get("audio_bitrate", "320k")
        fmt_label = self.audio_format_display_map.get(audio_fmt, audio_fmt.upper())
        self._log_msg(f"🎵 Bắt đầu tải riêng nhạc / audio ({fmt_label}) từ:\n   {url}")
        self._log_msg(f"📁 Thư mục lưu: {out_dir}")

        def run_audio_dl():
            from core.downloader import VideoDownloader
            try:
                def on_prog(pct, label):
                    self.task_queue.put({"type": "progress", "value": pct, "label": label})

                dl = VideoDownloader(
                    progress_callback=on_prog,
                    is_cancelled=lambda: self._download_cancelled,
                )
                file_path = dl.download_audio(url, out_dir, audio_format=audio_fmt, bitrate=bitrate)
                self.task_queue.put({"type": "audio_download_success", "file_path": file_path})
            except (InterruptedError, KeyboardInterrupt):
                self.task_queue.put({"type": "log", "message": "⚠️ Tiến trình tải nhạc đã bị hủy."})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Đã hủy"})
            except Exception as e:
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi tải nhạc: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_audio_dl, daemon=True).start()

    def _on_extract_audio_from_file_clicked(self):
        """Trích xuất ngay lập tức âm thanh từ file video đã chọn ở Tab 1 sang MP3 320kbps."""
        video_path = self.file_path_var.get().strip()
        if not video_path or not os.path.exists(video_path):
            self._log_msg("❌ Lỗi: Vui lòng chọn một file video ở Tab 1 trước khi bấm trích xuất.")
            return

        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        self._is_processing = True
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        if hasattr(self, "btn_extract_audio"):
            self.btn_extract_audio.configure(state="disabled")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.1)
        self.pct_badge.configure(text="10%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang bóc tách âm thanh sang MP3 320kbps...")
        self._set_active_step(1)

        out_dir = self.config.get("output_dir", str(Path.home() / "Desktop"))
        self._log_msg(f"🎵 Bắt đầu trích xuất âm thanh sang MP3 (320kbps) từ file:\n   {video_path}")
        self._log_msg(f"📁 Thư mục lưu: {out_dir}")

        def run_extract():
            from core.ffmpeg_processor import extract_audio
            try:
                def on_prog(pct, label):
                    self.task_queue.put({"type": "progress", "value": pct, "label": label})

                out_audio = extract_audio(
                    video_path,
                    out_dir,
                    audio_format="mp3",
                    bitrate="320k",
                    progress_callback=on_prog,
                )
                self.task_queue.put({"type": "audio_extract_success", "file_path": out_audio})
            except Exception as e:
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi trích xuất âm thanh: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_extract, daemon=True).start()

    def _cancel(self):
        if self._is_processing:
            self.status_label.configure(text="⚠️ Đang gửi yêu cầu hủy...")
            self.btn_cancel.configure(state="disabled")
            self._download_cancelled = True
            self._stop_timer(success=False)
            if self.pipeline:
                self.pipeline.cancel()

    def _process_queue(self):
        try:
            while True:
                msg = self.task_queue.get_nowait()
                msg_type = msg.get("type")

                if msg_type == "log":
                    text = msg["message"]
                    self._log_msg(text)

                    # Tự động cập nhật step tracker dựa trên nội dung log
                    text_lower = text.lower()
                    if "tải" in text_lower or "download" in text_lower or "trích xuất" in text_lower:
                        self._set_active_step(1)
                    elif "gemini" in text_lower or "dịch" in text_lower or "phụ đề" in text_lower or "phiên âm" in text_lower:
                        self._set_active_step(2)
                    elif "tts" in text_lower or "lồng tiếng" in text_lower or "giọng" in text_lower or "bỏ qua tts" in text_lower:
                        self._set_active_step(3)
                    elif "ghép" in text_lower or "render" in text_lower or "encode" in text_lower or "gắn phụ đề" in text_lower:
                        self._set_active_step(4)

                elif msg_type == "progress":
                    val = msg["value"]
                    lbl = msg["label"]
                    self.progress_bar.set(val)
                    self.pct_badge.configure(text=f"{int(val * 100)}%")
                    self.status_label.configure(text=lbl)

                elif msg_type == "review_subtitles":
                    segments = msg.get("segments", [])
                    srt_content = msg.get("srt_content", "")
                    video_path = msg.get("video_path", "")
                    ev = msg["event"]
                    holder = msg["holder"]

                    def _on_review_confirmed(updated_segments):
                        holder["segments"] = updated_segments
                        holder["cancelled"] = False
                        ev.set()

                    def _on_review_cancelled():
                        holder["cancelled"] = True
                        ev.set()

                    SubtitleEditorDialog(
                        self,
                        segments=segments,
                        srt_content=srt_content,
                        video_path=video_path,
                        mode="review",
                        on_confirm=_on_review_confirmed,
                        on_cancel=_on_review_cancelled,
                    )

                elif msg_type == "success":
                    self._set_active_step(5)  # All done
                    self._log_msg("\n✨ Xử lý thành công xuất sắc! Nhấn '📁 Mở Thư Mục Xuất' để xem video.")

                elif msg_type == "download_success":
                    fp = msg["file_path"]
                    fn = Path(fp).name
                    self._log_msg("\n" + "─" * 48)
                    self._log_msg("🎉 TẢI VIDEO GỐC THÀNH CÔNG!")
                    self._log_msg(f"   🎬 File: {fn}")
                    self._log_msg(f"   📁 Lưu tại: {fp}")
                    self._log_msg("✨ File gốc chất lượng cao nhất đã được lưu an toàn vào thư mục xuất.")
                    self._log_msg("💡 Sếp có thể bấm nút '📁 Mở Thư Mục Xuất' để mở video xem ngay!")
                    self.file_path_var.set(fp)
                    self.progress_bar.set(1.0)
                    self.pct_badge.configure(text="100%")
                    self.status_label.configure(text="✨ Đã tải xong video gốc.")

                elif msg_type in ("audio_download_success", "audio_extract_success"):
                    fp = msg["file_path"]
                    fn = Path(fp).name
                    is_extract = (msg_type == "audio_extract_success")
                    title = "TRÍCH XUẤT ÂM THANH" if is_extract else "TẢI NHẠC / AUDIO"
                    self._log_msg("\n" + "─" * 48)
                    self._log_msg(f"🎉 {title} THÀNH CÔNG!")
                    self._log_msg(f"   🎵 File: {fn}")
                    self._log_msg(f"   📁 Lưu tại: {fp}")
                    self._log_msg("✨ File âm thanh chuẩn phòng thu (MP3 320kbps / Lossless) đã lưu an toàn.")
                    self._log_msg("💡 Sếp có thể bấm nút '📁 Mở Thư Mục Xuất' để thưởng thức bài nhạc ngay!")
                    self.progress_bar.set(1.0)
                    self.pct_badge.configure(text="100%")
                    self.status_label.configure(text=f"✨ Đã hoàn thành {title.lower()}.")

                elif msg_type == "download_done" or msg_type == "done":
                    self._is_processing = False
                    elapsed_str = self._stop_timer(success=True)
                    self._log_msg(f"⏱️ Tổng thời gian thực hiện: {elapsed_str}")
                    self.btn_start.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    try:
                        self.tabview.configure(state="normal")
                        self.seg_url_mode.configure(state="normal")
                        self.quality_menu.configure(state="normal")
                        self.seg_lang.configure(state="normal")
                        self.switch_tts.configure(state="normal")
                        self.font_slider_main.configure(state="normal")
                        if hasattr(self, "chk_review_sub"):
                            self.chk_review_sub.configure(state="normal")
                        if hasattr(self, "chk_export_srt"):
                            self.chk_export_srt.configure(state="normal")
                        if hasattr(self, "chk_export_txt"):
                            self.chk_export_txt.configure(state="normal")
                        if hasattr(self, "btn_editor"):
                            self.btn_editor.configure(state="normal")
                        if hasattr(self, "btn_extract_audio"):
                            self.btn_extract_audio.configure(state="normal")
                    except Exception:
                        pass
                    self.pipeline = None

        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error in _process_queue: {e}")
        finally:
            self.after(100, self._process_queue)
