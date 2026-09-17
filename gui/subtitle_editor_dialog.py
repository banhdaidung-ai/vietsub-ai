"""
gui/subtitle_editor_dialog.py — Trình Chỉnh Sửa Phụ Đề Trực Quan (Subtitle Editor Studio)
Cho phép sửa lỗi phiên âm, chỉnh mốc thời gian, tìm & thay thế hàng loạt,
và ghép lại video siêu tốc mà không cần gọi lại AI.
"""

import os
import re
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk

from utils.srt_parser import (
    SRTSegment,
    ms_to_time,
    normalize_timestamp,
    parse_srt,
    segments_to_srt,
    time_to_ms,
)
from utils.config import get_output_dir


class SubtitleEditorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        segments: Optional[List[SRTSegment]] = None,
        srt_content: Optional[str] = None,
        video_path: Optional[str] = None,
        mode: str = "review",  # "review" (trong pipeline) | "standalone" (mở độc lập)
        on_confirm: Optional[Callable[[List[SRTSegment]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master)

        self.title("✏️ Trình Chỉnh Sửa Phụ Đề — Vietsub AI Studio")
        self.geometry("980x720")
        self.minsize(880, 580)

        # Modal behavior
        self.attributes("-topmost", True)
        self.after(150, lambda: self.attributes("-topmost", False))
        self.grab_set()

        self.mode = mode
        from utils.config import find_clean_raw_video
        clean_v = find_clean_raw_video(video_path)
        self.video_path = clean_v or video_path or ""
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.is_confirmed = False

        # Khởi tạo danh sách segments
        if segments:
            self.segments = [
                SRTSegment(
                    index=s.index,
                    start=s.start,
                    end=s.end,
                    text=s.text,
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                )
                for s in segments
            ]
        elif srt_content:
            self.segments = parse_srt(srt_content)
        else:
            self.segments = []

        self.row_widgets = []
        self._is_reburning = False

        self._build_ui()
        self._populate_rows()

        # Handle window close (X button)
        self.protocol("WM_DELETE_WINDOW", self._on_close_button)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Vùng bảng danh sách giãn nở

        # ─── 1. HEADER BAR ───
        header = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="✏️ Trình Chỉnh Sửa Phụ Đề (Subtitle Studio)",
            font=("Arial", 18, "bold"),
            text_color="#F8FAFC",
        ).pack(side="left")

        self.lbl_count = ctk.CTkLabel(
            title_box,
            text=f"{len(self.segments)} câu",
            font=("Arial", 11, "bold"),
            fg_color="#4F46E5",
            text_color="#FFFFFF",
            corner_radius=6,
            height=24,
            padx=8,
        )
        self.lbl_count.pack(side="left", padx=10)

        # Mode Badge & Quick actions
        top_actions = ctk.CTkFrame(header, fg_color="transparent")
        top_actions.grid(row=0, column=2, padx=20, pady=12, sticky="e")

        ctk.CTkButton(
            top_actions,
            text="➕ Thêm Câu Mới",
            font=("Arial", 12, "bold"),
            fg_color="#065F46",
            hover_color="#047857",
            height=32,
            corner_radius=8,
            command=self._add_new_segment,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            top_actions,
            text="💾 Xuất File .SRT",
            font=("Arial", 12),
            fg_color="#334155",
            hover_color="#475569",
            height=32,
            corner_radius=8,
            command=self._export_srt_file,
        ).pack(side="left")

        # ─── 2. TOOLBAR: TÌM & THAY THẾ + CHỈNH LỆCH THỜI GIAN ───
        toolbar = ctk.CTkFrame(self, fg_color="#0F172A", corner_radius=8, border_width=1, border_color="#334155")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(12, 6))

        # Khối Tìm & Thay thế
        find_box = ctk.CTkFrame(toolbar, fg_color="transparent")
        find_box.pack(side="left", padx=12, pady=8)

        ctk.CTkLabel(
            find_box,
            text="🔍 Tìm từ sai:",
            font=("Arial", 11, "bold"),
            text_color="#CBD5E1",
        ).pack(side="left", padx=(0, 6))

        self.entry_find = ctk.CTkEntry(
            find_box,
            placeholder_text="Ví dụ: Cốc ca cốc cốc",
            width=170,
            height=30,
            font=("Arial", 11),
        )
        self.entry_find.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            find_box,
            text="➡️ Thay bằng:",
            font=("Arial", 11, "bold"),
            text_color="#CBD5E1",
        ).pack(side="left", padx=(0, 6))

        self.entry_replace = ctk.CTkEntry(
            find_box,
            placeholder_text="Ví dụ: Lốc ca lốc cốc",
            width=170,
            height=30,
            font=("Arial", 11),
        )
        self.entry_replace.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            find_box,
            text="🔄 Thay Thế Hàng Loạt",
            font=("Arial", 11, "bold"),
            fg_color="#4F46E5",
            hover_color="#4338CA",
            height=30,
            corner_radius=6,
            command=self._replace_all,
        ).pack(side="left")

        # Khối Chỉnh lệch thời gian (Offset +/- ms)
        offset_box = ctk.CTkFrame(toolbar, fg_color="transparent")
        offset_box.pack(side="right", padx=12, pady=8)

        ctk.CTkLabel(
            offset_box,
            text="⏱️ Lệch sub:",
            font=("Arial", 11, "bold"),
            text_color="#CBD5E1",
        ).pack(side="left", padx=(0, 6))

        self.entry_offset = ctk.CTkEntry(
            offset_box,
            placeholder_text="+/- ms (vd: 500)",
            width=110,
            height=30,
            font=("Consolas", 11),
        )
        self.entry_offset.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            offset_box,
            text="Áp Dụng",
            font=("Arial", 11),
            fg_color="#334155",
            hover_color="#475569",
            width=70,
            height=30,
            corner_radius=6,
            command=self._apply_offset,
        ).pack(side="left")

        # ─── 3. BẢNG DANH SÁCH PHỤ ĐỀ (SCROLLABLE TABLE) ───
        table_container = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=10, border_width=1, border_color="#334155")
        table_container.grid(row=2, column=0, sticky="nsew", padx=20, pady=6)
        table_container.grid_columnconfigure(0, weight=1)
        table_container.grid_rowconfigure(1, weight=1)

        # Table Header
        th = ctk.CTkFrame(table_container, fg_color="#0F172A", height=36, corner_radius=6)
        th.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        th.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(th, text="#", font=("Arial", 11, "bold"), text_color="#94A3B8", width=36).grid(row=0, column=0, padx=4)
        ctk.CTkLabel(th, text="Bắt Đầu", font=("Arial", 11, "bold"), text_color="#94A3B8", width=105).grid(row=0, column=1, padx=4)
        ctk.CTkLabel(th, text="", font=("Arial", 11, "bold"), text_color="#94A3B8", width=24).grid(row=0, column=2)
        ctk.CTkLabel(th, text="Kết Thúc", font=("Arial", 11, "bold"), text_color="#94A3B8", width=105).grid(row=0, column=3, padx=4)
        ctk.CTkLabel(th, text="Nội Dung Phụ Đề / Lời Bài Hát (Nhấp vào ô để sửa)", font=("Arial", 11, "bold"), text_color="#38BDF8", anchor="w").grid(row=0, column=4, padx=12, sticky="w")
        ctk.CTkLabel(th, text="Xóa", font=("Arial", 11, "bold"), text_color="#94A3B8", width=44).grid(row=0, column=5, padx=6)

        # Scrollable Rows Frame
        self.scroll_rows = ctk.CTkScrollableFrame(table_container, fg_color="transparent")
        self.scroll_rows.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.scroll_rows.grid_columnconfigure(4, weight=1)

        # ─── 4. FOOTER ACTIONS ───
        footer = ctk.CTkFrame(self, fg_color="transparent", height=56)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 16))

        # Status note
        self.lbl_status = ctk.CTkLabel(
            footer,
            text="💡 Mẹo: Nhấp vào ô text để sửa từ ngữ. Dùng Tìm & Thay thế để sửa nhanh các từ lặp lại.",
            font=("Arial", 11),
            text_color="#94A3B8",
        )
        self.lbl_status.pack(side="left")

        # Action buttons
        btn_box = ctk.CTkFrame(footer, fg_color="transparent")
        btn_box.pack(side="right")

        ctk.CTkButton(
            btn_box,
            text="Hủy Bỏ",
            font=("Arial", 12),
            fg_color="#334155",
            hover_color="#475569",
            width=90,
            height=38,
            corner_radius=8,
            command=self._on_cancel_action,
        ).pack(side="left", padx=(0, 10))

        confirm_btn_text = "🚀 Xác Nhận & Ghép Video" if self.mode == "review" else "⚡ Ghép Lại Video Ngay"
        self.btn_confirm = ctk.CTkButton(
            btn_box,
            text=confirm_btn_text,
            font=("Arial", 13, "bold"),
            fg_color="#4F46E5",
            hover_color="#4338CA",
            width=200,
            height=38,
            corner_radius=8,
            command=self._on_confirm_action,
        )
        self.btn_confirm.pack(side="left")

    def _populate_rows(self):
        """Hiển thị tất cả các dòng phụ đề vào scroll_rows."""
        # Xóa các widget cũ nếu có
        for w in self.scroll_rows.winfo_children():
            w.destroy()
        self.row_widgets = []

        if not self.segments:
            empty_lbl = ctk.CTkLabel(
                self.scroll_rows,
                text="Chưa có đoạn phụ đề nào. Bấm '➕ Thêm Câu Mới' để bắt đầu.",
                font=("Arial", 13),
                text_color="#64748B",
            )
            empty_lbl.pack(pady=40)
            self.lbl_count.configure(text="0 câu")
            return

        self.lbl_count.configure(text=f"{len(self.segments)} câu")

        for i, seg in enumerate(self.segments):
            self._render_row(i, seg)

    def _render_row(self, i: int, seg: SRTSegment):
        row_frame = ctk.CTkFrame(self.scroll_rows, fg_color="#131F30", corner_radius=6)
        row_frame.pack(fill="x", pady=2)
        row_frame.grid_columnconfigure(4, weight=1)

        # 1. Index
        lbl_idx = ctk.CTkLabel(
            row_frame,
            text=str(i + 1),
            font=("Consolas", 11, "bold"),
            text_color="#64748B",
            width=36,
        )
        lbl_idx.grid(row=0, column=0, padx=4, pady=4)

        # 2. Start Time
        start_var = ctk.StringVar(value=normalize_timestamp(seg.start))
        entry_start = ctk.CTkEntry(
            row_frame,
            textvariable=start_var,
            font=("Consolas", 11),
            width=105,
            height=28,
            border_color="#334155",
        )
        entry_start.grid(row=0, column=1, padx=4, pady=4)

        # 3. Arrow
        ctk.CTkLabel(
            row_frame,
            text="→",
            font=("Consolas", 12),
            text_color="#64748B",
            width=24,
        ).grid(row=0, column=2, pady=4)

        # 4. End Time
        end_var = ctk.StringVar(value=normalize_timestamp(seg.end))
        entry_end = ctk.CTkEntry(
            row_frame,
            textvariable=end_var,
            font=("Consolas", 11),
            width=105,
            height=28,
            border_color="#334155",
        )
        entry_end.grid(row=0, column=3, padx=4, pady=4)

        # 5. Text (Nội dung phụ đề)
        text_var = ctk.StringVar(value=seg.text.replace("\n", " "))
        entry_text = ctk.CTkEntry(
            row_frame,
            textvariable=text_var,
            font=("Arial", 12),
            height=28,
            border_color="#334155",
        )
        entry_text.grid(row=0, column=4, padx=8, pady=4, sticky="ew")

        # 6. Nút xóa (Delete)
        btn_del = ctk.CTkButton(
            row_frame,
            text="🗑️",
            font=("Arial", 11),
            width=32,
            height=28,
            corner_radius=6,
            fg_color="#334155",
            hover_color="#EF4444",
            command=lambda idx=i: self._delete_row(idx),
        )
        btn_del.grid(row=0, column=5, padx=6, pady=4)

        self.row_widgets.append({
            "frame": row_frame,
            "lbl_idx": lbl_idx,
            "start_var": start_var,
            "end_var": end_var,
            "text_var": text_var,
        })

    def _collect_current_segments(self) -> List[SRTSegment]:
        """Thu thập dữ liệu hiện tại từ các ô nhập trên giao diện."""
        updated: List[SRTSegment] = []
        for i, r in enumerate(self.row_widgets):
            start_str = normalize_timestamp(r["start_var"].get())
            end_str = normalize_timestamp(r["end_var"].get())
            text = r["text_var"].get().strip()
            if text:
                updated.append(
                    SRTSegment(
                        index=i + 1,
                        start=start_str,
                        end=end_str,
                        text=text,
                        start_ms=time_to_ms(start_str),
                        end_ms=time_to_ms(end_str),
                    )
                )
        return updated

    def _replace_all(self):
        """Tìm và thay thế từ sai hàng loạt."""
        find_str = self.entry_find.get().strip()
        rep_str = self.entry_replace.get().strip()
        if not find_str:
            self.lbl_status.configure(
                text="⚠️ Vui lòng nhập từ khóa cần tìm vào ô '🔍 Tìm từ sai'.",
                text_color="#FBBF24",
            )
            return

        count = 0
        for r in self.row_widgets:
            current_text = r["text_var"].get()
            pattern = re.compile(re.escape(find_str), re.IGNORECASE)
            matches = pattern.findall(current_text)
            if matches:
                count += len(matches)
                new_text = pattern.sub(rep_str, current_text)
                r["text_var"].set(new_text)

        if count > 0:
            self.lbl_status.configure(
                text=f"✨ Đã thay thế thành công {count} chỗ từ '{find_str}' thành '{rep_str}'!",
                text_color="#34D399",
            )
        else:
            self.lbl_status.configure(
                text=f"ℹ️ Không tìm thấy từ '{find_str}' trong các câu phụ đề.",
                text_color="#94A3B8",
            )

    def _apply_offset(self):
        """Dịch chuyển toàn bộ mốc thời gian (+/- ms)."""
        offset_str = self.entry_offset.get().strip()
        try:
            offset_ms = int(offset_str)
        except ValueError:
            self.lbl_status.configure(
                text="⚠️ Độ lệch phải là số nguyên mili-giây (ví dụ: +500 hoặc -300).",
                text_color="#FBBF24",
            )
            return

        for r in self.row_widgets:
            try:
                cur_start = time_to_ms(r["start_var"].get())
                cur_end = time_to_ms(r["end_var"].get())
                new_start = max(0, cur_start + offset_ms)
                new_end = max(new_start + 100, cur_end + offset_ms)
                r["start_var"].set(ms_to_time(new_start))
                r["end_var"].set(ms_to_time(new_end))
            except Exception:
                pass

        sign = "+" if offset_ms >= 0 else ""
        self.lbl_status.configure(
            text=f"⏱️ Đã điều chỉnh toàn bộ mốc thời gian phụ đề: {sign}{offset_ms}ms.",
            text_color="#38BDF8",
        )

    def _add_new_segment(self):
        """Thêm một đoạn phụ đề mới vào cuối danh sách."""
        current = self._collect_current_segments()
        if current:
            last_end = current[-1].end_ms
            new_start_ms = last_end + 200
            new_end_ms = new_start_ms + 2500
        else:
            new_start_ms = 0
            new_end_ms = 3000

        new_seg = SRTSegment(
            index=len(current) + 1,
            start=ms_to_time(new_start_ms),
            end=ms_to_time(new_end_ms),
            text="Nhập nội dung phụ đề...",
            start_ms=new_start_ms,
            end_ms=new_end_ms,
        )
        self.segments = current + [new_seg]
        self._populate_rows()
        self.lbl_status.configure(
            text="➕ Đã thêm một dòng phụ đề mới ở cuối danh sách.",
            text_color="#34D399",
        )

    def _delete_row(self, idx: int):
        """Xóa một dòng phụ đề."""
        current = self._collect_current_segments()
        if 0 <= idx < len(current):
            del current[idx]
            self.segments = current
            self._populate_rows()
            self.lbl_status.configure(
                text=f"🗑️ Đã xóa dòng phụ đề #{idx + 1}.",
                text_color="#94A3B8",
            )

    def _export_srt_file(self):
        """Xuất file .SRT hiện tại ra ổ đĩa."""
        updated = self._collect_current_segments()
        if not updated:
            self.lbl_status.configure(text="❌ Không có nội dung phụ đề để lưu.", text_color="#F87171")
            return

        srt_text = segments_to_srt(updated)
        try:
            self.grab_release()
        except Exception:
            pass

        initial_name = "subtitles_edited.srt"
        if self.video_path:
            initial_name = f"{Path(self.video_path).stem}_edited.srt"

        filepath = ctk.filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".srt",
            filetypes=[("SRT Subtitles", "*.srt"), ("All Files", "*.*")],
            initialfile=initial_name,
        )
        try:
            self.grab_set()
        except Exception:
            pass

        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(srt_text)
            self.lbl_status.configure(
                text=f"💾 Đã lưu file phụ đề thành công: {Path(filepath).name}",
                text_color="#34D399",
            )

    def _on_confirm_action(self):
        """Xác nhận phụ đề đã sửa để ghép vào video."""
        updated = self._collect_current_segments()
        if not updated:
            self.lbl_status.configure(
                text="❌ Danh sách phụ đề đang trống. Vui lòng thêm ít nhất một câu.",
                text_color="#F87171",
            )
            return

        self.segments = updated
        self.is_confirmed = True

        if self.mode == "review":
            if self.on_confirm:
                self.on_confirm(self.segments)
            self.destroy()
        else:
            # Standalone mode: Re-burn trực tiếp vào video
            self._start_standalone_reburn()

    def _start_standalone_reburn(self):
        """Chạy re-burn phụ đề vào video độc lập bằng FFmpeg."""
        from utils.config import find_clean_raw_video

        # Tự động truy vết và dùng video gốc sạch (không có sub cũ)
        clean_v = find_clean_raw_video(self.video_path)
        if clean_v and os.path.exists(clean_v):
            self.video_path = clean_v

        if not self.video_path or not os.path.exists(self.video_path):
            try:
                self.grab_release()
            except Exception:
                pass
            v_path = ctk.filedialog.askopenfilename(
                parent=self,
                title="Chọn file Video GỐC (chưa có phụ đề) để ghép",
                filetypes=[("Video Files", "*.mp4 *.mkv *.mov *.webm *.avi")],
            )
            try:
                self.grab_set()
            except Exception:
                pass
            if not v_path:
                self.lbl_status.configure(text="⚠️ Bạn chưa chọn file video gốc.", text_color="#FBBF24")
                return
            clean_picked = find_clean_raw_video(v_path)
            self.video_path = clean_picked or v_path

        if self._is_reburning:
            return

        self._is_reburning = True
        self.btn_confirm.configure(state="disabled", text="⏳ Đang ghép lại video...")
        raw_name = Path(self.video_path).name
        self.lbl_status.configure(
            text=f"🎬 Đang ghép phụ đề mới vào video gốc: {raw_name}...",
            text_color="#38BDF8",
        )

        def run_reburn():
            from core.ffmpeg_processor import FFmpegProcessor
            from utils.config import load_config
            cfg = load_config()

            tmp_dir = tempfile.mkdtemp(prefix="vietsub_reburn_")
            srt_tmp = os.path.join(tmp_dir, "reburn.srt")
            srt_str = segments_to_srt(self.segments)
            with open(srt_tmp, "w", encoding="utf-8") as f:
                f.write(srt_str)

            out_dir = get_output_dir(cfg)
            stem = Path(self.video_path).stem
            clean_stem = re.sub(r"_(sub_vi|vietsub|reburn)_\d{8}_\d{4,6}$", "", stem).strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_video = os.path.join(out_dir, f"{clean_stem}_reburn_{timestamp}.mp4")

            try:
                def _prog_cb(pct: float, msg: str):
                    pct_str = f" ({int(pct * 100)}%)" if pct > 0 else ""
                    self.after(
                        0,
                        lambda m=f"🎬 {msg}{pct_str}": self.lbl_status.configure(
                            text=m, text_color="#38BDF8"
                        ),
                    )

                ffmpeg = FFmpegProcessor(progress_callback=_prog_cb)
                ffmpeg.process_video(
                    video_path=self.video_path,
                    srt_path=srt_tmp,
                    output_path=out_video,
                    sub_only=True,
                    subtitle_font_size=int(cfg.get("subtitle_font_size", 10)),
                    subtitle_margin_v=int(cfg.get("subtitle_margin_v", 8)),
                    subtitle_style_preset=cfg.get("subtitle_style_preset", "capcut_yellow"),
                )
                self.after(0, lambda p=out_video: self._on_reburn_success(p))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: self._on_reburn_error(msg))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=run_reburn, daemon=True).start()

    def _on_reburn_success(self, out_video: str):
        self._is_reburning = False
        self.btn_confirm.configure(state="normal", text="✅ Đã Ghép Xong!")
        self.lbl_status.configure(
            text=f"🎉 Ghép video thành công rực rỡ! Đã lưu: {Path(out_video).name}",
            text_color="#34D399",
        )
        if hasattr(self.master, "_log_msg"):
            self.master._log_msg("\n" + "─" * 45)
            self.master._log_msg("🎉 Ghép lại video thành công rực rỡ!")
            self.master._log_msg(f"   🎬 File: {Path(out_video).name}")
            self.master._log_msg(f"   📁 Lưu tại: {out_video}")
            self.master._log_msg("✨ Đã tự động sử dụng video gốc sạch không bị chồng đè chữ.")
        if hasattr(self.master, "_set_active_step"):
            self.master._set_active_step(5)
        try:
            import subprocess
            subprocess.run(["open", "-R", out_video], check=False)
        except Exception:
            pass
        # Tự động đóng cửa sổ sau 1.2 giây để chuyển trọng tâm về giao diện chính
        self.after(1200, self.destroy)

    def _on_reburn_error(self, err_msg: str):
        self._is_reburning = False
        self.btn_confirm.configure(state="normal", text="⚡ Thử Ghép Lại")
        self.lbl_status.configure(
            text=f"❌ Lỗi khi ghép video: {err_msg[:80]}",
            text_color="#F87171",
        )

    def _on_cancel_action(self):
        """Hủy bỏ thao tác."""
        if not self.is_confirmed and self.on_cancel:
            self.on_cancel()
        self.destroy()

    def _on_close_button(self):
        """Bấm nút X trên thanh tiêu đề."""
        self._on_cancel_action()
