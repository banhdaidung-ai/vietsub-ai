"""
utils/subtitle_styles.py — Bộ Sưu Tập Mẫu Phụ Đề Chuẩn Phong Cách CapCut / TikTok
Cung cấp các preset màu sắc, viền, bóng, hộp nền và sinh chuỗi style cho FFmpeg.
"""

from typing import Dict, List, Any


CAPCUT_SUBTITLE_STYLES: Dict[str, Dict[str, Any]] = {
    "capcut_yellow": {
        "id": "capcut_yellow",
        "name": "✨ CapCut Vàng Chanh (Trending)",
        "desc": "Chữ vàng tươi, viền đen dày nổi bật số 1 trên TikTok, Shorts",
        "font_name": "Arial",
        "bold": 1,
        "italic": 0,
        "primary_color": "&H0000E6FF",   # Vàng chanh rực rỡ (RGB: #FFE600)
        "outline_color": "&H00000000",   # Viền đen sắc nét
        "back_color": "&H00000000",      # Trong suốt
        "border_style": 1,               # 1 = Outline + Drop shadow
        "outline_width": 2.2,
        "shadow_depth": 1.0,
        "ui_fg": "#FFE600",              # Màu chữ trên UI preview
        "ui_bg": "#1E2028",              # Màu nền preview
        "ui_border": "#FFE600",          # Viền preview
    },
    "capcut_white": {
        "id": "capcut_white",
        "name": "⚪ CapCut Trắng Viền Đen (Classic Bold)",
        "desc": "Chữ trắng tinh khôi viền đen đậm, tương phản cực cao trên mọi video",
        "font_name": "Arial",
        "bold": 1,
        "italic": 0,
        "primary_color": "&H00FFFFFF",   # Trắng tinh
        "outline_color": "&H00000000",   # Viền đen đậm
        "back_color": "&H00000000",
        "border_style": 1,
        "outline_width": 2.4,
        "shadow_depth": 1.0,
        "ui_fg": "#FFFFFF",
        "ui_bg": "#1E2028",
        "ui_border": "#94A3B8",
    },
    "capcut_blackbox": {
        "id": "capcut_blackbox",
        "name": "⬛ CapCut Hộp Nền Đen (Modern Box)",
        "desc": "Chữ trắng nằm trong hộp nền mờ sang trọng, phong cách Vlog / Podcast",
        "font_name": "Arial",
        "bold": 1,
        "italic": 0,
        "primary_color": "&H00FFFFFF",   # Trắng
        "outline_color": "&H50000000",   # Bo nhẹ viền hộp
        "back_color": "&H70000000",      # Hộp nền đen mờ sang trọng
        "border_style": 3,               # 3 = Hộp nền (Opaque Box background)
        "outline_width": 2.0,            # Độ dày đệm hộp
        "shadow_depth": 0.0,
        "ui_fg": "#FFFFFF",
        "ui_bg": "#000000",
        "ui_border": "#475569",
    },
    "capcut_cyan": {
        "id": "capcut_cyan",
        "name": "💠 CapCut Xanh Neon (Cyber Glow)",
        "desc": "Chữ xanh lơ neon rực rỡ phong cách công nghệ, trẻ trung, hiện đại",
        "font_name": "Arial",
        "bold": 1,
        "italic": 0,
        "primary_color": "&H00FFFF00",   # Xanh lơ Cyber Cyan (RGB: #00FFFF)
        "outline_color": "&H00000000",   # Viền đen
        "back_color": "&H00000000",
        "border_style": 1,
        "outline_width": 2.2,
        "shadow_depth": 1.0,
        "ui_fg": "#00FFFF",
        "ui_bg": "#1E2028",
        "ui_border": "#00FFFF",
    },
    "capcut_orange": {
        "id": "capcut_orange",
        "name": "🔥 CapCut Cam Lửa (Viral Highlight)",
        "desc": "Chữ cam vàng rực rỡ phong cách tin tức nóng hổi, kịch tính",
        "font_name": "Arial",
        "bold": 1,
        "italic": 0,
        "primary_color": "&H00008CFF",   # Cam lửa ấm áp (RGB: #FF8C00)
        "outline_color": "&H00000000",   # Viền đen đậm
        "back_color": "&H00000000",
        "border_style": 1,
        "outline_width": 2.4,
        "shadow_depth": 1.0,
        "ui_fg": "#FF8C00",
        "ui_bg": "#1E2028",
        "ui_border": "#FF8C00",
    },
    "capcut_minimal": {
        "id": "capcut_minimal",
        "name": "🎬 CapCut Tối Giản Điện Ảnh (Cinema)",
        "desc": "Chữ trắng trang nhã, viền mảnh tự nhiên cho phim tài liệu, phong cảnh",
        "font_name": "Arial",
        "bold": 1,
        "italic": 0,
        "primary_color": "&H00F0F0F0",   # Trắng ngọc trai
        "outline_color": "&H00181818",   # Viền xám đen mảnh
        "back_color": "&H00000000",
        "border_style": 1,
        "outline_width": 1.0,
        "shadow_depth": 0.5,
        "ui_fg": "#F1F5F9",
        "ui_bg": "#1E2028",
        "ui_border": "#64748B",
    },
}

