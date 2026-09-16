"""
gui/settings_dialog.py — Hộp thoại Cài đặt nâng cao, hiện đại cho Vietsub AI
"""

import os
import webbrowser
from typing import Callable

import customtkinter as ctk

from utils.config import save_config


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
            "⚡ Gemini 3.8 Flash (Mới nhất, siêu nhanh & thông minh)": "gemini-3.8-flash",
            "🚀 Gemini 3.7 Flash (Thế hệ mới 3.7)": "gemini-3.7-flash",
            "✨ Gemini 3.6 Flash (Tốc độ cao 3.6)": "gemini-3.6-flash",
            "🛡️ Gemini 2.5 Flash (Bản chuẩn, ít nghẽn tải nhất)": "gemini-2.5-flash",
            "🔄 Tự động (Ưu tiên 3.8 ➔ 3.7 ➔ 3.6 ➔ 2.5)": "auto",
        }
        self.reverse_model_map = {v: k for k, v in self.model_map.items()}

        current_model = self.config.get("gemini_model", "gemini-3.8-flash")
        current_model_display = self.reverse_model_map.get(
            current_model, "⚡ Gemini 3.8 Flash (Mới nhất, siêu nhanh & thông minh)"
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

        # Voice Selector
        voice_frame = ctk.CTkFrame(card_audio, fg_color="transparent")
        voice_frame.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            voice_frame,
            text="Giọng đọc tiếng Việt (Microsoft Edge Neural):",
            font=("Arial", 12),
            text_color="#94A3B8",
        ).pack(anchor="w", pady=(0, 4))

        self.voice_map = {
            "vi-VN-HoaiMyNeural (Nữ - Tự nhiên, truyền cảm)": "vi-VN-HoaiMyNeural",
            "vi-VN-NamMinhNeural (Nam - Trầm ấm, dõng dạc)": "vi-VN-NamMinhNeural",
        }
        self.reverse_voice_map = {v: k for k, v in self.voice_map.items()}

        current_voice = self.config.get("tts_voice", "vi-VN-HoaiMyNeural")
        current_display = self.reverse_voice_map.get(
            current_voice, "vi-VN-HoaiMyNeural (Nữ - Tự nhiên, truyền cảm)"
        )

        self.voice_display_var = ctk.StringVar(value=current_display)
        self.voice_combo = ctk.CTkComboBox(
            voice_frame,
            values=list(self.voice_map.keys()),
            variable=self.voice_display_var,
            state="readonly",
            height=36,
            corner_radius=8,
        )
        self.voice_combo.pack(fill="x")

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
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # ─── SECTION 4: OUTPUT DIRECTORY ───
        card_out = ctk.CTkFrame(scroll_container, corner_radius=12, border_width=1, border_color="#334155")
        card_out.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_out,
            text="📁 Thư Mục Lưu Video Xuất",
            font=("Arial", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        out_box = ctk.CTkFrame(card_out, fg_color="transparent")
        out_box.pack(fill="x", padx=16, pady=(0, 14))

        self.out_dir_var = ctk.StringVar(value=self.config.get("output_dir", ""))
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
            fg_color="#4F46E5",
            hover_color="#4338CA",
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

    def _save(self):
        selected_display = self.voice_display_var.get()
        real_voice = self.voice_map.get(selected_display, "vi-VN-HoaiMyNeural")

        selected_model_display = self.model_display_var.get()
        real_model = self.model_map.get(selected_model_display, "gemini-3.8-flash")

        self.config["gemini_api_key"] = self.api_entry.get().strip()
        self.config["gemini_model"] = real_model
        self.config["tts_voice"] = real_voice
        self.config["audio_mode"] = self.audio_mode_var.get()
        self.config["original_volume"] = round(float(self.org_vol_slider.get()), 2)
        self.config["tts_volume"] = round(float(self.tts_vol_slider.get()), 2)
        self.config["subtitle_font_size"] = int(self.font_size_slider.get())
        self.config["subtitle_margin_v"] = int(self.margin_v_slider.get())
        self.config["output_dir"] = self.out_dir_var.get()

        save_config(self.config)
        self.on_save(self.config)
        self.destroy()
