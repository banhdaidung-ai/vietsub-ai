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

# NOTE: core modules (Pipeline, audio_separator, douyin) are lazy-imported
# inside the methods that need them to avoid blocking UI startup on Windows.
# Heavy packages like google-genai, yt_dlp, edge_tts, curl_cffi take 2-5s
# to load from PyInstaller frozen bundles.
from gui.ffmpeg_download_dialog import FFmpegDownloadDialog
from gui.settings_dialog import SettingsDialog
from gui.completion_dialog import CompletionDialog, _fmt_size
from gui.subtitle_editor_dialog import SubtitleEditorDialog
from gui.audio_separator_dialog import AudioSeparatorDialog
from gui.guide_view import GuideView
from utils.config import get_output_dir, load_config, save_config
from utils.ffmpeg_check import check_ffmpeg, get_ffmpeg_path
from utils.subtitle_styles import (
    get_style_display_names,
    get_preset_by_name,
    get_preset_by_id,
)

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
APPLE_PURPLE = "#AF52DE"       # Apple Purple
APPLE_PURPLE_HOVER = "#9333EA"
APPLE_PURPLE_BG = "#2B143E"    # Subtle purple pill bg
APPLE_PURPLE_BORDER = "#581C87"
APPLE_INDIGO = "#5E5CE6"       # Apple Indigo
APPLE_CYAN = "#64D2FF"         # Apple Cyan

TEXT_PRIMARY = "#F5F5F7"       # Apple pure bright text
TEXT_SECONDARY = "#98989F"     # Apple SF muted caption
TEXT_TERTIARY = "#636366"      # Apple subtle placeholder
TEXT_MUTED = "#636366"         # Apple muted gray for inactive steps

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_TKDND = True
except Exception:
    HAS_TKDND = False
    TkinterDnD = None
    DND_FILES = None

if HAS_TKDND:
    class _BaseWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self._dnd_enabled = True
            except Exception:
                self._dnd_enabled = False
else:
    class _BaseWindow(ctk.CTk):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._dnd_enabled = False