DEFAULT_PRESET_ID = "capcut_yellow"


def get_style_preset_list() -> List[Dict[str, Any]]:
    """Trả về danh sách các preset hỗ trợ sắp xếp theo thứ tự hiển thị."""
    return list(CAPCUT_SUBTITLE_STYLES.values())


def get_style_display_names() -> List[str]:
    """Trả về danh sách tên hiển thị cho dropdown UI."""
    return [p["name"] for p in CAPCUT_SUBTITLE_STYLES.values()]


def get_preset_by_name(display_name: str) -> Dict[str, Any]:
    """Tìm preset theo tên hiển thị trên UI."""
    for p in CAPCUT_SUBTITLE_STYLES.values():
        if p["name"] == display_name:
            return p
    return CAPCUT_SUBTITLE_STYLES[DEFAULT_PRESET_ID]


def get_preset_by_id(preset_id: str) -> Dict[str, Any]:
    """Tìm preset theo ID kỹ thuật."""
    return CAPCUT_SUBTITLE_STYLES.get(preset_id, CAPCUT_SUBTITLE_STYLES[DEFAULT_PRESET_ID])


def build_ffmpeg_subtitle_style(
    preset_id: str = "capcut_yellow",
    font_size: int = 12,
    margin_v: int = 15,
    alignment: int = 2,
) -> str:
    """
    Sinh chuỗi cấu hình style chuẩn ASS cho FFmpeg filter `subtitles=...:force_style='...'`.
    
    Args:
        preset_id: ID của mẫu phụ đề CapCut (ví dụ: 'capcut_yellow', 'capcut_blackbox'...)
        font_size: Cỡ chữ (pt)
        margin_v: Khoảng cách từ đáy video lên vị trí chữ (px)
        alignment: Căn lề (2 = Căn giữa dưới)
    """
    preset = get_preset_by_id(preset_id)

    style_tokens = [
        f"Fontname={preset.get('font_name', 'Arial')}",
        f"FontSize={font_size}",
        f"Bold={preset.get('bold', 1)}",
        f"Italic={preset.get('italic', 0)}",
        f"PrimaryColour={preset.get('primary_color', '&H00FFFFFF')}",
        f"OutlineColour={preset.get('outline_color', '&H00000000')}",
        f"BackColour={preset.get('back_color', '&H00000000')}",
        f"BorderStyle={preset.get('border_style', 1)}",
        f"Outline={preset.get('outline_width', 2.0)}",
        f"Shadow={preset.get('shadow_depth', 1.0)}",
        f"MarginV={margin_v}",
        f"Alignment={alignment}",
    ]

    return ",".join(style_tokens)
