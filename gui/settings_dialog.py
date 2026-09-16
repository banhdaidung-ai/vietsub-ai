"""
gui/settings_dialog.py — Hộp thoại Cài đặt
"""

from typing import Callable

import customtkinter as ctk
from PIL import Image

from utils.config import save_config


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, config: dict, on_save: Callable[[dict], None]):
        super().__init__(master)
        self.title("Cài đặt Vietsub AI")
        self.geometry("450x550")
        self.resizable(False, False)
        
        # Đảm bảo cửa sổ luôn ở trên cùng (modal behavior cơ bản)
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self.config = config.copy()
        self.on_save = on_save

        # --- Gemini API Key ---
        self.api_frame = ctk.CTkFrame(self)
        self.api_frame.pack(padx=15, pady=(15, 5), fill="x")
        
        ctk.CTkLabel(
            self.api_frame, text="Gemini API Key:", font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.api_entry = ctk.CTkEntry(
            self.api_frame,
            placeholder_text="Nhập API Key bắt đầu bằng AIza...",
            show="*"
        )
        self.api_entry.insert(0, self.config.get("gemini_api_key", ""))
        self.api_entry.pack(padx=10, pady=(0, 10), fill="x")
        
        # --- TTS Voice ---
        self.voice_frame = ctk.CTkFrame(self)
        self.voice_frame.pack(padx=15, pady=5, fill="x")
        
        ctk.CTkLabel(
            self.voice_frame, text="Giọng đọc (edge-tts):", font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.voice_var = ctk.StringVar(
            value=self.config.get("tts_voice", "vi-VN-HoaiMyNeural")
        )
        self.voice_combo = ctk.CTkComboBox(
            self.voice_frame,
            values=["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"],
            variable=self.voice_var,
            state="readonly"
        )
        self.voice_combo.pack(padx=10, pady=(0, 10), fill="x")
        
        # --- Audio Mixing ---
        self.audio_frame = ctk.CTkFrame(self)
        self.audio_frame.pack(padx=15, pady=5, fill="x")
        
        ctk.CTkLabel(
            self.audio_frame, text="Xử lý âm thanh:", font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.audio_mode_var = ctk.StringVar(
            value=self.config.get("audio_mode", "mix")
        )
        
        self.rad_mix = ctk.CTkRadioButton(
            self.audio_frame,
            text="Mix: Giữ nhạc nền gốc + Giọng Việt",
            variable=self.audio_mode_var,
            value="mix",
            command=self._update_sliders
        )
        self.rad_mix.pack(anchor="w", padx=10, pady=5)
        
        self.rad_replace = ctk.CTkRadioButton(
            self.audio_frame,
            text="Replace: Xóa tiếng gốc, chỉ dùng giọng Việt",
            variable=self.audio_mode_var,
            value="replace",
            command=self._update_sliders
        )
        self.rad_replace.pack(anchor="w", padx=10, pady=5)
        
        # Sliders
        self.sliders_frame = ctk.CTkFrame(self.audio_frame, fg_color="transparent")
        self.sliders_frame.pack(fill="x", padx=10, pady=5)
        
        # Org volume
        ctk.CTkLabel(self.sliders_frame, text="Âm lượng gốc:").grid(row=0, column=0, sticky="w")
        self.org_vol_slider = ctk.CTkSlider(self.sliders_frame, from_=0.0, to=1.0)
        self.org_vol_slider.set(self.config.get("original_volume", 0.3))
        self.org_vol_slider.grid(row=0, column=1, sticky="ew", padx=5)
        
        # TTS volume
        ctk.CTkLabel(self.sliders_frame, text="Âm lượng TTS:").grid(row=1, column=0, sticky="w", pady=5)
        self.tts_vol_slider = ctk.CTkSlider(self.sliders_frame, from_=0.0, to=2.0)
        self.tts_vol_slider.set(self.config.get("tts_volume", 1.0))
        self.tts_vol_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        self.sliders_frame.grid_columnconfigure(1, weight=1)
        self._update_sliders()
        
        # --- Output Directory ---
        self.out_frame = ctk.CTkFrame(self)
        self.out_frame.pack(padx=15, pady=5, fill="x")
        
        ctk.CTkLabel(
            self.out_frame, text="Thư mục xuất file:", font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 0))
        
        self.out_dir_var = ctk.StringVar(value=self.config.get("output_dir", ""))
        
        out_inner = ctk.CTkFrame(self.out_frame, fg_color="transparent")
        out_inner.pack(fill="x", padx=10, pady=(5, 10))
        
        self.out_entry = ctk.CTkEntry(out_inner, textvariable=self.out_dir_var, state="readonly")
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(
            out_inner, text="Chọn...", width=60, command=self._browse_out_dir
        ).pack(side="right")
        
        # --- Buttons ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=15)
        
        ctk.CTkButton(btn_frame, text="Hủy", width=100, fg_color="gray", command=self.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Lưu", width=100, command=self._save).pack(side="left", padx=10)

    def _update_sliders(self):
        state = "normal" if self.audio_mode_var.get() == "mix" else "disabled"
        self.org_vol_slider.configure(state=state)

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
        self.config["gemini_api_key"] = self.api_entry.get().strip()
        self.config["tts_voice"] = self.voice_var.get()
        self.config["audio_mode"] = self.audio_mode_var.get()
        self.config["original_volume"] = float(self.org_vol_slider.get())
        self.config["tts_volume"] = float(self.tts_vol_slider.get())
        self.config["output_dir"] = self.out_dir_var.get()
        
        save_config(self.config)
        self.on_save(self.config)
        self.destroy()
