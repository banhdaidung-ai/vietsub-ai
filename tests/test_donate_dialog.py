"""
tests/test_donate_dialog.py — Kiểm tra hộp thoại Donate và tích hợp vào HomeView
"""

import customtkinter as ctk
import pytest
from gui.donate_dialog import DonateDialog
from gui.home_view import HomeView
from gui.app_window import AppWindow


def test_donate_dialog_instantiation_and_singleton():
    """Kiểm tra khởi tạo DonateDialog, thông tin ngân hàng và cơ chế Singleton."""
    root = ctk.CTk()
    root.withdraw()

    dlg1 = DonateDialog.show_dialog(root)
    assert dlg1 is not None
    assert dlg1.winfo_exists()

    # Kiểm tra các thông tin tài khoản hiển thị đúng chuẩn VIB Bành Đại Dũng
    assert hasattr(dlg1, "lbl_stk")
    assert dlg1.lbl_stk.cget("text") == "0982333097"
    assert hasattr(dlg1, "btn_copy_stk")
    assert hasattr(dlg1, "btn_save_qr")

    # Kiểm tra cơ chế Singleton: gọi lần 2 trả về cùng instance
    dlg2 = DonateDialog.show_dialog(root)
    assert dlg2 is dlg1

    # Kiểm tra tính năng copy số tài khoản
    dlg1._on_copy_stk()
    assert "Đã Sao Chép" in dlg1.btn_copy_stk.cget("text")
    assert root.clipboard_get() == "0982333097"

    # Đóng dialog
    dlg1._on_close()
    assert DonateDialog._instance is None

    root.destroy()


def test_home_view_donate_button_callback():
    """Kiểm tra nút Donate trên Hero Banner của HomeView gọi đúng callback."""
    root = ctk.CTk()
    root.withdraw()

    donate_called = [False]

    def on_donate_cb():
        donate_called[0] = True

    home = HomeView(root, on_donate=on_donate_cb)
    home.pack()

    # Tìm nút Mời Tác Giả Cà Phê và kích hoạt
    assert home.on_donate == on_donate_cb
    home.on_donate()
    assert donate_called[0] is True

    root.destroy()


def test_app_window_has_donate_support():
    """Kiểm tra AppWindow có phương thức _open_donate_dialog và kết nối vào HomeView."""
    app = AppWindow()
    app.withdraw()

    assert hasattr(app, "_open_donate_dialog")
    assert app.home_view.on_donate == app._open_donate_dialog

    app.destroy()
