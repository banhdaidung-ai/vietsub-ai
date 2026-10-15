"""
gui/image_compressor_dialog.py — Nén ảnh hàng loạt thông minh
Thiết kế theo ngôn ngữ Apple macOS Dark Mode của Vietsub AI Studio.
Tích hợp: View nhúng vào app chính, popup hoàn tất, đồng bộ log, lưu/khôi phục cài đặt.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
from PIL import Image

try:
    from tkinterdnd2 import DND_FILES
    HAS_TKDND = True
except Exception:
    HAS_TKDND = False
    DND_FILES = None

from core.image_compressor import (
    CompressResult,
    CompressTask,
    ImageCompressorEngine,
    SUPPORTED_EXTENSIONS,
    WatermarkConfig,
    apply_watermark,
    build_output_path,
    scan_images,
)
from utils.config import load_config, save_config

# ── Reuse design tokens from app_window ──
BG_WINDOW   = "#141518"
BG_CARD     = "#1C1F27"
BG_INSET    = "#121419"
BG_PILL     = "#272B37"
BG_PILL_HOV = "#343949"
BORDER_CARD = "#2E3342"
BORDER_INSET= "#252834"

APPLE_BLUE        = "#0A84FF"
APPLE_BLUE_HOVER  = "#0071E3"
APPLE_GREEN       = "#30D158"
APPLE_GREEN_HOVER = "#28B84C"
APPLE_ORANGE      = "#FF9F0A"
APPLE_RED         = "#FF453A"
APPLE_RED_BG      = "#361413"
APPLE_CYAN        = "#64D2FF"
APPLE_PURPLE      = "#AF52DE"

TEXT_PRIMARY   = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_TERTIARY  = "#636366"


# ─────────────────────────────────────────────────────────────
# Hàm tiện ích chung & Âm thanh thông báo hệ thống (Cross-Platform)
# ─────────────────────────────────────────────────────────────

def _fmt_kb(kb: float) -> str:
    """Định dạng số KB thành chuỗi KB hoặc MB hiển thị trực quan."""
    try:
        kb_val = float(kb)
        if kb_val >= 1024:
            return f"{kb_val / 1024:.2f} MB"
        return f"{kb_val:.0f} KB"
    except Exception:
        return f"{kb} KB"


def _play_system_sound() -> None:
    """Phát âm thanh thông báo hệ thống cross-platform (macOS Glass, Windows asterisk)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"], stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Popup thông báo hoàn tất nén ảnh
# ─────────────────────────────────────────────────────────────

