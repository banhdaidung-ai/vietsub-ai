"""
gui/app_window.py — Giao diện chính nâng cấp của ứng dụng Vietsub AI
Hiện đại, trực quan, chuyên nghiệp với Pipeline Step Tracker và Studio Terminal
"""

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from core.pipeline import Pipeline
from gui.ffmpeg_download_dialog import FFmpegDownloadDialog
from gui.settings_dialog import SettingsDialog
from utils.config import load_config, save_config
from utils.ffmpeg_check import check_ffmpeg, get_ffmpeg_path

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Vietsub AI — Dịch & Lồng Tiếng Video Chuyên Nghiệp")
        self.geometry("900x740")
        self.minsize(840, 680)

        self.config = load_config()
        self.task_queue = queue.Queue()
        self.pipeline: Optional[Pipeline] = None
        self._is_processing = False
        self._download_cancelled = False
        self._current_step = 0

        self._set_app_icon()
        self._build_ui()
        self._check_prerequisites()
        self._update_step_labels()

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
        # 1. HEADER BAR
        # ═════════════════════════════════════════════════════════
        header_card = ctk.CTkFrame(self, fg_color="transparent")
        header_card.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        header_card.grid_columnconfigure(1, weight=1)

        # Left: Brand Logo & Title
        brand_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        brand_frame.grid(row=0, column=0, sticky="w")

        # Load Icon
        try:
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                logo_path = Path(sys._MEIPASS) / "assets" / "icon.png"
            else:
                logo_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
            if logo_path.exists():
                logo_img = ctk.CTkImage(Image.open(logo_path), size=(38, 38))
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
            font=("Arial", 22, "bold"),
            text_color="#F8FAFC",
        ).pack(side="left")

        ctk.CTkLabel(
            title_row,
            text="PRO",
            font=("Arial", 10, "bold"),
            fg_color="#4F46E5",
            text_color="#FFFFFF",
            corner_radius=4,
            width=38,
            height=18,
        ).pack(side="left", padx=8)

        ctk.CTkLabel(
            title_inner,
            text="Tự động dịch, lồng tiếng & ghép phụ đề chuẩn xác bằng Gemini AI",
            font=("Arial", 11),
            text_color="#94A3B8",
        ).pack(anchor="w")

        # Right: System Health Badges & Controls
        controls_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        controls_frame.grid(row=0, column=2, sticky="e")

        # Status Badges
        self.badge_ffmpeg = ctk.CTkButton(
            controls_frame,
            text="⚡ FFmpeg: Đang kiểm tra",
            font=("Arial", 11, "bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            text_color="#94A3B8",
            corner_radius=6,
            height=26,
            command=self._on_ffmpeg_badge_click,
        )
        self.badge_ffmpeg.pack(side="left", padx=4)

        self.badge_api = ctk.CTkLabel(
            controls_frame,
            text="🔑 Gemini: Đang kiểm tra",
            font=("Arial", 11, "bold"),
            fg_color="#1E293B",
            text_color="#94A3B8",
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.badge_api.pack(side="left", padx=4)

        # Theme toggle button
        self.btn_theme = ctk.CTkButton(
            controls_frame,
            text="🌓",
            width=36,
            height=32,
            corner_radius=8,
            fg_color="#1E293B",
            hover_color="#334155",
            command=self._toggle_theme,
        )
        self.btn_theme.pack(side="left", padx=4)

        # Settings button
        ctk.CTkButton(
            controls_frame,
            text="⚙️ Cài đặt",
            font=("Arial", 12, "bold"),
            width=90,
            height=32,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=self._open_settings,
        ).pack(side="left", padx=(4, 0))

        # ═════════════════════════════════════════════════════════
        # 2. INPUT SECTION (CARD VIEW)
        # ═════════════════════════════════════════════════════════
        input_card = ctk.CTkFrame(self, corner_radius=14, border_width=1, border_color="#334155")
        input_card.grid(row=1, column=0, sticky="ew", padx=24, pady=6)

        self.tabview = ctk.CTkTabview(
            input_card,
            height=150,
            corner_radius=10,
            segmented_button_selected_color="#4F46E5",
            segmented_button_selected_hover_color="#4338CA",
        )
        self.tabview.pack(fill="x", padx=12, pady=(6, 12))

        tab_file = self.tabview.add("📂 Chọn File Video Trên Máy")
        tab_url = self.tabview.add("🌐 Dán Link Online (TikTok, YouTube, Facebook...)")

        # ── Tab 1: File Video ──
        self.file_path_var = ctk.StringVar()
        file_box = ctk.CTkFrame(tab_file, fg_color="transparent")
        file_box.pack(fill="x", pady=10)

        self.file_entry = ctk.CTkEntry(
            file_box,
            textvariable=self.file_path_var,
            placeholder_text="Chưa có file nào được chọn... Bấm nút bên cạnh để duyệt file video",
            state="readonly",
            height=38,
            corner_radius=8,
            font=("Consolas", 12),
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            file_box,
            text="📂 Chọn Video...",
            font=("Arial", 12, "bold"),
            width=130,
            height=38,
            corner_radius=8,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            command=self._browse_file,
        ).pack(side="right")

        ctk.CTkLabel(
            tab_file,
            text="💡 Hỗ trợ các định dạng phổ biến: MP4, MKV, MOV, AVI, WEBM (Tốc độ đọc và dịch tức thì)",
            font=("Arial", 11),
            text_color="#94A3B8",
        ).pack(anchor="w")

        # ── Tab 2: URL Online ──
        self.url_var = ctk.StringVar()
        url_input_box = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_input_box.pack(fill="x", pady=(8, 6))

        self.url_entry = ctk.CTkEntry(
            url_input_box,
            textvariable=self.url_var,
            placeholder_text="Dán đường link TikTok, Facebook Reels, YouTube Shorts, Bilibili vào đây...",
            height=38,
            corner_radius=8,
            font=("Consolas", 12),
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            url_input_box,
            text="📋 Dán",
            width=65,
            height=38,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=self._paste_clipboard,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            url_input_box,
            text="✖",
            width=38,
            height=38,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: self.url_var.set(""),
        ).pack(side="right")

        url_bottom_bar = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_bottom_bar.pack(fill="x", pady=(2, 4))

        self.btn_download_only = ctk.CTkButton(
            url_bottom_bar,
            text="⬇️ TẢI VIDEO GỐC VỀ MÁY",
            fg_color="#059669",
            hover_color="#047857",
            font=("Arial", 12, "bold"),
            height=32,
            corner_radius=8,
            command=self._start_download_only,
        )
        self.btn_download_only.pack(side="left", padx=(0, 12))

        # Platform badges
        ctk.CTkLabel(
            url_bottom_bar,
            text="Hỗ trợ: 🎵 TikTok  •  📺 YouTube  •  📘 Facebook  •  ⚡ Bilibili",
            font=("Arial", 11),
            text_color="#94A3B8",
        ).pack(side="left")

        # ── Thanh Tùy Chọn: Ngôn ngữ nguồn, Cỡ chữ & Lồng tiếng AI ──
        options_bar = ctk.CTkFrame(input_card, fg_color="#1E293B", corner_radius=10, border_width=1, border_color="#334155")
        options_bar.pack(fill="x", padx=12, pady=(0, 10))

        # 1. Trái: Chọn ngôn ngữ nguồn
        lang_box = ctk.CTkFrame(options_bar, fg_color="transparent")
        lang_box.pack(side="left", padx=12, pady=8)

        ctk.CTkLabel(
            lang_box,
            text="🌐 Ngôn ngữ:",
            font=("Arial", 12, "bold"),
            text_color="#F8FAFC",
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
            height=32,
            corner_radius=8,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
        )
        self.seg_lang.set(self.lang_display_map.get(current_lang, "🇨🇳 Tiếng Trung"))
        self.seg_lang.pack(side="left")

        # 2. Giữa: Thanh trượt cỡ chữ phụ đề (Trực quan ngay trên màn hình chính)
        font_box = ctk.CTkFrame(options_bar, fg_color="transparent")
        font_box.pack(side="left", padx=(16, 12), pady=8)

        ctk.CTkLabel(
            font_box,
            text="📝 Cỡ chữ sub:",
            font=("Arial", 12, "bold"),
            text_color="#F8FAFC",
        ).pack(side="left", padx=(0, 6))

        current_font_size = self.config.get("subtitle_font_size", 10)
        self.font_slider_main = ctk.CTkSlider(
            font_box,
            from_=8,
            to=24,
            number_of_steps=16,
            width=110,
            command=self._on_main_font_slide,
            progress_color="#6366F1",
            button_color="#818CF8",
        )
        self.font_slider_main.set(current_font_size)
        self.font_slider_main.pack(side="left", padx=(0, 6))

        self.lbl_font_main = ctk.CTkLabel(
            font_box,
            text=f"{int(current_font_size)} pt",
            font=("Consolas", 12, "bold"),
            text_color="#38BDF8",
            width=42,
        )
        self.lbl_font_main.pack(side="left")

        # 3. Phải: Switch Lồng tiếng AI (TTS)
        tts_box = ctk.CTkFrame(options_bar, fg_color="transparent")
        tts_box.pack(side="right", padx=12, pady=8)

        current_enable_tts = self.config.get("enable_tts", True if current_lang != "vi" else False)
        self.enable_tts_var = ctk.BooleanVar(value=current_enable_tts)

        self.switch_tts = ctk.CTkSwitch(
            tts_box,
            text="🎙️ Lồng tiếng AI",
            font=("Arial", 12, "bold"),
            text_color="#F8FAFC",
            progress_color="#10B981",
            command=self._on_tts_toggle,
            variable=self.enable_tts_var,
        )
        self.switch_tts.pack(side="right")

        # ═════════════════════════════════════════════════════════
        # 3. PIPELINE STAGE TRACKER (4 BƯỚC XỬ LÝ)
        # ═════════════════════════════════════════════════════════
        tracker_card = ctk.CTkFrame(self, corner_radius=12, fg_color="#1E293B", border_width=1, border_color="#334155")
        tracker_card.grid(row=2, column=0, sticky="ew", padx=24, pady=6)
        tracker_card.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.steps = []
        step_definitions = [
            ("1", "📥 Tải Video"),
            ("2", "🤖 AI Dịch Thuật"),
            ("3", "🎙️ TTS Lồng Tiếng"),
            ("4", "🎬 Ghép Sub & Xuất"),
        ]

        for i, (num, name) in enumerate(step_definitions):
            step_box = ctk.CTkFrame(tracker_card, fg_color="transparent")
            step_box.grid(row=0, column=i, padx=8, pady=8, sticky="ew")

            pill = ctk.CTkLabel(
                step_box,
                text=name,
                font=("Arial", 11, "bold"),
                fg_color="#0F172A",
                text_color="#64748B",
                corner_radius=8,
                height=30,
            )
            pill.pack(fill="x")
            self.steps.append(pill)

        # ═════════════════════════════════════════════════════════
        # 4. TERMINAL & LOG CONSOLE CARD
        # ═════════════════════════════════════════════════════════
        log_card = ctk.CTkFrame(self, corner_radius=14, border_width=1, border_color="#334155")
        log_card.grid(row=3, column=0, sticky="nsew", padx=24, pady=6)
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        # Terminal Header
        term_header = ctk.CTkFrame(log_card, fg_color="transparent")
        term_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))

        ctk.CTkLabel(
            term_header,
            text="📋 Nhật Ký Xử Lý (Studio Terminal)",
            font=("Arial", 13, "bold"),
            text_color="#F8FAFC",
        ).pack(side="left")

        self.pct_badge = ctk.CTkLabel(
            term_header,
            text="0%",
            font=("Consolas", 11, "bold"),
            fg_color="#1E293B",
            text_color="#38BDF8",
            corner_radius=6,
            width=48,
            height=22,
        )
        self.pct_badge.pack(side="left", padx=10)

        ctk.CTkButton(
            term_header,
            text="🗑️ Xóa Log",
            font=("Arial", 11),
            width=70,
            height=24,
            corner_radius=6,
            fg_color="#334155",
            hover_color="#475569",
            command=self._clear_logs,
        ).pack(side="right")

        # Terminal Content Box
        self.log_box = ctk.CTkTextbox(
            log_card,
            font=("Consolas", 12),
            fg_color="#090D16",
            text_color="#E2E8F0",
            corner_radius=8,
            border_width=1,
            border_color="#1E293B",
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            log_card,
            height=8,
            corner_radius=4,
            progress_color="#6366F1",
            fg_color="#1E293B",
        )
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.progress_bar.set(0.0)

        # ═════════════════════════════════════════════════════════
        # 5. BOTTOM ACTION FOOTER
        # ═════════════════════════════════════════════════════════
        footer_card = ctk.CTkFrame(self, fg_color="transparent")
        footer_card.grid(row=4, column=0, sticky="ew", padx=24, pady=(6, 16))
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
            width=140,
            height=40,
            corner_radius=8,
            fg_color="#1E293B",
            hover_color="#334155",
            font=("Arial", 12, "bold"),
            command=self._open_output_dir,
        )
        self.btn_open_folder.pack(side="left", padx=(0, 10))

        self.btn_cancel = ctk.CTkButton(
            btn_group,
            text="⏹ Hủy",
            width=80,
            height=40,
            corner_radius=8,
            fg_color="#991B1B",
            hover_color="#7F1D1D",
            state="disabled",
            font=("Arial", 12, "bold"),
            command=self._cancel,
        )
        self.btn_cancel.pack(side="left", padx=(0, 10))

        self.btn_start = ctk.CTkButton(
            btn_group,
            text="🚀 BẮT ĐẦU DỊCH",
            width=160,
            height=40,
            corner_radius=8,
            font=("Arial", 13, "bold"),
            fg_color="#4F46E5",
            hover_color="#4338CA",
            command=self._start,
        )
        self.btn_start.pack(side="left")

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

    def _set_active_step(self, step_idx: int):
        """Cập nhật giao diện 4 bước của Pipeline: 0=None, 1=Tải, 2=Dịch, 3=TTS, 4=Render"""
        self._current_step = step_idx
        for i, pill in enumerate(self.steps, start=1):
            if i < step_idx:
                # Đã hoàn thành bước trước
                pill.configure(fg_color="#064E3B", text_color="#34D399")
            elif i == step_idx:
                # Đang xử lý bước hiện tại
                pill.configure(fg_color="#4F46E5", text_color="#FFFFFF")
            else:
                # Chưa đến lượt
                pill.configure(fg_color="#0F172A", text_color="#64748B")

    def _reset_steps(self):
        self._set_active_step(0)

    def _update_step_labels(self):
        source_lang = getattr(self, "source_lang_var", None) and self.source_lang_var.get() or "zh"
        enable_tts = getattr(self, "enable_tts_var", None) and self.enable_tts_var.get()
        if enable_tts is None:
            enable_tts = True

        if source_lang == "vi":
            self.steps[1].configure(text="🤖 AI Phiên Âm")
            if not enable_tts:
                self.steps[2].configure(text="📝 Xuất Phụ Đề")
                self.btn_start.configure(text="🚀 TẠO PHỤ ĐỀ VIỆT")
            else:
                self.steps[2].configure(text="🎙️ TTS Lồng Tiếng")
                self.btn_start.configure(text="🚀 TẠO SUB & LỒNG TIẾNG")
        else:
            self.steps[1].configure(text="🤖 AI Dịch Thuật")
            if not enable_tts:
                self.steps[2].configure(text="📝 Xuất Phụ Đề")
                self.btn_start.configure(text="🚀 DỊCH & GHÉP SUB")
            else:
                self.steps[2].configure(text="🎙️ TTS Lồng Tiếng")
                self.btn_start.configure(text="🚀 BẮT ĐẦU DỊCH")

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
                fg_color="#064E3B",
                hover_color="#047857",
                text_color="#34D399",
            )
        else:
            self.badge_ffmpeg.configure(
                text="❌ FFmpeg: Thiếu (Bấm tải)",
                fg_color="#7F1D1D",
                hover_color="#991B1B",
                text_color="#FCA5A5",
            )
            self._log_msg(f"❌ {msg}")
            self._log_msg("💡 Mẹo: Bấm vào huy hiệu '❌ FFmpeg: Thiếu (Bấm tải)' ở góc trên để tải tự động 1-click!")
            self.btn_start.configure(state="disabled")

        api_key = self.config.get("gemini_api_key", "").strip()
        if api_key:
            self.badge_api.configure(
                text="🔑 Gemini: Đã kết nối", fg_color="#064E3B", text_color="#34D399"
            )
        else:
            self.badge_api.configure(
                text="⚠️ Gemini: Chưa có Key", fg_color="#78350F", text_color="#FCD34D"
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
        self.btn_download_only.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
            self.seg_lang.configure(state="disabled")
            self.switch_tts.configure(state="disabled")
            self.font_slider_main.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self.status_label.configure(text="⏳ Đang khởi động quy trình...")
        self._set_active_step(1 if is_url else 2)

        # Cập nhật cấu hình hiện tại và lưu lại
        self.config["source_language"] = self.source_lang_var.get()
        self.config["enable_tts"] = self.enable_tts_var.get()
        save_config(self.config)

        # Chạy pipeline trên thread riêng
        self.pipeline = Pipeline(self.task_queue)
        thread = threading.Thread(
            target=self.pipeline.run,
            args=(self.config, source, is_url),
            daemon=True,
        )
        thread.start()

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
        self.btn_download_only.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.pct_badge.configure(text="0%")
        self.status_label.configure(text="⏳ Đang kết nối tới máy chủ video...")
        self._set_active_step(1)

        out_dir = self.config.get("output_dir", str(Path.home() / "Desktop"))
        self._log_msg(f"📥 Bắt đầu tải video từ:\n   {url}")
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
                file_path = dl.download(url, out_dir)
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

    def _cancel(self):
        if self._is_processing:
            self.status_label.configure(text="⚠️ Đang gửi yêu cầu hủy...")
            self.btn_cancel.configure(state="disabled")
            self._download_cancelled = True
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
                    if "tải" in text_lower or "download" in text_lower:
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

                elif msg_type == "success":
                    self._set_active_step(5)  # All done
                    self._log_msg("\n✨ Xử lý thành công xuất sắc! Nhấn '📁 Mở Thư Mục Xuất' để xem video.")

                elif msg_type == "download_success":
                    fp = msg["file_path"]
                    fn = Path(fp).name
                    self._log_msg("\n" + "─" * 48)
                    self._log_msg("🎉 TẢI VIDEO THÀNH CÔNG!")
                    self._log_msg(f"   🎬 File: {fn}")
                    self._log_msg(f"   📁 Lưu tại: {fp}")
                    self._log_msg("💡 Video đã được tự động đưa vào tab 'Chọn File Video'. Sếp có thể bấm bắt đầu để tiếp tục!")
                    self.file_path_var.set(fp)
                    self.tabview.set("📂 Chọn File Video Trên Máy")
                    self.progress_bar.set(1.0)
                    self.pct_badge.configure(text="100%")
                    self.status_label.configure(text="✨ Đã tải xong video.")

                elif msg_type == "download_done" or msg_type == "done":
                    self._is_processing = False
                    self.btn_start.configure(state="normal")
                    self.btn_download_only.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    try:
                        self.tabview.configure(state="normal")
                        self.seg_lang.configure(state="normal")
                        self.switch_tts.configure(state="normal")
                        self.font_slider_main.configure(state="normal")
                    except Exception:
                        pass
                    self.pipeline = None

        except queue.Empty:
            pass

        self.after(100, self._process_queue)
