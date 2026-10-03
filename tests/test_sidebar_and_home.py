"""
tests/test_sidebar_and_home.py — Bộ test chuyên biệt cho kiến trúc Sidebar & Home Dashboard
Kiểm tra:
1. HomeView: khởi tạo các thẻ công cụ, callback điều hướng
2. AppWindow Sidebar: danh sách nút, trạng thái highlight macOS
3. Chuyển đổi linh hoạt giữa Home, Vietsub Studio, và GuideView
4. Đồng bộ 2 chiều giữa Sidebar và Studio Tabview
"""

import pytest
import customtkinter as ctk
from gui.app_window import AppWindow
from gui.home_view import HomeView


def test_home_view_standalone():
    """Kiểm tra HomeView hoạt động độc lập và gửi đúng tool_id khi click."""
    root = ctk.CTk()
    root.withdraw()

    clicked_ids = []

    def on_nav(tid):
        clicked_ids.append(tid)

    home = HomeView(root, on_navigate=on_nav)
    home.pack(fill="both", expand=True)

    # Test click callback
    home._handle_click("vietsub")
    home._handle_click("compressor")
    home._handle_click("separator")

    assert clicked_ids == ["vietsub", "compressor", "separator"]

    root.destroy()


def test_app_window_sidebar_and_canvas():
    """Kiểm tra AppWindow: Sidebar, Home Dashboard, Vietsub Studio và GuideView."""
    app = AppWindow()
    app.withdraw()

    # Kiểm tra sự tồn tại của Sidebar và các container chính
    assert hasattr(app, "sidebar_card"), "Phải có sidebar_card"
    assert hasattr(app, "main_canvas"), "Phải có main_canvas"
    assert hasattr(app, "home_view"), "Phải có home_view"
    assert hasattr(app, "vietsub_container"), "Phải có vietsub_container"
    assert hasattr(app, "guide_view"), "Phải có guide_view"

    # Kiểm tra các nút trong Sidebar
    expected_keys = {"home", "vietsub", "separator", "downloader", "compressor", "sub_editor", "guide"}
    assert set(app._sidebar_buttons.keys()) == expected_keys

    # Mặc định khởi động vào Trang Chủ
    assert getattr(app, "_current_canvas_view", "") == "home"
    assert getattr(app, "_active_sidebar_key", "") == "home"

    # Chuyển sang Vietsub Studio
    app._on_sidebar_select("vietsub")
    assert app._current_canvas_view == "vietsub"
    assert app._active_sidebar_key == "vietsub"

    # Chuyển sang Downloader (thuộc Studio nhưng chọn tab URL Online)
    app._on_sidebar_select("downloader")
    assert app._current_canvas_view == "vietsub"
    assert app._active_sidebar_key == "downloader"
    assert "Link Online" in app.tabview.get()

    # Chuyển sang Hướng Dẫn
    app._on_sidebar_select("guide")
    assert app._current_canvas_view == "guide"
    assert app._active_sidebar_key == "guide"

    # Chuyển quay lại Trang Chủ
    app._on_sidebar_select("home")
    assert app._current_canvas_view == "home"
    assert app._active_sidebar_key == "home"

    app.destroy()


def test_tabview_sidebar_synchronization():
    """Kiểm tra tính đồng bộ 2 chiều: khi đổi tab trong Vietsub Studio thì Sidebar đổi tương ứng."""
    app = AppWindow()
    app.withdraw()

    # Mở Vietsub Studio
    app._on_sidebar_select("vietsub")
    assert app._active_sidebar_key == "vietsub"

    # Giả lập chuyển sang tab URL Online trong Studio
    app.tabview.set("🌐 Dán Link Online (TikTok, YouTube, Facebook...)")
    app._on_tab_changed()
    assert app._active_sidebar_key == "downloader"

    # Giả lập chuyển lại tab Chọn File trong Studio
    app.tabview.set("📂 Chọn File Video Trên Máy")
    app._on_tab_changed()
    assert app._active_sidebar_key == "vietsub"

    app.destroy()