class CompressCompletionModal(ctk.CTkToplevel):
    """Popup thông báo nén ảnh hoàn tất theo chuẩn giao diện Apple macOS & Windows."""

    def __init__(
        self,
        parent,
        ok_count: int,
        total_count: int,
        src_size_str: str,
        dst_size_str: str,
        saved_str: str,
        reduction_pct: float,
        out_dir: str,
        is_compress_mode: bool = True,
        elapsed_str: str = "",
    ):
        super().__init__(parent)
        self.is_compress_mode = is_compress_mode
        self.title("Hoàn Tất Nén Ảnh — Vietsub AI" if is_compress_mode else "Hoàn Tất Đóng Dấu Ảnh — Vietsub AI")
        self.geometry("520x450")
        self.resizable(False, False)
        self.configure(fg_color=BG_WINDOW)

        self.out_dir = out_dir

        top = parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent
        try:
            self.transient(top)
        except Exception:
            pass
        self.lift()
        self.grab_set()
        self.focus_force()
        try:
            self.attributes("-topmost", True)
            self.after(500, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
        except Exception:
            pass

        # Căn giữa cửa sổ con so với cửa sổ cha
        try:
            self.update_idletasks()
            px = top.winfo_rootx() + (top.winfo_width() - 520) // 2
            py = top.winfo_rooty() + (top.winfo_height() - 450) // 2
            self.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

        # ── 1. Header Banner ──
        hdr_frame = ctk.CTkFrame(self, fg_color="transparent")
        hdr_frame.pack(fill="x", padx=24, pady=(20, 12))

        ctk.CTkLabel(
            hdr_frame,
            text="🎉",
            font=("Arial", 36),
        ).pack(side="left", padx=(0, 14))

        title_inner = ctk.CTkFrame(hdr_frame, fg_color="transparent")
        title_inner.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_inner,
            text="Nén Ảnh Hoàn Tất!" if is_compress_mode else "Đóng Dấu Ảnh Hoàn Tất!",
            font=("Arial", 18, "bold"),
            text_color=APPLE_GREEN if is_compress_mode else APPLE_ORANGE,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_inner,
            text="Tất cả các tệp hình ảnh đã được tối ưu dung lượng thành công." if is_compress_mode else "Tất cả các tệp hình ảnh đã được chèn Logo & Mã SP với chất lượng gốc 100%.",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        # ── 2. Stat Card ──
        card = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_CARD,
        )
        card.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        time_val = elapsed_str if elapsed_str else "Nhanh chóng"
        if is_compress_mode:
            stats = [
                ("🖼️ Số lượng ảnh:", f"{ok_count}/{total_count} ảnh thành công", APPLE_CYAN),
                ("⏱️ Thời gian chạy:", time_val, APPLE_CYAN),
                ("📊 Dung lượng gốc:", src_size_str, TEXT_PRIMARY),
                ("📦 Sau khi nén:", dst_size_str, TEXT_PRIMARY),
                ("📉 Tiết kiệm được:", f"{saved_str}  (-{reduction_pct:.1f}%)", APPLE_GREEN),
                ("📁 Thư mục lưu:", out_dir, TEXT_SECONDARY),
            ]
        else:
            stats = [
                ("🖼️ Số lượng ảnh:", f"{ok_count}/{total_count} ảnh thành công", APPLE_CYAN),
                ("⏱️ Thời gian chạy:", time_val, APPLE_CYAN),
                ("📦 Dung lượng xuất:", dst_size_str, TEXT_PRIMARY),
                ("✨ Trạng thái chất lượng:", "Giữ nguyên 100% chất lượng gốc", APPLE_GREEN),
                ("🏷️ Chế độ xử lý:", "Chỉ đóng dấu Watermark (Không nén)", APPLE_ORANGE),
                ("📁 Thư mục lưu:", out_dir, TEXT_SECONDARY),
            ]

        for i, (label, val, clr) in enumerate(stats):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(10 if i == 0 else 6, 10 if i == len(stats) - 1 else 0))

            ctk.CTkLabel(
                row,
                text=label,
                font=("Arial", 11, "bold"),
                text_color=TEXT_SECONDARY,
                width=130,
                anchor="w",
            ).pack(side="left")

            lbl_val = ctk.CTkLabel(
                row,
                text=val,
                font=("Arial", 11, "bold" if clr in (APPLE_GREEN, APPLE_CYAN) else "normal"),
                text_color=clr,
                anchor="w",
            )
            lbl_val.pack(side="left", fill="x", expand=True)

        # ── 3. Footer Buttons ──
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=24, pady=(0, 20))

        ctk.CTkButton(
            btn_bar,
            text="📁 Mở Thư Mục Chứa Ảnh",
            font=("Arial", 12, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            text_color="#FFFFFF",
            height=38,
            corner_radius=8,
            command=self._open_folder,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            btn_bar,
            text="✓ Đóng",
            font=("Arial", 12, "bold"),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_CARD,
            height=38,
            width=100,
            corner_radius=8,
            command=self.destroy,
        ).pack(side="right")

    def _open_folder(self):
        if os.path.isdir(self.out_dir):
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", self.out_dir])
                elif sys.platform == "win32":
                    norm_path = os.path.normpath(str(self.out_dir))
                    try:
                        os.startfile(norm_path)
                    except Exception:
                        subprocess.Popen(["explorer", norm_path])
                else:
                    subprocess.Popen(["xdg-open", self.out_dir])
            except Exception:
                pass
        self.destroy()


# ─────────────────────────────────────────────────────────────
# Image Compressor Dialog Chính
# ─────────────────────────────────────────────────────────────

class ImageCompressorDialog(ctk.CTkToplevel):
    """
    Dialog nén ảnh hàng loạt.
    - Kéo thả / chọn nhiều file / cả thư mục
    - Điều chỉnh dung lượng mục tiêu (KB hoặc MB)
    - Chọn thư mục xuất
    - Hiển thị bảng kết quả chi tiết
    - Nút Cancel mid-batch
    - Tự động đồng bộ log ra Studio Terminal và hiển thị popup hoàn tất
    """

    def __init__(self, parent, initial_files: Optional[List[str]] = None):
        super().__init__(parent)
        self.parent = parent
        self.title("🖼️ Nén Ảnh Hàng Loạt — Vietsub AI Studio")
        self.geometry("1260x840")
        self.minsize(980, 620)
        self.configure(fg_color=BG_WINDOW)
        self.resizable(True, True)

        # Đưa dialog lên trên
        self.transient(parent)
        self.lift()
        self.focus_force()

        # Lắng nghe sự kiện đóng cửa sổ để lưu cấu hình
        try:
            self.protocol("WM_DELETE_WINDOW", self._on_dialog_close)
        except Exception:
            pass

        # Mặc định mở toàn màn hình (maximized) khi mở cửa sổ
        self.after(50, self._maximize_window)

        self._init_state()
        self._build_ui()
        self._setup_dnd()

        self._msg_queue = queue.Queue()
        self.after(50, self._poll_queue)

        if initial_files:
            self._add_paths(initial_files)

    def _on_dialog_close(self):
        """Lưu toàn bộ cài đặt trước khi đóng dialog."""
        try:
            self._save_img_settings()
        except Exception:
            pass
        self.destroy()

    def _init_state(self):
        """Khởi tạo toàn bộ biến trạng thái từ config đã lưu (hoặc giá trị mặc định)."""
        # Đọc config ưu tiên từ toplevel window (AppWindow), parent, hoặc load fresh từ file
        cfg = None
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "config") and isinstance(getattr(top, "config"), dict):
                cfg = top.config
        except Exception:
            pass
        if cfg is None and hasattr(self.parent, "config") and isinstance(getattr(self.parent, "config"), dict):
            cfg = self.parent.config
        if cfg is None or not isinstance(cfg, dict):
            cfg = load_config()
        self._app_config = cfg

        self._engine = ImageCompressorEngine()
        self._is_running = False
        self._image_paths: List[str] = []      # Danh sách ảnh đã thêm
        self._results: List[CompressResult] = []

        # ── Timer & Stopwatch state ──
        self._batch_start_time: Optional[float] = None
        self._timer_running = False
        self._timer_after_id = None
        self._save_settings_timer = None

        # ── Compress state (load từ config: hỗ trợ cả flat keys và nested dict) ──
        img_cfg = cfg.get("image_compressor", {}) if isinstance(cfg.get("image_compressor"), dict) else {}

        def _get_cfg_val(flat_key, nested_key, default):
            if nested_key in img_cfg:
                return img_cfg[nested_key]
            if flat_key in cfg:
                return cfg[flat_key]
            return default

        self._compress_enabled = ctk.BooleanVar(value=bool(_get_cfg_val("img_compress_enabled", "compress_enabled", True)))
        self._target_var = ctk.StringVar(value=str(_get_cfg_val("img_target_value", "target_value", "500")))
        self._unit_var = ctk.StringVar(value=str(_get_cfg_val("img_target_unit", "target_unit", "KB")))
        self._fmt_var = ctk.StringVar(value=str(_get_cfg_val("img_output_format", "output_format", "Tự động")))
        self._exif_var = ctk.BooleanVar(value=bool(_get_cfg_val("img_keep_exif", "keep_exif", True)))

        _saved_out = str(_get_cfg_val("img_output_dir", "output_dir", "")).strip()
        default_out = _saved_out if _saved_out else str(Path.home() / "Downloads" / "compressed_images")
        self._out_dir_var = ctk.StringVar(value=default_out)

        # Bảng ánh xạ vị trí tiếng Anh sang tiếng Việt nếu file lưu chuẩn cũ
        _REV_POS_MAP = {
            "top-left": "Góc trái trên", "topleft": "Góc trái trên",
            "top-right": "Góc phải trên", "topright": "Góc phải trên",
            "bottom-left": "Góc trái dưới", "bottomleft": "Góc trái dưới",
            "bottom-right": "Góc phải dưới", "bottomright": "Góc phải dưới",
            "center": "Giữa",
        }

        # ── Watermark state (load từ config) ──
        self._wm_logo_enabled  = ctk.BooleanVar(value=bool(_get_cfg_val("img_wm_logo_enabled", "logo_enabled", False)))
        self._wm_logo_path     = ctk.StringVar(value=str(_get_cfg_val("img_wm_logo_path", "logo_path", "")))
        self._wm_logo_scale    = ctk.DoubleVar(value=float(_get_cfg_val("img_wm_logo_scale", "logo_scale", 0.15)))
        _saved_lpos = str(_get_cfg_val("img_wm_logo_pos", "logo_pos", "Góc phải dưới"))
        self._wm_logo_pos      = ctk.StringVar(value=_REV_POS_MAP.get(_saved_lpos, _saved_lpos))
        _raw_lop = float(_get_cfg_val("img_wm_logo_opacity", "logo_opacity", 100))
        if 0 < _raw_lop <= 1.0:
            _raw_lop *= 100
        self._wm_logo_opacity  = ctk.IntVar(value=int(round(_raw_lop)))

        _raw_loffx = float(_get_cfg_val("img_wm_logo_offset_x", "logo_offset_x", 0.0))
        if abs(_raw_loffx) > 1.0:
            _raw_loffx /= 100.0
        self._wm_logo_offset_x = ctk.DoubleVar(value=_raw_loffx)

        _raw_loffy = float(_get_cfg_val("img_wm_logo_offset_y", "logo_offset_y", 0.0))
        if abs(_raw_loffy) > 1.0:
            _raw_loffy /= 100.0
        self._wm_logo_offset_y = ctk.DoubleVar(value=_raw_loffy)

        self._wm_text_enabled  = ctk.BooleanVar(value=bool(_get_cfg_val("img_wm_text_enabled", "text_enabled", False)))
        self._wm_text_source   = ctk.StringVar(value=str(_get_cfg_val("img_wm_text_source", "text_source", "Tên file ảnh")))
        self._wm_text_custom   = ctk.StringVar(value=str(_get_cfg_val("img_wm_text_custom", "text_custom", "")))
        _saved_tpos = str(_get_cfg_val("img_wm_text_pos", "text_pos", "Góc trái dưới"))
        self._wm_text_pos      = ctk.StringVar(value=_REV_POS_MAP.get(_saved_tpos, _saved_tpos))
        self._wm_text_size     = ctk.IntVar(value=int(_get_cfg_val("img_wm_text_size", "text_size", 20)))
        self._wm_text_color    = str(_get_cfg_val("img_wm_text_color", "text_color", "#000000"))
        self._wm_text_bold     = ctk.BooleanVar(value=bool(_get_cfg_val("img_wm_text_bold", "text_bold", False)))
        self._wm_text_shadow   = ctk.BooleanVar(value=bool(_get_cfg_val("img_wm_text_shadow", "text_shadow", False)))
        self._wm_text_box      = ctk.BooleanVar(value=bool(_get_cfg_val("img_wm_text_box", "text_box", False)))
        self._wm_text_box_color= str(_get_cfg_val("img_wm_text_box_color", "text_box_color", "#000000"))
        _raw_bop = float(_get_cfg_val("img_wm_text_box_opacity", "box_opacity", 60))
        if 0 < _raw_bop <= 1.0:
            _raw_bop *= 100
        self._wm_text_box_opacity = ctk.IntVar(value=int(round(_raw_bop)))

        _raw_toffx = float(_get_cfg_val("img_wm_text_offset_x", "text_offset_x", 0.0))
        if abs(_raw_toffx) > 1.0:
            _raw_toffx /= 100.0
        self._wm_text_offset_x = ctk.DoubleVar(value=_raw_toffx)

        _raw_toffy = float(_get_cfg_val("img_wm_text_offset_y", "text_offset_y", 0.0))
        if abs(_raw_toffy) > 1.0:
            _raw_toffy /= 100.0
        self._wm_text_offset_y = ctk.DoubleVar(value=_raw_toffy)

        # ── Preview state & Cache ──
        self._current_preview_index = 0
        self._cached_preview_thumb: Optional[Image.Image] = None
        self._cached_preview_src: str = ""
        self._cached_orig_size = (0, 0)
        self._preview_show_original = False
        self._preview_photo    = None   # CTkImage cho preview
        self._preview_job      = None   # After job debounce ID
        self._preview_zoom_factor = 1.0 # 1.0 = Fit vừa vặn khung nhìn
        self._preview_zoom_var = ctk.DoubleVar(value=1.0)

        # ── Auto-save traces cho TẤT CẢ các biến cài đặt ──
        # Đảm bảo mỗi khi người dùng thay đổi bất kỳ ô nhập, thanh trượt hay switch nào
        # thì cấu hình đều được ghi nhận và lưu lại ngay lập tức
        _tracked_vars = [
            self._compress_enabled, self._target_var, self._unit_var,
            self._fmt_var, self._exif_var, self._out_dir_var,
            self._wm_logo_enabled, self._wm_logo_path, self._wm_logo_scale,
            self._wm_logo_pos, self._wm_logo_opacity, self._wm_logo_offset_x, self._wm_logo_offset_y,
            self._wm_text_enabled, self._wm_text_source, self._wm_text_custom,
            self._wm_text_pos, self._wm_text_size, self._wm_text_bold,
            self._wm_text_shadow, self._wm_text_box, self._wm_text_box_opacity,
            self._wm_text_offset_x, self._wm_text_offset_y,
        ]
        for v in _tracked_vars:
            v.trace_add("write", lambda *_: self._schedule_save_settings())

    def _schedule_save_settings(self, now: bool = False):
        """Tự động lưu cài đặt (ngay lập tức hoặc debounce 50ms)."""
        if hasattr(self, "_save_settings_timer") and self._save_settings_timer:
            try:
                self.after_cancel(self._save_settings_timer)
            except Exception:
                pass
            self._save_settings_timer = None
        if now:
            self._save_img_settings()
        else:
            self._save_settings_timer = self.after(50, self._save_img_settings)


    def _maximize_window(self):
        """Mở cửa sổ cực đại / full màn hình theo chuẩn hệ điều hành."""
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                try:
                    sw = self.winfo_screenwidth()
                    sh = self.winfo_screenheight()
                    self.geometry(f"{sw}x{sh}+0+0")
                except Exception:
                    pass

    def _start_timer(self):
        """Khởi động bộ đếm thời gian nén ảnh."""
        self._batch_start_time = time.time()
        self._timer_running = True
        self._tick_timer()

    def _tick_timer(self):
        """Cập nhật huy hiệu thời gian định kỳ khi đang nén ảnh."""
        if not self._timer_running:
            return
        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        if hasattr(self, "_time_badge"):
            self._time_badge.configure(text=f"⏱️ {mins:02d}:{secs:02d}")
        if self._is_running:
            self._timer_after_id = self.after(500, self._tick_timer)

    def _stop_timer(self):
        """Dừng bộ đếm thời gian nén ảnh."""
        self._timer_running = False
        if self._timer_after_id is not None:
            try:
                self.after_cancel(self._timer_after_id)
            except Exception:
                pass
            self._timer_after_id = None

    def _poll_queue(self):
        """Hút và xử lý các sự kiện từ background thread trên main UI thread."""
        try:
            while not self._msg_queue.empty():
                msg = self._msg_queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "progress":
                    self._update_progress(msg["current"], msg["total"], msg["result"])
                elif msg_type == "done":
                    self._finalize(msg["results"])
        except Exception:
            pass

        try:
            if self.winfo_exists():
                self.after(50, self._poll_queue)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # Đồng bộ log ra Studio Terminal của cửa sổ chính
    # ─────────────────────────────────────────────────────────

    def _log_to_parent(self, msg: str):
        """Ghi thông điệp ra Console Studio Terminal của màn hình chính nếu có."""
        if hasattr(self.parent, "_log_msg"):
            try:
                self.parent._log_msg(msg)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────
    # UI Builder
    # ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # 2-cột: Cột trái nội dung (col=0) + Cột phải preview sidebar (col=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=420)  # preview sidebar: 420px
        self.grid_rowconfigure(0, weight=1)

        # ── Preview Sidebar (phải, chiếm trọn chiều cao) ──
        self._build_preview_sidebar()

        # ── Khung chứa cột trái (left_col) ──
        left_col = ctk.CTkFrame(self, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=12)

        # ── Header ──
        hdr = ctk.CTkFrame(left_col, fg_color=BG_CARD, corner_radius=12,
                           border_width=1, border_color=BORDER_CARD)
        hdr.pack(side="top", fill="x", pady=(0, 6))

        hdr_inner = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(hdr_inner, text="🖼️  Nén Ảnh Thông Minh",
                     font=("Arial", 18, "bold"), text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(hdr_inner,
                     text="Giảm dung lượng hàng loạt • Giữ chất lượng tối đa • Hỗ trợ JPG / PNG / WEBP",
                     font=("Arial", 11), text_color=TEXT_SECONDARY).pack(side="left", padx=(14, 0))

        # ── Footer Actions (Ghim ở ĐÁY cột trái TRƯỚC để LUÔN hiển thị, không bao giờ bị đẩy ra ngoài) ──
        footer = ctk.CTkFrame(left_col, fg_color="transparent")
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        footer.grid_columnconfigure(0, weight=1)

        self._lbl_status = ctk.CTkLabel(footer, text="✨ Sẵn sàng nén ảnh.",
                                         font=("Arial", 12), text_color="#94A3B8")
        self._lbl_status.grid(row=0, column=0, sticky="w")

        btn_grp = ctk.CTkFrame(footer, fg_color="transparent")
        btn_grp.grid(row=0, column=1, sticky="e")

        self._btn_cancel = ctk.CTkButton(
            btn_grp, text="⏹ Dừng", font=("Arial", 12, "bold"),
            width=90, height=38, corner_radius=8,
            fg_color=APPLE_RED_BG, hover_color=APPLE_RED, text_color=APPLE_RED,
            state="disabled", command=self._cancel,
        )
        self._btn_cancel.pack(side="left", padx=(0, 10))

        self._btn_start = ctk.CTkButton(
            btn_grp, text="🚀 Bắt Đầu Nén", font=("Arial", 13, "bold"),
            width=190, height=38, corner_radius=8,
            fg_color=APPLE_GREEN, hover_color=APPLE_GREEN_HOVER,
            command=self._start,
        )
        self._btn_start.pack(side="left")
        self._update_action_button_label()

        # ── Khung cuộn nội dung ở giữa (CTkScrollableFrame co giãn giữa header và footer) ──
        self._scroll_content = ctk.CTkScrollableFrame(left_col, fg_color="transparent")
        self._scroll_content.pack(side="top", fill="both", expand=True)
        self._scroll_content.grid_columnconfigure(0, weight=1)

        # Hỗ trợ cuộn chuột siêu mượt
        def _on_mousewheel(event):
            try:
                if sys.platform == "darwin":
                    self._scroll_content._parent_canvas.yview_scroll(int(-1 * event.delta), "units")
                else:
                    self._scroll_content._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        self._scroll_content.bind("<MouseWheel>", _on_mousewheel, add="+")
        self._scroll_content._parent_canvas.bind("<MouseWheel>", _on_mousewheel, add="+")

        # ── Drop Zone + File List ──
        drop_card = ctk.CTkFrame(self._scroll_content, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER_CARD)
        drop_card.pack(fill="x", pady=(0, 6))
        drop_card.grid_columnconfigure(0, weight=1)

        # Drop zone hint
        self._drop_frame = ctk.CTkFrame(drop_card, fg_color=BG_INSET, corner_radius=10,
                                         border_width=2, border_color=BORDER_INSET, height=68)
        self._drop_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))
        self._drop_frame.grid_propagate(False)
        self._drop_frame.grid_columnconfigure(0, weight=1)
        self._drop_frame.grid_rowconfigure(0, weight=1)

        self._lbl_drop = ctk.CTkLabel(
            self._drop_frame,
            text="⬇️  Kéo & thả ảnh hoặc thư mục vào đây  |  JPG · PNG · WEBP · BMP · TIFF",
            font=("Arial", 12), text_color=TEXT_TERTIARY
        )
        self._lbl_drop.grid(row=0, column=0)

        # Buttons: Add files / Add folder / Clear
        btn_row = ctk.CTkFrame(drop_card, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))

        ctk.CTkButton(btn_row, text="📂 Thêm Ảnh", font=("Arial", 11, "bold"),
                      width=120, height=30, corner_radius=7,
                      fg_color=APPLE_BLUE, hover_color=APPLE_BLUE_HOVER,
                      command=self._add_files).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="🗂️ Thêm Thư Mục", font=("Arial", 11, "bold"),
                      width=135, height=30, corner_radius=7,
                      fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=APPLE_CYAN,
                      border_width=1, border_color="#1E3A8A",
                      command=self._add_folder).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="🗑️ Xóa Danh Sách", font=("Arial", 11, "bold"),
                      width=130, height=30, corner_radius=7,
                      fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=APPLE_RED,
                      border_width=1, border_color="#692523",
                      command=self._clear_list).pack(side="left")

        self._lbl_count = ctk.CTkLabel(btn_row, text="0 ảnh đã thêm",
                                        font=("Arial", 11, "bold"),
                                        text_color=APPLE_GREEN)
        self._lbl_count.pack(side="right")

        # File list textbox
        self._file_box = ctk.CTkTextbox(
            drop_card, height=80, font=("Consolas", 10),
            fg_color="#0D0E12", text_color="#D8DEE9",
            corner_radius=8, border_width=1, border_color=BORDER_INSET,
        )
        self._file_box.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))
        self._file_box.configure(state="disabled")

        # ── Settings Card (Thiết lập phân luồng rõ ràng, không bị chèn ép) ──
        cfg_card = ctk.CTkFrame(self._scroll_content, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER_CARD)
        cfg_card.pack(fill="x", pady=(0, 6))

        # Dòng 1: Switch nén + Mục tiêu dung lượng + Nút chọn nhanh (Mặc định 500KB)
        cfg_row1 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        cfg_row1.pack(fill="x", padx=14, pady=(8, 4))

        self._compress_switch = ctk.CTkSwitch(
            cfg_row1,
            text="⚡ Nén dung lượng",
            variable=self._compress_enabled,
            font=("Arial", 11, "bold"),
            text_color=APPLE_CYAN,
            progress_color=APPLE_BLUE,
            width=36, height=18,
            command=self._on_compress_toggle,
        )
        self._compress_switch.pack(side="left", padx=(0, 10))

        self._target_container = ctk.CTkFrame(cfg_row1, fg_color="transparent")
        self._target_container.pack(side="left", fill="x", expand=True)

        self._size_grp = ctk.CTkFrame(self._target_container, fg_color="transparent")
        self._size_grp.pack(side="left")

        ctk.CTkLabel(self._size_grp, text="🎯 Mục tiêu:",
                     font=("Arial", 11, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 6))

        self._target_entry = ctk.CTkEntry(
            self._size_grp, textvariable=self._target_var,
            width=65, height=28, corner_radius=7,
            fg_color=BG_INSET, border_color=BORDER_INSET, border_width=1,
            text_color=APPLE_CYAN, font=("Consolas", 12, "bold"),
            justify="center",
        )
        self._target_entry.pack(side="left", padx=(0, 4))

        self._unit_menu = ctk.CTkOptionMenu(
            self._size_grp, values=["KB", "MB"], variable=self._unit_var,
            width=62, height=28, corner_radius=7,
            fg_color=BG_INSET, button_color=BG_PILL, button_hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY, font=("Arial", 11),
            command=self._on_unit_change,
        )
        self._unit_menu.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(self._size_grp, text="Nhanh:", font=("Arial", 10),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        for label, val, unit in [("500 KB", "500", "KB"), ("1 MB", "1", "MB"),
                                  ("2 MB", "2", "MB"), ("5 MB", "5", "MB")]:
            ctk.CTkButton(
                self._size_grp, text=label, font=("Arial", 10, "bold"),
                width=52, height=26, corner_radius=6,
                fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=APPLE_ORANGE,
                border_width=1, border_color="#633B11",
                command=lambda v=val, u=unit: self._set_preset(v, u),
            ).pack(side="left", padx=2)

        self._no_compress_hint = ctk.CTkFrame(self._target_container, fg_color="transparent")
        ctk.CTkLabel(
            self._no_compress_hint,
            text="✨ Giữ nguyên 100% độ phân giải & chất lượng gốc (Không nén)",
            font=("Arial", 11, "bold"), text_color=APPLE_GREEN
        ).pack(side="left", padx=(4, 0))

        # Dòng 2: Định dạng & Giữ EXIF (Dòng riêng giúp bố cục rộng rãi, không bị đè chữ khi co hẹp)
        cfg_row_fmt = ctk.CTkFrame(cfg_card, fg_color="transparent")
        cfg_row_fmt.pack(fill="x", padx=14, pady=(2, 4))

        ctk.CTkLabel(cfg_row_fmt, text="📦 Định dạng xuất:",
                     font=("Arial", 11, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(
            cfg_row_fmt, values=["Tự động", "JPEG", "PNG", "WEBP"],
            variable=self._fmt_var,
            width=110, height=28, corner_radius=7,
            fg_color=BG_INSET, button_color=BG_PILL, button_hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY, font=("Arial", 11),
            command=lambda _: self._save_img_settings(),
        ).pack(side="left", padx=(0, 16))

        ctk.CTkSwitch(
            cfg_row_fmt, text="Giữ metadata EXIF gốc", variable=self._exif_var,
            font=("Arial", 11), text_color=TEXT_SECONDARY,
            progress_color=APPLE_GREEN, width=44, height=20,
            command=self._save_img_settings,
        ).pack(side="left")

        # Dòng 3: Thư mục xuất
        cfg_row2 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        cfg_row2.pack(fill="x", padx=14, pady=(2, 8))

        ctk.CTkLabel(cfg_row2, text="📁 Thư mục xuất:",
                     font=("Arial", 12, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 8))

        self._out_entry = ctk.CTkEntry(
            cfg_row2, textvariable=self._out_dir_var,
            height=32, corner_radius=7,
            fg_color=BG_INSET, border_color=BORDER_INSET, border_width=1,
            text_color=TEXT_PRIMARY, font=("Arial", 11),
        )
        self._out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            cfg_row2,
            text="📂 Chọn Thư Mục...",
            font=("Arial", 11, "bold"),
            width=140, height=32, corner_radius=7,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY,
            border_width=1, border_color=BORDER_CARD,
            command=self._browse_out_dir,
        ).pack(side="right")

        self._build_watermark_card()

        # ── Results Area ──
        result_card = ctk.CTkFrame(self._scroll_content, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER_CARD)
        result_card.pack(fill="x", pady=(0, 6))
        result_card.grid_columnconfigure(0, weight=1)

        # Progress header
        prog_hdr = ctk.CTkFrame(result_card, fg_color="transparent")
        prog_hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))

        # Traffic lights
        for col, clr in [("#FF5F56", 0), ("#FFBD2E", 1), ("#27C93F", 2)]:
            ctk.CTkLabel(prog_hdr, text="●", font=("Arial", 13),
                         text_color=col).pack(side="left", padx=2)
        ctk.CTkLabel(prog_hdr, text="  Nhật Ký & Kết Quả Nén", font=("Arial", 12, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        self._pct_badge = ctk.CTkLabel(prog_hdr, text="0%",
                                        font=("Consolas", 11, "bold"),
                                        fg_color=BG_INSET, text_color=APPLE_CYAN,
                                        corner_radius=6, width=48, height=22)
        self._pct_badge.pack(side="left", padx=(8, 0))

        # Timer badge hiển thị thời gian khi chạy nén file
        self._time_badge = ctk.CTkLabel(prog_hdr, text="⏱️ 00:00",
                                         font=("Consolas", 11, "bold"),
                                         fg_color=BG_INSET, text_color=APPLE_CYAN,
                                         corner_radius=6, width=68, height=22)
        self._time_badge.pack(side="left", padx=(6, 0))

        self._stat_badge = ctk.CTkLabel(prog_hdr, text="",
                                         font=("Arial", 11, "bold"), text_color=APPLE_GREEN)
        self._stat_badge.pack(side="left", padx=(10, 0))

        ctk.CTkButton(prog_hdr, text="📁 Mở Thư Mục Xuất",
                      font=("Arial", 11), width=140, height=24, corner_radius=6,
                      fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
                      command=self._open_out_dir).pack(side="right")

        self._progress_bar = ctk.CTkProgressBar(result_card, height=6, corner_radius=3,
                                                  progress_color=APPLE_BLUE, fg_color=BG_INSET)
        self._progress_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        self._progress_bar.set(0.0)

        # ── Banner Trạng Thái Thành Công Nổi Bật (In-App Success Card) ──
        self._success_banner = ctk.CTkFrame(
            result_card,
            fg_color="#0D2818",
            border_width=1.5,
            border_color="#10B981",
            corner_radius=10,
        )
        self._success_banner.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        self._success_banner.grid_remove()  # Ẩn mặc định khi chưa chạy

        sb_inner = ctk.CTkFrame(self._success_banner, fg_color="transparent")
        sb_inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            sb_inner,
            text="🎉",
            font=("Arial", 28),
        ).pack(side="left", padx=(0, 12))

        sb_text_grp = ctk.CTkFrame(sb_inner, fg_color="transparent")
        sb_text_grp.pack(side="left", fill="x", expand=True)

        self._sb_title = ctk.CTkLabel(
            sb_text_grp,
            text="NÉN ẢNH HOÀN TẤT THÀNH CÔNG!",
            font=("Arial", 14, "bold"),
            text_color="#34D399",
            anchor="w",
        )
        self._sb_title.pack(anchor="w")

        self._sb_desc = ctk.CTkLabel(
            sb_text_grp,
            text="Tất cả các tệp hình ảnh đã được xử lý hoàn tất.",
            font=("Arial", 11),
            text_color="#E2E8F0",
            anchor="w",
        )
        self._sb_desc.pack(anchor="w", pady=(2, 0))

        sb_btn_grp = ctk.CTkFrame(sb_inner, fg_color="transparent")
        sb_btn_grp.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            sb_btn_grp,
            text="📁 Mở Thư Mục Xuất",
            font=("Arial", 11, "bold"),
            fg_color="#059669",
            hover_color="#10B981",
            text_color="#FFFFFF",
            height=32,
            corner_radius=7,
            command=self._open_out_dir,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            sb_btn_grp,
            text="✕",
            font=("Arial", 12, "bold"),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY,
            width=32,
            height=32,
            corner_radius=7,
            command=lambda: self._success_banner.grid_remove(),
        ).pack(side="left")

        # Log Textbox (Row 3 co giãn tối đa)
        result_card.grid_rowconfigure(3, weight=1)
        self._result_box = ctk.CTkTextbox(
            result_card, font=("Consolas", 11),
            fg_color="#0D0E12", text_color="#D8DEE9",
            corner_radius=10, border_width=1, border_color=BORDER_INSET,
            height=140,
        )
        self._result_box.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 10))
        self._result_box.configure(state="disabled")

        # Đồng bộ giao diện chuẩn xác theo các giá trị cấu hình đã khôi phục
        try:
            self._on_compress_toggle()
            self._on_text_source_change(self._wm_text_source.get())
            self._update_action_button_label()
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # Preview Sidebar (Panel Xem Trước Phía Bên Phải)
    # ─────────────────────────────────────────────────────────

    def _build_preview_sidebar(self):
        """Sidebar preview rộng rãi 420px bên phải, span toàn bộ chiều cao cửa sổ."""
        sidebar = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER_CARD,
            width=420,
        )
        sidebar.grid(row=0, column=1, sticky="nsew",
                     padx=(0, 16), pady=12)
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(1, weight=1)  # Khung xem ảnh co giãn tối đa

        # ── Header ──
        hdr = ctk.CTkFrame(sidebar, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))

        hdr_left = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_left.pack(side="left")
        ctk.CTkLabel(
            hdr_left, text="👁️  Xem Trước Watermark",
            font=("Arial", 13, "bold"), text_color=TEXT_PRIMARY
        ).pack(anchor="w")
        ctk.CTkLabel(
            hdr_left, text="⚡ Thời gian thực • Tỉ lệ 1:1 chuẩn xuất file",
            font=("Arial", 10), text_color=TEXT_TERTIARY
        ).pack(anchor="w")

        hdr_right = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_right.pack(side="right")

        self._btn_compare = ctk.CTkButton(
            hdr_right, text="👁️ Gốc", width=58, height=28, corner_radius=6,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=APPLE_CYAN,
            font=("Arial", 10, "bold"),
            command=self._toggle_compare_preview,
        )
        self._btn_compare.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            hdr_right, text="🔄", width=32, height=28, corner_radius=6,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 12),
            command=lambda: self._refresh_preview(force_reload=True),
        ).pack(side="left")

        # ── Khung Hiển Thị Ảnh (Viewport tối ưu nhất) ──
        view_card = ctk.CTkFrame(
            sidebar, fg_color="#090A0D", corner_radius=10,
            border_width=1, border_color="#1F232D"
        )
        self._preview_view_card = view_card
        view_card.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        view_card.grid_propagate(False)
        view_card.grid_columnconfigure(0, weight=1)
        view_card.grid_rowconfigure(0, weight=1)

        self._preview_label = ctk.CTkLabel(
            view_card,
            text="Chưa có ảnh.\n\nKéo & thả hoặc bấm '📂 Thêm Ảnh'\nđể xem trước logo và mã sản phẩm tại đây.",
            font=("Arial", 12), text_color=TEXT_TERTIARY,
            wraplength=340,
            anchor="center",
        )
        self._preview_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        view_card.bind("<Configure>", self._on_view_card_resize)

        # ── Thanh Điều Chỉnh Kích Thước / Thu Phóng Preview ──
        zoom_bar = ctk.CTkFrame(sidebar, fg_color=BG_INSET, corner_radius=8,
                                border_width=1, border_color=BORDER_INSET)
        zoom_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        zoom_bar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            zoom_bar, text="🔍", font=("Arial", 11), text_color=TEXT_TERTIARY
        ).grid(row=0, column=0, padx=(8, 2), pady=4)

        self._btn_zoom_out = ctk.CTkButton(
            zoom_bar, text="➖", width=26, height=24, corner_radius=5,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 10, "bold"),
            command=self._zoom_out,
        )
        self._btn_zoom_out.grid(row=0, column=1, padx=2, pady=4)

        self._zoom_slider = ctk.CTkSlider(
            zoom_bar, from_=0.3, to=2.0, number_of_steps=34,
            variable=self._preview_zoom_var, height=14,
            progress_color=APPLE_CYAN, button_color=APPLE_CYAN,
            command=self._on_zoom_slider,
        )
        self._zoom_slider.grid(row=0, column=2, sticky="ew", padx=4, pady=4)

        self._btn_zoom_in = ctk.CTkButton(
            zoom_bar, text="➕", width=26, height=24, corner_radius=5,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 10, "bold"),
            command=self._zoom_in,
        )
        self._btn_zoom_in.grid(row=0, column=3, padx=2, pady=4)

        self._lbl_zoom_val = ctk.CTkLabel(
            zoom_bar, text="Fit", font=("Consolas", 10, "bold"),
            text_color=APPLE_CYAN, width=38,
        )
        self._lbl_zoom_val.grid(row=0, column=4, padx=2, pady=4)

        self._btn_zoom_fit = ctk.CTkButton(
            zoom_bar, text="Vừa Khung", width=70, height=24, corner_radius=5,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=APPLE_CYAN,
            font=("Arial", 10, "bold"),
            command=self._zoom_fit,
        )
        self._btn_zoom_fit.grid(row=0, column=5, padx=(2, 4), pady=4)

        self._btn_zoom_100 = ctk.CTkButton(
            zoom_bar, text="100%", width=44, height=24, corner_radius=5,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 10, "bold"),
            command=lambda: self._zoom_to(1.0),
        )
        self._btn_zoom_100.grid(row=0, column=6, padx=(0, 6), pady=4)

        # ── Footer Info & Batch Navigation ──
        foot_bar = ctk.CTkFrame(sidebar, fg_color=BG_INSET, corner_radius=8,
                                border_width=1, border_color=BORDER_INSET)
        foot_bar.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        foot_bar.grid_columnconfigure(1, weight=1)

        # Nút Previous
        self._btn_prev_img = ctk.CTkButton(
            foot_bar, text="◀", width=28, height=26, corner_radius=5,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 11),
            command=self._prev_preview_image,
        )
        self._btn_prev_img.grid(row=0, column=0, padx=(6, 4), pady=5)

        # Info & Counter
        self._preview_info_lbl = ctk.CTkLabel(
            foot_bar,
            text="Chưa nạp ảnh",
            font=("Consolas", 10), text_color=TEXT_SECONDARY,
            anchor="center",
        )
        self._preview_info_lbl.grid(row=0, column=1, sticky="ew", padx=4, pady=5)

        # Nút Next
        self._btn_next_img = ctk.CTkButton(
            foot_bar, text="▶", width=28, height=26, corner_radius=5,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 11),
            command=self._next_preview_image,
        )
        self._btn_next_img.grid(row=0, column=2, padx=(4, 6), pady=5)

    # ─────────────────────────────────────────────────────────
    # Watermark Card
    # ─────────────────────────────────────────────────────────

    def _build_watermark_card(self):
        """Xây dựng card Watermark (Logo + Text). Preview ở sidebar phải."""
        wm_card = ctk.CTkFrame(
            self._scroll_content, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER_CARD
        )
        wm_card.pack(fill="x", pady=(0, 6))

        # ── Header ──
        wm_hdr = ctk.CTkFrame(wm_card, fg_color="transparent")
        wm_hdr.pack(fill="x", padx=14, pady=(8, 4))
        ctk.CTkLabel(
            wm_hdr, text="🏷️  Watermark — Chèn Logo & Mã Sản Phẩm",
            font=("Arial", 12, "bold"), text_color=TEXT_PRIMARY
        ).pack(side="left")
        ctk.CTkLabel(
            wm_hdr,
            text="Preview xem trước ở cột phải →",
            font=("Arial", 10), text_color=TEXT_TERTIARY
        ).pack(side="right", padx=(10, 0))

        # ── Body: 2 cột Logo | Text ──
        body = ctk.CTkFrame(wm_card, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        # ════ Cột Trái — LOGO ════
        logo_col = ctk.CTkFrame(
            body, fg_color=BG_INSET, corner_radius=10,
            border_width=1, border_color=BORDER_INSET
        )
        logo_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
        logo_col.grid_columnconfigure(0, weight=1)

        logo_hdr = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ctk.CTkLabel(logo_hdr, text="🖼️ Logo",
                     font=("Arial", 11, "bold"), text_color=APPLE_CYAN).pack(side="left")
        self._logo_switch = ctk.CTkSwitch(
            logo_hdr, text="", variable=self._wm_logo_enabled,
            width=36, height=18, progress_color=APPLE_CYAN,
            command=self._on_wm_toggle,
        )
        self._logo_switch.pack(side="right")

        logo_path_row = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_path_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        self._logo_path_entry = ctk.CTkEntry(
            logo_path_row, textvariable=self._wm_logo_path,
            placeholder_text="Đường dẫn logo (PNG/JPG)...",
            height=28, corner_radius=6,
            fg_color=BG_PILL, border_color=BORDER_CARD, border_width=1,
            text_color=TEXT_PRIMARY, font=("Arial", 10),
        )
        self._logo_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            logo_path_row, text="📂", width=30, height=28, corner_radius=6,
            fg_color=BG_PILL, hover_color=BG_PILL_HOV, text_color=TEXT_PRIMARY,
            font=("Arial", 11),
            command=self._browse_logo,
        ).pack(side="right")

        logo_scale_row = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_scale_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(logo_scale_row, text="Kích thước:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        _scale_init = int(float(self._wm_logo_scale.get()) * 100)
        self._logo_scale_lbl = ctk.CTkLabel(
            logo_scale_row, text=f"{_scale_init}%",
            font=("Consolas", 10, "bold"), text_color=APPLE_CYAN, width=36
        )
        self._logo_scale_lbl.pack(side="right")
        ctk.CTkSlider(
            logo_scale_row, from_=0.03, to=0.60, number_of_steps=57,
            variable=self._wm_logo_scale, height=14,
            progress_color=APPLE_CYAN, button_color=APPLE_CYAN,
            command=lambda v: (
                self._logo_scale_lbl.configure(text=f"{int(float(v)*100)}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        logo_pos_row = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_pos_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(logo_pos_row, text="Vị trí:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            logo_pos_row,
            values=["Góc trái trên", "Góc phải trên",
                    "Góc trái dưới", "Góc phải dưới", "Giữa"],
            variable=self._wm_logo_pos,
            width=130, height=26, corner_radius=6,
            fg_color=BG_PILL, button_color=BG_PILL, button_hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY, font=("Arial", 10),
            command=lambda _: self._schedule_preview(),
        ).pack(side="left", fill="x", expand=True)

        logo_op_row = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_op_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkLabel(logo_op_row, text="Opacity:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        _op_init = int(float(self._wm_logo_opacity.get()))
        self._logo_op_lbl = ctk.CTkLabel(
            logo_op_row, text=f"{_op_init}%",
            font=("Consolas", 10, "bold"), text_color=APPLE_CYAN, width=36
        )
        self._logo_op_lbl.pack(side="right")
        ctk.CTkSlider(
            logo_op_row, from_=0, to=100, number_of_steps=100,
            variable=self._wm_logo_opacity, height=14,
            progress_color=APPLE_CYAN, button_color=APPLE_CYAN,
            command=lambda v: (
                self._logo_op_lbl.configure(text=f"{int(float(v))}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # ── Logo Offset X ──
        logo_offx_row = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_offx_row.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(logo_offx_row, text="Lệch X:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        _offx_init = int(float(self._wm_logo_offset_x.get()) * 100)
        self._logo_offx_lbl = ctk.CTkLabel(
            logo_offx_row, text=f"{_offx_init:+d}%",
            font=("Consolas", 10, "bold"), text_color=APPLE_CYAN, width=36
        )
        self._logo_offx_lbl.pack(side="right")
        ctk.CTkSlider(
            logo_offx_row, from_=-0.50, to=0.50, number_of_steps=200,
            variable=self._wm_logo_offset_x, height=14,
            progress_color=APPLE_CYAN, button_color=APPLE_CYAN,
            command=lambda v: (
                self._logo_offx_lbl.configure(text=f"{int(float(v)*100):+d}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # ── Logo Offset Y ──
        logo_offy_row = ctk.CTkFrame(logo_col, fg_color="transparent")
        logo_offy_row.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkLabel(logo_offy_row, text="Lệch Y:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        _offy_init = int(float(self._wm_logo_offset_y.get()) * 100)
        self._logo_offy_lbl = ctk.CTkLabel(
            logo_offy_row, text=f"{_offy_init:+d}%",
            font=("Consolas", 10, "bold"), text_color=APPLE_CYAN, width=36
        )
        self._logo_offy_lbl.pack(side="right")
        ctk.CTkSlider(
            logo_offy_row, from_=-0.50, to=0.50, number_of_steps=200,
            variable=self._wm_logo_offset_y, height=14,
            progress_color=APPLE_CYAN, button_color=APPLE_CYAN,
            command=lambda v: (
                self._logo_offy_lbl.configure(text=f"{int(float(v)*100):+d}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # ════ Cột Phải — TEXT ════
        text_col = ctk.CTkFrame(
            body, fg_color=BG_INSET, corner_radius=10,
            border_width=1, border_color=BORDER_INSET
        )
        text_col.grid(row=0, column=1, sticky="nsew", pady=0)
        text_col.grid_columnconfigure(0, weight=1)

        text_hdr = ctk.CTkFrame(text_col, fg_color="transparent")
        text_hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ctk.CTkLabel(text_hdr, text="✏️ Mã Sản Phẩm",
                     font=("Arial", 11, "bold"), text_color=APPLE_ORANGE).pack(side="left")
        self._text_switch = ctk.CTkSwitch(
            text_hdr, text="", variable=self._wm_text_enabled,
            width=36, height=18, progress_color=APPLE_ORANGE,
            command=self._on_wm_toggle,
        )
        self._text_switch.pack(side="right")

        # Row 1: Nguồn selector
        src_row = ctk.CTkFrame(text_col, fg_color="transparent")
        src_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(src_row, text="Nguồn:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=50, anchor="w").pack(side="left")
        self._text_src_menu = ctk.CTkOptionMenu(
            src_row,
            values=["Tên file ảnh", "Tuỳ chỉnh"],
            variable=self._wm_text_source,
            width=110, height=26, corner_radius=6,
            fg_color=BG_PILL, button_color=BG_PILL, button_hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY, font=("Arial", 10),
            command=self._on_text_source_change,
        )
        self._text_src_menu.pack(side="left", fill="x", expand=True)

        # Row 2: Khung hiển thị nội dung text (Tự động hoặc Tuỳ chỉnh)
        self._text_content_container = ctk.CTkFrame(text_col, fg_color="transparent")
        self._text_content_container.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 3))
        self._text_content_container.grid_columnconfigure(0, weight=1)

        # Badge hiển thị tên file nguồn được chọn
        self._filename_hint_lbl = ctk.CTkLabel(
            self._text_content_container,
            text="🏷️ Tự động lấy tên file ảnh",
            font=("Arial", 10, "bold"), text_color=APPLE_ORANGE,
            anchor="w", fg_color=BG_PILL, corner_radius=6, height=28,
            padx=8,
        )
        self._filename_hint_lbl.grid(row=0, column=0, sticky="ew")

        # Entry nhập text tuỳ chỉnh (hiển thị khi chọn Tuỳ chỉnh)
        self._text_custom_entry = ctk.CTkEntry(
            self._text_content_container, textvariable=self._wm_text_custom,
            placeholder_text="Nhập mã SP / text tuỳ chỉnh...",
            height=28, corner_radius=6,
            fg_color=BG_PILL, border_color=BORDER_CARD, border_width=1,
            text_color=APPLE_ORANGE, font=("Arial", 10),
        )
        # Bắt sự kiện gõ text tuỳ chỉnh để render preview thời gian thực
        self._wm_text_custom.trace_add("write", lambda *_: self._schedule_preview())

        # Row 3: Cỡ chữ
        size_row = ctk.CTkFrame(text_col, fg_color="transparent")
        size_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(size_row, text="Cỡ chữ:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=50, anchor="w").pack(side="left")
        _tsize_init = int(float(self._wm_text_size.get()))
        self._text_size_lbl = ctk.CTkLabel(
            size_row, text=str(_tsize_init),
            font=("Consolas", 10, "bold"), text_color=APPLE_ORANGE, width=32
        )
        self._text_size_lbl.pack(side="right")
        ctk.CTkSlider(
            size_row, from_=8, to=80, number_of_steps=72,
            variable=self._wm_text_size, height=14,
            progress_color=APPLE_ORANGE, button_color=APPLE_ORANGE,
            command=lambda v: (
                self._text_size_lbl.configure(text=f"{int(float(v))}"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        tpos_row = ctk.CTkFrame(text_col, fg_color="transparent")
        tpos_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(tpos_row, text="Vị trí:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            tpos_row,
            values=["Góc trái trên", "Góc phải trên",
                    "Góc trái dưới", "Góc phải dưới", "Giữa"],
            variable=self._wm_text_pos,
            width=130, height=26, corner_radius=6,
            fg_color=BG_PILL, button_color=BG_PILL, button_hover_color=BG_PILL_HOV,
            text_color=TEXT_PRIMARY, font=("Arial", 10),
            command=lambda _: self._schedule_preview(),
        ).pack(side="left", fill="x", expand=True)

        color_row = ctk.CTkFrame(text_col, fg_color="transparent")
        color_row.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkLabel(color_row, text="Màu:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        self._text_color_btn = ctk.CTkButton(
            color_row, text="  ", width=32, height=24, corner_radius=5,
            fg_color=self._wm_text_color, hover_color=self._wm_text_color,
            border_width=1, border_color="#64748B",
            command=self._pick_text_color,
        )
        self._text_color_btn.pack(side="left", padx=(0, 8))
        ctk.CTkCheckBox(
            color_row, text="Bold", variable=self._wm_text_bold,
            font=("Arial", 10), text_color=TEXT_SECONDARY,
            checkbox_width=14, checkbox_height=14, corner_radius=3,
            border_color=BORDER_CARD, checkmark_color="white", fg_color=APPLE_ORANGE,
            command=self._schedule_preview,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(
            color_row, text="Shadow", variable=self._wm_text_shadow,
            font=("Arial", 10), text_color=TEXT_SECONDARY,
            checkbox_width=14, checkbox_height=14, corner_radius=3,
            border_color=BORDER_CARD, checkmark_color="white", fg_color=APPLE_PURPLE,
            command=self._schedule_preview,
        ).pack(side="left")

        box_row = ctk.CTkFrame(text_col, fg_color="transparent")
        box_row.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkCheckBox(
            box_row, text="Hộp nền", variable=self._wm_text_box,
            font=("Arial", 10), text_color=TEXT_SECONDARY,
            checkbox_width=14, checkbox_height=14, corner_radius=3,
            border_color=BORDER_CARD, checkmark_color="white", fg_color=APPLE_BLUE,
            command=self._schedule_preview,
        ).pack(side="left", padx=(0, 6))
        self._box_color_btn = ctk.CTkButton(
            box_row, text="  ", width=28, height=22, corner_radius=4,
            fg_color=self._wm_text_box_color, hover_color=self._wm_text_box_color,
            border_width=1, border_color=BORDER_CARD,
            command=self._pick_box_color,
        )
        self._box_color_btn.pack(side="left", padx=(0, 6))
        _boxop_init = int(float(self._wm_text_box_opacity.get()))
        self._box_op_lbl = ctk.CTkLabel(
            box_row, text=f"{_boxop_init}%",
            font=("Consolas", 10, "bold"), text_color=TEXT_SECONDARY, width=32
        )
        self._box_op_lbl.pack(side="right")
        ctk.CTkSlider(
            box_row, from_=0, to=100, number_of_steps=100,
            variable=self._wm_text_box_opacity, height=14,
            progress_color=APPLE_BLUE, button_color=APPLE_BLUE,
            command=lambda v: (
                self._box_op_lbl.configure(text=f"{int(float(v))}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # ── Text Offset X ──
        text_offx_row = ctk.CTkFrame(text_col, fg_color="transparent")
        text_offx_row.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 2))
        ctk.CTkLabel(text_offx_row, text="Lệch X:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        _toffx_init = int(float(self._wm_text_offset_x.get()) * 100)
        self._text_offx_lbl = ctk.CTkLabel(
            text_offx_row, text=f"{_toffx_init:+d}%",
            font=("Consolas", 10, "bold"), text_color=APPLE_ORANGE, width=36
        )
        self._text_offx_lbl.pack(side="right")
        ctk.CTkSlider(
            text_offx_row, from_=-0.50, to=0.50, number_of_steps=200,
            variable=self._wm_text_offset_x, height=14,
            progress_color=APPLE_ORANGE, button_color=APPLE_ORANGE,
            command=lambda v: (
                self._text_offx_lbl.configure(text=f"{int(float(v)*100):+d}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # ── Text Offset Y ──
        text_offy_row = ctk.CTkFrame(text_col, fg_color="transparent")
        text_offy_row.grid(row=8, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkLabel(text_offy_row, text="Lệch Y:",
                     font=("Arial", 10), text_color=TEXT_SECONDARY, width=70, anchor="w").pack(side="left")
        _toffy_init = int(float(self._wm_text_offset_y.get()) * 100)
        self._text_offy_lbl = ctk.CTkLabel(
            text_offy_row, text=f"{_toffy_init:+d}%",
            font=("Consolas", 10, "bold"), text_color=APPLE_ORANGE, width=36
        )
        self._text_offy_lbl.pack(side="right")
        ctk.CTkSlider(
            text_offy_row, from_=-0.50, to=0.50, number_of_steps=200,
            variable=self._wm_text_offset_y, height=14,
            progress_color=APPLE_ORANGE, button_color=APPLE_ORANGE,
            command=lambda v: (
                self._text_offy_lbl.configure(text=f"{int(float(v)*100):+d}%"),
                self._schedule_preview()
            ),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))


    # ─────────────────────────────────────────────────────────
    # Drag & Drop Setup
    # ─────────────────────────────────────────────────────────

    def _setup_dnd(self):
        if not HAS_TKDND or DND_FILES is None:
            return
        for widget in [self, self._drop_frame, self._file_box]:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
                widget.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

    def _on_drag_enter(self, event=None):
        try:
            self._drop_frame.configure(border_color=APPLE_BLUE, border_width=2)
            self._lbl_drop.configure(text_color=APPLE_BLUE)
        except Exception:
            pass

    def _on_drag_leave(self, event=None):
        try:
            self._drop_frame.configure(border_color=BORDER_INSET, border_width=2)
            self._lbl_drop.configure(text_color=TEXT_TERTIARY)
        except Exception:
            pass

    def _on_drop(self, event):
        self._on_drag_leave()
        raw = getattr(event, "data", "")
        if not raw:
            return
        try:
            files = list(self.tk.splitlist(raw))
        except Exception:
            files = [raw.strip("{}").strip()]
        paths = [os.path.abspath(f.strip().strip("\"'")) for f in files if f.strip()]
        self._add_paths(paths)

    # ─────────────────────────────────────────────────────────
    # File Management
    # ─────────────────────────────────────────────────────────

    def _add_files(self):
        import tkinter.filedialog as fd
        files = fd.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Chọn ảnh để nén",
            filetypes=[("Ảnh", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.tif"),
                       ("Tất cả", "*.*")]
        )
        if files:
            self._add_paths(list(files))

    def _add_folder(self):
        import tkinter.filedialog as fd
        folder = fd.askdirectory(parent=self.winfo_toplevel(), title="Chọn thư mục chứa ảnh")
        if folder:
            self._add_paths([folder])

    def _add_paths(self, paths: List[str]):
        found = scan_images(paths)
        new = [p for p in found if p not in self._image_paths]
        self._image_paths.extend(new)
        self._refresh_file_list()
        if new:
            msg = f"✅ Đã thêm {len(new)} ảnh mới. Tổng: {len(self._image_paths)} ảnh.\n"
            self._log_result(msg)
            self._log_to_parent(f"🖼️ [Nén ảnh] Đã nạp {len(new)} ảnh (Tổng: {len(self._image_paths)} ảnh).")
            # Cập nhật filename hint và refresh preview tự động
            self._update_filename_hint()
            self._schedule_preview()

    def _clear_list(self):
        self._image_paths.clear()
        self._cached_preview_thumb = None
        self._cached_preview_src = ""
        self._current_preview_index = 0
        self._refresh_file_list()
        self._clear_results()
        self._refresh_preview()

    def _refresh_file_list(self):
        self._lbl_count.configure(text=f"{len(self._image_paths)} ảnh đã thêm")
        self._file_box.configure(state="normal")
        self._file_box.delete("1.0", "end")
        for p in self._image_paths:
            size_kb = os.path.getsize(p) / 1024.0
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            self._file_box.insert("end", f"  [{size_str:>8}]  {os.path.basename(p)}\n")
        self._file_box.configure(state="disabled")

    # ─────────────────────────────────────────────────────────
    # Settings Helpers
    # ─────────────────────────────────────────────────────────

    def _save_img_settings(self):
        """Lưu toàn bộ thông số Image Compressor vào config để khôi phục khi mở lại."""
        try:
            cfg = getattr(self, "_app_config", None)
            if cfg is None or not isinstance(cfg, dict):
                cfg = load_config()
                self._app_config = cfg

            cfg["img_compress_enabled"] = bool(self._compress_enabled.get())
            cfg["img_target_value"]     = str(self._target_var.get()).strip()
            cfg["img_target_unit"]      = str(self._unit_var.get()).strip()
            cfg["img_output_format"]    = str(self._fmt_var.get()).strip()
            cfg["img_keep_exif"]        = bool(self._exif_var.get())
            cfg["img_output_dir"]       = str(self._out_dir_var.get()).strip()

            cfg["img_wm_logo_enabled"]  = bool(self._wm_logo_enabled.get())
            cfg["img_wm_logo_path"]     = str(self._wm_logo_path.get()).strip()
            cfg["img_wm_logo_scale"]    = float(self._wm_logo_scale.get())
            cfg["img_wm_logo_pos"]      = str(self._wm_logo_pos.get())
            cfg["img_wm_logo_opacity"]  = int(self._wm_logo_opacity.get())
            cfg["img_wm_logo_offset_x"] = float(self._wm_logo_offset_x.get())
            cfg["img_wm_logo_offset_y"] = float(self._wm_logo_offset_y.get())

            cfg["img_wm_text_enabled"]  = bool(self._wm_text_enabled.get())
            cfg["img_wm_text_source"]   = str(self._wm_text_source.get())
            cfg["img_wm_text_custom"]   = str(self._wm_text_custom.get())
            cfg["img_wm_text_pos"]      = str(self._wm_text_pos.get())
            cfg["img_wm_text_size"]     = int(self._wm_text_size.get())
            cfg["img_wm_text_color"]    = str(self._wm_text_color)
            cfg["img_wm_text_bold"]     = bool(self._wm_text_bold.get())
            cfg["img_wm_text_shadow"]   = bool(self._wm_text_shadow.get())
            cfg["img_wm_text_box"]      = bool(self._wm_text_box.get())
            cfg["img_wm_text_box_color"]= str(self._wm_text_box_color)
            cfg["img_wm_text_box_opacity"] = int(self._wm_text_box_opacity.get())
            cfg["img_wm_text_offset_x"] = float(self._wm_text_offset_x.get())
            cfg["img_wm_text_offset_y"] = float(self._wm_text_offset_y.get())

            # Đồng bộ cả sub-dictionary "image_compressor" để tương thích tối đa
            cfg["image_compressor"] = {
                "compress_enabled": cfg["img_compress_enabled"],
                "target_value": cfg["img_target_value"],
                "target_unit": cfg["img_target_unit"],
                "output_format": cfg["img_output_format"],
                "keep_exif": cfg["img_keep_exif"],
                "output_dir": cfg["img_output_dir"],
                "logo_enabled": cfg["img_wm_logo_enabled"],
                "logo_path": cfg["img_wm_logo_path"],
                "logo_scale": cfg["img_wm_logo_scale"],
                "logo_pos": cfg["img_wm_logo_pos"],
                "logo_opacity": cfg["img_wm_logo_opacity"],
                "logo_offset_x": cfg["img_wm_logo_offset_x"],
                "logo_offset_y": cfg["img_wm_logo_offset_y"],
                "text_enabled": cfg["img_wm_text_enabled"],
                "text_source": cfg["img_wm_text_source"],
                "text_custom": cfg["img_wm_text_custom"],
                "text_pos": cfg["img_wm_text_pos"],
                "text_size": cfg["img_wm_text_size"],
                "text_color": cfg["img_wm_text_color"],
                "text_bold": cfg["img_wm_text_bold"],
                "text_shadow": cfg["img_wm_text_shadow"],
                "text_box": cfg["img_wm_text_box"],
                "text_box_color": cfg["img_wm_text_box_color"],
                "text_box_opacity": cfg["img_wm_text_box_opacity"],
                "text_offset_x": cfg["img_wm_text_offset_x"],
                "text_offset_y": cfg["img_wm_text_offset_y"],
            }

            # Cập nhật config của cửa sổ chính (AppWindow / Toplevel) nếu có
            try:
                top = self.winfo_toplevel()
                if hasattr(top, "config") and isinstance(getattr(top, "config"), dict):
                    top.config.update(cfg)
            except Exception:
                pass

            if hasattr(self.parent, "config") and isinstance(getattr(self.parent, "config"), dict):
                self.parent.config.update(cfg)

            save_config(cfg)
        except Exception as e:
            print(f"[CompressorView] _save_img_settings error: {e}")

    def _show_success_banner(self, ok: int, total: int, saved_str: str, red_pct: float, elapsed_str: str, is_compress: bool):
        """Hiển thị Card Banner thông báo thành công rực rỡ ngay trên giao diện."""
        if not hasattr(self, "_success_banner"):
            return
        if is_compress:
            self._sb_title.configure(text=f"🎉 NÉN HOÀN TẤT: {ok}/{total} ẢNH THÀNH CÔNG!")
            self._sb_desc.configure(
                text=f"⏱️ Thời gian: {elapsed_str}  •  Tiết kiệm: {saved_str} (-{red_pct:.1f}%)  •  📁 Đã lưu vào: {self._out_dir_var.get()}"
            )
        else:
            self._sb_title.configure(text=f"🎉 ĐÓNG DẤU HOÀN TẤT: {ok}/{total} ẢNH THÀNH CÔNG!")
            self._sb_desc.configure(
                text=f"⏱️ Thời gian: {elapsed_str}  •  Giữ nguyên 100% chất lượng gốc  •  📁 Đã lưu vào: {self._out_dir_var.get()}"
            )
        self._success_banner.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))

    def _hide_success_banner(self):
        """Ẩn Card Banner thông báo thành công."""
        if hasattr(self, "_success_banner"):
            self._success_banner.grid_remove()

    def _set_preset(self, val: str, unit: str):
        self._target_var.set(val)
        self._unit_var.set(unit)
        self._save_img_settings()

    def _on_unit_change(self, _=None):
        self._save_img_settings()

    def _browse_out_dir(self):
        import tkinter.filedialog as fd
        folder = fd.askdirectory(parent=self.winfo_toplevel(), title="Chọn thư mục lưu ảnh nén")
        if folder:
            self._out_dir_var.set(folder)
            self._save_img_settings()

    def _open_out_dir(self):
        out = self._out_dir_var.get()
        if os.path.isdir(out):
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", out])
                elif sys.platform == "win32":
                    norm_path = os.path.normpath(str(out))
                    try:
                        os.startfile(norm_path)
                    except Exception:
                        subprocess.Popen(["explorer", norm_path])
                else:
                    subprocess.Popen(["xdg-open", out])
            except Exception:
                pass

    def _get_target_kb(self) -> int:
        try:
            val = float(self._target_var.get().strip())
            if self._unit_var.get() == "MB":
                return int(val * 1024)
            return int(val)
        except ValueError:
            return 500  # Default 500KB

    # ─────────────────────────────────────────────────────────
    # Compression & Watermark Mode Helpers
    # ─────────────────────────────────────────────────────────

    def _on_compress_toggle(self):
        """Bật/tắt chế độ nén dung lượng."""
        if self._compress_enabled.get():
            self._no_compress_hint.pack_forget()
            self._size_grp.pack(side="left")
        else:
            self._size_grp.pack_forget()
            self._no_compress_hint.pack(side="left")
        self._update_action_button_label()
        self._save_img_settings()

    def _update_action_button_label(self):
        """Cập nhật nhãn và trạng thái nút Bắt đầu theo ngữ cảnh nén / watermark."""
        if not hasattr(self, "_btn_start"):
            return
        if self._is_running:
            return

        compress_on = self._compress_enabled.get()
        logo_on = self._wm_logo_enabled.get()
        text_on = self._wm_text_enabled.get()
        wm_on = logo_on or text_on

        if compress_on and wm_on:
            self._btn_start.configure(
                text="🚀 Bắt Đầu (Nén + Đóng Dấu)",
                fg_color=APPLE_GREEN,
                hover_color=APPLE_GREEN_HOVER,
                text_color="#FFFFFF",
                state="normal"
            )
            self._lbl_status.configure(text="✨ Sẵn sàng: Vừa nén dung lượng vừa chèn Logo / Mã sản phẩm.")
        elif compress_on and not wm_on:
            self._btn_start.configure(
                text="🚀 Bắt Đầu Nén Ảnh",
                fg_color=APPLE_GREEN,
                hover_color=APPLE_GREEN_HOVER,
                text_color="#FFFFFF",
                state="normal"
            )
            self._lbl_status.configure(text="✨ Sẵn sàng: Chỉ nén giảm dung lượng ảnh (không đóng dấu).")
        elif not compress_on and wm_on:
            self._btn_start.configure(
                text="🏷️ Bắt Đầu Đóng Dấu",
                fg_color=APPLE_ORANGE,
                hover_color="#E08B00",
                text_color="#FFFFFF",
                state="normal"
            )
            self._lbl_status.configure(text="✨ Sẵn sàng: Chỉ chèn Logo & Mã SP (Giữ nguyên 100% chất lượng gốc).")
        else:
            self._btn_start.configure(
                text="⚠️ Chọn Ít Nhất 1 Thao Tác",
                fg_color=BG_PILL,
                hover_color=BG_PILL_HOV,
                text_color=TEXT_SECONDARY,
                state="disabled"
            )
            self._lbl_status.configure(text="⚠️ Vui lòng bật ít nhất một tùy chọn: 'Nén dung lượng' hoặc 'Watermark'.")

    def _on_wm_toggle(self):
        """Refresh preview và cập nhật trạng thái nút khi bật/tắt watermark."""
        self._update_action_button_label()
        self._schedule_preview()
        self._save_img_settings()

    def _on_text_source_change(self, value: str):
        """Chuyển đổi giao diện giữa lấy tên file tự động và nhập text tuỳ chỉnh."""
        if value == "Tuỳ chỉnh":
            try:
                self._filename_hint_lbl.grid_remove()
            except Exception:
                pass
            self._text_custom_entry.grid(row=0, column=0, sticky="ew")
        else:
            try:
                self._text_custom_entry.grid_remove()
            except Exception:
                pass
            self._filename_hint_lbl.grid(row=0, column=0, sticky="ew")
            self._update_filename_hint()
        self._schedule_preview()

    def _browse_logo(self):
        import tkinter.filedialog as fd
        path = fd.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Chọn file logo",
            filetypes=[("Hình ảnh", "*.png *.jpg *.jpeg *.webp *.bmp"),
                       ("Tất cả", "*.*")],
        )
        if path:
            self._wm_logo_path.set(path)
            self._wm_logo_enabled.set(True)  # Tự động kích hoạt switch logo khi chọn file
            self._update_action_button_label()
            self._schedule_preview()
            self._save_img_settings()

    def _pick_text_color(self):
        import tkinter.colorchooser as cc
        color = cc.askcolor(color=self._wm_text_color, parent=self.winfo_toplevel(), title="Chọn màu chữ")
        if color and color[1]:
            self._wm_text_color = color[1]
            self._text_color_btn.configure(
                fg_color=self._wm_text_color,
                hover_color=self._wm_text_color,
            )
            self._schedule_preview()
            self._save_img_settings()

    def _pick_box_color(self):
        import tkinter.colorchooser as cc
        color = cc.askcolor(color=self._wm_text_box_color, parent=self.winfo_toplevel(), title="Chọn màu hộp nền")
        if color and color[1]:
            self._wm_text_box_color = color[1]
            self._box_color_btn.configure(
                fg_color=self._wm_text_box_color,
                hover_color=self._wm_text_box_color,
            )
            self._schedule_preview()
            self._save_img_settings()

    _POS_MAP = {
        "Góc trái trên": "top-left",
        "Góc phải trên": "top-right",
        "Góc trái dưới": "bottom-left",
        "Góc phải dưới": "bottom-right",
        "Giữa": "center",
    }

    def _build_watermark_config(self) -> Optional[WatermarkConfig]:
        """Đọc toàn bộ settings watermark GUI và trả về WatermarkConfig.
        Nếu cả logo và text đều tắt thì trả None để bỏ qua bước watermark."""
        logo_on = self._wm_logo_enabled.get()
        text_on = self._wm_text_enabled.get()
        if not logo_on and not text_on:
            return None
        text_src = "filename" if self._wm_text_source.get() == "Tên file ảnh" else "custom"
        return WatermarkConfig(
            logo_enabled=logo_on,
            logo_path=self._wm_logo_path.get().strip(),
            logo_scale=float(self._wm_logo_scale.get()),
            logo_position=self._POS_MAP.get(self._wm_logo_pos.get(), "bottom-right"),
            logo_opacity=int(self._wm_logo_opacity.get()),
            logo_offset_x=float(self._wm_logo_offset_x.get()),
            logo_offset_y=float(self._wm_logo_offset_y.get()),
            text_enabled=text_on,
            text_source=text_src,
            text_custom=self._wm_text_custom.get().strip(),
            text_position=self._POS_MAP.get(self._wm_text_pos.get(), "bottom-left"),
            text_size=int(self._wm_text_size.get()),
            text_color=self._wm_text_color,
            text_bold=self._wm_text_bold.get(),
            text_shadow=self._wm_text_shadow.get(),
            text_box=self._wm_text_box.get(),
            text_box_color=self._wm_text_box_color,
            text_box_opacity=int(self._wm_text_box_opacity.get()),
            text_offset_x=float(self._wm_text_offset_x.get()),
            text_offset_y=float(self._wm_text_offset_y.get()),
        )

    def _schedule_preview(self, *_):
        """Debounce 60ms siêu mượt rồi gọi _refresh_preview() trên main thread."""
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.after(60, self._refresh_preview)

    def _update_filename_hint(self):
        """Cập nhật label hint tên file khi nguồn = Tên file ảnh."""
        try:
            if self._image_paths:
                idx = min(self._current_preview_index, len(self._image_paths) - 1)
                name = Path(self._image_paths[idx]).stem
                self._filename_hint_lbl.configure(text=f"🏷️ Mã: {name}")
            else:
                self._filename_hint_lbl.configure(text="🏷️ Tự động lấy tên file ảnh")
        except Exception:
            pass

    def _prepare_preview_base(self, force: bool = False):
        """Tạo và cache thumbnail cơ sở cho ảnh đang chọn xem trước."""
        if not self._image_paths:
            self._cached_preview_thumb = None
            self._cached_preview_src = ""
            return

        if self._current_preview_index >= len(self._image_paths):
            self._current_preview_index = 0
        src = self._image_paths[self._current_preview_index]

        if not force and self._cached_preview_thumb is not None and self._cached_preview_src == src:
            return

        try:
            img = Image.open(src)
            from PIL import ImageOps as _IOS
            img = _IOS.exif_transpose(img)
            self._cached_orig_size = img.size
            # Cache bản độ phân giải cao (1200x1200) để khi zoom không vỡ nét
            base = img.copy()
            base.thumbnail((1200, 1200), Image.LANCZOS)
            self._cached_preview_thumb = base
            self._cached_preview_src = src
        except Exception:
            self._cached_preview_thumb = None
            self._cached_preview_src = ""

    def _refresh_preview(self, force_reload: bool = False):
        """Render watermark siêu tốc (<10ms) trên thumbnail cached rồi cập nhật ngay."""
        self._preview_job = None
        if not self.winfo_exists():
            return

        if not self._image_paths:
            self._preview_label.configure(
                image=None,
                text="Chưa có ảnh.\n\nKéo & thả hoặc bấm '📂 Thêm Ảnh'\nđể xem trước logo và mã sản phẩm tại đây."
            )
            self._preview_info_lbl.configure(text="Chưa nạp ảnh")
            if hasattr(self, "_lbl_zoom_val"):
                self._lbl_zoom_val.configure(text="Fit")
            return

        self._prepare_preview_base(force=force_reload)
        if self._cached_preview_thumb is None:
            self._preview_label.configure(image=None, text="⚠️ Không thể đọc file ảnh này.")
            return

        src = self._cached_preview_src
        cfg = self._build_watermark_config()

        import time
        t0 = time.time()

        # Tính toán kích thước hiển thị chính xác theo Viewport và Tỉ lệ Zoom
        orig_w, orig_h = getattr(self, "_cached_orig_size", self._cached_preview_thumb.size)
        if orig_w <= 0 or orig_h <= 0:
            orig_w, orig_h = self._cached_preview_thumb.size

        # Kích thước viewport khả dụng thực tế của view_card
        card_w = 376
        card_h = 480
        if hasattr(self, "_preview_view_card"):
            try:
                cw = self._preview_view_card.winfo_width() - 20
                ch = self._preview_view_card.winfo_height() - 20
                if cw > 150:
                    card_w = cw
                if ch > 150:
                    card_h = ch
            except Exception:
                pass

        # Tính kích thước Fit vừa vặn 100% trong khung (không tràn viền, không xén mép)
        fit_scale = min(card_w / orig_w, card_h / orig_h)
        base_fit_w = max(10, int(orig_w * fit_scale))
        base_fit_h = max(10, int(orig_h * fit_scale))

        zoom = getattr(self, "_preview_zoom_factor", 1.0)
        target_w = max(10, int(base_fit_w * zoom))
        target_h = max(10, int(base_fit_h * zoom))

        work_img = self._cached_preview_thumb.copy()
        work_img.thumbnail((target_w, target_h), Image.BILINEAR)

        if self._preview_show_original or cfg is None:
            result = work_img
        else:
            result = apply_watermark(work_img, cfg, src)

        elapsed_ms = max(1, int((time.time() - t0) * 1000))

        try:
            w, h = result.size
            thumb = ctk.CTkImage(light_image=result, dark_image=result, size=(w, h))
            self._preview_photo = thumb
            self._preview_label.configure(image=thumb, text="")

            # Cập nhật thông tin chi tiết và thanh điều hướng
            total = len(self._image_paths)
            idx_display = self._current_preview_index + 1
            name = os.path.basename(src)
            zoom_pct = int(zoom * 100)
            zoom_str = "Vừa khung" if abs(zoom - 1.0) < 0.02 else f"{zoom_pct}%"
            mode_str = " (Ảnh gốc)" if self._preview_show_original else ""
            self._preview_info_lbl.configure(
                text=f"[{idx_display}/{total}] {name} • {orig_w}×{orig_h} • {zoom_str} • ⚡{elapsed_ms}ms{mode_str}"
            )
            if hasattr(self, "_lbl_zoom_val"):
                self._lbl_zoom_val.configure(text=f"{zoom_pct}%" if abs(zoom - 1.0) >= 0.02 else "Fit")
            self._update_filename_hint()
        except Exception as exc:
            self._preview_label.configure(text=f"⚠️ Hiển thị lỗi: {exc}", image=None)

    def _zoom_to(self, factor: float):
        """Đặt tỉ lệ thu phóng xem trước ảnh."""
        factor = max(0.3, min(2.0, factor))
        self._preview_zoom_factor = factor
        if hasattr(self, "_preview_zoom_var"):
            self._preview_zoom_var.set(factor)
        if hasattr(self, "_lbl_zoom_val"):
            pct = int(factor * 100)
            self._lbl_zoom_val.configure(text=f"{pct}%" if abs(factor - 1.0) >= 0.02 else "Fit")
        self._refresh_preview()

    def _zoom_in(self):
        """Phóng to thêm 15%."""
        curr = getattr(self, "_preview_zoom_factor", 1.0)
        self._zoom_to(round(curr + 0.15, 2))

    def _zoom_out(self):
        """Thu nhỏ bớt 15%."""
        curr = getattr(self, "_preview_zoom_factor", 1.0)
        self._zoom_to(round(curr - 0.15, 2))

    def _zoom_fit(self):
        """Đặt lại kích thước vừa vặn hoàn hảo trong khung."""
        self._zoom_to(1.0)

    def _on_zoom_slider(self, val):
        """Bắt sự kiện trượt thanh zoom."""
        self._preview_zoom_factor = float(val)
        if hasattr(self, "_lbl_zoom_val"):
            pct = int(float(val) * 100)
            self._lbl_zoom_val.configure(text=f"{pct}%" if abs(float(val) - 1.0) >= 0.02 else "Fit")
        self._schedule_preview()

    def _on_view_card_resize(self, event):
        """Tự động điều chỉnh tỉ lệ vừa khung khi kích thước cửa sổ thay đổi."""
        if getattr(self, "_preview_zoom_factor", 1.0) == 1.0 and getattr(self, "_cached_preview_thumb", None) is not None:
            self._schedule_preview()

    def _prev_preview_image(self):
        """Chuyển sang xem trước ảnh phía trước trong batch."""
        if not self._image_paths:
            return
        self._current_preview_index = (self._current_preview_index - 1) % len(self._image_paths)
        self._refresh_preview(force_reload=True)

    def _next_preview_image(self):
        """Chuyển sang xem trước ảnh tiếp theo trong batch."""
        if not self._image_paths:
            return
        self._current_preview_index = (self._current_preview_index + 1) % len(self._image_paths)
        self._refresh_preview(force_reload=True)

    def _toggle_compare_preview(self):
        """Bật/tắt so sánh giữa ảnh gốc và ảnh đã chèn watermark."""
        self._preview_show_original = not self._preview_show_original
        if self._preview_show_original:
            self._btn_compare.configure(text="🏷️ Watermark", fg_color=APPLE_ORANGE)
        else:
            self._btn_compare.configure(text="👁️ Gốc", fg_color=BG_PILL)
        self._refresh_preview()


    # ─────────────────────────────────────────────────────────
    # Run / Cancel
    # ─────────────────────────────────────────────────────────

    def _start(self):
        if self._is_running:
            return
        if not self._image_paths:
            self._lbl_status.configure(text="⚠️ Chưa có ảnh nào trong danh sách!")
            return

        compress_on = self._compress_enabled.get()
        wm_config = self._build_watermark_config()  # None nếu không bật

        if not compress_on and wm_config is None:
            self._lbl_status.configure(text="⚠️ Vui lòng bật ít nhất một tùy chọn: 'Nén dung lượng' hoặc 'Watermark'!")
            return

        target_kb = self._get_target_kb()
        out_dir = self._out_dir_var.get().strip()
        keep_exif = self._exif_var.get()
        fmt_raw = self._fmt_var.get()
        fmt = "auto" if fmt_raw == "Tự động" else fmt_raw

        # Giữ nguyên 100% tên file gốc khi xuất file theo yêu cầu
        suffix = ""
        tasks = [
            CompressTask(
                src_path=p,
                dst_path=build_output_path(p, out_dir, suffix, output_format=fmt),
                target_kb=target_kb,
                compress_enabled=compress_on,
                keep_exif=keep_exif,
                output_format=fmt,
                watermark=wm_config,
            )
            for p in self._image_paths
        ]

        self._is_running = True
        self._results.clear()
        self._clear_results()
        self._hide_success_banner()
        self._btn_start.configure(state="disabled")
        self._btn_cancel.configure(state="normal")
        self._progress_bar.set(0.0)
        self._pct_badge.configure(text="0%")
        self._stat_badge.configure(text="")
        if hasattr(self, "_time_badge"):
            self._time_badge.configure(text="⏱️ 00:00")
        self._start_timer()

        action_verb = "nén" if compress_on else "đóng dấu"
        action_title = "Nén ảnh" if compress_on else "Đóng dấu ảnh"
        self._lbl_status.configure(text=f"🚀 Đang {action_verb} {len(tasks)} ảnh...", text_color=APPLE_CYAN)

        if compress_on:
            target_disp = f"{target_kb} KB" if target_kb < 1024 else f"{target_kb/1024:.1f} MB"
            mode_desc = f"mục tiêu ≤ {target_disp}"
        else:
            mode_desc = "giữ 100% chất lượng gốc (không nén)"

        wm_disp = ""
        if wm_config:
            parts = []
            if wm_config.logo_enabled:
                parts.append("Logo")
            if wm_config.text_enabled:
                parts.append("Text")
            wm_disp = f" + Watermark ({', '.join(parts)})" if parts else ""
        start_msg = f"🚀 Bắt đầu {action_verb} {len(tasks)} ảnh → {mode_desc}{wm_disp}\n"
        self._log_result(start_msg)
        if compress_on:
            self._log_result(f"{'Tên file':<35} {'Gốc':>9}  {'Sau':>9}  {'Giảm':>7}  {'Kích thước'}\n")
        else:
            self._log_result(f"{'Tên file':<35} {'Gốc':>9}  {'Sau':>9}  {'Chất lượng':>10}  {'Kích thước'}\n")
        self._log_result("─" * 80 + "\n")

        self._log_to_parent(f"🚀 [{action_title}] Bắt đầu xử lý {len(tasks)} ảnh → {mode_desc}{wm_disp}...")

        self._engine.compress_batch(
            tasks=tasks,
            on_progress=self._on_progress,
            on_done=self._on_done,
        )

    def _cancel(self):
        self._stop_timer()
        self._engine.cancel()
        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        self._lbl_status.configure(text=f"⏹ Đã yêu cầu dừng sau {elapsed:.1f}s...")
        self._log_to_parent(f"⏹ [Xử lý ảnh] Người dùng đã nhấn dừng tiến trình sau {elapsed:.1f}s.")

    # ─────────────────────────────────────────────────────────
    # Callbacks (từ background thread sang main UI thread)
    # ─────────────────────────────────────────────────────────

    def _on_progress(self, current: int, total: int, result: CompressResult):
        self._msg_queue.put({"type": "progress", "current": current, "total": total, "result": result})

    def _on_done(self, results: List[CompressResult]):
        self._msg_queue.put({"type": "done", "results": results})

    def _update_progress(self, current: int, total: int, result: CompressResult):
        pct = current / total if total > 0 else 0
        self._progress_bar.set(pct)
        self._pct_badge.configure(text=f"{int(pct*100)}%")
        compress_on = self._compress_enabled.get()
        action_verb = "nén" if compress_on else "đóng dấu"

        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        time_txt = f"{mins:02d}:{secs:02d}"

        self._lbl_status.configure(
            text=f"🚀 Đang {action_verb} {current}/{total} ảnh ({int(pct*100)}%) • ⏱️ {time_txt}..."
        )

        name = os.path.basename(result.src_path)[:34]
        if result.success:
            src_s = self._fmt_kb(result.src_size_kb)
            dst_s = self._fmt_kb(result.dst_size_kb)
            if compress_on:
                red = f"-{result.reduction_pct:.0f}%" if result.reduction_pct >= 0 else f"+{-result.reduction_pct:.0f}%"
            else:
                red = "Gốc 100%"
            dim   = f"{result.width}×{result.height}"
            line  = f"  ✅ {name:<33} {src_s:>9}  {dst_s:>9}  {red:>10 if not compress_on else 7}  {dim}\n"
        else:
            line  = f"  ❌ {name:<33} Lỗi: {result.error}\n"

        self._log_result(line)
        action_tag = "Nén ảnh" if compress_on else "Đóng dấu"
        self._log_to_parent(f"🖼️ [{action_tag}] {line.strip()}")

    def _finalize(self, results: List[CompressResult]):
        self._results = results
        self._is_running = False
        self._stop_timer()
        self._update_action_button_label()
        self._btn_cancel.configure(state="disabled")
        self._progress_bar.set(1.0)
        self._pct_badge.configure(text="100%")

        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        mins = int(elapsed // 60)
        secs = elapsed % 60
        if mins > 0:
            elapsed_str = f"{mins}p {secs:.1f}s"
        else:
            elapsed_str = f"{secs:.1f}s"

        if hasattr(self, "_time_badge"):
            self._time_badge.configure(text=f"⏱️ {elapsed_str}")

        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        total_src = sum(r.src_size_kb for r in results if r.success)
        total_dst = sum(r.dst_size_kb for r in results if r.success)
        saved = max(0.0, total_src - total_dst)
        red_pct = (saved / total_src * 100) if total_src > 0 else 0.0

        compress_on = self._compress_enabled.get()
        if compress_on:
            summary_line = (
                f"📊 Kết quả: {ok} thành công, {fail} thất bại  |  "
                f"Gốc: {_fmt_kb(total_src)}  →  Sau: {_fmt_kb(total_dst)}  "
                f"|  Tiết kiệm: {_fmt_kb(saved)} (-{red_pct:.1f}%)"
            )
            action_tag = "Nén ảnh"
            stat = f"✅ {ok}/{len(results)} ảnh  •  ⏱️ {elapsed_str}  •  Tiết kiệm {_fmt_kb(saved)}"
            status_text = f"🎉 Hoàn tất trong {elapsed_str}! {ok} ảnh nén thành công vào: {self._out_dir_var.get()}"
        else:
            summary_line = (
                f"📊 Kết quả: {ok} thành công, {fail} thất bại  |  "
                f"Tổng dung lượng xuất: {_fmt_kb(total_dst)}  |  "
                f"Chất lượng: Giữ nguyên 100% gốc (Không nén)"
            )
            action_tag = "Đóng dấu ảnh"
            stat = f"✅ {ok}/{len(results)} ảnh  •  ⏱️ {elapsed_str}  •  Đã chèn watermark"
            status_text = f"🎉 Hoàn tất trong {elapsed_str}! {ok} ảnh đã đóng dấu thành công vào: {self._out_dir_var.get()}"

        time_msg = f"⏱️ Thời gian thực hiện: {elapsed_str}"
        if ok > 0:
            time_msg += f" (trung bình {elapsed/ok:.2f}s / ảnh)"

        self._log_result("\n" + "─" * 80 + "\n")
        self._log_result(summary_line + "\n")
        self._log_result(time_msg + "\n")
        self._log_to_parent(f"🎉 [{action_tag}] {summary_line}")
        self._log_to_parent(f"⏱️ [{action_tag}] {time_msg}")
        self._log_to_parent(f"📁 [{action_tag}] Thư mục lưu: {self._out_dir_var.get()}")

        self._stat_badge.configure(text=stat)
        self._lbl_status.configure(text=status_text, text_color=APPLE_GREEN)

        # Hiển thị Banner Card thông báo thành công rực rỡ ngay trên giao diện
        self._show_success_banner(ok, len(results), _fmt_kb(saved), red_pct, elapsed_str, compress_on)

        # Phát âm thanh thông báo hệ thống cross-platform (macOS / Windows)
        _play_system_sound()

        # Hiển thị Popup hoàn tất nổi bật cho người dùng sau 200ms
        def _launch_modal():
            try:
                # Dùng winfo_toplevel() để luôn lấy cửa sổ gốc (hoạt động đúng cả Frame và Toplevel)
                _modal_parent = self.winfo_toplevel()
                modal = CompressCompletionModal(
                    _modal_parent,
                    ok_count=ok,
                    total_count=len(results),
                    src_size_str=_fmt_kb(total_src),
                    dst_size_str=_fmt_kb(total_dst),
                    saved_str=_fmt_kb(saved),
                    reduction_pct=red_pct,
                    out_dir=self._out_dir_var.get(),
                    is_compress_mode=compress_on,
                    elapsed_str=elapsed_str,
                )
                modal.lift()
                modal.focus_force()
            except Exception as e:
                print(f"[CompressorView] Completion modal error: {e}")

        self.after(200, _launch_modal)


    # ─────────────────────────────────────────────────────────
    # Log Helpers
    # ─────────────────────────────────────────────────────────

    def _log_result(self, text: str):
        self._result_box.configure(state="normal")
        self._result_box.insert("end", text)
        self._result_box.see("end")
        self._result_box.configure(state="disabled")

    def _clear_results(self):
        self._result_box.configure(state="normal")
        self._result_box.delete("1.0", "end")
        self._result_box.configure(state="disabled")
        self._progress_bar.set(0.0)
        self._pct_badge.configure(text="0%")
        self._stat_badge.configure(text="")
        self._lbl_status.configure(text="✨ Sẵn sàng nén ảnh.")

    @staticmethod
    def _fmt_kb(kb: float) -> str:
        return _fmt_kb(kb)


# ─────────────────────────────────────────────────────────────
# ImageCompressorView — View nhúng vào Main Canvas (không phải popup)
# Kế thừa toàn bộ logic từ ImageCompressorDialog nhưng là CTkFrame
# ─────────────────────────────────────────────────────────────

class ImageCompressorView(ctk.CTkFrame):
    """
    View nén ảnh hàng loạt nhúng trực tiếp vào Main Canvas của AppWindow.
    Giống hệt ImageCompressorDialog về giao diện và logic,
    nhưng kế thừa CTkFrame thay vì CTkToplevel nên không mở cửa sổ riêng.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_WINDOW, **kwargs)
        self.parent = parent

        # Grid fill toàn bộ
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=420)
        self.grid_rowconfigure(0, weight=1)

        self._init_state()
        self._build_ui()
        self._setup_dnd()

        self._msg_queue = queue.Queue()
        self.after(50, self._poll_queue)

    # ── Tái dùng toàn bộ logic từ ImageCompressorDialog ──
    _init_state           = ImageCompressorDialog._init_state
    _save_img_settings    = ImageCompressorDialog._save_img_settings
    _schedule_save_settings = ImageCompressorDialog._schedule_save_settings
    _show_success_banner  = ImageCompressorDialog._show_success_banner
    _hide_success_banner  = ImageCompressorDialog._hide_success_banner
    _start_timer          = ImageCompressorDialog._start_timer
    _tick_timer           = ImageCompressorDialog._tick_timer
    _stop_timer           = ImageCompressorDialog._stop_timer
    _poll_queue           = ImageCompressorDialog._poll_queue
    _log_to_parent        = ImageCompressorDialog._log_to_parent
    _build_ui             = ImageCompressorDialog._build_ui
    _build_preview_sidebar= ImageCompressorDialog._build_preview_sidebar
    _build_watermark_card = ImageCompressorDialog._build_watermark_card
    _setup_dnd            = ImageCompressorDialog._setup_dnd
    _on_drag_enter        = ImageCompressorDialog._on_drag_enter
    _on_drag_leave        = ImageCompressorDialog._on_drag_leave
    _on_drop              = ImageCompressorDialog._on_drop
    _add_files            = ImageCompressorDialog._add_files
    _add_folder           = ImageCompressorDialog._add_folder
    _add_paths            = ImageCompressorDialog._add_paths
    _clear_list           = ImageCompressorDialog._clear_list
    _refresh_file_list    = ImageCompressorDialog._refresh_file_list
    _set_preset           = ImageCompressorDialog._set_preset
    _on_unit_change       = ImageCompressorDialog._on_unit_change
    _browse_out_dir       = ImageCompressorDialog._browse_out_dir
    _open_out_dir         = ImageCompressorDialog._open_out_dir
    _get_target_kb        = ImageCompressorDialog._get_target_kb
    _on_compress_toggle   = ImageCompressorDialog._on_compress_toggle
    _update_action_button_label = ImageCompressorDialog._update_action_button_label
    _on_wm_toggle         = ImageCompressorDialog._on_wm_toggle
    _on_text_source_change= ImageCompressorDialog._on_text_source_change
    _browse_logo          = ImageCompressorDialog._browse_logo
    _pick_text_color      = ImageCompressorDialog._pick_text_color
    _pick_box_color       = ImageCompressorDialog._pick_box_color
    _POS_MAP              = ImageCompressorDialog._POS_MAP
    _build_watermark_config = ImageCompressorDialog._build_watermark_config
    _schedule_preview     = ImageCompressorDialog._schedule_preview
    _update_filename_hint = ImageCompressorDialog._update_filename_hint
    _prepare_preview_base = ImageCompressorDialog._prepare_preview_base
    _refresh_preview      = ImageCompressorDialog._refresh_preview
    _zoom_to              = ImageCompressorDialog._zoom_to
    _zoom_in              = ImageCompressorDialog._zoom_in
    _zoom_out             = ImageCompressorDialog._zoom_out
    _zoom_fit             = ImageCompressorDialog._zoom_fit
    _on_zoom_slider       = ImageCompressorDialog._on_zoom_slider
    _on_view_card_resize  = ImageCompressorDialog._on_view_card_resize
    _prev_preview_image   = ImageCompressorDialog._prev_preview_image
    _next_preview_image   = ImageCompressorDialog._next_preview_image
    _toggle_compare_preview = ImageCompressorDialog._toggle_compare_preview
    _start                = ImageCompressorDialog._start
    _cancel               = ImageCompressorDialog._cancel
    _on_progress          = ImageCompressorDialog._on_progress
    _on_done              = ImageCompressorDialog._on_done
    _update_progress      = ImageCompressorDialog._update_progress
    _finalize             = ImageCompressorDialog._finalize
    _log_result           = ImageCompressorDialog._log_result
    _clear_results        = ImageCompressorDialog._clear_results
    _fmt_kb               = staticmethod(_fmt_kb)

    def add_initial_files(self, files: List[str]):
        """Nạp danh sách ảnh vào view (dùng khi kéo thả từ Main App)."""
        if files:
            self._add_paths(files)
