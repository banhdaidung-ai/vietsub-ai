"""
gui/home_view.py — Trang Chủ Trung Tâm (Dashboard Hub) cho Vietsub AI Studio
Thiết kế theo ngôn ngữ Apple macOS Sequoia / Dark Glassmorphism.
Cung cấp cái nhìn tổng quan, bộ thẻ studio công cụ, và lối tắt trực quan.
"""

import sys
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

# ═════════════════════════════════════════════════════════
# DESIGN SYSTEM TOKENS (Đồng bộ với app_window.py)
# ═════════════════════════════════════════════════════════
BG_CARD = "#1C1F27"
BORDER_CARD = "#2E3342"
BG_INSET = "#121419"
BORDER_INSET = "#252834"
BG_PILL = "#272B37"
BG_PILL_HOVER = "#343949"

APPLE_BLUE = "#0A84FF"
APPLE_BLUE_HOVER = "#0071E3"
APPLE_GREEN = "#30D158"
APPLE_GREEN_HOVER = "#28B84C"
APPLE_ORANGE = "#FF9F0A"
APPLE_ORANGE_HOVER = "#D98200"
APPLE_RED = "#FF453A"
APPLE_PURPLE = "#AF52DE"
APPLE_PURPLE_HOVER = "#9333EA"
APPLE_INDIGO = "#5E5CE6"
APPLE_CYAN = "#64D2FF"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_TERTIARY = "#636366"


