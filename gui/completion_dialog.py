"""
gui/completion_dialog.py — Popup thông báo hoàn tất xử lý video
Hiện ra sau khi pipeline xử lý xong với đầy đủ thông tin và các nút hành động.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import customtkinter as ctk

# ─── Design tokens (đồng bộ với app_window.py) ───────────────────────────────
BG_WINDOW     = "#141518"
BG_CARD       = "#1C1F27"
BG_INSET      = "#121419"
BORDER_CARD   = "#2E3342"
BORDER_INSET  = "#252834"
BG_PILL       = "#272B37"

APPLE_BLUE        = "#0A84FF"
APPLE_BLUE_HOVER  = "#0071E3"
APPLE_GREEN       = "#30D158"
APPLE_GREEN_HOVER = "#28B84C"
APPLE_ORANGE      = "#FF9F0A"
APPLE_ORANGE_BG   = "#331E08"

TEXT_PRIMARY   = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_MUTED     = "#636366"
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_size(path: str) -> str:
    """Trả về chuỗi dung lượng file dễ đọc (KB / MB / GB)."""
    try:
        sz = os.path.getsize(path)
        for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
            if sz >= threshold:
                return f"{sz / threshold:.1f} {unit}"
        return f"{sz} B"
    except OSError:
        return "N/A"


def _open_file(path: str) -> None:
    """Mở file bằng ứng dụng mặc định của hệ điều hành."""
    try:
        if not path:
            return
        p = Path(path).resolve()
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        elif sys.platform == "win32":
            os.startfile(os.path.normpath(str(p)))
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception:
        pass


def _reveal_file(path: str) -> None:
    """Mở thư mục chứa file và highlight đúng file đó, hoặc mở thư mục nếu là folder."""
    try:
        if not path:
            return
        p = Path(path).resolve()
        if sys.platform == "darwin":
            if p.is_file():
                subprocess.Popen(["open", "-R", str(p)])
            elif p.is_dir():
                subprocess.Popen(["open", str(p)])
            elif p.parent.exists():
                subprocess.Popen(["open", str(p.parent)])
        elif sys.platform == "win32":
            norm = os.path.normpath(str(p))
            if p.is_file():
                try:
                    subprocess.Popen(f'explorer /select,"{norm}"')
                except Exception:
                    os.startfile(os.path.normpath(str(p.parent)))
            elif p.is_dir():
                os.startfile(norm)
            elif p.parent.exists():
                os.startfile(os.path.normpath(str(p.parent)))
        else:
            folder = str(p) if p.is_dir() else str(p.parent)
            subprocess.Popen(["xdg-open", folder])
    except Exception:
        try:
            p_parent = Path(path).resolve().parent
            if p_parent.exists():
                if sys.platform == "win32":
                    os.startfile(os.path.normpath(str(p_parent)))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(p_parent)])
                else:
                    subprocess.Popen(["xdg-open", str(p_parent)])
        except Exception:
            pass


def _play_system_sound() -> None:
    """Phát âm thanh thông báo của hệ thống (bất đồng bộ, không block UI)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        elif sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        # Linux: bỏ qua (đa dạng quá, tránh lỗi)
    except Exception:
        pass


