"""
gui/settings_dialog.py — Hộp thoại Cài đặt nâng cao, hiện đại cho Vietsub AI
"""

import os
import webbrowser
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from gui.ffmpeg_download_dialog import FFmpegDownloadDialog
from utils.config import get_output_dir, save_config
from utils.ffmpeg_check import check_ffmpeg, get_ffmpeg_path
from utils.subtitle_styles import (
    DEFAULT_PRESET_ID,
    get_style_display_names,
    get_preset_by_name,
    get_preset_by_id,
)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, config: dict, on_save: Callable[[dict], None]):
        super().__init__(master)
        self.title("Cài Đặt — Vietsub AI")
        self.geometry("540x720")
        self.minsize(500, 640)
        self.resizable(False, False)

        # Modal behavior
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self.config = config.copy()
        self.on_save = on_save
        self._show_key = False

        self._build_ui()

    def _build_ui(self):
        # ─── HEADER ───
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=24, pady=(20, 15))

        ctk.CTkLabel(
            header_frame,
            text="⚙️ Cài Đặt Hệ Thống",
            font=("Arial", 20, "bold"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_frame,
            text="Tùy chỉnh khóa Gemini AI, giọng đọc lồng tiếng và thư mục lưu trữ.",
            font=("Arial", 12),
            text_color="#94A3B8",
        ).pack(anchor="w", pady=(2, 0))

        # ─── SCROLLABLE CONTAINER ───
        scroll_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # ─── SECTION 1: GEMINI AI ───
        card_ai = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_ai.pack(fill="x", pady=8)

        ai_header = ctk.CTkFrame(card_ai, fg_color="transparent")
        ai_header.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            ai_header,
            text="🤖 Google Gemini API Key",
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        ctk.CTkButton(
            ai_header,
            text="🔗 Lấy Key Miễn Phí",
            font=("Arial", 11, "underline"),
            fg_color="transparent",
            hover_color="#1E293B",
            text_color="#38BDF8",
            width=110,
            height=24,
            command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
        ).pack(side="right")

        key_box = ctk.CTkFrame(card_ai, fg_color="transparent")
        key_box.pack(fill="x", padx=16, pady=(0, 14))

        self.api_entry = ctk.CTkEntry(
            key_box,
            placeholder_text="Nhập API Key bắt đầu bằng AIzaSy...",
            show="•",
            height=36,
            corner_radius=8,
            font=("Consolas", 12),
        )
        self.api_entry.insert(0, self.config.get("gemini_api_key", ""))
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_toggle_eye = ctk.CTkButton(
            key_box,
            text="👁️ Hiện",
            width=65,
            height=36,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=self._toggle_api_visibility,
        )
        self.btn_toggle_eye.pack(side="right")

        # Model Selector
        model_frame = ctk.CTkFrame(card_ai, fg_color="transparent")
        model_frame.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkLabel(
            model_frame,
            text="Phiên bản Gemini AI ưu tiên:",
            font=("Arial", 12),
            text_color="#94A3B8",
        ).pack(anchor="w", pady=(0, 4))

        self.model_map = {
            "🔄 Tự động (Ưu tiên 3.8 ➔ 3.7 ➔ 3.6 ➔ 2.5)": "auto",
            "⚡ Gemini 3.8 Flash (Mới nhất, siêu nhanh & thông minh)": "gemini-3.8-flash",
            "🚀 Gemini 3.7 Flash (Thế hệ mới 3.7)": "gemini-3.7-flash",
            "✨ Gemini 3.6 Flash (Tốc độ cao 3.6)": "gemini-3.6-flash",
            "🛡️ Gemini 2.5 Flash (Bản chuẩn, ít nghẽn tải nhất)": "gemini-2.5-flash",
        }
        self.reverse_model_map = {v: k for k, v in self.model_map.items()}

        current_model = self.config.get("gemini_model", "auto")
        current_model_display = self.reverse_model_map.get(
            current_model, "🔄 Tự động (Ưu tiên 3.8 ➔ 3.7 ➔ 3.6 ➔ 2.5)"
        )

        self.model_display_var = ctk.StringVar(value=current_model_display)
        self.model_combo = ctk.CTkComboBox(
            model_frame,
            values=list(self.model_map.keys()),
            variable=self.model_display_var,
            height=34,
            corner_radius=8,
            state="readonly",
        )
        self.model_combo.pack(fill="x")

        # ─── SECTION 2: TTS & AUDIO ───
        card_audio = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_audio.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_audio,
            text="🎙️ Giọng Đọc & Xử Lý Âm Thanh",
            font=("Arial", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 10))

        # Công nghệ lồng tiếng
        tech_frame = ctk.CTkFrame(card_audio, fg_color="transparent")
        tech_frame.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            tech_frame,
            text="Công nghệ lồng tiếng:",
            font=("Arial", 12),
            text_color="#94A3B8",
        ).pack(anchor="w", pady=(0, 4))

        self.tts_tech_var = ctk.StringVar(value=self.config.get("tts_technology", "edge"))
        self.seg_tts_tech = ctk.CTkSegmentedButton(
            tech_frame,
            values=["🎙️ Microsoft AI (Chuẩn Việt)", "🎭 Google Gemini AI (Biểu Cảm)"],
            command=self._on_tts_tech_change,
            height=34,
            corner_radius=8,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
        )
        if self.tts_tech_var.get() == "gemini":
            self.seg_tts_tech.set("🎭 Google Gemini AI (Biểu Cảm)")
        else:
            self.seg_tts_tech.set("🎙️ Microsoft AI (Chuẩn Việt)")
        self.seg_tts_tech.pack(fill="x")

        self.lbl_tech_desc = ctk.CTkLabel(
            tech_frame,
            text="",
            font=("Arial", 11),
            text_color="#94A3B8",
            wraplength=480,
            justify="left",
        )
        self.lbl_tech_desc.pack(anchor="w", pady=(4, 0))

        # Voice Selector
        voice_frame = ctk.CTkFrame(card_audio, fg_color="transparent")
        voice_frame.pack(fill="x", padx=16, pady=(0, 8))

        self.lbl_voice_title = ctk.CTkLabel(
            voice_frame,
            text="Chọn giọng đọc:",
            font=("Arial", 12),
            text_color="#94A3B8",
        )
        self.lbl_voice_title.pack(anchor="w", pady=(0, 4))

        self.edge_voice_map = {
            "vi-VN-HoaiMyNeural (Nữ - Tự nhiên, truyền cảm)": "vi-VN-HoaiMyNeural",
            "vi-VN-NamMinhNeural (Nam - Trầm ấm, dõng dạc)": "vi-VN-NamMinhNeural",
        }
        self.reverse_edge_voice_map = {v: k for k, v in self.edge_voice_map.items()}

        self.gemini_voice_map = {
            "Aoede (Nữ - Truyền cảm, ấm áp)": "Aoede",
            "Kore (Nữ - Trong trẻo, tự nhiên)": "Kore",
            "Charon (Nam - Trầm sâu, điện ảnh)": "Charon",
            "Fenrir (Nam - Mạnh mẽ, dứt khoát)": "Fenrir",
            "Puck (Nam - Trẻ trung, linh hoạt)": "Puck",
        }
        self.reverse_gemini_voice_map = {v: k for k, v in self.gemini_voice_map.items()}
        self.voice_map = self.edge_voice_map

        self.voice_display_var = ctk.StringVar()
        self.voice_combo = ctk.CTkComboBox(
            voice_frame,
            values=[],
            variable=self.voice_display_var,
            state="readonly",
            height=36,
            corner_radius=8,
        )
        self.voice_combo.pack(fill="x")

        # Customization container (Speed/Pitch sliders for Edge or Note for Gemini)
        self.voice_custom_box = ctk.CTkFrame(card_audio, fg_color="transparent")
        self.voice_custom_box.pack(fill="x", padx=16, pady=(0, 8))

        # Speed & Pitch Frame for Microsoft AI
        self.tuning_frame = ctk.CTkFrame(self.voice_custom_box, fg_color="#1E293B", corner_radius=8)
        self.tuning_frame.grid_columnconfigure(1, weight=1)

        # Speed slider (-20% to +30%)
        ctk.CTkLabel(
            self.tuning_frame, text="Tốc độ đọc:", font=("Arial", 12), text_color="#CBD5E1"
        ).grid(row=0, column=0, sticky="w", padx=12, pady=6)

        current_speed_str = self.config.get("tts_speed", "+0%")
        try:
            current_speed_val = int(current_speed_str.replace("%", ""))
        except Exception:
            current_speed_val = 0

        self.speed_slider = ctk.CTkSlider(
            self.tuning_frame,
            from_=-20,
            to=30,
            number_of_steps=50,
            command=self._on_speed_slide,
            progress_color="#6366F1",
            button_color="#818CF8",
        )
        self.speed_slider.set(current_speed_val)
        self.speed_slider.grid(row=0, column=1, sticky="ew", padx=8, pady=6)

        self.lbl_speed_val = ctk.CTkLabel(
            self.tuning_frame,
            text=f"{current_speed_val:+d}%",
            font=("Consolas", 12, "bold"),
            width=50,
        )
        self.lbl_speed_val.grid(row=0, column=2, sticky="e", padx=12, pady=6)

        # Pitch slider (-10Hz to +10Hz)
        ctk.CTkLabel(
            self.tuning_frame, text="Cao độ giọng:", font=("Arial", 12), text_color="#CBD5E1"
        ).grid(row=1, column=0, sticky="w", padx=12, pady=6)

        current_pitch_str = self.config.get("tts_pitch", "+0Hz")
        try:
            current_pitch_val = int(current_pitch_str.replace("Hz", ""))
        except Exception:
            current_pitch_val = 0

        self.pitch_slider = ctk.CTkSlider(
            self.tuning_frame,
            from_=-10,
            to=10,
            number_of_steps=20,
            command=self._on_pitch_slide,
            progress_color="#6366F1",
            button_color="#818CF8",
        )
        self.pitch_slider.set(current_pitch_val)
        self.pitch_slider.grid(row=1, column=1, sticky="ew", padx=8, pady=6)

        self.lbl_pitch_val = ctk.CTkLabel(
            self.tuning_frame,
            text=f"{current_pitch_val:+d}Hz",
            font=("Consolas", 12, "bold"),
            width=50,
        )
        self.lbl_pitch_val.grid(row=1, column=2, sticky="e", padx=12, pady=6)

        # Note for Gemini AI
        self.lbl_gemini_note = ctk.CTkLabel(
            self.voice_custom_box,
            text="✨ Google Gemini AI tự động biểu cảm ngữ điệu (vui buồn, kịch tính, thì thầm...) theo kịch bản vietsub.",
            font=("Arial", 11, "italic"),
            text_color="#818CF8",
            wraplength=480,
            justify="left",
        )

        self._refresh_tts_ui()

        # Audio Mixing Mode
        mode_frame = ctk.CTkFrame(card_audio, fg_color="transparent")
        mode_frame.pack(fill="x", padx=16, pady=(5, 10))

        ctk.CTkLabel(
            mode_frame,
            text="Chế độ âm thanh xuất:",
            font=("Arial", 12),
            text_color="#94A3B8",
        ).pack(anchor="w", pady=(0, 6))

        self.audio_mode_var = ctk.StringVar(value=self.config.get("audio_mode", "mix"))
        self.seg_mode = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Mix: Giữ nhạc nền + Giọng Việt", "Replace: Chỉ dùng giọng Việt"],
            command=self._on_mode_change,
            height=34,
            corner_radius=8,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
        )
        if self.audio_mode_var.get() == "mix":
            self.seg_mode.set("Mix: Giữ nhạc nền + Giọng Việt")
        else:
            self.seg_mode.set("Replace: Chỉ dùng giọng Việt")
        self.seg_mode.pack(fill="x")

        # Volume sliders
        sliders_box = ctk.CTkFrame(card_audio, fg_color="transparent")
        sliders_box.pack(fill="x", padx=16, pady=(5, 16))
        sliders_box.grid_columnconfigure(1, weight=1)

        # Original Volume
        self.lbl_org_title = ctk.CTkLabel(
            sliders_box, text="Âm lượng nhạc nền:", font=("Arial", 12), text_color="#CBD5E1"
        )
        self.lbl_org_title.grid(row=0, column=0, sticky="w", pady=6)

        self.org_vol_slider = ctk.CTkSlider(
            sliders_box,
            from_=0.0,
            to=1.0,
            command=self._on_org_vol_slide,
            progress_color="#6366F1",
            button_color="#818CF8",
        )
        self.org_vol_slider.set(self.config.get("original_volume", 0.3))
        self.org_vol_slider.grid(row=0, column=1, sticky="ew", padx=12, pady=6)

        self.lbl_org_val = ctk.CTkLabel(
            sliders_box,
            text=f"{int(self.org_vol_slider.get() * 100)}%",
            font=("Consolas", 12, "bold"),
            width=45,
        )
        self.lbl_org_val.grid(row=0, column=2, sticky="e", pady=6)

        # TTS Volume
        ctk.CTkLabel(
            sliders_box, text="Âm lượng giọng đọc:", font=("Arial", 12), text_color="#CBD5E1"
        ).grid(row=1, column=0, sticky="w", pady=6)

        self.tts_vol_slider = ctk.CTkSlider(
            sliders_box,
            from_=0.0,
            to=2.0,
            command=self._on_tts_vol_slide,
            progress_color="#10B981",
            button_color="#34D399",
        )
        self.tts_vol_slider.set(self.config.get("tts_volume", 1.0))
        self.tts_vol_slider.grid(row=1, column=1, sticky="ew", padx=12, pady=6)

        self.lbl_tts_val = ctk.CTkLabel(
            sliders_box,
            text=f"{int(self.tts_vol_slider.get() * 100)}%",
            font=("Consolas", 12, "bold"),
            width=45,
        )
        self.lbl_tts_val.grid(row=1, column=2, sticky="e", pady=6)

        self._update_slider_states()

        # ─── SECTION 3: SUBTITLE STYLING ───
        card_sub = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_sub.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_sub,
            text="📝 Kiểu Chữ Phụ Đề (Vietsub Style)",
            font=("Arial", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 10))

        # 0. Mẫu phụ đề CapCut / TikTok
        preset_frame = ctk.CTkFrame(card_sub, fg_color="transparent")
        preset_frame.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            preset_frame,
            text="Mẫu phụ đề (CapCut / TikTok):",
            font=("Arial", 12, "bold"),
            text_color="#F8FAFC",
        ).pack(anchor="w", pady=(0, 4))

        current_preset_id = self.config.get("subtitle_style_preset", DEFAULT_PRESET_ID)
        current_preset = get_preset_by_id(current_preset_id)

        self.preset_combo = ctk.CTkOptionMenu(
            preset_frame,
            values=get_style_display_names(),
            command=self._on_preset_change,
            height=34,
            corner_radius=8,
            fg_color="#1E293B",
            button_color="#6366F1",
            button_hover_color="#4F46E5",
        )
        self.preset_combo.set(current_preset["name"])
        self.preset_combo.pack(fill="x", pady=(0, 6))

        # Mô tả ngắn preset
        self.lbl_preset_desc = ctk.CTkLabel(
            preset_frame,
            text=f"ℹ️ {current_preset['desc']}",
            font=("Arial", 11),
            text_color="#94A3B8",
            wraplength=480,
            justify="left",
        )
        self.lbl_preset_desc.pack(anchor="w", pady=(0, 8))

        # Khung xem trước trực tiếp (Live Preview Card)
        self.preview_card = ctk.CTkFrame(
            preset_frame,
            fg_color=current_preset["ui_bg"],
            corner_radius=8,
            border_width=1,
            border_color=current_preset["ui_border"],
            height=46,
        )
        self.preview_card.pack(fill="x", pady=(0, 4))
        self.preview_card.pack_propagate(False)

        self.lbl_preview_text = ctk.CTkLabel(
            self.preview_card,
            text="✨ Đây là phụ đề mẫu chuẩn phong cách CapCut",
            font=("Arial", 13, "bold"),
            text_color=current_preset["ui_fg"],
        )
        self.lbl_preview_text.place(relx=0.5, rely=0.5, anchor="center")

        sub_controls = ctk.CTkFrame(card_sub, fg_color="transparent")
        sub_controls.pack(fill="x", padx=16, pady=(0, 10))
        sub_controls.grid_columnconfigure(1, weight=1)

        # 1. Cỡ chữ (Font size)
        ctk.CTkLabel(
            sub_controls, text="Cỡ chữ phụ đề:", font=("Arial", 12), text_color="#CBD5E1"
        ).grid(row=0, column=0, sticky="w", pady=6)

        current_size = self.config.get("subtitle_font_size", 10)
        self.font_size_slider = ctk.CTkSlider(
            sub_controls,
            from_=8,
            to=24,
            number_of_steps=16,
            command=self._on_font_size_slide,
            progress_color="#6366F1",
            button_color="#818CF8",
        )
        self.font_size_slider.set(current_size)
        self.font_size_slider.grid(row=0, column=1, sticky="ew", padx=12, pady=6)

        self.lbl_font_size = ctk.CTkLabel(
            sub_controls,
            text=f"{int(current_size)} pt",
            font=("Consolas", 12, "bold"),
            width=50,
        )
        self.lbl_font_size.grid(row=0, column=2, sticky="e", pady=6)

        # 2. Khoảng cách mép đáy (MarginV)
        ctk.CTkLabel(
            sub_controls, text="Vị trí cách đáy:", font=("Arial", 12), text_color="#CBD5E1"
        ).grid(row=1, column=0, sticky="w", pady=6)

        current_margin = self.config.get("subtitle_margin_v", 8)
        self.margin_v_slider = ctk.CTkSlider(
            sub_controls,
            from_=4,
            to=40,
            number_of_steps=36,
            command=self._on_margin_v_slide,
            progress_color="#10B981",
            button_color="#34D399",
        )
        self.margin_v_slider.set(current_margin)
        self.margin_v_slider.grid(row=1, column=1, sticky="ew", padx=12, pady=6)

        self.lbl_margin_v = ctk.CTkLabel(
            sub_controls,
            text=f"{int(current_margin)} px",
            font=("Consolas", 12, "bold"),
            width=50,
        )
        self.lbl_margin_v.grid(row=1, column=2, sticky="e", pady=6)

        ctk.CTkLabel(
            card_sub,
            text="💡 Gợi ý: Cỡ 10-12pt & cách đáy 8px giúp chữ Vietsub nhỏ gọn, thanh lịch, nằm ngay dưới phụ đề gốc video.",
            font=("Arial", 11),
            text_color="#94A3B8",
        ).pack(anchor="w", padx=16, pady=(0, 6))

        # Tùy chọn duyệt & sửa phụ đề trước khi ghép
        review_sub_box = ctk.CTkFrame(card_sub, fg_color="transparent")
        review_sub_box.pack(fill="x", padx=16, pady=(0, 14))

        self.review_sub_var = ctk.BooleanVar(value=self.config.get("review_subtitles", False))
        self.chk_review_sub = ctk.CTkCheckBox(
            review_sub_box,
            text="✏️ Bật bảng duyệt & chỉnh sửa phụ đề trước khi ghép video",
            variable=self.review_sub_var,
            font=("Arial", 12, "bold"),
            text_color="#F8FAFC",
            checkmark_color="#FFFFFF",
            fg_color="#10B981",
            hover_color="#059669",
            border_color="#64748B",
        )
        self.chk_review_sub.pack(side="left")

        # ─── SECTION 4: OUTPUT DIRECTORY ───
        card_out = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_out.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_out,
            text="📁 Thư Mục Lưu Video Xuất",
            font=("Arial", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        out_box = ctk.CTkFrame(card_out, fg_color="transparent")
        out_box.pack(fill="x", padx=16, pady=(0, 10))

        current_out = get_output_dir(self.config)
        self.out_dir_var = ctk.StringVar(value=current_out)
        self.out_entry = ctk.CTkEntry(
            out_box,
            textvariable=self.out_dir_var,
            state="readonly",
            height=36,
            corner_radius=8,
            font=("Consolas", 11),
        )
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            out_box,
            text="📂 Chọn...",
            width=80,
            height=36,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=self._browse_out_dir,
        ).pack(side="right")

        # Tùy chọn xuất file kèm theo (.srt / .txt)
        export_extra_box = ctk.CTkFrame(card_out, fg_color="transparent")
        export_extra_box.pack(fill="x", padx=16, pady=(0, 14))

        self.export_srt_var = ctk.BooleanVar(value=self.config.get("export_srt", True))
        self.chk_srt = ctk.CTkCheckBox(
            export_extra_box,
            text="Xuất kèm file phụ đề (.srt)",
            variable=self.export_srt_var,
            font=("Arial", 12),
            text_color="#CBD5E1",
            fg_color="#4F46E5",
            hover_color="#4338CA",
            border_color="#64748B",
        )
        self.chk_srt.pack(side="left", padx=(0, 20))

        self.export_txt_var = ctk.BooleanVar(value=self.config.get("export_txt", True))
        self.chk_txt = ctk.CTkCheckBox(
            export_extra_box,
            text="Xuất kèm file văn bản lời thoại (.txt)",
            variable=self.export_txt_var,
            font=("Arial", 12),
            text_color="#CBD5E1",
            fg_color="#4F46E5",
            hover_color="#4338CA",
            border_color="#64748B",
        )
        self.chk_txt.pack(side="left")

        # ─── SECTION 5: FFMPEG ENGINE ───
        card_ffmpeg = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_ffmpeg.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_ffmpeg,
            text="⚡ Bộ Giải Mã FFmpeg (Video Engine)",
            font=("Arial", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ffmpeg_box = ctk.CTkFrame(card_ffmpeg, fg_color="transparent")
        ffmpeg_box.pack(fill="x", padx=16, pady=(0, 14))

        self.lbl_ffmpeg_status = ctk.CTkLabel(
            ffmpeg_box,
            text="Đang kiểm tra...",
            font=("Arial", 11),
            text_color="#94A3B8",
            wraplength=320,
            justify="left",
        )
        self.lbl_ffmpeg_status.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_download_ffmpeg = ctk.CTkButton(
            ffmpeg_box,
            text="⚡ Tải FFmpeg",
            width=115,
            height=36,
            corner_radius=8,
            fg_color="#065F46",
            hover_color="#047857",
            command=self._open_ffmpeg_download,
        )
        self.btn_download_ffmpeg.pack(side="right")

        self._update_ffmpeg_status()

        # ─── SECTION 6: AUTHOR / ABOUT ───
        card_about = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_about.pack(fill="x", pady=8)

        about_inner = ctk.CTkFrame(card_about, fg_color="transparent")
        about_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            about_inner,
            text="⭐️ Tác Giả & Bản Quyền",
            font=("Arial", 13, "bold"),
            text_color="#F8FAFC",
        ).pack(anchor="w")

        ctk.CTkLabel(
            about_inner,
            text="Được phát triển bởi Bành Đại Dũng - 0982333097",
            font=("Arial", 12, "bold"),
            text_color="#38BDF8",
        ).pack(anchor="w", pady=(4, 2))

        ctk.CTkLabel(
            about_inner,
            text="Ứng dụng Vietsub AI & Lồng Tiếng Chuyên Nghiệp trên macOS.",
            font=("Arial", 11),
            text_color="#94A3B8",
        ).pack(anchor="w")

        # ─── FOOTER ACTIONS ───
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(10, 20))

        ctk.CTkButton(
            footer,
            text="Đóng / Hủy",
            width=110,
            height=38,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            footer,
            text="💾 Lưu Cấu Hình",
            width=140,
            height=38,
            corner_radius=8,
            fg_color="#0A84FF",
            hover_color="#0071E3",
            font=("Arial", 13, "bold"),
            command=self._save,
        ).pack(side="right")

    def _toggle_api_visibility(self):
        self._show_key = not self._show_key
        if self._show_key:
            self.api_entry.configure(show="")
            self.btn_toggle_eye.configure(text="🔒 Ẩn")
        else:
            self.api_entry.configure(show="•")
            self.btn_toggle_eye.configure(text="👁️ Hiện")

    def _on_mode_change(self, value: str):
        if "Mix" in value:
            self.audio_mode_var.set("mix")
        else:
            self.audio_mode_var.set("replace")
        self._update_slider_states()

    def _update_slider_states(self):
        is_mix = self.audio_mode_var.get() == "mix"
        state = "normal" if is_mix else "disabled"
        self.org_vol_slider.configure(state=state)
        text_color = "#CBD5E1" if is_mix else "#64748B"
        self.lbl_org_title.configure(text_color=text_color)
        self.lbl_org_val.configure(text_color=text_color)

    def _on_org_vol_slide(self, val: float):
        self.lbl_org_val.configure(text=f"{int(val * 100)}%")

    def _on_tts_vol_slide(self, val: float):
        self.lbl_tts_val.configure(text=f"{int(val * 100)}%")

    def _on_font_size_slide(self, val: float):
        self.lbl_font_size.configure(text=f"{int(val)} pt")

    def _on_margin_v_slide(self, val: float):
        self.lbl_margin_v.configure(text=f"{int(val)} px")

    def _browse_out_dir(self):
        try:
            self.grab_release()
        except Exception:
            pass
        dir_path = ctk.filedialog.askdirectory(initialdir=self.out_dir_var.get(), parent=self)
        try:
            self.grab_set()
        except Exception:
            pass
        if dir_path:
            self.out_dir_var.set(dir_path)

    def _on_tts_tech_change(self, value: str):
        if "Gemini" in value:
            self.tts_tech_var.set("gemini")
        else:
            self.tts_tech_var.set("edge")
        self._refresh_tts_ui()

    def _refresh_tts_ui(self):
        tech = self.tts_tech_var.get()
        if tech == "gemini":
            self.lbl_tech_desc.configure(
                text="🌟 Lồng tiếng điện ảnh đa cảm xúc chân thực theo ngữ cảnh vietsub (Gemini Flash Audio)."
            )
            self.lbl_voice_title.configure(text="Giọng đọc điện ảnh (Google Gemini Audio):")
            self.voice_combo.configure(values=list(self.gemini_voice_map.keys()))
            cur_voice = self.config.get("tts_voice_gemini", "Aoede")
            cur_display = self.reverse_gemini_voice_map.get(
                cur_voice, "Aoede (Nữ - Truyền cảm, ấm áp)"
            )
            self.voice_display_var.set(cur_display)
            self.tuning_frame.pack_forget()
            self.lbl_gemini_note.pack(fill="x", pady=(4, 2))
        else:
            self.lbl_tech_desc.configure(
                text="⚡ Giọng đọc nhanh, chuẩn âm điệu tiếng Việt, hỗ trợ tùy chỉnh tốc độ & cao độ."
            )
            self.lbl_voice_title.configure(text="Giọng đọc tiếng Việt (Microsoft Edge Neural):")
            self.voice_combo.configure(values=list(self.edge_voice_map.keys()))
            cur_voice = self.config.get("tts_voice", "vi-VN-HoaiMyNeural")
            cur_display = self.reverse_edge_voice_map.get(
                cur_voice, "vi-VN-HoaiMyNeural (Nữ - Tự nhiên, truyền cảm)"
            )
            self.voice_display_var.set(cur_display)
            self.lbl_gemini_note.pack_forget()
            self.tuning_frame.pack(fill="x")

    def _on_speed_slide(self, val: float):
        int_val = int(round(val))
        self.lbl_speed_val.configure(text=f"{int_val:+d}%")

    def _on_pitch_slide(self, val: float):
        int_val = int(round(val))
        self.lbl_pitch_val.configure(text=f"{int_val:+d}Hz")

    def _on_preset_change(self, display_name: str):
        preset = get_preset_by_name(display_name)
        self.lbl_preset_desc.configure(text=f"ℹ️ {preset['desc']}")
        self.preview_card.configure(
            fg_color=preset["ui_bg"],
            border_color=preset["ui_border"],
        )
        self.lbl_preview_text.configure(text_color=preset["ui_fg"])

    def _save(self):
        tts_tech = self.tts_tech_var.get()
        self.config["tts_technology"] = tts_tech
        selected_display = self.voice_display_var.get()

        if tts_tech == "gemini":
            real_voice = self.gemini_voice_map.get(selected_display, "Aoede")
            self.config["tts_voice_gemini"] = real_voice
        else:
            real_voice = self.edge_voice_map.get(selected_display, "vi-VN-HoaiMyNeural")
            self.config["tts_voice"] = real_voice

        speed_val = int(round(self.speed_slider.get()))
        pitch_val = int(round(self.pitch_slider.get()))
        self.config["tts_speed"] = f"{speed_val:+d}%"
        self.config["tts_pitch"] = f"{pitch_val:+d}Hz"

        selected_model_display = self.model_display_var.get()
        real_model = self.model_map.get(selected_model_display, "gemini-3.8-flash")

        selected_preset_display = self.preset_combo.get()
        real_preset = get_preset_by_name(selected_preset_display)

        self.config["gemini_api_key"] = self.api_entry.get().strip()
        self.config["gemini_model"] = real_model
        self.config["audio_mode"] = self.audio_mode_var.get()
        self.config["original_volume"] = round(float(self.org_vol_slider.get()), 2)
        self.config["tts_volume"] = round(float(self.tts_vol_slider.get()), 2)
        self.config["subtitle_style_preset"] = real_preset["id"]
        self.config["subtitle_font_size"] = int(self.font_size_slider.get())
        self.config["subtitle_margin_v"] = int(self.margin_v_slider.get())
        self.config["output_dir"] = self.out_dir_var.get().strip() or get_output_dir(self.config)
        self.config["export_srt"] = self.export_srt_var.get()
        self.config["export_txt"] = self.export_txt_var.get()
        self.config["review_subtitles"] = self.review_sub_var.get()

        save_config(self.config)
        self.on_save(self.config)
        self.destroy()

    def _update_ffmpeg_status(self):
        ok, msg = check_ffmpeg()
        if ok:
            path = get_ffmpeg_path() or "Hệ thống"
            self.lbl_ffmpeg_status.configure(
                text=f"✅ Đã kết nối: {path}",
                text_color="#34D399",
            )
            self.btn_download_ffmpeg.configure(
                text="🔄 Tải Lại",
                fg_color="#334155",
                hover_color="#475569",
            )
        else:
            self.lbl_ffmpeg_status.configure(
                text="❌ Chưa tìm thấy FFmpeg trên máy (cần thiết để ghép phụ đề và video)",
                text_color="#FCA5A5",
            )
            self.btn_download_ffmpeg.configure(
                text="⚡ Tải Tự Động",
                fg_color="#065F46",
                hover_color="#047857",
            )

    def _open_ffmpeg_download(self):
        FFmpegDownloadDialog(self, on_success=self._update_ffmpeg_status)
