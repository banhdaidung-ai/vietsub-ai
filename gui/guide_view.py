"""
gui/guide_view.py — Tab Hướng Dẫn Toàn Diện (Landing Page) cho Vietsub AI Studio
Thiết kế theo phong cách Apple macOS Sequoia / Dark Glassmorphism,
cung cấp tổng quan quy trình, chi tiết từng phân hệ, bảng tra cứu, bí kíp và FAQ.
"""

from typing import Callable, Optional
import customtkinter as ctk

# ═════════════════════════════════════════════════════════
# DESIGN TOKENS (Đồng bộ với app_window)
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
APPLE_ORANGE = "#FF9F0A"
APPLE_RED = "#FF453A"
APPLE_PURPLE = "#AF52DE"
APPLE_INDIGO = "#5E5CE6"
APPLE_CYAN = "#64D2FF"

TEXT_PRIMARY = "#F5F5F7"
TEXT_SECONDARY = "#98989F"
TEXT_TERTIARY = "#636366"


class GuideView(ctk.CTkScrollableFrame):
    """
    Component Landing Page Hướng Dẫn Sử Dụng Toàn Diện cho Vietsub AI Pro Studio.
    Được thiết kế cuộn mượt mà, bao quát từ tổng quan đến chi tiết từng tính năng.
    """

    def __init__(self, master, on_start_clicked: Optional[Callable] = None, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            corner_radius=12,
            **kwargs,
        )
        self.on_start_clicked = on_start_clicked

        self.grid_columnconfigure(0, weight=1)

        # Xây dựng các Section của Landing Page
        self._build_hero_section()
        self._build_quick_metrics()
        self._build_workflow_section()
        self._build_features_deep_dive()
        self._build_cheat_sheet_section()
        self._build_pro_tips_section()
        self._build_faq_section()
        self._build_footer_cta()

        # Cấu hình cuộn chuột siêu nhạy và mượt mà cho macOS & Windows
        self._setup_mousewheel_scroll()

    # ═════════════════════════════════════════════════════════
    # 1. HERO BANNER SECTION
    # ═════════════════════════════════════════════════════════
    def _build_hero_section(self):
        hero_card = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        hero_card.pack(fill="x", padx=4, pady=(4, 12))
        hero_card.grid_columnconfigure(0, weight=1)

        # Top Badge
        badge_row = ctk.CTkFrame(hero_card, fg_color="transparent")
        badge_row.pack(anchor="center", pady=(20, 10))

        ctk.CTkLabel(
            badge_row,
            text="✨ VIETSUB AI PRO STUDIO • HƯỚNG DẪN SỬ DỤNG TOÀN DIỆN",
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
            text="Studio Dịch Thuật, Phụ Đề & Lồng Tiếng Video AI Đẳng Cấp",
            font=("Arial", 22, "bold"),
            text_color=TEXT_PRIMARY,
            justify="center",
        ).pack(padx=20, pady=(0, 6))

        # Subtitle
        ctk.CTkLabel(
            hero_card,
            text="Nền tảng tự động hóa sản xuất video đa ngôn ngữ với Gemini AI, giọng đọc Neural truyền cảm\n"
            "và công nghệ tách âm thanh điện ảnh. Hướng dẫn này sẽ giúp bạn làm chủ 100% sức mạnh của ứng dụng.",
            font=("Arial", 12),
            text_color=TEXT_SECONDARY,
            justify="center",
        ).pack(padx=30, pady=(0, 18))

        # CTA Button Row
        cta_row = ctk.CTkFrame(hero_card, fg_color="transparent")
        cta_row.pack(pady=(0, 20))

        ctk.CTkButton(
            cta_row,
            text="🚀 Bắt Đầu Làm Video Ngay",
            font=("Arial", 13, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            height=38,
            width=210,
            corner_radius=8,
            command=self._handle_start_click,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            cta_row,
            text="💡 Khám Phá Tính Năng Cốt Lõi",
            font=("Arial", 12, "bold"),
            fg_color=BG_PILL,
            hover_color=BG_PILL_HOVER,
            text_color=TEXT_PRIMARY,
            height=38,
            width=210,
            corner_radius=8,
            command=self._scroll_to_features,
        ).pack(side="left", padx=8)

    # ═════════════════════════════════════════════════════════
    # 2. QUICK HIGHLIGHTS / METRICS PILLS
    # ═════════════════════════════════════════════════════════
    def _build_quick_metrics(self):
        metrics_frame = ctk.CTkFrame(self, fg_color="transparent")
        metrics_frame.pack(fill="x", padx=4, pady=(0, 14))
        metrics_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        metrics = [
            ("🌐 Đa Nền Tảng", "TikTok, Douyin, Reels, YouTube", APPLE_BLUE),
            ("🤖 Trí Tuệ Gemini", "Dịch hiểu ngữ cảnh & từ lóng", APPLE_PURPLE),
            ("🎙️ Neural TTS", "Giọng Hoài My & Nam Minh", APPLE_GREEN),
            ("🎵 Tách Nhạc AI", "Giữ 100% nhạc nền & âm thanh SFX", APPLE_ORANGE),
        ]

        for idx, (title, desc, color) in enumerate(metrics):
            card = ctk.CTkFrame(
                metrics_frame,
                fg_color=BG_CARD,
                border_width=1,
                border_color=BORDER_CARD,
                corner_radius=10,
            )
            card.grid(row=0, column=idx, padx=(0 if idx == 0 else 4, 0 if idx == 3 else 4), sticky="ew")

            ctk.CTkLabel(
                card,
                text=title,
                font=("Arial", 12, "bold"),
                text_color=color,
            ).pack(anchor="w", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                card,
                text=desc,
                font=("Arial", 10),
                text_color=TEXT_SECONDARY,
            ).pack(anchor="w", padx=12, pady=(0, 10))

    # ═════════════════════════════════════════════════════════
    # 3. WORKFLOW 4 BƯỚC CHUẨN (PIPELINE STEPS)
    # ═════════════════════════════════════════════════════════
    def _build_workflow_section(self):
        container = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        container.pack(fill="x", padx=4, pady=(0, 14))

        # Header Title
        title_box = ctk.CTkFrame(container, fg_color="transparent")
        title_box.pack(fill="x", padx=18, pady=(16, 12))

        ctk.CTkLabel(
            title_box,
            text="🔄 QUY TRÌNH HOẠT ĐỘNG 4 BƯỚC ĐƠN GIẢN",
            font=("Arial", 15, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="Toàn bộ quy trình từ video thô đến thành phẩm chất lượng cao được tự động hóa hoàn toàn",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        # 4 Steps Cards Grid
        steps_grid = ctk.CTkFrame(container, fg_color="transparent")
        steps_grid.pack(fill="x", padx=14, pady=(0, 16))
        steps_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        steps_data = [
            (
                "1️⃣ Nạp Video",
                "Chọn file từ máy (kéo thả) hoặc dán link online TikTok, Douyin, YouTube, Facebook Reels.",
                APPLE_BLUE,
            ),
            (
                "2️⃣ Thiết Lập AI",
                "Chọn ngôn ngữ nguồn (Trung, Anh, Việt), bật/tắt lồng tiếng, chọn giọng đọc và mẫu phụ đề.",
                APPLE_PURPLE,
            ),
            (
                "3️⃣ Xử Lý Tự Động",
                "AI lắng nghe, phiên âm, dịch sát ngữ cảnh, tách vocal và lồng tiếng ăn khớp từng mili-giây.",
                APPLE_GREEN,
            ),
            (
                "4️⃣ Xuất Bản & Xem",
                "Xem trước, chỉnh sửa câu chữ bằng Visual Editor, render video 4K và xuất file phụ đề SRT/TXT.",
                APPLE_ORANGE,
            ),
        ]

        for idx, (step_title, step_desc, color) in enumerate(steps_data):
            step_box = ctk.CTkFrame(
                steps_grid,
                fg_color=BG_INSET,
                border_width=1,
                border_color=BORDER_INSET,
                corner_radius=10,
            )
            step_box.grid(row=0, column=idx, padx=4, sticky="nsew")

            ctk.CTkLabel(
                step_box,
                text=step_title,
                font=("Arial", 12, "bold"),
                text_color=color,
            ).pack(anchor="w", padx=10, pady=(10, 4))

            ctk.CTkLabel(
                step_box,
                text=step_desc,
                font=("Arial", 10),
                text_color=TEXT_SECONDARY,
                wraplength=175,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 12))

    # ═════════════════════════════════════════════════════════
    # 4. CHI TIẾT TỪNG PHÂN HỆ CỐT LÕI (FEATURE DEEP DIVE)
    # ═════════════════════════════════════════════════════════
    def _build_features_deep_dive(self):
        self.features_anchor = ctk.CTkFrame(self, fg_color="transparent")
        self.features_anchor.pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkLabel(
            self.features_anchor,
            text="💎 CHI TIẾT TỪNG PHÂN HỆ & TÍNH NĂNG CỐT LÕI",
            font=("Arial", 16, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=4, pady=(6, 2))

        ctk.CTkLabel(
            self.features_anchor,
            text="Khám phá chi tiết công năng và cách sử dụng hiệu quả của từng module trong ứng dụng",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", padx=4, pady=(0, 10))

        # Danh sách 6 phân hệ cốt lõi
        modules = [
            (
                "🌐 1. Phân Hệ Tải & Nạp Video Đa Nền Tảng (Universal Downloader)",
                APPLE_BLUE,
                [
                    ("Tải Video Không Watermark:", "Hỗ trợ tải video sạch không dính logo từ TikTok, Douyin (TikTok Trung Quốc), Xiaohongshu (Tiểu Hồng Thư), Kuaishou, Facebook Reels/Video, YouTube Shorts/Video, Instagram..."),
                    ("Nút 'Dán Link' Thông Minh:", "Tự động nhận diện nội dung clipboard, làm sạch các đoạn văn bản rác hoặc link rút gọn khi chia sẻ từ điện thoại."),
                    ("Đa Dạng Độ Phân Giải:", "Linh hoạt lựa chọn: Tốt nhất (1080p/4K), 720p, 480p hoặc chế độ 'Chỉ tải âm thanh MP3'."),
                    ("Kéo & Thả Trực Quan:", "Hỗ trợ kéo thả trực tiếp tệp video/âm thanh (MP4, MKV, MOV, AVI, MP3, WAV...) từ máy tính vào cửa sổ app."),
                    ("Cookie Douyin Chống Chặn:", "Tích hợp sẵn mục nhập Cookie Douyin trong Cài đặt để vượt qua giới hạn kiểm duyệt mạng và tải các video dài mượt mà."),
                ],
            ),
            (
                "🤖 2. Bộ Não AI Gemini: Dịch Thuật & Phụ Đề Ngữ Cảnh Cao Cấp",
                APPLE_PURPLE,
                [
                    ("🇨🇳 Tiếng Trung → Tiếng Việt:", "Dịch thuật hiểu sâu bối cảnh văn hóa, phim cổ trang, kiếm hiệp, vlog hiện đại, tự động chuyển đổi thành ngữ Hán-Việt mượt mà, tự nhiên như người bản xứ."),
                    ("🇺🇸 Tiếng Anh → Tiếng Việt:", "Xử lý thành thạo idioms, tiếng lóng đời thường, khẩu ngữ ngắn, thuật ngữ công nghệ, không dịch thô cứng theo từng từ như Google Dịch thông thường."),
                    ("🇻🇳 Tạo Phụ Đề Tiếng Việt:", "Chuyên biệt cho video người Việt nói tiếng Việt. AI lắng nghe và phiên âm chuẩn 100% có dấu, ngắt câu đúng nhịp thở và giữ nguyên 100% âm thanh gốc."),
                    ("Đồng Bộ Timestamp Mili-giây:", "Khớp từng khung hình video, đảm bảo chữ chạy đến đâu là giọng nói vang lên đến đó, không lệch nhịp."),
                ],
            ),
            (
                "🎙️ 3. Studio Lồng Tiếng AI Neural (Microsoft Edge TTS)",
                APPLE_GREEN,
                [
                    ("Giọng Nữ Hoài My (vi-VN-HoaiMyNeural):", "Chất giọng truyền cảm, ấm áp, nhả chữ mượt mà, giàu cảm xúc. Rất phù hợp cho video review phim, vlog du lịch, ẩm thực, kể chuyện tâm sự, video đời sống."),
                    ("Giọng Nam Nam Minh (vi-VN-NamMinhNeural):", "Chất giọng trầm ấm, đĩnh đạc, dứt khoát, uy lực. Lựa chọn số 1 cho video tin tức, tài liệu khoa học, lịch sử, phân tích chiến thuật, review công nghệ."),
                    ("Điều Chỉnh Tốc Độ Đọc (0.8x - 1.3x):", "Linh hoạt tăng giảm tốc độ đọc để khớp vừa vặn với độ dài khung hình và nhịp điệu của video ngắn."),
                    ("Công Tắc Bật/Tắt Lồng Tiếng:", "Nếu bạn chỉ muốn tạo phụ đề chữ mà không muốn lồng tiếng, chỉ cần gạt tắt nút 'Lồng tiếng AI'."),
                ],
            ),
            (
                "🎵 4. Bộ Tách Nhạc Nền & Hòa Âm Thông Minh (Audio Separator & Ducking)",
                APPLE_ORANGE,
                [
                    ("Tách Vocal Giữ Nhạc Nền AI (Spleeter):", "Tách sạch giọng nói tiếng nước ngoài ra khỏi âm thanh gốc, giữ lại nguyên vẹn tiếng nhạc nền (BGM) và hiệu ứng âm thanh (SFX - tiếng nổ, tiếng xe, tiếng vỗ tay...)."),
                    ("Lồng Tiếng Chuẩn Phòng Thu:", "Sau khi tách, giọng đọc AI tiếng Việt sẽ được mix đè lên bản nhạc nền gốc, tạo cảm giác video được lồng tiếng chuyên nghiệp như rạp phim."),
                    ("Hạ Âm Lượng Nhạc Nền (Audio Ducking):", "Khi có giọng đọc AI, nhạc nền tự động giảm nhỏ xuống (15% - 30%) và tự động tăng lên khi hết câu nói."),
                    ("Trích Xuất MP3 320kbps Siêu Tốc:", "Công cụ 1-click giúp trích xuất âm thanh từ bất kỳ video nào thành file MP3 chất lượng cao ngay lập tức."),
                ],
            ),
            (
                "✍️ 5. Trình Chỉnh Sửa Phụ Đề Trực Quan (Visual Subtitle Editor)",
                APPLE_INDIGO,
                [
                    ("Xem Trước Danh Sách Câu Thoại:", "Hiển thị toàn bộ câu phụ đề kèm timestamp (thời điểm bắt đầu - kết thúc) rõ ràng."),
                    ("Chỉnh Sửa Trực Tiếp:", "Cho phép sửa lại lỗi chính tả, thay đổi từ ngữ theo phong cách cá nhân trước khi render video cuối cùng."),
                    ("Nghe Thử Từng Câu:", "Tích hợp nút nghe thử phát âm AI từng câu ngay trên danh sách để kiểm tra độ trôi chảy."),
                    ("Xuất File Độc Lập:", "Xuất ra file phụ đề chuẩn `.srt` và file kịch bản `.txt` để nhập vào CapCut, Premiere, DaVinci Resolve."),
                ],
            ),
            (
                "🎨 6. Cá Nhân Hóa Phong Cách Phụ Đề & Hạ Tầng Kỹ Thuật",
                APPLE_CYAN,
                [
                    ("5 Mẫu Preset Điện Ảnh:", "Vàng Viền Đen Nổi Bật (Viral TikTok), Trắng Tối Giản (Cinema), Hộp Đen (Boxed), Xanh Neon Gradient, Chữ To Nền Mờ."),
                    ("Tùy Biến Typography:", "Chỉnh phông chữ (Arial, Roboto, Montserrat...), kích cỡ chữ, màu sắc, độ dày viền nét (stroke), canh lề vị trí (Bottom, Center, Top)."),
                    ("Tự Động Kiểm Tra FFmpeg:", "Tích hợp công cụ chẩn đoán FFmpeg. Nếu máy chưa cài, bạn có thể tải và cài đặt tự động chỉ với 1-click."),
                    ("Quản Lý API Key Gemini:", "Nhập Key cá nhân để không bị nghẽn hạn ngạch, hỗ trợ chuyển đổi giữa Gemini 2.5 Flash và Gemini 2.5 Pro."),
                ],
            ),
        ]

        for mod_title, mod_color, mod_items in modules:
            card = ctk.CTkFrame(
                self,
                fg_color=BG_CARD,
                border_width=1,
                border_color=BORDER_CARD,
                corner_radius=12,
            )
            card.pack(fill="x", padx=4, pady=(0, 10))

            # Header Card
            ctk.CTkLabel(
                card,
                text=mod_title,
                font=("Arial", 13, "bold"),
                text_color=mod_color,
            ).pack(anchor="w", padx=16, pady=(12, 8))

            # Items
            items_box = ctk.CTkFrame(card, fg_color="transparent")
            items_box.pack(fill="x", padx=16, pady=(0, 12))

            for label, detail in mod_items:
                row = ctk.CTkFrame(items_box, fg_color="transparent")
                row.pack(fill="x", pady=3)

                ctk.CTkLabel(
                    row,
                    text=f"• {label} ",
                    font=("Arial", 11, "bold"),
                    text_color=TEXT_PRIMARY,
                ).pack(side="left", anchor="n")

                ctk.CTkLabel(
                    row,
                    text=detail,
                    font=("Arial", 11),
                    text_color=TEXT_SECONDARY,
                    wraplength=640,
                    justify="left",
                ).pack(side="left", fill="x", expand=True, anchor="w")

    # ═════════════════════════════════════════════════════════
    # 5. BẢNG TRA CỨU NHANH (CHEAT SHEET)
    # ═════════════════════════════════════════════════════════
    def _build_cheat_sheet_section(self):
        container = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        container.pack(fill="x", padx=4, pady=(4, 14))

        title_box = ctk.CTkFrame(container, fg_color="transparent")
        title_box.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            title_box,
            text="📊 BẢNG TRA CỨU NHANH CẤU HÌNH THEO NHU CẦU",
            font=("Arial", 14, "bold"),
            text_color=APPLE_ORANGE,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="Gợi ý cấu hình tối ưu cho từng thể loại video thường gặp",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        # Matrix Table
        table = ctk.CTkFrame(container, fg_color=BG_INSET, corner_radius=10, border_width=1, border_color=BORDER_INSET)
        table.pack(fill="x", padx=14, pady=(0, 16))
        table.grid_columnconfigure((0, 1, 2, 3), weight=1)

        headers = ["Loại Video", "Chế Độ Chọn", "Giọng Đọc & Tách Nhạc", "Mẫu Phụ Đề Đề Xuất"]
        for col, h in enumerate(headers):
            ctk.CTkLabel(
                table,
                text=h,
                font=("Arial", 11, "bold"),
                text_color=TEXT_PRIMARY,
            ).grid(row=0, column=col, padx=8, pady=8, sticky="w")

        rows = [
            ("Review Phim Trung, Douyin", "🇨🇳 Trung → Việt", "Hoài My (1.0x) + Tách nhạc BGM", "🟡 Vàng Viền Đen (TikTok)"),
            ("Bài Học, Phim Tài Liệu Anh", "🇺🇸 Anh → Việt", "Nam Minh (1.0x) + Giảm âm gốc 25%", "⚪️ Trắng Tối Giản"),
            ("Podcast, Vlog Tiếng Việt", "🇻🇳 Phụ Đề Tiếng Việt", "Tắt lồng tiếng (Giữ 100% giọng gốc)", "⬛️ Hộp Đen (Boxed)"),
            ("Tin Tức, Bình Luận Công Nghệ", "🇺🇸 Anh → Việt", "Nam Minh (1.05x) + Giữ âm gốc 15%", "🔵 Xanh Dương Modern"),
        ]

        for r_idx, row_data in enumerate(rows):
            bg = "transparent" if r_idx % 2 == 0 else BG_PILL
            for c_idx, cell in enumerate(row_data):
                f = ctk.CTkFrame(table, fg_color=bg, corner_radius=4)
                f.grid(row=r_idx + 1, column=c_idx, padx=4, pady=2, sticky="nsew")
                ctk.CTkLabel(
                    f,
                    text=cell,
                    font=("Arial", 10),
                    text_color=TEXT_SECONDARY if c_idx > 0 else APPLE_CYAN,
                ).pack(anchor="w", padx=4, pady=4)

    # ═════════════════════════════════════════════════════════
    # 6. BÍ KÍP PRO & PHÍM TẮT TIỆN ÍCH
    # ═════════════════════════════════════════════════════════
    def _build_pro_tips_section(self):
        self.tips_anchor = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        self.tips_anchor.pack(fill="x", padx=4, pady=(0, 14))

        title_box = ctk.CTkFrame(self.tips_anchor, fg_color="transparent")
        title_box.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            title_box,
            text="💡 BÍ KÍP SỬ DỤNG PRO & PHÍM TẮT TIỆN ÍCH",
            font=("Arial", 14, "bold"),
            text_color=APPLE_GREEN,
        ).pack(anchor="w")

        tips = [
            ("⚡ Dán Link Siêu Tốc:", "Khi copy link từ TikTok hoặc Facebook, chỉ cần click nút '📋 Dán Link', ứng dụng sẽ tự động loại bỏ các đoạn ký tự thừa và trích xuất URL gốc sạch sẽ."),
            ("📁 Kéo Thả Tiện Lợi:", "Bạn có thể kéo trực tiếp file video từ thư mục Desktop hoặc Finder thả vào bất kỳ đâu trên giao diện app."),
            ("🎬 Xuất Sang CapCut / Premiere:", "Mỗi lần dịch xong, app luôn lưu sẵn file phụ đề `.srt` trong thư mục `output/`. Bạn có thể kéo file `.srt` này vào CapCut để tạo hiệu ứng chữ động độc đáo."),
            ("🔑 Tăng Tốc Độ Dịch Với Key Riêng:", "Thêm API Key Gemini cá nhân tại mục '⚙️ Cài đặt' để không bao giờ bị giới hạn tốc độ hay chờ đợi hạn ngạch."),
            ("🌓 Chế Độ Ban Đêm (Dark Mode):", "Nhấn nút '🌓' ở góc trên bên phải để chuyển đổi giữa giao diện Dark Mode bảo vệ mắt và Light Mode hiện đại."),
        ]

        tips_box = ctk.CTkFrame(self.tips_anchor, fg_color="transparent")
        tips_box.pack(fill="x", padx=16, pady=(0, 16))

        for tip_title, tip_content in tips:
            row = ctk.CTkFrame(tips_box, fg_color="transparent")
            row.pack(fill="x", pady=4)

            ctk.CTkLabel(
                row,
                text=f"• {tip_title} ",
                font=("Arial", 11, "bold"),
                text_color=APPLE_CYAN,
            ).pack(side="left", anchor="n")

            ctk.CTkLabel(
                row,
                text=tip_content,
                font=("Arial", 11),
                text_color=TEXT_SECONDARY,
                wraplength=620,
                justify="left",
            ).pack(side="left", fill="x", expand=True, anchor="w")

    # ═════════════════════════════════════════════════════════
    # 7. GIẢI ĐÁP CÂU HỎI THƯỜNG GẶP (FAQ)
    # ═════════════════════════════════════════════════════════
    def _build_faq_section(self):
        container = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        container.pack(fill="x", padx=4, pady=(0, 14))

        title_box = ctk.CTkFrame(container, fg_color="transparent")
        title_box.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            title_box,
            text="❓ GIẢI ĐÁP THẮC MẮC THƯỜNG GẶP (FAQ)",
            font=("Arial", 14, "bold"),
            text_color=APPLE_PURPLE,
        ).pack(anchor="w")

        faqs = [
            (
                "Video hoàn thành được lưu ở đâu?",
                "Tất cả video đã ghép phụ đề, file âm thanh trích xuất và file phụ đề `.srt`, `.txt` đều được lưu tự động trong thư mục 'output/' của ứng dụng. Bạn có thể nhấp nút '📂 Mở Thư Mục' trên màn hình kết thúc để xem ngay.",
            ),
            (
                "Báo lỗi 'FFmpeg chưa sẵn sàng' thì khắc phục thế nào?",
                "Rất đơn giản, bạn chỉ cần nhấp vào huy hiệu '⚡ FFmpeg: Chưa có' trên thanh tiêu đề góc trên bên phải. Hệ thống sẽ mở hộp thoại tải và cài đặt tự động gói FFmpeg chính thức chỉ trong vài giây.",
            ),
            (
                "Làm sao để chỉ ghép phụ đề chữ mà không có giọng đọc đè lên?",
                "Ở thẻ cài đặt âm thanh, bạn chỉ cần tắt công tắc '🎙️ Lồng tiếng AI'. Ứng dụng sẽ giữ nguyên 100% giọng nói và âm thanh gốc của video và chỉ in phụ đề chữ lên màn hình.",
            ),
            (
                "Tôi có thể lấy Gemini API Key miễn phí ở đâu?",
                "Bạn chỉ cần truy cập aistudio.google.com, đăng nhập bằng tài khoản Google bất kỳ và chọn 'Get API Key'. Sau đó dán key vào mục '⚙️ Cài đặt' của ứng dụng.",
            ),
        ]

        faq_box = ctk.CTkFrame(container, fg_color="transparent")
        faq_box.pack(fill="x", padx=16, pady=(0, 16))

        for q, a in faqs:
            item_frame = ctk.CTkFrame(faq_box, fg_color=BG_INSET, corner_radius=8, border_width=1, border_color=BORDER_INSET)
            item_frame.pack(fill="x", pady=4)

            ctk.CTkLabel(
                item_frame,
                text=f"Q: {q}",
                font=("Arial", 11, "bold"),
                text_color=TEXT_PRIMARY,
            ).pack(anchor="w", padx=12, pady=(8, 2))

            ctk.CTkLabel(
                item_frame,
                text=f"👉 {a}",
                font=("Arial", 11),
                text_color=TEXT_SECONDARY,
                wraplength=670,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 8))

    # ═════════════════════════════════════════════════════════
    # 8. FOOTER CALL TO ACTION (QUAY VỀ STUDIO)
    # ═════════════════════════════════════════════════════════
    def _build_footer_cta(self):
        footer_card = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=14,
        )
        footer_card.pack(fill="x", padx=4, pady=(4, 20))

        ctk.CTkLabel(
            footer_card,
            text="Sẵn Sàng Trải Nghiệm Công Nghệ Dịch Thuật Đỉnh Cao?",
            font=("Arial", 15, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            footer_card,
            text="Quay lại Studio để chọn video và bắt đầu sáng tạo ngay bây giờ!",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
        ).pack(pady=(0, 12))

        ctk.CTkButton(
            footer_card,
            text="🎬 BẮT ĐẦU LÀM VIỆC TẠI STUDIO",
            font=("Arial", 13, "bold"),
            fg_color=APPLE_BLUE,
            hover_color=APPLE_BLUE_HOVER,
            height=40,
            width=260,
            corner_radius=8,
            command=self._handle_start_click,
        ).pack(pady=(0, 14))

        ctk.CTkLabel(
            footer_card,
            text="⭐️ Bản quyền & phát triển bởi Bành Đại Dũng - Hotline / Zalo: 0982333097",
            font=("Arial", 10, "bold"),
            text_color=APPLE_CYAN,
        ).pack(pady=(0, 12))

    # ═════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═════════════════════════════════════════════════════════
    def _handle_start_click(self):
        if self.on_start_clicked:
            self.on_start_clicked()

    def _scroll_to_features(self):
        # Cuộn nhẹ nhàng xuống phần chi tiết tính năng
        try:
            self._parent_canvas.yview_moveto(0.18)
        except Exception:
            pass

    def _setup_mousewheel_scroll(self):
        """Cấu hình cuộn chuột siêu nhạy và mượt mà cho macOS và Windows."""
        import sys

        # Ghi đè phương thức _mouse_wheel_all của CustomTkinter để tối ưu độ nhạy con lăn
        self._mouse_wheel_all = self._on_mousewheel_event

        # Bắt sự kiện lăn chuột trên toàn bộ cửa sổ để cuộn kể cả khi hover vào bất kỳ thẻ card nào
        self.bind_all("<MouseWheel>", self._on_mousewheel_event, add=True)
        self.bind_all("<Button-4>", self._on_mousewheel_event, add=True)
        self.bind_all("<Button-5>", self._on_mousewheel_event, add=True)

    def _on_mousewheel_event(self, event):
        """Xử lý sự kiện lăn chuột với độ nhạy tối ưu trên macOS và Windows."""
        # Chỉ xử lý khi GuideView đang được hiển thị trên màn hình
        try:
            if not self._parent_frame.winfo_ismapped():
                return
        except Exception:
            return

        # Kiểm tra con trỏ chuột có đang nằm trong phạm vi GuideView không
        try:
            x_root = event.x_root
            y_root = event.y_root
            target = self.winfo_containing(x_root, y_root)
        except Exception:
            target = None

        if target is None:
            return

        # Kiểm tra target có phải con cháu của GuideView không
        is_inside = False
        curr = target
        while curr is not None:
            if curr == self or curr == self._parent_canvas or curr == self._parent_frame:
                is_inside = True
                break
            curr = getattr(curr, "master", None)

        if not is_inside:
            return

        # Tính toán khoảng cách cuộn
        import sys
        delta = getattr(event, "delta", 0)
        if sys.platform == "darwin":
            # Trên macOS: chuột thường (notched wheel) có delta = 1 hoặc -1; trackpad có delta biến thiên
            if delta != 0:
                if abs(delta) <= 2:
                    # Chuột con lăn có khấc (Logitech, chuột dây, chuột Bluetooth thông thường)
                    step = -int(delta * 28)
                else:
                    # Trackpad hoặc Apple Magic Mouse
                    step = -int(delta * 2)
            else:
                step = -25 if getattr(event, "num", 0) == 4 else 25
        elif sys.platform.startswith("win"):
            step = -int(delta / 4)
        else:
            # Linux
            step = -25 if getattr(event, "num", 0) == 4 else 25

        if step != 0:
            try:
                self._parent_canvas.yview_scroll(step, "units")
            except Exception:
                pass
            return "break"