class HomeView(ctk.CTkScrollableFrame):
    """
    Trang Chủ (Dashboard) - Trung tâm điều khiển toàn bộ tính năng Studio.
    Hiển thị Hero banner, trạng thái hệ thống, và 6 thẻ tính năng lớn.
    """

    def __init__(
        self,
        master,
        on_navigate: Optional[Callable[[str], None]] = None,
        on_open_folder: Optional[Callable] = None,
        on_open_settings: Optional[Callable] = None,
        on_donate: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color="transparent",
            corner_radius=12,
            **kwargs,
        )
        self.on_navigate = on_navigate
        self.on_open_folder = on_open_folder
        self.on_open_settings = on_open_settings
        self.on_donate = on_donate

        self.grid_columnconfigure(0, weight=1)

        self._build_hero_section()
        self._build_tools_grid()
        self._build_quick_drop_banner()
        self._build_footer()
        self._setup_mousewheel_scroll()

    def _setup_mousewheel_scroll(self):
        """Hỗ trợ cuộn chuột siêu mượt trên macOS và Windows."""
        def _on_mousewheel(event):
            try:
                if sys.platform == "darwin":
                    self._parent_canvas.yview_scroll(int(-1 * event.delta), "units")
                else:
                    self._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.bind("<MouseWheel>", _on_mousewheel, add="+")
        self._parent_canvas.bind("<MouseWheel>", _on_mousewheel, add="+")

    # ═════════════════════════════════════════════════════════
    # 1. HERO BANNER
    # ═════════════════════════════════════════════════════════
    def _build_hero_section(self):
        hero_card = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        hero_card.pack(fill="x", padx=10, pady=(6, 14))
        hero_card.grid_columnconfigure(0, weight=1)

        # Top Badge
        badge_frame = ctk.CTkFrame(hero_card, fg_color="transparent")
        badge_frame.pack(anchor="center", pady=(18, 8))

        ctk.CTkLabel(
            badge_frame,
            text="⭐️ VIETSUB AI PRO STUDIO • TRUNG TÂM SÁNG TẠO MEDIA",
            font=("Arial", 11, "bold"),
            text_color=APPLE_CYAN,
            fg_color=BG_PILL,
            corner_radius=12,
            padx=14,
            pady=4,
        ).pack()

        # Headline
        ctk.CTkLabel(
            hero_card,
            text="Chào mừng bạn đến với Vietsub AI Studio",
            font=("Arial", 22, "bold"),
            text_color=TEXT_PRIMARY,
            justify="center",
        ).pack(padx=20, pady=(0, 6))

        # Subtitle
        ctk.CTkLabel(
            hero_card,
            text="Bộ công cụ AI toàn diện: Dịch thuật, Phụ đề CapCut, Lồng tiếng tự nhiên, Tách Beat, Tải Media & Nén Ảnh tối ưu.",
            font=("Arial", 12),
            text_color=TEXT_SECONDARY,
            justify="center",
        ).pack(padx=30, pady=(0, 16))

        # Status pills bar
        pills_bar = ctk.CTkFrame(hero_card, fg_color="transparent")
        pills_bar.pack(anchor="center", pady=(0, 18))

        # Pill 1: AI Model
        p1 = ctk.CTkFrame(pills_bar, fg_color=BG_INSET, corner_radius=8,
                           border_width=1, border_color=BORDER_INSET)
        p1.pack(side="left", padx=4)
        ctk.CTkLabel(p1, text="⚡ Gemini 3.8 Flash", font=("Arial", 11, "bold"),
                     text_color=APPLE_CYAN, padx=10, pady=4).pack()

        # Pill 2: Demucs Vocal Separator
        p2 = ctk.CTkFrame(pills_bar, fg_color=BG_INSET, corner_radius=8,
                           border_width=1, border_color=BORDER_INSET)
        p2.pack(side="left", padx=4)
        ctk.CTkLabel(p2, text="🎤 Demucs AI v4", font=("Arial", 11, "bold"),
                     text_color=APPLE_PURPLE, padx=10, pady=4).pack()

        # Pill 3: Edge TTS Voices
        p3 = ctk.CTkFrame(pills_bar, fg_color=BG_INSET, corner_radius=8,
                           border_width=1, border_color=BORDER_INSET)
        p3.pack(side="left", padx=4)
        ctk.CTkLabel(p3, text="🎙️ Microsoft Neural Voices", font=("Arial", 11, "bold"),
                     text_color=APPLE_GREEN, padx=10, pady=4).pack()

        # Pill 4: Open Output Directory
        if self.on_open_folder:
            ctk.CTkButton(
                pills_bar,
                text="📁 Thư Mục Xuất",
                font=("Arial", 11, "bold"),
                fg_color=BG_PILL,
                hover_color=BG_PILL_HOVER,
                text_color=TEXT_PRIMARY,
                border_width=1,
                border_color=BORDER_CARD,
                height=28,
                corner_radius=8,
                command=self.on_open_folder,
            ).pack(side="left", padx=4)

        # Pill 5: Mời tác giả cà phê (Donate)
        if self.on_donate:
            ctk.CTkButton(
                pills_bar,
                text="☕ Mời Tác Giả Cà Phê",
                font=("Arial", 11, "bold"),
                fg_color="#2B2115",
                hover_color="#45341F",
                text_color="#FFB340",
                border_width=1,
                border_color="#5E4324",
                height=28,
                corner_radius=8,
                cursor="hand2",
                command=self.on_donate,
            ).pack(side="left", padx=4)

    # ═════════════════════════════════════════════════════════
    # 2. STUDIO TOOLS GRID (2 CỘT x 3 HÀNG)
    # ═════════════════════════════════════════════════════════
    def _build_tools_grid(self):
        section_title = ctk.CTkFrame(self, fg_color="transparent")
        section_title.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            section_title,
            text="🎯 CÁC CÔNG CỤ STUDIO NỔI BẬT",
            font=("Arial", 13, "bold"),
            text_color=APPLE_BLUE,
        ).pack(side="left")

        ctk.CTkLabel(
            section_title,
            text="Chọn một công cụ bên dưới để bắt đầu làm việc ngay",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(10, 0))

        # Grid Container
        grid_container = ctk.CTkFrame(self, fg_color="transparent")
        grid_container.pack(fill="x", padx=6, pady=(0, 10))
        grid_container.grid_columnconfigure((0, 1), weight=1, uniform="tools")

        tools_data = [
            {
                "id": "vietsub",
                "icon": "🎬",
                "title": "Vietsub & Lồng Tiếng AI",
                "tag": "CÔNG CỤ CHỦ LỰC",
                "tag_color": APPLE_BLUE,
                "desc": "Tự động nghe, nhận diện giọng nói đa ngôn ngữ, dịch chuẩn văn cảnh tiếng Việt, gắn phụ đề CapCut thời thượng và lồng tiếng AI truyền cảm.",
                "btn_text": "Mở Studio Vietsub ➔",
                "btn_color": APPLE_BLUE,
                "btn_hover": APPLE_BLUE_HOVER,
            },
            {
                "id": "separator",
                "icon": "🎤",
                "title": "Tách Beat & Giọng Hát",
                "tag": "DEMUCS AI v4",
                "tag_color": APPLE_PURPLE,
                "desc": "Tách riêng giọng hát ca sĩ (Vocal) và nhạc nền karaoke (Instrumental) chuẩn phòng thu, phục vụ làm video cover hoặc lồng tiếng mới.",
                "btn_text": "Tách Nhạc & Lời ➔",
                "btn_color": APPLE_PURPLE,
                "btn_hover": APPLE_PURPLE_HOVER,
            },
            {
                "id": "downloader",
                "icon": "📥",
                "title": "Tải Video & Nhạc Online",
                "tag": "MẠNG XÃ HỘI",
                "tag_color": APPLE_GREEN,
                "desc": "Tải video gốc siêu nét không logo hoặc trích xuất MP3 320kbps từ TikTok, Douyin, YouTube, Facebook, Instagram, SoundCloud, Artlist...",
                "btn_text": "Tải Media Ngay ➔",
                "btn_color": APPLE_GREEN,
                "btn_hover": APPLE_GREEN_HOVER,
            },
            {
                "id": "gdrive",
                "icon": "☁️",
                "title": "Tải Google Drive Trực Tiếp",
                "tag": "KHÔNG CẦN ZIP",
                "tag_color": APPLE_CYAN,
                "desc": "Tải trực tiếp toàn bộ thư mục phân cấp hoặc tệp đơn từ Google Drive tốc độ cao, bảo toàn 100% cấu trúc tệp mà không cần nén ZIP.",
                "btn_text": "Mở Tải Google Drive ➔",
                "btn_color": "#1E3A8A",
                "btn_hover": APPLE_BLUE,
            },
            {
                "id": "compressor",
                "icon": "🖼️",
                "title": "Nén Ảnh Hàng Loạt",
                "tag": "TỐI ƯU DUNG LƯỢNG",
                "tag_color": APPLE_CYAN,
                "desc": "Giảm dung lượng hình ảnh hàng loạt về mức mục tiêu (1MB, 500KB...) với thuật toán thông minh, bảo toàn độ sắc nét và màu sắc tuyệt đối.",
                "btn_text": "Mở Nén Ảnh ➔",
                "btn_color": "#1E3A8A",
                "btn_hover": APPLE_BLUE,
            },
            {
                "id": "sub_editor",
                "icon": "✏️",
                "title": "Biên Tập Phụ Đề",
                "tag": "SRT EDITOR",
                "tag_color": APPLE_ORANGE,
                "desc": "Xem trước video song song với phụ đề, chỉnh sửa từng câu từ mốc thời gian, tạo và xuất file .srt / .txt nhanh chóng, chính xác.",
                "btn_text": "Sửa Phụ Đề ➔",
                "btn_color": APPLE_ORANGE,
                "btn_hover": APPLE_ORANGE_HOVER,
            },
            {
                "id": "guide",
                "icon": "📖",
                "title": "Hướng Dẫn & Cẩm Nang",
                "tag": "BÍ KÍP PRO",
                "tag_color": APPLE_INDIGO,
                "desc": "Kho tài liệu chi tiết, các mẹo sử dụng, bảng tra cứu ngôn ngữ, hướng dẫn thiết lập API Key miễn phí và giải đáp thắc mắc thường gặp.",
                "btn_text": "Xem Hướng Dẫn ➔",
                "btn_color": BG_PILL,
                "btn_hover": BG_PILL_HOVER,
            },
        ]

        for i, item in enumerate(tools_data):
            r = i // 2
            c = i % 2
            card = self._create_tool_card(grid_container, item)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")

    def _create_tool_card(self, parent, item: dict) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=12,
        )
        card.grid_columnconfigure(0, weight=1)

        # Header Row: Icon + Title + Tag
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            hdr,
            text=item["icon"],
            font=("Arial", 22),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            hdr,
            text=item["title"],
            font=("Arial", 14, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            hdr,
            text=f"  {item['tag']}  ",
            font=("Arial", 9, "bold"),
            text_color=item["tag_color"],
            fg_color=BG_INSET,
            corner_radius=6,
            height=20,
        ).pack(side="right")

        # Description
        ctk.CTkLabel(
            card,
            text=item["desc"],
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
            wraplength=380,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 12))

        # Action Button
        btn = ctk.CTkButton(
            card,
            text=item["btn_text"],
            font=("Arial", 11, "bold"),
            fg_color=item["btn_color"],
            hover_color=item["btn_hover"],
            text_color=TEXT_PRIMARY if item["id"] == "guide" else "#FFFFFF",
            border_width=1 if item["id"] == "guide" else 0,
            border_color=BORDER_CARD if item["id"] == "guide" else None,
            height=32,
            corner_radius=8,
            command=lambda tid=item["id"]: self._handle_click(tid),
        )
        btn.pack(fill="x", padx=14, pady=(0, 12))

        return card

    def _handle_click(self, tool_id: str):
        if self.on_navigate:
            self.on_navigate(tool_id)

    # ═════════════════════════════════════════════════════════
    # 3. QUICK DROP BANNER
    # ═════════════════════════════════════════════════════════
    def _build_quick_drop_banner(self):
        banner = ctk.CTkFrame(
            self,
            fg_color=BG_INSET,
            border_width=1,
            border_color=BORDER_INSET,
            corner_radius=10,
        )
        banner.pack(fill="x", padx=10, pady=(4, 10))

        inner = ctk.CTkFrame(banner, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        ctk.CTkLabel(
            inner,
            text="💡 Mẹo nhanh: Bạn có thể kéo & thả trực tiếp bất kỳ tệp video (MP4, MKV), âm thanh (MP3, WAV) hoặc ảnh (JPG, PNG) vào cửa sổ ứng dụng bất cứ lúc nào.",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(side="left")

    # ═════════════════════════════════════════════════════════
    # 4. FOOTER
    # ═════════════════════════════════════════════════════════
    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=10, pady=(0, 12))

        ctk.CTkLabel(
            foot,
            text="⭐️ Bản quyền & phát triển bởi Bành Đại Dũng - 0982333097",
            font=("Arial", 11, "bold"),
            text_color=APPLE_CYAN,
        ).pack(side="left")

        ctk.CTkLabel(
            foot,
            text="Vietsub AI Studio • macOS Edition",
            font=("Arial", 10),
            text_color=TEXT_TERTIARY,
        ).pack(side="right")
