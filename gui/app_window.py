"""
gui/app_window.py — Giao diện chính của ứng dụng Vietsub AI
"""

import queue
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from core.pipeline import Pipeline
from gui.settings_dialog import SettingsDialog
from utils.config import load_config
from utils.ffmpeg_check import check_ffmpeg

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Vietsub AI — Dịch Video Tiếng Trung sang Tiếng Việt")
        self.geometry("800x650")
        self.minsize(700, 600)

        self.config = load_config()
        self.task_queue = queue.Queue()
        self.pipeline: Optional[Pipeline] = None
        self._is_processing = False
        self._download_cancelled = False

        self._set_app_icon()
        self._build_ui()
        self._check_prerequisites()

        # Polling queue định kỳ (100ms) để cập nhật UI từ background thread
        self.after(100, self._process_queue)

    def _set_app_icon(self):
        try:
            import os
            import sys
            from PIL import ImageTk, Image
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
        self.grid_rowconfigure(2, weight=1)

        # ─── HEADER ───
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(
            header_frame,
            text="Vietsub AI",
            font=("Arial", 28, "bold")
        ).pack(side="left")
        
        ctk.CTkButton(
            header_frame,
            text="⚙️ Cài đặt",
            width=100,
            command=self._open_settings
        ).pack(side="right")

        # ─── INPUT SECTION ───
        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        
        # Tabs for Local File / URL
        self.tabview = ctk.CTkTabview(input_frame, height=140)
        self.tabview.pack(padx=15, pady=10, fill="x")
        
        tab_file = self.tabview.add("File Video")
        tab_url = self.tabview.add("Link Online (TikTok, Facebook, YouTube...)")
        
        # Tab: File
        self.file_path_var = ctk.StringVar()
        file_inner = ctk.CTkFrame(tab_file, fg_color="transparent")
        file_inner.pack(fill="x", pady=10)
        
        self.file_entry = ctk.CTkEntry(
            file_inner, textvariable=self.file_path_var, state="readonly"
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(
            file_inner, text="📂 Chọn File...", width=120, command=self._browse_file
        ).pack(side="right")
        
        # Tab: URL
        self.url_var = ctk.StringVar()
        url_inner = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_inner.pack(fill="x", pady=(5, 2))
        
        ctk.CTkEntry(
            url_inner,
            textvariable=self.url_var,
            placeholder_text="Dán link TikTok, Facebook Reels/Video, YouTube, Bilibili vào đây..."
        ).pack(fill="x", expand=True)

        url_btn_frame = ctk.CTkFrame(tab_url, fg_color="transparent")
        url_btn_frame.pack(fill="x", pady=(4, 6))

        self.btn_download_only = ctk.CTkButton(
            url_btn_frame,
            text="⬇️ TẢI VIDEO VỀ MÁY",
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            font=("Arial", 12, "bold"),
            height=30,
            command=self._start_download_only,
        )
        self.btn_download_only.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            url_btn_frame,
            text="Hỗ trợ tải MP4 chất lượng cao từ TikTok, Facebook, YouTube (Không cần API Key)",
            font=("Arial", 11),
            text_color="gray",
        ).pack(side="left")

        # ─── LOG SECTION ───
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(log_frame, text="Tiến trình xử lý:", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        self.log_box = ctk.CTkTextbox(log_frame, font=("Consolas", 13))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # ─── STATUS & CONTROLS ───
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))
        status_frame.grid_columnconfigure(0, weight=1)
        
        self.progress_bar = ctk.CTkProgressBar(status_frame)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.progress_bar.set(0)
        
        self.status_label = ctk.CTkLabel(status_frame, text="Sẵn sàng.")
        self.status_label.grid(row=1, column=0, sticky="w")
        
        btn_inner = ctk.CTkFrame(status_frame, fg_color="transparent")
        btn_inner.grid(row=1, column=0, sticky="e")

        self.btn_open_folder = ctk.CTkButton(
            btn_inner,
            text="📁 Mở thư mục xuất",
            width=130,
            fg_color="#37474F",
            hover_color="#263238",
            command=self._open_output_dir,
        )
        self.btn_open_folder.pack(side="left", padx=(0, 10))

        self.btn_cancel = ctk.CTkButton(
            btn_inner, text="Hủy", width=80, fg_color="#D32F2F", hover_color="#B71C1C", state="disabled", command=self._cancel
        )
        self.btn_cancel.pack(side="left", padx=(0, 10))

        self.btn_start = ctk.CTkButton(
            btn_inner, text="▶ BẮT ĐẦU DỊCH", width=140, font=("Arial", 14, "bold"), command=self._start
        )
        self.btn_start.pack(side="left")

    def _check_prerequisites(self):
        """Kiểm tra FFmpeg và API Key khi khởi động."""
        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            self.btn_start.configure(state="disabled")
            return

        if not self.config.get("gemini_api_key"):
            self._log_msg("⚠️ Chưa có Gemini API Key. Vui lòng vào Cài đặt để nhập key.")

    def _open_output_dir(self):
        import os
        import subprocess
        import sys
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
            ok, _ = check_ffmpeg()
            if ok and self.config.get("gemini_api_key"):
                self.btn_start.configure(state="normal")

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
            self._log_msg("❌ Lỗi: Chưa có API Key.")
            self._open_settings()
            return

        is_url = self.tabview.get().startswith("Link Online")
        source = self.url_var.get().strip() if is_url else self.file_path_var.get().strip()

        if not source:
            self._log_msg("❌ Lỗi: Vui lòng chọn file hoặc nhập URL.")
            return

        # Khóa UI
        self._is_processing = True
        self.btn_start.configure(state="disabled")
        self.btn_download_only.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        try:
            self.tabview.configure(state="disabled")
        except Exception:
            pass

        self.log_box.delete("1.0", "end")
        self.progress_bar.set(0)
        self.status_label.configure(text="Đang bắt đầu...")

        # Chạy pipeline trên thread riêng
        self.pipeline = Pipeline(self.task_queue)
        thread = threading.Thread(
            target=self.pipeline.run,
            args=(self.config, source, is_url),
            daemon=True
        )
        thread.start()

    def _start_download_only(self):
        """Chỉ tải video gốc về máy tính từ URL (TikTok, Facebook, YouTube...) mà không dịch."""
        url = self.url_var.get().strip()
        if not url:
            self._log_msg("❌ Lỗi: Vui lòng dán link video (TikTok, Facebook, YouTube...) vào ô nhập.")
            return

        ok, msg = check_ffmpeg()
        if not ok:
            self._log_msg(f"❌ {msg}")
            return

        # Khóa UI
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
        self.progress_bar.set(0)
        self.status_label.configure(text="Đang kết nối tới máy chủ video...")

        out_dir = self.config.get("output_dir", str(Path.home() / "Desktop"))
        self._log_msg(f"📥 Đang tải video từ:\n   {url}")
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
            self.status_label.configure(text="Đang hủy...")
            self.btn_cancel.configure(state="disabled")
            self._download_cancelled = True
            if self.pipeline:
                self.pipeline.cancel()

    def _process_queue(self):
        """Đọc message từ pipeline và cập nhật UI (chạy trên main thread)."""
        try:
            while True:
                msg = self.task_queue.get_nowait()
                msg_type = msg.get("type")

                if msg_type == "log":
                    self._log_msg(msg["message"])
                elif msg_type == "progress":
                    self.progress_bar.set(msg["value"])
                    self.status_label.configure(text=msg["label"])
                elif msg_type == "error":
                    pass
                elif msg_type == "success":
                    self._log_msg("\n✨ Xử lý thành công! Nhấn nút '📁 Mở thư mục xuất' để xem video.")
                elif msg_type == "download_success":
                    fp = msg["file_path"]
                    fn = Path(fp).name
                    self._log_msg("\n" + "─" * 45)
                    self._log_msg("🎉 TẢI THÀNH CÔNG!")
                    self._log_msg(f"   🎬 File video: {fn}")
                    self._log_msg(f"   📁 Vị trí lưu: {fp}")
                    self._log_msg("💡 Video đã được tự động chọn sẵn ở tab 'File Video'. Sếp có thể bấm '▶ BẮT ĐẦU DỊCH' bất cứ lúc nào nếu muốn dịch sang tiếng Việt!")
                    self.file_path_var.set(fp)
                    self.progress_bar.set(1.0)
                    self.status_label.configure(text="Tải xong!")
                elif msg_type == "download_done":
                    self._is_processing = False
                    self.btn_start.configure(state="normal")
                    self.btn_download_only.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    try:
                        self.tabview.configure(state="normal")
                    except Exception:
                        pass
                elif msg_type == "done":
                    self._is_processing = False
                    self.btn_start.configure(state="normal")
                    self.btn_download_only.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    try:
                        self.tabview.configure(state="normal")
                    except Exception:
                        pass
                    self.pipeline = None
                    self.status_label.configure(text="Hoàn tất hoặc đã dừng.")

        except queue.Empty:
            pass

        # Lặp lại sau 100ms
        self.after(100, self._process_queue)