class AppWindow(_BaseWindow):
    def __init__(self):
        super().__init__()

        self.title("Vietsub AI Studio — macOS Edition")
        self.geometry("980x830")
        self.minsize(920, 750)
        self.configure(fg_color=BG_WINDOW)

        self.config = load_config()
        self.task_queue = queue.Queue()
        self.pipeline = None
        self._is_processing = False
        self._download_cancelled = False
        self._audio_sep_cancel_event = threading.Event()
        self._current_step = 0
        self._last_elapsed_str = "00:00"   # Lưu thời gian xử lý để dùng cho popup

        # Stopwatch / Timer đếm thời gian thực hiện
        self._timer_start_time = None
        self._timer_running = False
        self._timer_after_id = None

        self._set_app_icon()
        self._build_ui()
        self._update_step_labels()
        self._update_action_button()

        # Chạy kiểm tra FFmpeg & API Key trên background thread để không block UI khởi động
        threading.Thread(target=self._check_prerequisites_async, daemon=True).start()

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
        self.grid_rowconfigure(4, weight=1)

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
        header_card.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        header_card.grid_columnconfigure(0, weight=1)
        header_card.grid_columnconfigure(1, weight=1)

        # Left (Row 0): Brand Logo & Title
        brand_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        brand_frame.grid(row=0, column=0, sticky="w", padx=16, pady=(10, 4))

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
            text="Studio Dịch Thuật, Phụ Đề & Lồng Tiếng AI Đẳng Cấp",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w")

        # Right (Row 0): System Health Badges & Controls
        controls_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        controls_frame.grid(row=0, column=1, sticky="e", padx=16, pady=(10, 4))

        # Bottom (Row 1 - Spanning across): Main Navigation Tabs (Studio vs Hướng Dẫn)
        nav_container = ctk.CTkFrame(header_card, fg_color="transparent")
        nav_container.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 10))

        self.nav_tabs = ctk.CTkSegmentedButton(
            nav_container,
            values=["🎬 Studio Làm Việc", "📖 Hướng Dẫn Sử Dụng"],
            command=self._on_main_nav_changed,
            font=("Arial", 12, "bold"),
            height=34,
            width=360,
            corner_radius=8,
            fg_color=BG_INSET,
            selected_color=APPLE_BLUE,
            selected_hover_color=APPLE_BLUE_HOVER,
            unselected_color=BG_INSET,
            unselected_hover_color=BG_PILL,
            text_color=TEXT_PRIMARY,
        )
        self.nav_tabs.set("🎬 Studio Làm Việc")
        self.nav_tabs.pack(anchor="center")

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
        # 2. INPUT SECTION (NGUỒN VIDEO / LINK ONLINE)
        # ═════════════════════════════════════════════════════════
        self.input_card = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        self.input_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 6))

        self.tabview = ctk.CTkTabview(
            self.input_card,
            height=138,
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
        self.tabview.pack(fill="x", padx=14, pady=(6, 8))

        tab_file = self.tabview.add("📂 Chọn File Video Trên Máy")
        tab_url = self.tabview.add("🌐 Dán Link Online (TikTok, YouTube, Facebook...)")
        self.tab_file = tab_file

        # ── Tab 1: File Video ──
        self.file_path_var = ctk.StringVar()
        file_box = ctk.CTkFrame(tab_file, fg_color="transparent")
        file_box.pack(fill="x", pady=(6, 8))

        self.file_entry = ctk.CTkEntry(
            file_box,
            textvariable=self.file_path_var,
            placeholder_text="Kéo thả video vào đây hoặc nhấp 'Chọn Video' để duyệt tệp...",
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
            width=140,
            height=38,
            corner_radius=8,
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            text_color="#FFFFFF",
            command=self._browse_file,
        ).pack(side="right")

        file_action_bar = ctk.CTkFrame(tab_file, fg_color="transparent")
        file_action_bar.pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(
            file_action_bar,
            text="💡 Kéo & thả video trực tiếp vào đây hoặc duyệt tệp (MP4, MKV, MOV, AVI, WEBM, MP3, WAV...)",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(side="left")

        # Auxiliary toolbar buttons styled cleanly as subtle pills
        self.btn_separate_audio = ctk.CTkButton(
            file_action_bar,
            text="🎤 Tách Beat & Lời (AI)",
            font=("Arial", 11, "bold"),
            width=165,
            height=28,
            corner_radius=7,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color="#D8B4FE",
            border_width=1,
            border_color=APPLE_PURPLE_BORDER,
            command=self._on_separate_audio_clicked,
        )
        self.btn_separate_audio.pack(side="right", padx=(6, 0))

        self.btn_extract_audio = ctk.CTkButton(
            file_action_bar,
            text="🎵 Trích Audio (MP3 320k)",
            font=("Arial", 11, "bold"),
            width=165,
            height=28,
            corner_radius=7,
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=APPLE_ORANGE,
            border_width=1,
            border_color=APPLE_ORANGE_BORDER,
            command=self._on_extract_audio_from_file_clicked,
        )
        self.btn_extract_audio.pack(side="right")

        # ── Tab 2: URL Online ──
        self.url_var = ctk.StringVar()
        url_input_box = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_input_box.pack(fill="x", pady=(4, 6))

        self.url_entry = ctk.CTkEntry(
            url_input_box,
            textvariable=self.url_var,
            placeholder_text="Dán link Douyin, TikTok, YouTube, Facebook, SoundCloud, Artlist...",
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

        url_controls_bar = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_controls_bar.pack(fill="x", pady=(2, 4))

        ctk.CTkLabel(
            url_controls_bar,
            text="🎯 Chế độ:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self.url_mode_display_map = {
            "download_only": "⬇️ Video Gốc",
            "download_audio": "🎵 Chỉ Tải Nhạc",
            "download_and_sub": "⚡ Tải & Vietsub",
            "download_and_separate": "🎤 Tách Nhạc & Lời",
        }
        self.reverse_url_mode_map = {v: k for k, v in self.url_mode_display_map.items()}

        current_url_mode = self.config.get("url_action_mode", "download_only")
        if current_url_mode not in self.url_mode_display_map:
            current_url_mode = "download_only"

        self.url_mode_var = ctk.StringVar(
            value=self.url_mode_display_map.get(current_url_mode, "⬇️ Video Gốc")
        )

        if current_url_mode == "download_only":
            init_color = APPLE_GREEN
        elif current_url_mode == "download_audio":
            init_color = APPLE_ORANGE
        elif current_url_mode == "download_and_separate":
            init_color = APPLE_PURPLE
        else:
            init_color = APPLE_BLUE

        self.seg_url_mode = ctk.CTkSegmentedButton(
            url_controls_bar,
            values=list(self.url_mode_display_map.values()),
            command=self._on_url_mode_changed,
            height=30,
            corner_radius=8,
            selected_color=init_color,
            selected_hover_color=init_color,
            variable=self.url_mode_var,
        )
        self.seg_url_mode.pack(side="left", padx=(0, 14))

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

        # ═════════════════════════════════════════════════════════
        # 3. STUDIO CONTROLS (THIẾT LẬP DỊCH THUẬT & PHỤ ĐỀ)
        # ═════════════════════════════════════════════════════════
        settings_card = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        settings_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 6))

        # Dòng 1: Ngôn ngữ nguồn (trái) & Lồng tiếng AI / Editor (phải)
        settings_row1 = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_row1.pack(fill="x", padx=16, pady=(10, 5))

        lang_group = ctk.CTkFrame(settings_row1, fg_color="transparent")
        lang_group.pack(side="left")

        ctk.CTkLabel(
            lang_group,
            text="🌐 Bản dịch:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self.source_lang_display_map = {
            "auto": "🌍 Tự Động (AI nhận diện)",
            "zh":   "🇨🇳 Tiếng Trung",
            "en":   "🇺🇸 Tiếng Anh",
            "vi":   "🇻🇳 Tiếng Việt",
            "ja":   "🇯🇵 Tiếng Nhật",
            "ko":   "🇰🇷 Tiếng Hàn",
            "th":   "🇹🇭 Tiếng Thái",
            "fr":   "🇫🇷 Tiếng Pháp",
            "es":   "🇪🇸 Tiếng Tây Ban Nha",
            "de":   "🇩🇪 Tiếng Đức",
        }
        self.source_lang_reverse_map = {v: k for k, v in self.source_lang_display_map.items()}

        self.target_lang_display_map = {
            "vi": "🇻🇳 Tiếng Việt",
            "en": "🇺🇸 Tiếng Anh",
        }
        self.target_lang_reverse_map = {v: k for k, v in self.target_lang_display_map.items()}

        current_lang = self.config.get("source_language", "zh")
        current_target = self.config.get("target_language", "vi")
        self.source_lang_var = ctk.StringVar(value=current_lang)
        self.target_lang_var = ctk.StringVar(value=current_target)

        ctk.CTkLabel(
            lang_group,
            text="Gốc:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))

        self.menu_source_lang = ctk.CTkOptionMenu(
            lang_group,
            values=list(self.source_lang_display_map.values()),
            command=self._on_source_lang_change,
            height=30,
            width=180,
            corner_radius=8,
            fg_color=BG_INSET,
            button_color=APPLE_BLUE,
            button_hover_color=APPLE_BLUE_HOVER,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_PILL_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
            font=("Arial", 11),
        )
        self.menu_source_lang.set(
            self.source_lang_display_map.get(current_lang, "🌍 Tự Động (AI nhận diện)")
        )
        self.menu_source_lang.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            lang_group,
            text="➔",
            font=("Arial", 13, "bold"),
            text_color=APPLE_GREEN,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            lang_group,
            text="Đích:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))

        self.menu_target_lang = ctk.CTkOptionMenu(
            lang_group,
            values=list(self.target_lang_display_map.values()),
            command=self._on_target_lang_change,
            height=30,
            width=145,
            corner_radius=8,
            fg_color=BG_INSET,
            button_color=APPLE_GREEN,
            button_hover_color=APPLE_GREEN_HOVER,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_PILL_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
            font=("Arial", 11),
        )
        self.menu_target_lang.set(
            self.target_lang_display_map.get(current_target, "🇻🇳 Tiếng Việt")
        )
        self.menu_target_lang.pack(side="left")

        # Right of Row 1: Voice and Sub Editor
        audio_group = ctk.CTkFrame(settings_row1, fg_color="transparent")
        audio_group.pack(side="right")

        current_enable_tts = self.config.get("enable_tts", True if current_lang not in ("vi",) else False)
        if current_target != "vi":
            current_enable_tts = False
        self.enable_tts_var = ctk.BooleanVar(value=current_enable_tts)

        self.switch_tts = ctk.CTkSwitch(
            audio_group,
            text="🎙️ Lồng tiếng AI",
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
            progress_color=APPLE_GREEN,
            command=self._on_tts_toggle,
            variable=self.enable_tts_var,
        )
        self.switch_tts.pack(side="left", padx=(0, 14))
        if current_target != "vi":
            self.switch_tts.configure(state="disabled")

        self.btn_editor = ctk.CTkButton(
            audio_group,
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
        self.btn_editor.pack(side="left")

        # Dòng 2: Mẫu phụ đề & Cỡ chữ (trái) + Duyệt sub & Xuất file (phải)
        settings_row2 = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_row2.pack(fill="x", padx=16, pady=(4, 10))

        style_group = ctk.CTkFrame(settings_row2, fg_color="transparent")
        style_group.pack(side="left")

        ctk.CTkLabel(
            style_group,
            text="🎨 Mẫu Sub:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 6))

        current_preset_id = self.config.get("subtitle_style_preset", "capcut_yellow")
        current_preset = get_preset_by_id(current_preset_id)

        self.menu_subtitle_style = ctk.CTkOptionMenu(
            style_group,
            values=get_style_display_names(),
            command=self._on_subtitle_style_change,
            height=28,
            width=175,
            corner_radius=8,
            fg_color=BG_INSET,
            button_color=APPLE_BLUE,
            button_hover_color=APPLE_BLUE_HOVER,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_PILL_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
            font=("Arial", 11),
        )
        self.menu_subtitle_style.set(current_preset["name"])
        self.menu_subtitle_style.pack(side="left", padx=(0, 6))

        self.style_preview_pill = ctk.CTkFrame(
            style_group,
            fg_color=current_preset["ui_bg"],
            border_width=1,
            border_color=current_preset["ui_border"],
            corner_radius=6,
            height=26,
            width=64,
        )
        self.style_preview_pill.pack(side="left", padx=(0, 14))
        self.style_preview_pill.pack_propagate(False)

        self.lbl_style_preview_text = ctk.CTkLabel(
            self.style_preview_pill,
            text="Aa Sub",
            font=("Arial", 11, "bold"),
            text_color=current_preset["ui_fg"],
        )
        self.lbl_style_preview_text.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            style_group,
            text="📝 Cỡ:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))

        current_font_size = self.config.get("subtitle_font_size", 10)
        self.font_slider_main = ctk.CTkSlider(
            style_group,
            from_=8,
            to=24,
            number_of_steps=16,
            width=80,
            command=self._on_main_font_slide,
            progress_color=APPLE_BLUE,
            button_color="#99C7FF",
        )
        self.font_slider_main.set(current_font_size)
        self.font_slider_main.pack(side="left", padx=(0, 4))

        self.lbl_font_main = ctk.CTkLabel(
            style_group,
            text=f"{int(current_font_size)} pt",
            font=("Consolas", 11, "bold"),
            text_color=APPLE_CYAN,
            width=36,
        )
        self.lbl_font_main.pack(side="left")

        export_group = ctk.CTkFrame(settings_row2, fg_color="transparent")
        export_group.pack(side="right")

        self.review_subtitles_var = ctk.BooleanVar(value=self.config.get("review_subtitles", False))
        self.chk_review_sub = ctk.CTkCheckBox(
            export_group,
            text="✏️ Duyệt sub trước khi ghép",
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
        self.chk_review_sub.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(
            export_group,
            text="📤 Xuất:",
            font=("Arial", 11, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 6))

        self.export_srt_var = ctk.BooleanVar(value=self.config.get("export_srt", True))
        self.chk_export_srt = ctk.CTkCheckBox(
            export_group,
            text=".SRT",
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
        self.chk_export_srt.pack(side="left", padx=(0, 10))

        self.export_txt_var = ctk.BooleanVar(value=self.config.get("export_txt", True))
        self.chk_export_txt = ctk.CTkCheckBox(
            export_group,
            text=".TXT",
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
        # 4. PIPELINE STAGE TRACKER (macOS PROGRESS STEPPER)
        # ═════════════════════════════════════════════════════════
        tracker_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        tracker_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 6))
        tracker_card.grid_columnconfigure((0, 2, 4, 6), weight=1)

        self.steps = []
        step_definitions = [
            ("1", "1  📥 Nhận Video"),
            ("2", "2  🤖 Gemini Dịch"),
            ("3", "3  🎙️ Lồng Tiếng AI"),
            ("4", "4  🎬 Ghép & Xuất"),
        ]

        for i, (num, name) in enumerate(step_definitions):
            col = i * 2
            pill = ctk.CTkLabel(
                tracker_card,
                text=name,
                font=("Arial", 11, "bold"),
                fg_color=BG_INSET,
                text_color=TEXT_MUTED,
                corner_radius=8,
                height=30,
            )
            pill.grid(row=0, column=col, padx=(8 if i == 0 else 4, 4), pady=6, sticky="ew")
            self.steps.append(pill)

            if i < 3:
                ctk.CTkLabel(
                    tracker_card,
                    text="›",
                    font=("Arial", 14, "bold"),
                    text_color=TEXT_MUTED,
                ).grid(row=0, column=col + 1, padx=2, pady=6)

        # ═════════════════════════════════════════════════════════
        # 5. TERMINAL & LOG CONSOLE CARD (macOS CONSOLE WINDOW)
        # ═════════════════════════════════════════════════════════
        log_card = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
        )
        log_card.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 6))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(2, weight=1)

        # Terminal Header with macOS Traffic Lights
        term_header = ctk.CTkFrame(log_card, fg_color="transparent")
        term_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 4))

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

        # Progress Bar directly under header
        self.progress_bar = ctk.CTkProgressBar(
            log_card,
            height=8,
            corner_radius=4,
            progress_color=APPLE_BLUE,
            fg_color=BG_INSET,
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 6))
        self.progress_bar.set(0.0)

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
        self.log_box.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))

        # ═════════════════════════════════════════════════════════
        # 6. BOTTOM ACTION FOOTER
        # ═════════════════════════════════════════════════════════
        footer_card = ctk.CTkFrame(self, fg_color="transparent")
        footer_card.grid(row=5, column=0, sticky="ew", padx=20, pady=(4, 10))
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
            width=150,
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
            width=190,
            height=38,
            corner_radius=8,
            font=("Arial", 13, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            command=self._on_main_action_clicked,
        )
        self.btn_start.pack(side="left")

        # ═════════════════════════════════════════════════════════
        # 7. AUTHOR & BRANDING BAR (macOS FOOTER STRIP)
        # ═════════════════════════════════════════════════════════
        credit_bar = ctk.CTkFrame(self, fg_color="transparent")
        credit_bar.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 8))
        credit_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            credit_bar,
            text="⭐️ Bản quyền & phát triển bởi Bành Đại Dũng - 0982333097",
            font=("Arial", 11, "bold"),
            text_color=APPLE_CYAN,
        ).pack(side="left")

        ctk.CTkLabel(
            credit_bar,
            text="Vietsub AI Studio • macOS Edition",
            font=("Arial", 10),
            text_color=TEXT_TERTIARY,
        ).pack(side="right")

        # ── Quản lý các widget Studio để hỗ trợ chuyển tab an toàn (Zero-Regression) ──
        self.settings_card = settings_card
        self.tracker_card = tracker_card
        self.log_card = log_card
        self.footer_card = footer_card
        self.credit_bar = credit_bar

        self._studio_widgets = [
            self.input_card,
            self.settings_card,
            self.tracker_card,
            self.log_card,
            self.footer_card,
            self.credit_bar,
        ]
        self._studio_grid_info = {w: w.grid_info() for w in self._studio_widgets}

        # Khởi tạo Landing Page Hướng Dẫn Sử Dụng
        self.guide_view = GuideView(
            self,
            on_start_clicked=lambda: self._switch_to_tab("🎬 Studio Làm Việc"),
        )
        self.guide_view.grid_remove()

        # Khởi tạo tính năng Kéo & Thả (Drag & Drop)
        self._setup_drag_and_drop()

    def _setup_drag_and_drop(self):
        """Đăng ký tính năng Kéo & Thả (Drag & Drop) video/media vào cửa sổ ứng dụng."""
        if not getattr(self, "_dnd_enabled", False) or DND_FILES is None:
            return

        widgets_to_register = [self]
        if hasattr(self, "input_card"):
            widgets_to_register.append(self.input_card)
        if hasattr(self, "tabview"):
            widgets_to_register.append(self.tabview)
        if hasattr(self, "file_entry"):
            widgets_to_register.append(self.file_entry)

        for w in widgets_to_register:
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                w.dnd_bind("<<DropLeave>>", self._on_drag_leave)
                w.dnd_bind("<<Drop>>", self._on_file_drop)
            except Exception:
                pass

    def _on_drag_enter(self, event=None):
        """Hiệu ứng thị giác viền xanh Apple Blue khi kéo tệp vào vùng giao diện."""
        if getattr(self, "_is_processing", False):
            return
        try:
            if hasattr(self, "input_card"):
                self.input_card.configure(border_color=APPLE_BLUE, border_width=2)
            if hasattr(self, "file_entry"):
                self.file_entry.configure(border_color=APPLE_BLUE, border_width=2)
        except Exception:
            pass

    def _on_drag_leave(self, event=None):
        """Khôi phục viền giao diện khi chuột rời khỏi vùng kéo thả."""
        try:
            if hasattr(self, "input_card"):
                self.input_card.configure(border_color=BORDER_CARD, border_width=1)
            if hasattr(self, "file_entry"):
                self.file_entry.configure(border_color=BORDER_INSET, border_width=1)
        except Exception:
            pass

    def _on_file_drop(self, event):
        """Xử lý sự kiện khi người dùng thả tệp vào ứng dụng."""
        self._on_drag_leave(event)

        if getattr(self, "_is_processing", False):
            self._log_msg("⚠️ Hệ thống đang bận xử lý tác vụ, vui lòng chờ hoàn thành trước khi nạp tệp mới.")
            return

        raw_data = getattr(event, "data", "")
        if not raw_data:
            return

        try:
            # Tcl list có thể chứa đường dẫn có dấu cách được bao bọc bởi {}
            files = list(self.tk.splitlist(raw_data))
        except Exception:
            files = [raw_data.strip("{}").strip()]

        if not files:
            return

        first_file = os.path.abspath(files[0].strip().strip('"\''))
        if not os.path.exists(first_file):
            self._log_msg(f"❌ Đường dẫn tệp không tồn tại: {first_file}")
            return

        if os.path.isdir(first_file):
            self._log_msg(f"⚠️ '{os.path.basename(first_file)}' là thư mục. Vui lòng kéo thả trực tiếp tệp video hoặc âm thanh.")
            return

        ext = Path(first_file).suffix.lower()

        # Nếu là file phụ đề .srt, hỗ trợ mở trực tiếp trình chỉnh sửa phụ đề
        if ext == ".srt":
            self._log_msg(f"📝 Đã nhận file phụ đề: {os.path.basename(first_file)}")
            try:
                SubtitleEditorDialog(self, first_file)
            except Exception as e:
                self._log_msg(f"❌ Không thể mở trình sửa phụ đề: {e}")
            return

        media_exts = {
            ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v",
            ".ts", ".m2ts", ".3gp", ".mp3", ".wav", ".m4a", ".flac", ".aac",
            ".ogg", ".opus", ".wma"
        }

        if ext not in media_exts:
            self._log_msg(f"⚠️ Tệp '{os.path.basename(first_file)}' có định dạng '{ext}' có thể không được hỗ trợ. Đã nạp đường dẫn để thử xử lý.")

        # Tự động chuyển về Tab Studio nếu đang ở Tab Hướng Dẫn
        if hasattr(self, "nav_tabs"):
            self._switch_to_tab("🎬 Studio Làm Việc")

        # Tự động chuyển về tab Chọn File nếu người dùng đang ở tab Link Online
        if hasattr(self, "tabview"):
            try:
                self.tabview.set("📂 Chọn File Video Trên Máy")
            except Exception:
                pass

        # Cập nhật đường dẫn file
        self.file_path_var.set(first_file)
        self._update_action_button()

        # Hiển thị thông báo nạp thành công
        try:
            size_mb = os.path.getsize(first_file) / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"
            self._log_msg(f"🎬 Đã nhận tệp kéo thả: {os.path.basename(first_file)} ({size_str})")
            if len(files) > 1:
                self._log_msg(f"ℹ️ Lưu ý: Đã nhận {len(files)} tệp kéo thả, đang chọn tệp đầu tiên: {os.path.basename(first_file)}")
        except Exception:
            self._log_msg(f"🎬 Đã nhận tệp kéo thả: {os.path.basename(first_file)}")

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
                from core.downloader import extract_universal_url
                clean_url = extract_universal_url(text)
                self.url_var.set(clean_url if clean_url else text)
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

    def _on_main_nav_changed(self, selected_tab: str):
        """Xử lý sự kiện khi người dùng nhấn chuyển Tab ở thanh điều hướng trên cùng."""
        self._switch_to_tab(selected_tab)

    def _switch_to_tab(self, tab_name: str):
        """Chuyển đổi giao diện giữa Studio Làm Việc và Hướng Dẫn Sử Dụng an toàn 100%."""
        if hasattr(self, "nav_tabs") and self.nav_tabs.get() != tab_name:
            self.nav_tabs.set(tab_name)

        if "Hướng Dẫn" in tab_name:
            # Ẩn toàn bộ widget của Studio
            for w in getattr(self, "_studio_widgets", []):
                try:
                    w.grid_remove()
                except Exception:
                    pass
            # Cấu hình grid row để GuideView chiếm trọn chiều cao
            self.grid_rowconfigure(4, weight=0)
            self.grid_rowconfigure(1, weight=1)
            # Hiển thị GuideView
            if hasattr(self, "guide_view"):
                self.guide_view.grid(row=1, column=0, rowspan=6, sticky="nsew", padx=20, pady=(0, 8))
        else:
            # Ẩn GuideView
            if hasattr(self, "guide_view"):
                try:
                    self.guide_view.grid_remove()
                except Exception:
                    pass
            # Khôi phục cấu hình grid row Studio (row 4 log_card nhận weight=1)
            self.grid_rowconfigure(1, weight=0)
            self.grid_rowconfigure(4, weight=1)
            # Khôi phục toàn bộ widget Studio về vị trí ban đầu
            for w in getattr(self, "_studio_widgets", []):
                try:
                    w.grid()
                except Exception:
                    if hasattr(self, "_studio_grid_info") and w in self._studio_grid_info:
                        w.grid(**self._studio_grid_info[w])

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
        elif mode_key == "download_and_separate":
            self.seg_url_mode.configure(
                selected_color=APPLE_PURPLE,
                selected_hover_color=APPLE_PURPLE_HOVER,
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
        if mode in ("download_audio", "download_and_separate"):
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
            elif mode == "download_and_separate":
                audio_fmt = self.config.get("audio_format", "mp3").upper()
                self.btn_start.configure(
                    text=f"🎤 TẢI & TÁCH NHẠC / LỜI ({audio_fmt})",
                    fg_color=APPLE_PURPLE,
                    hover_color=APPLE_PURPLE_HOVER,
                )
                if hasattr(self, "lbl_url_hint"):
                    self.lbl_url_hint.configure(
                        text="💡 Tải bài nhạc/video về máy và tự động dùng Demucs AI bóc tách giọng hát & beat karaoke riêng biệt.",
                        text_color="#D8B4FE",
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
            target_lang = getattr(self, "target_lang_var", None) and self.target_lang_var.get() or "vi"
            enable_tts = getattr(self, "enable_tts_var", None) and self.enable_tts_var.get()
            if enable_tts is None:
                enable_tts = True

            if target_lang == "en":
                btn_text = "🚀 TẠO SUB TIẾNG ANH"
            elif source_lang == "vi":
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
            elif mode == "download_and_separate":
                self._start_url_download_and_separate()
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
        """Khi thả dropdown Ngôn ngữ gốc."""
        val = self.source_lang_reverse_map.get(display_val, "auto")
        self.source_lang_var.set(val)
        target_lang = self.target_lang_var.get()
        # Việt gốc + Việt đích → tắt TTS mặc định; ngược lại bật
        if val == "vi" and target_lang == "vi":
            self.enable_tts_var.set(False)
            self.switch_tts.deselect()
        elif target_lang == "vi":
            self.enable_tts_var.set(True)
            self.switch_tts.select()
        self._update_step_labels()

    def _on_target_lang_change(self, display_val: str):
        """Khi thả dropdown Ngôn ngữ đích (Sub đầu ra)."""
        val = self.target_lang_reverse_map.get(display_val, "vi")
        self.target_lang_var.set(val)
        if val == "vi":
            # Mở khoá TTS, khôi phục theo source lang
            self.switch_tts.configure(state="normal")
            source = self.source_lang_var.get()
            if source != "vi":
                self.enable_tts_var.set(True)
                self.switch_tts.select()
        else:
            # Khoá TTS vì chưa hỗ trợ giọng nước ngoài
            self.enable_tts_var.set(False)
            self.switch_tts.deselect()
            self.switch_tts.configure(state="disabled")
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

    def _update_style_preview(self, preset: dict):
        """Cập nhật huy hiệu xem trước kiểu phụ đề."""
        if hasattr(self, "style_preview_pill") and hasattr(self, "lbl_style_preview_text"):
            self.style_preview_pill.configure(
                fg_color=preset.get("ui_bg", "#1E2028"),
                border_color=preset.get("ui_border", "#FFE600"),
            )
            self.lbl_style_preview_text.configure(
                text_color=preset.get("ui_fg", "#FFE600")
            )

    def _on_subtitle_style_change(self, display_name: str):
        preset = get_preset_by_name(display_name)
        self.config["subtitle_style_preset"] = preset["id"]
        save_config(self.config)
        self._update_style_preview(preset)
        self._log_msg(f"🎨 Đã chọn mẫu phụ đề: {preset['name']}")

    def _check_prerequisites_async(self):
        """Chạy trên background thread: kiểm tra FFmpeg và API Key rồi đẩy vào task_queue để cập nhật UI trên main thread."""
        try:
            ok, msg = check_ffmpeg()
            api_key = self.config.get("gemini_api_key", "")
            self.task_queue.put({
                "type": "prerequisites_result",
                "ffmpeg_ok": ok,
                "ffmpeg_msg": msg,
                "api_key": api_key,
            })
        except Exception as e:
            self.task_queue.put({
                "type": "prerequisites_result",
                "ffmpeg_ok": False,
                "ffmpeg_msg": str(e),
                "api_key": "",
            })

    def _apply_prerequisites_result(self, ffmpeg_ok: bool, ffmpeg_msg: str, api_key: str):
        """Áp dụng kết quả kiểm tra prerequisites lên UI (chạy trên main thread)."""
        if ffmpeg_ok:
            self.badge_ffmpeg.configure(
                text="⚡ FFmpeg: Sẵn sàng",
                fg_color=APPLE_GREEN_BG,
                hover_color=APPLE_GREEN_BG,
                text_color=APPLE_GREEN,
            )
            if api_key and self.file_path_var.get().strip():
                self.btn_start.configure(state="normal")
        else:
            self.badge_ffmpeg.configure(
                text="❌ FFmpeg: Thiếu (Bấm tải)",
                fg_color=APPLE_RED_BG,
                hover_color=APPLE_RED_BG,
                text_color=APPLE_RED,
            )
            self._log_msg(f"❌ {ffmpeg_msg}")
            self._log_msg("💡 Mẹo: Bấm vào huy hiệu '❌ FFmpeg: Thiếu (Bấm tải)' ở góc trên để tải tự động 1-click!")
            self.btn_start.configure(state="disabled")

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

    def _check_prerequisites(self):
        """Kiểm tra đồng bộ FFmpeg và API Key (được gọi từ callback sau khi lưu settings)."""
        ok, msg = check_ffmpeg()
        self._apply_prerequisites_result(ok, msg, self.config.get("gemini_api_key", "").strip())

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
        out_dir = get_output_dir(self.config)
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
            # Đồng bộ mẫu phụ đề CapCut
            new_preset_id = new_config.get("subtitle_style_preset", "capcut_yellow")
            if hasattr(self, "menu_subtitle_style"):
                preset_obj = get_preset_by_id(new_preset_id)
                self.menu_subtitle_style.set(preset_obj["name"])
                self._update_style_preview(preset_obj)
            if hasattr(self, "export_srt_var"):
                self.export_srt_var.set(new_config.get("export_srt", True))
            if hasattr(self, "export_txt_var"):
                self.export_txt_var.set(new_config.get("export_txt", True))
            if hasattr(self, "review_subtitles_var"):
                self.review_subtitles_var.set(new_config.get("review_subtitles", False))

        SettingsDialog(self, self.config, on_save)

    def _browse_file(self):
        filepath = ctk.filedialog.askopenfilename(
            filetypes=[
                ("Tệp video & âm thanh", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac *.aac"),
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"),
                ("Audio files", "*.mp3 *.wav *.m4a *.flac *.aac"),
                ("Tất cả tệp", "*.*"),
            ]
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
        if is_url and source:
            from core.downloader import extract_universal_url
            clean_url = extract_universal_url(source)
            if clean_url:
                source = clean_url
                self.url_var.set(clean_url)

        if not source:
            self._log_msg("❌ Lỗi: Vui lòng chọn file video hoặc dán link online.")
            return

        if not is_url and not os.path.exists(source):
            self._log_msg(f"❌ Lỗi: Không tìm thấy file nguồn hoặc đường dẫn không hợp lệ:\n   {source}")
            return

        # Khóa UI
        self._is_processing = True
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.menu_source_lang.configure(state="disabled")
            self.menu_target_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "menu_subtitle_style"):
                self.menu_subtitle_style.configure(state="disabled")
            if hasattr(self, "chk_review_sub"):
                self.chk_review_sub.configure(state="disabled")
            if hasattr(self, "chk_export_srt"):
                self.chk_export_srt.configure(state="disabled")
            if hasattr(self, "chk_export_txt"):
                self.chk_export_txt.configure(state="disabled")
            if hasattr(self, "btn_editor"):
                self.btn_editor.configure(state="disabled")
            if hasattr(self, "btn_extract_audio"):
                self.btn_extract_audio.configure(state="disabled")
            if hasattr(self, "btn_separate_audio"):
                self.btn_separate_audio.configure(state="disabled")
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
            self.config["target_language"] = self.target_lang_var.get()
            self.config["enable_tts"] = self.enable_tts_var.get()
            self.config["download_quality"] = self.reverse_quality_map.get(self.download_quality_var.get(), "best")
            self.config["export_srt"] = self.export_srt_var.get()
            self.config["export_txt"] = self.export_txt_var.get()
            self.config["review_subtitles"] = self.review_subtitles_var.get()
            save_config(self.config)

            # Chạy pipeline trên thread riêng (lazy-import để tăng tốc khởi động ứng dụng)
            from core.pipeline import Pipeline
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
        if url:
            from core.downloader import extract_universal_url
            clean_url = extract_universal_url(url)
            if clean_url:
                url = clean_url
                self.url_var.set(clean_url)

        if not url:
            self._log_msg("❌ Lỗi: Vui lòng dán link video (Douyin, TikTok, Facebook, YouTube...) vào ô nhập.")
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
            self.menu_source_lang.configure(state="disabled")
            self.menu_target_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "menu_subtitle_style"):
                self.menu_subtitle_style.configure(state="disabled")
            if hasattr(self, "chk_export_srt"):
                self.chk_export_srt.configure(state="disabled")
            if hasattr(self, "chk_export_txt"):
                self.chk_export_txt.configure(state="disabled")
            if hasattr(self, "btn_extract_audio"):
                self.btn_extract_audio.configure(state="disabled")
            if hasattr(self, "btn_separate_audio"):
                self.btn_separate_audio.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang kết nối tới máy chủ video...")
        self._set_active_step(1)

        out_dir = get_output_dir(self.config)
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
                import traceback
                try:
                    (Path.home() / ".vietsub_ai" / "last_download_error.log").write_text(traceback.format_exc(), encoding="utf-8")
                except Exception:
                    pass
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi tải video: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_dl, daemon=True).start()

    def _start_audio_download(self):
        """Tải riêng file âm thanh/nhạc từ link online (Douyin, YouTube, TikTok, Facebook, SoundCloud, Artlist...)."""
        url = self.url_var.get().strip()
        if url:
            from core.downloader import extract_universal_url
            clean_url = extract_universal_url(url)
            if clean_url:
                url = clean_url
                self.url_var.set(clean_url)

        if not url:
            self._log_msg("❌ Lỗi: Vui lòng dán link video hoặc link bài nhạc (Douyin, TikTok, YouTube...) vào ô nhập.")
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
            self.menu_source_lang.configure(state="disabled")
            self.menu_target_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "menu_subtitle_style"):
                self.menu_subtitle_style.configure(state="disabled")
            if hasattr(self, "chk_export_srt"):
                self.chk_export_srt.configure(state="disabled")
            if hasattr(self, "chk_export_txt"):
                self.chk_export_txt.configure(state="disabled")
            if hasattr(self, "btn_extract_audio"):
                self.btn_extract_audio.configure(state="disabled")
            if hasattr(self, "btn_separate_audio"):
                self.btn_separate_audio.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang kết nối tải bài nhạc...")
        self._set_active_step(1)

        out_dir = get_output_dir(self.config)
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
                import traceback
                try:
                    (Path.home() / ".vietsub_ai" / "last_download_error.log").write_text(traceback.format_exc(), encoding="utf-8")
                except Exception:
                    pass
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi tải nhạc: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_audio_dl, daemon=True).start()

    def _on_separate_audio_clicked(self):
        """Mở hộp thoại tùy chọn tách giọng hát (Vocal) và nhạc nền (Beat Karaoke)."""
        video_path = self.file_path_var.get().strip()
        if not video_path or not os.path.exists(video_path):
            self._log_msg("❌ Lỗi: Vui lòng chọn một file video hoặc bài nhạc ở Tab 1 trước khi bấm tách.")
            return

        from core.audio_separator import check_demucs_installed
        ok, msg = check_demucs_installed()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        AudioSeparatorDialog(
            self,
            input_file=video_path,
            on_start=self._start_audio_separation,
        )

    def _start_audio_separation(self, mode: str, audio_format: str, bitrate: str):
        """Bắt đầu tiến trình tách giọng hát và nhạc beat bằng Demucs AI."""
        video_path = self.file_path_var.get().strip()
        if not video_path or not os.path.exists(video_path):
            self._log_msg("❌ Lỗi: Không tìm thấy file nguồn.")
            return

        self._is_processing = True
        self._audio_sep_cancel_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        if hasattr(self, "btn_extract_audio"):
            self.btn_extract_audio.configure(state="disabled")
        if hasattr(self, "btn_separate_audio"):
            self.btn_separate_audio.configure(state="disabled")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.menu_source_lang.configure(state="disabled")
            self.menu_target_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "menu_subtitle_style"):
                self.menu_subtitle_style.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.05)
        self.pct_badge.configure(text="5%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang khởi tạo mô hình AI tách âm thanh...")
        self._set_active_step(1)

        out_dir = get_output_dir(self.config)
        mode_label = "Lời riêng & Nhạc Beat riêng" if mode == "both" else ("Chỉ lấy Nhạc Beat (Karaoke)" if mode == "instrumental" else "Chỉ lấy Giọng hát (Acapella)")
        self._log_msg(f"🎤 Bắt đầu tách âm thanh bằng AI Demucs v4:")
        self._log_msg(f"   📁 Tệp nguồn: {video_path}")
        self._log_msg(f"   🎯 Chế độ: {mode_label}")
        self._log_msg(f"   🎵 Định dạng: {audio_format.upper()} ({bitrate})")
        self._log_msg(f"   📂 Thư mục lưu: {out_dir}")

        def run_separate():
            try:
                def on_prog(pct, label):
                    self.task_queue.put({"type": "progress", "value": pct, "label": label})

                from core.audio_separator import separate_audio_stems
                results = separate_audio_stems(
                    input_path=video_path,
                    output_dir=out_dir,
                    mode=mode,
                    audio_format=audio_format,
                    bitrate=bitrate,
                    progress_callback=on_prog,
                    cancel_event=self._audio_sep_cancel_event,
                )
                self.task_queue.put({
                    "type": "audio_separate_success",
                    "results": results,
                    "mode": mode,
                    "out_dir": out_dir,
                })
            except Exception as e:
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi tách âm thanh: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_separate, daemon=True).start()

    def _start_url_download_and_separate(self):
        """Tải bài nhạc/video từ link online rồi tự động chạy Demucs AI để tách lời và beat."""
        url = self.url_var.get().strip()
        if url:
            from core.downloader import extract_universal_url
            clean_url = extract_universal_url(url)
            if clean_url:
                url = clean_url
                self.url_var.set(clean_url)

        if not url:
            self._log_msg("❌ Lỗi: Vui lòng dán link video hoặc bài nhạc (Douyin, YouTube, TikTok...) vào ô nhập.")
            return

        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        from core.audio_separator import check_demucs_installed
        ok_demucs, msg_demucs = check_demucs_installed()
        if not ok_demucs:
            self._log_msg(f"❌ {msg_demucs}")
            return

        self._is_processing = True
        self._download_cancelled = False
        self._audio_sep_cancel_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        if hasattr(self, "btn_extract_audio"):
            self.btn_extract_audio.configure(state="disabled")
        if hasattr(self, "btn_separate_audio"):
            self.btn_separate_audio.configure(state="disabled")
        try:
            self.tabview.configure(state="disabled")
            self.seg_url_mode.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.menu_source_lang.configure(state="disabled")
            self.menu_target_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
            if hasattr(self, "menu_subtitle_style"):
                self.menu_subtitle_style.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self._start_timer()
        self.status_label.configure(text="⏳ Đang kết nối tải bài nhạc...")
        self._set_active_step(1)

        out_dir = get_output_dir(self.config)
        audio_fmt = self.config.get("audio_format", "mp3")
        bitrate = self.config.get("audio_bitrate", "320k")
        self._log_msg(f"🎤 Bắt đầu quy trình Tải & Tách Nhạc/Lời từ:\n   {url}")
        self._log_msg(f"📁 Thư mục lưu: {out_dir}")

        def run_url_dl_and_separate():
            from core.downloader import VideoDownloader
            try:
                def on_dl_prog(pct, label):
                    mapped = pct * 0.30
                    self.task_queue.put({"type": "progress", "value": mapped, "label": f"[1/2] {label}"})

                dl = VideoDownloader(
                    progress_callback=on_dl_prog,
                    is_cancelled=lambda: self._download_cancelled,
                )
                dl_file = dl.download_audio(url, out_dir, audio_format="wav")

                if self._download_cancelled or self._audio_sep_cancel_event.is_set():
                    raise InterruptedError("Người dùng đã hủy tác vụ.")

                def on_sep_prog(pct, label):
                    mapped = 0.30 + pct * 0.70
                    self.task_queue.put({"type": "progress", "value": mapped, "label": f"[2/2] {label}"})

                from core.audio_separator import separate_audio_stems
                results = separate_audio_stems(
                    input_path=dl_file,
                    output_dir=out_dir,
                    mode="both",
                    audio_format=audio_fmt,
                    bitrate=bitrate,
                    progress_callback=on_sep_prog,
                    cancel_event=self._audio_sep_cancel_event,
                )

                if audio_fmt != "wav" and os.path.exists(dl_file):
                    try:
                        os.remove(dl_file)
                    except Exception:
                        pass

                self.task_queue.put({
                    "type": "audio_separate_success",
                    "results": results,
                    "mode": "both",
                    "out_dir": out_dir,
                })
            except (InterruptedError, KeyboardInterrupt):
                self.task_queue.put({"type": "log", "message": "⚠️ Tiến trình tải và tách nhạc đã bị hủy."})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Đã hủy"})
            except Exception as e:
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi trong quá trình xử lý: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_url_dl_and_separate, daemon=True).start()

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
        self._download_cancelled = False
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        if hasattr(self, "btn_extract_audio"):
            self.btn_extract_audio.configure(state="disabled")
        if hasattr(self, "btn_separate_audio"):
            self.btn_separate_audio.configure(state="disabled")
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

        out_dir = get_output_dir(self.config)
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
                    is_cancelled=lambda: self._download_cancelled,
                )
                self.task_queue.put({"type": "audio_extract_success", "file_path": out_audio})
            except (InterruptedError, KeyboardInterrupt):
                self.task_queue.put({"type": "log", "message": "⚠️ Tiến trình trích xuất âm thanh đã bị hủy."})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Đã hủy"})
            except Exception as e:
                self.task_queue.put({"type": "log", "message": f"❌ Lỗi khi trích xuất âm thanh: {e}"})
                self.task_queue.put({"type": "progress", "value": 0.0, "label": "Thất bại"})
            finally:
                self.task_queue.put({"type": "download_done"})

        threading.Thread(target=run_extract, daemon=True).start()

    def _cancel(self):
        if self._is_processing:
            self._download_cancelled = True
            if hasattr(self, "_audio_sep_cancel_event"):
                self._audio_sep_cancel_event.set()
            self._stop_timer(success=False)
            if self.pipeline:
                self.pipeline.cancel()
            self.status_label.configure(text="⚠️ Đang hủy tiến trình...")
            self._log_msg("⚠️ Đã gửi yêu cầu dừng tiến trình ngay lập tức...")
            self.btn_cancel.configure(state="disabled")

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

                elif msg_type == "prerequisites_result":
                    self._apply_prerequisites_result(
                        ffmpeg_ok=msg.get("ffmpeg_ok", False),
                        ffmpeg_msg=msg.get("ffmpeg_msg", ""),
                        api_key=msg.get("api_key", ""),
                    )

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
                    # Hiện popup hoàn tất
                    video_path = msg.get("video_path", "")
                    srt_path   = msg.get("srt_path", None)
                    txt_path   = msg.get("txt_path", None)
                    self.after(
                        300,
                        lambda vp=video_path, sp=srt_path, tp=txt_path: CompletionDialog(
                            self,
                            video_path=vp,
                            srt_path=sp,
                            txt_path=tp,
                            elapsed_str=self._last_elapsed_str,
                            on_new_video=self._reset_for_new_video,
                        ),
                    )

                elif msg_type == "download_success":
                    fp = msg["file_path"]
                    fn = Path(fp).name
                    sz = _fmt_size(fp)
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

                    # Hiển thị Popup hoàn tất cho video gốc
                    self.after(
                        300,
                        lambda p=fp, n=fn, s=sz: CompletionDialog(
                            self,
                            video_path=p,
                            title_text="TẢI VIDEO GỐC THÀNH CÔNG!",
                            subtitle_text="Video gốc chất lượng cao nhất đã được tải về và lưu an toàn.",
                            custom_rows=[
                                ("🎬", "File video gốc:", f"{n}  ({s})", TEXT_PRIMARY),
                                ("📁", "Thư mục lưu:", str(Path(p).parent), TEXT_SECONDARY),
                                ("⏱️", "Thời gian tải:", self._last_elapsed_str or "Hoàn tất", APPLE_GREEN),
                            ],
                            elapsed_str=self._last_elapsed_str or "00:00",
                            on_new_video=self._reset_for_new_video,
                        ),
                    )

                elif msg_type in ("audio_download_success", "audio_extract_success"):
                    fp = msg["file_path"]
                    fn = Path(fp).name
                    sz = _fmt_size(fp)
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

                    # Hiển thị Popup hoàn tất cho audio
                    self.after(
                        300,
                        lambda p=fp, n=fn, s=sz, t=title: CompletionDialog(
                            self,
                            video_path=p,
                            title_text=f"{t} THÀNH CÔNG!",
                            subtitle_text="File âm thanh chất lượng cao đã sẵn sàng để sử dụng.",
                            custom_rows=[
                                ("🎵", "File âm thanh:", f"{n}  ({s})", APPLE_PURPLE),
                                ("📁", "Thư mục lưu:", str(Path(p).parent), TEXT_SECONDARY),
                                ("⏱️", "Thời gian tải:", self._last_elapsed_str or "Hoàn tất", APPLE_GREEN),
                            ],
                            elapsed_str=self._last_elapsed_str or "00:00",
                            on_new_video=self._reset_for_new_video,
                        ),
                    )

                elif msg_type == "audio_separate_success":
                    results = msg.get("results", {})
                    out_dir = msg.get("out_dir", "")
                    mode = msg.get("mode", "both")
                    self._log_msg("\n" + "─" * 48)
                    self._log_msg("🎉 TÁCH LỜI VÀ NHẠC BEAT THÀNH CÔNG!")
                    custom_rows = []
                    primary_file = ""

                    if "vocals" in results and os.path.exists(results["vocals"]):
                        v_path = results["vocals"]
                        fn = Path(v_path).name
                        sz = _fmt_size(v_path)
                        self._log_msg(f"   🎤 Lời ca sĩ (Vocal): {fn} ({sz})")
                        custom_rows.append(("🎤", "Lời ca sĩ:", f"{fn}  ({sz})", APPLE_PURPLE))
                        primary_file = v_path

                    if "instrumental" in results and os.path.exists(results["instrumental"]):
                        i_path = results["instrumental"]
                        fn = Path(i_path).name
                        sz = _fmt_size(i_path)
                        self._log_msg(f"   🎸 Nhạc beat (Karaoke): {fn} ({sz})")
                        custom_rows.append(("🎸", "Nhạc Beat:", f"{fn}  ({sz})", APPLE_GREEN))
                        if not primary_file:
                            primary_file = i_path

                    self._log_msg(f"   📁 Lưu tại: {out_dir}")
                    custom_rows.append(("📁", "Lưu tại:", out_dir, TEXT_SECONDARY))
                    custom_rows.append(("⏱️", "Thời gian:", self._last_elapsed_str or "Hoàn tất", APPLE_GREEN))

                    self._log_msg("✨ File âm thanh chất lượng cao đã sẵn sàng để sử dụng!")
                    self.progress_bar.set(1.0)
                    self.pct_badge.configure(text="100%")
                    self.status_label.configure(text="✨ Tách lời và nhạc hoàn tất xuất sắc!")

                    # Hiển thị CompletionDialog
                    self.after(
                        300,
                        lambda pf=primary_file, cr=custom_rows: CompletionDialog(
                            self,
                            video_path=pf,
                            title_text="TÁCH LỜI & NHẠC THÀNH CÔNG!",
                            subtitle_text="Đã bóc tách giọng ca sĩ và nhạc beat karaoke an toàn.",
                            custom_rows=cr,
                            elapsed_str=self._last_elapsed_str,
                            on_new_video=self._reset_for_new_video,
                        ),
                    )

                elif msg_type == "download_done" or msg_type == "done":
                    self._is_processing = False
                    elapsed_str = self._stop_timer(success=True)
                    self._last_elapsed_str = elapsed_str  # Lưu lại để popup hoàn tất dùng
                    self._log_msg(f"⏱️ Tổng thời gian thực hiện: {elapsed_str}")
                    self.btn_start.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    try:
                        self.tabview.configure(state="normal")
                        self.seg_url_mode.configure(state="normal")
                        self.quality_menu.configure(state="normal")
                        self.menu_source_lang.configure(state="normal")
                        self.menu_target_lang.configure(state="normal")
                        # Giữ TTS disabled nếu target vẫn là ngôn ngữ không phải Tiếng Việt
                        if getattr(self, "target_lang_var", None) and self.target_lang_var.get() != "vi":
                            self.switch_tts.configure(state="disabled")
                        else:
                            self.switch_tts.configure(state="normal")
                        self.font_slider_main.configure(state="normal")
                        if hasattr(self, "menu_subtitle_style"):
                            self.menu_subtitle_style.configure(state="normal")
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
                        if hasattr(self, "btn_separate_audio"):
                            self.btn_separate_audio.configure(state="normal")
                    except Exception:
                        pass
                    self.pipeline = None

        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error in _process_queue: {e}")
        finally:
            self.after(100, self._process_queue)

    # ─────────────────────────────────────────────────────────────────────────
    # RESET UI CHO VIDEO MỚI
    # ─────────────────────────────────────────────────────────────────────────

    def _reset_for_new_video(self):
        """Đặt lại giao diện để người dùng sẵn sàng xử lý video tiếp theo.
        Được gọi từ nút '✨ Làm Video Tiếp Theo' trong CompletionDialog.
        """
        try:
            # Xoá ô nhập URL / link
            if hasattr(self, "url_entry"):
                self.url_entry.delete(0, "end")
            # Xoá ô nhập file path
            if hasattr(self, "file_path_var"):
                self.file_path_var.set("")
            # Xoá log
            self.log_box.delete("1.0", "end")
            # Reset thanh tiến trình
            self.progress_bar.set(0.0)
            self.pct_badge.configure(text="0%")
            self.status_label.configure(text="Sẵn sàng xử lý video mới...")
            # Reset pipeline step tracker
            self._reset_steps()
            # Reset timer badge
            if hasattr(self, "timer_badge"):
                self.timer_badge.configure(text="⏱️ 00:00", text_color="#98989F")
            self._last_elapsed_str = "00:00"
            # Chuyển về Tab đầu tiên (Chọn File) nếu đang ở tab khác
            try:
                self.tabview.set("📂 Chọn File Video Trên Máy")
            except Exception:
                pass
        except Exception as e:
            print(f"[_reset_for_new_video] {e}")