class CompletionDialog(ctk.CTkToplevel):
    """
    Popup thông báo hoàn tất xử lý — hiện sau khi pipeline trả về "success".

    Tham số:
        master       — cửa sổ cha (AppWindow)
        video_path   — đường dẫn file video đã xuất
        srt_path     — đường dẫn file .srt (hoặc None)
        txt_path     — đường dẫn file .txt (hoặc None)
        elapsed_str  — chuỗi thời gian xử lý dạng "mm:ss"
        on_new_video — callback gọi khi nhấn "Làm video tiếp theo" (reset UI)
    """

    def __init__(
        self,
        master,
        video_path: str = "",
        srt_path: Optional[str] = None,
        txt_path: Optional[str] = None,
        elapsed_str: str = "00:00",
        on_new_video=None,
        title_text: Optional[str] = None,
        subtitle_text: Optional[str] = None,
        custom_rows: Optional[list] = None,
    ):
        super().__init__(master)

        self._video_path   = video_path
        self._srt_path     = srt_path
        self._txt_path     = txt_path
        self._elapsed_str  = elapsed_str
        self._on_new_video = on_new_video
        self._title_text   = title_text or "XỬ LÝ VIDEO THÀNH CÔNG!"
        self._subtitle_text = subtitle_text or "Tất cả file đầu ra đã được lưu an toàn."
        self._custom_rows  = custom_rows

        self.title("🎉 Hoàn Tất Xử Lý")
        self.resizable(False, False)
        self.configure(fg_color=BG_WINDOW)

        # Luôn hiển thị trên cùng, sau đó thả ra để không annoying
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self._build_ui()

        # Căn giữa so với cửa sổ cha sau khi build xong
        self.update_idletasks()
        self._center_on_parent(master)

        # Phát âm thanh thông báo
        _play_system_sound()

    # ─── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer padding frame
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=28, pady=24)

        # ── Tiêu đề ──────────────────────────────────────────────────────────
        header_row = ctk.CTkFrame(outer, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(
            header_row,
            text="🎉",
            font=("Arial", 40),
        ).pack(side="left", padx=(0, 12))

        title_col = ctk.CTkFrame(header_row, fg_color="transparent")
        title_col.pack(side="left", fill="y")

        ctk.CTkLabel(
            title_col,
            text=self._title_text,
            font=("Arial", 18, "bold"),
            text_color=APPLE_GREEN,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col,
            text=self._subtitle_text,
            font=("Arial", 12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # ── Card thông tin ────────────────────────────────────────────────────
        info_card = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_CARD,
        )
        info_card.pack(fill="x", pady=(0, 20))

        rows = self._build_info_rows()
        for r_idx, (icon, label, value, value_color) in enumerate(rows):
            # Dòng separator (trừ dòng đầu)
            if r_idx > 0:
                ctk.CTkFrame(
                    info_card,
                    height=1,
                    fg_color=BORDER_INSET,
                ).pack(fill="x", padx=16)

            row_frame = ctk.CTkFrame(info_card, fg_color="transparent")
            row_frame.pack(fill="x", padx=16, pady=10)
            row_frame.grid_columnconfigure(2, weight=1)

            ctk.CTkLabel(
                row_frame,
                text=icon,
                font=("Arial", 16),
                width=28,
            ).grid(row=0, column=0, sticky="w")

            ctk.CTkLabel(
                row_frame,
                text=label,
                font=("Arial", 12),
                text_color=TEXT_SECONDARY,
                width=100,
                anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=(4, 8))

            ctk.CTkLabel(
                row_frame,
                text=value,
                font=("Arial", 12, "bold"),
                text_color=value_color or TEXT_PRIMARY,
                anchor="w",
                wraplength=280,
            ).grid(row=0, column=2, sticky="w")

        # ── Nhóm nút hành động (hàng 1) ──────────────────────────────────────
        btn_frame = ctk.CTkFrame(outer, fg_color="transparent")
        btn_frame.pack(fill="x")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Nút 1: Mở xem ngay
        ctk.CTkButton(
            btn_frame,
            text="▶️  Mở Xem Ngay",
            font=("Arial", 13, "bold"),
            fg_color=APPLE_GREEN,
            hover_color=APPLE_GREEN_HOVER,
            text_color="#000000",
            height=42,
            corner_radius=10,
            command=self._on_open_file,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        # Nút 2: Mở thư mục (highlight file)
        ctk.CTkButton(
            btn_frame,
            text="📁  Mở Thư Mục",
            font=("Arial", 13, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            text_color="#FFFFFF",
            height=42,
            corner_radius=10,
            command=self._on_reveal_file,
        ).grid(row=0, column=1, sticky="ew", padx=6)

        # Nút 3: Trở lại
        ctk.CTkButton(
            btn_frame,
            text="↩  Trở Lại",
            font=("Arial", 13),
            fg_color=BG_PILL,
            hover_color="#343949",
            text_color=TEXT_PRIMARY,
            height=42,
            corner_radius=10,
            command=self._on_back,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # ── Nút "Làm video tiếp theo" (hàng dưới, full width) ────────────────
        ctk.CTkButton(
            outer,
            text="✨  Làm Video Tiếp Theo",
            font=("Arial", 12),
            fg_color="transparent",
            hover_color=APPLE_ORANGE_BG,
            text_color=APPLE_ORANGE,
            border_width=1,
            border_color=APPLE_ORANGE,
            height=36,
            corner_radius=10,
            command=self._on_new_video_clicked,
        ).pack(fill="x", pady=(10, 0))

    def _build_info_rows(self):
        """Trả về list (icon, label, value, value_color) cho từng dòng thông tin."""
        if self._custom_rows:
            return self._custom_rows

        rows = []

        # File video
        if self._video_path:
            fn = Path(self._video_path).name
            sz = _fmt_size(self._video_path)
            rows.append(("🎬", "File video:", f"{fn}  ({sz})", TEXT_PRIMARY))

        # File phụ đề
        if self._srt_path and os.path.exists(self._srt_path):
            rows.append(("📄", "Phụ đề:", Path(self._srt_path).name, TEXT_PRIMARY))

        # File văn bản
        if self._txt_path and os.path.exists(self._txt_path):
            rows.append(("📝", "Văn bản:", Path(self._txt_path).name, TEXT_PRIMARY))

        # Thư mục xuất
        if self._video_path:
            out_dir = str(Path(self._video_path).parent)
            rows.append(("📁", "Lưu tại:", out_dir, TEXT_SECONDARY))

        # Thời gian xử lý
        rows.append(("⏱️", "Thời gian:", self._elapsed_str, APPLE_GREEN))

        return rows

    def _find_active_path(self) -> Optional[str]:
        """Dò tìm file hoặc thư mục đích khả dụng nhất để mở."""
        # 1. Thử file video chính
        if self._video_path and os.path.exists(self._video_path):
            return self._video_path

        # 2. Thử file srt hoặc txt
        for candidate in (self._srt_path, self._txt_path):
            if candidate and os.path.exists(candidate):
                return candidate

        # 3. Thử tìm từ các dòng thông tin custom_rows
        if self._custom_rows:
            for row in self._custom_rows:
                if len(row) >= 3:
                    val = str(row[2]).strip()
                    clean_val = val.split("  (")[0].strip()
                    if os.path.exists(val):
                        return val
                    if os.path.exists(clean_val):
                        return clean_val

        # 4. Thử thư mục lưu trong custom_rows
        if self._custom_rows:
            for row in self._custom_rows:
                if len(row) >= 3 and any(k in row[1] for k in ("Lưu tại:", "Thư mục", "Thư mục lưu:")):
                    folder = str(row[2]).strip()
                    if os.path.exists(folder):
                        return folder

        # 5. Thử thư mục cha của _video_path
        if self._video_path:
            p_dir = str(Path(self._video_path).parent)
            if os.path.exists(p_dir):
                return p_dir

        # 6. Fallback từ master window nếu có
        if hasattr(self.master, "_resolve_output_dir"):
            try:
                out = self.master._resolve_output_dir()
                if out and os.path.exists(out):
                    return out
            except Exception:
                pass

        if hasattr(self.master, "config"):
            try:
                from utils.helpers import get_output_dir
                out = get_output_dir(self.master.config)
                if out and os.path.exists(out):
                    return out
            except Exception:
                pass

        return None

    # ─── Button handlers ─────────────────────────────────────────────────────

    def _on_open_file(self):
        """Mở file hoặc thư mục bằng ứng dụng mặc định."""
        target = self._find_active_path()
        if target:
            _open_file(target)
        self.destroy()

    def _on_reveal_file(self):
        """Mở Finder/Explorer và bôi đen đúng file vừa xuất (hoặc mở thư mục lưu)."""
        target = self._find_active_path()
        if target:
            _reveal_file(target)
        self.destroy()

    def _on_back(self):
        """Chỉ đóng popup, trở về màn hình chính giữ nguyên log."""
        self.destroy()

    def _on_new_video_clicked(self):
        """Đóng popup và gọi callback để reset UI làm video mới."""
        self.destroy()
        if callable(self._on_new_video):
            self._on_new_video()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _center_on_parent(self, master):
        """Căn giữa dialog so với cửa sổ cha."""
        try:
            w  = self.winfo_width()
            h  = self.winfo_height()
            px = master.winfo_x()
            py = master.winfo_y()
            pw = master.winfo_width()
            ph = master.winfo_height()
            x  = px + (pw - w) // 2
            y  = py + (ph - h) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
