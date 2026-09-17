"""
tests/test_subtitle_styles.py — Kiểm tra bộ mẫu phụ đề chuẩn CapCut / TikTok
"""

import pytest
from utils.subtitle_styles import (
    CAPCUT_SUBTITLE_STYLES,
    DEFAULT_PRESET_ID,
    get_style_preset_list,
    get_style_display_names,
    get_preset_by_name,
    get_preset_by_id,
    build_ffmpeg_subtitle_style,
)


def test_presets_structure():
    """Kiểm tra cấu trúc và tính đầy đủ của các preset phụ đề."""
    assert len(CAPCUT_SUBTITLE_STYLES) >= 6
    for preset_id, preset in CAPCUT_SUBTITLE_STYLES.items():
        assert "name" in preset
        assert "desc" in preset
        assert "font_name" in preset
        assert "primary_color" in preset
        assert "outline_color" in preset
        assert "back_color" in preset
        assert "border_style" in preset
        assert "outline_width" in preset
        assert "shadow_depth" in preset
        assert "ui_fg" in preset
        assert "ui_bg" in preset
        assert "ui_border" in preset


def test_get_style_preset_list():
    presets = get_style_preset_list()
    assert isinstance(presets, list)
    assert len(presets) == len(CAPCUT_SUBTITLE_STYLES)
    assert any(p["id"] == "capcut_yellow" for p in presets)
    assert any(p["id"] == "capcut_blackbox" for p in presets)


def test_get_style_display_names():
    names = get_style_display_names()
    assert isinstance(names, list)
    assert len(names) == len(CAPCUT_SUBTITLE_STYLES)
    assert any("Vàng Chanh" in name for name in names)
    assert any("Nền Đen Xám" in name for name in names)


def test_get_preset_by_name():
    names = get_style_display_names()
    first_name = names[0]
    preset = get_preset_by_name(first_name)
    assert preset["name"] == first_name

    # Fallback khi không tìm thấy
    fallback = get_preset_by_name("Non-Existent Style")
    assert fallback["id"] == DEFAULT_PRESET_ID


def test_get_preset_by_id():
    p_box = get_preset_by_id("capcut_blackbox")
    assert p_box["id"] == "capcut_blackbox"
    assert p_box["border_style"] == 3  # Hộp nền mờ/đen xám
    assert p_box["back_color"] == "&H00171313"

    # Fallback khi ID không tồn tại
    p_invalid = get_preset_by_id("invalid_xyz")
    assert p_invalid["id"] == DEFAULT_PRESET_ID


def test_build_ffmpeg_subtitle_style():
    # Test preset vàng
    style_yellow = build_ffmpeg_subtitle_style("capcut_yellow", font_size=12, margin_v=15)
    assert "Fontname=Arial" in style_yellow
    assert "FontSize=12" in style_yellow
    assert "PrimaryColour=&H0000E6FF" in style_yellow
    assert "MarginV=15" in style_yellow
    assert "Alignment=2" in style_yellow

    # Test preset hộp đen xám (BorderStyle=3)
    style_blackbox = build_ffmpeg_subtitle_style("capcut_blackbox", font_size=14, margin_v=20)
    assert "FontSize=14" in style_blackbox
    assert "BorderStyle=3" in style_blackbox
    assert "BackColour=&H00171313" in style_blackbox
    assert "MarginV=20" in style_blackbox


def test_all_presets_produce_valid_ffmpeg_style():
    """Đảm bảo tất cả preset đều sinh chuỗi style hợp lệ không lỗi."""
    for preset_id in CAPCUT_SUBTITLE_STYLES.keys():
        style_str = build_ffmpeg_subtitle_style(preset_id, font_size=11, margin_v=10)
        assert isinstance(style_str, str)
        assert len(style_str) > 20
        assert "PrimaryColour=" in style_str
        assert "FontSize=11" in style_str
        assert "MarginV=10" in style_str
