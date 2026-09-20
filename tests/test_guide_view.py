"""
tests/test_guide_view.py — Kiểm thử tự động Tab Hướng Dẫn Sử Dụng (Landing Page)
và cơ chế chuyển đổi Tab an toàn (Zero-Regression) trong Vietsub AI Studio.
"""

import pytest
import customtkinter as ctk
from gui.guide_view import GuideView


def test_guide_view_instantiation():
    """Kiểm tra khởi tạo GuideView độc lập thành công."""
    root = ctk.CTk()
    root.withdraw()

    start_clicked = []
    guide = GuideView(root, on_start_clicked=lambda: start_clicked.append(True))
    assert guide is not None

    # Thử click nút bắt đầu
    guide._handle_start_click()
    assert start_clicked == [True]

    root.destroy()


def test_guide_view_mousewheel_scrolling():
    """Kiểm tra sự kiện lăn chuột hoạt động nhạy và mượt mà trên macOS."""
    root = ctk.CTk()
    root.withdraw()

    guide = GuideView(root)
    guide.pack(fill="both", expand=True)
    root.update_idletasks()

    initial_pos = guide._parent_canvas.yview()[0]

    # Giả lập lăn chuột xuống (delta = -1 trên macOS)
    guide._parent_canvas.yview_scroll(28, "units")
    new_pos = guide._parent_canvas.yview()[0]
    assert new_pos > initial_pos, "Vị trí trang phải cuộn xuống khi lăn chuột"

    root.destroy()


def test_app_window_tab_switching():
    """Kiểm tra việc tích hợp GuideView và chuyển đổi tab trên AppWindow."""
    from gui.app_window import AppWindow

    app = AppWindow()
    app.withdraw()

    assert hasattr(app, "nav_tabs")
    assert hasattr(app, "guide_view")
    assert hasattr(app, "_studio_widgets")

    # Mặc định ở tab Studio
    assert app.nav_tabs.get() == "🎬 Studio Làm Việc"

    # Chuyển sang Tab Hướng Dẫn
    app._switch_to_tab("📖 Hướng Dẫn Sử Dụng")
    assert app.nav_tabs.get() == "📖 Hướng Dẫn Sử Dụng"

    # Chuyển lại về Tab Studio
    app._switch_to_tab("🎬 Studio Làm Việc")
    assert app.nav_tabs.get() == "🎬 Studio Làm Việc"

    app.destroy()
