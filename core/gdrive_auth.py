"""
core/gdrive_auth.py — Quản lý xác thực tài khoản Google công ty (Cookies & Session)
Hỗ trợ đăng nhập trực tiếp qua trình duyệt, dán chuỗi Cookie hoặc nhập file cookies.txt
để tải các tệp/thư mục nội bộ Google Workspace/Google Drive bị giới hạn email công ty.
"""

import http.cookiejar
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

CONFIG_DIR = Path.home() / ".vietsub_ai"
GDRIVE_COOKIES_FILE = CONFIG_DIR / "gdrive_cookies.txt"


def get_cookies_path() -> Optional[str]:
    """Trả về đường dẫn tệp cookie nếu tồn tại và hợp lệ, ngược lại trả về None."""
    if GDRIVE_COOKIES_FILE.exists() and GDRIVE_COOKIES_FILE.stat().st_size > 50:
        return str(GDRIVE_COOKIES_FILE)
    return None


AUTH_COOKIE_NAMES = {"SID", "OSID", "__Secure-OSID", "__Secure-1PSID", "__Secure-3PSID", "SSID", "HSID"}


def has_valid_cookies() -> bool:
    """Kiểm tra xem hệ thống đã lưu cookie Google hợp lệ hay chưa."""
    path = get_cookies_path()
    if not path:
        return False
    try:
        jar = http.cookiejar.MozillaCookieJar(path)
        jar.load(ignore_discard=True, ignore_expires=True)
        # Kiểm tra xem có ít nhất một cookie phiên xác thực hợp lệ của Google hay không
        for c in jar:
            if "google" in c.domain.lower() and c.name in AUTH_COOKIE_NAMES and len(c.value or "") > 10:
                return True
    except Exception:
        pass
    return False


def clear_cookies() -> None:
    """Xóa tệp cookie đã lưu."""
    if GDRIVE_COOKIES_FILE.exists():
        try:
            GDRIVE_COOKIES_FILE.unlink()
        except Exception:
            pass


def save_raw_cookie_string(cookie_str: str) -> bool:
    """
    Chuyển đổi chuỗi Cookie (dạng key=val; key2=val2) thành tệp Netscape cookies.txt chuẩn.
    """
    if not cookie_str or not cookie_str.strip():
        return False

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Created by Vietsub AI for Google Drive",
        "",
    ]

    pairs = [p.strip() for p in cookie_str.split(";") if "=" in p]
    if not pairs:
        return False

    now_future = int(time.time()) + 30 * 86400  # 30 ngày

    for p in pairs:
        parts = p.split("=", 1)
        name, val = parts[0].strip(), parts[1].strip()
        if not name or not val:
            continue
        # Ghi cho cả .google.com và drive.google.com
        lines.append(f".google.com\tTRUE\t/\tTRUE\t{now_future}\t{name}\t{val}")
        lines.append(f"drive.google.com\tFALSE\t/\tTRUE\t{now_future}\t{name}\t{val}")

    try:
        with open(GDRIVE_COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False


def save_cookie_file(src_path: str) -> bool:
    """Sao chép tệp cookies.txt từ người dùng vào thư mục cấu hình của ứng dụng."""
    if not src_path or not os.path.exists(src_path):
        return False
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, str(GDRIVE_COOKIES_FILE))
        return has_valid_cookies()
    except Exception:
        return False


def cookies_dict_to_netscape(cookies: List[Dict[str, Any]], target_file: Path) -> bool:
    """Chuyển đổi danh sách cookie từ Playwright thành tệp Netscape cookies.txt chuẩn."""
    lines = [
        "# Netscape HTTP Cookie File",
        "# Created by Vietsub AI Google Drive Authentication",
        "",
    ]
    for c in cookies:
        domain = c.get("domain", "")
        tailmatch = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expires = int(c.get("expires", -1))
        if expires <= 0:
            expires = int(time.time()) + 30 * 86400
        name = c.get("name", "")
        value = c.get("value", "")
        if name and value:
            lines.append(f"{domain}\t{tailmatch}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

    try:
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False


def login_google_via_browser(
    on_status: Optional[Callable[[str], None]] = None,
    on_success: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    manual_save_event: Optional[threading.Event] = None,
) -> None:
    """
    Mở cửa sổ trình duyệt Chrome/Chromium để người dùng đăng nhập tài khoản Google (email công ty).
    Khi người dùng đăng nhập thành công vào Google Drive, tự động trích xuất cookie và lưu lại.
    Hỗ trợ nút lưu thủ công ngay khi người dùng đã vào đến Drive.
    """
    def log(msg: str):
        if on_status:
            on_status(msg)

    try:
        log("🌐 Đang khởi động trình duyệt để đăng nhập tài khoản Google công ty...")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Thử mở trình duyệt Chrome thật trên máy nếu có, hoặc dùng Chromium tích hợp
            launch_kwargs: Dict[str, Any] = {
                "headless": False,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
                "ignore_default_args": ["--enable-automation"],
            }
            if sys.platform == "darwin" and os.path.exists("/Applications/Google Chrome.app"):
                launch_kwargs["channel"] = "chrome"

            try:
                browser = p.chromium.launch(**launch_kwargs)
            except Exception:
                # Fallback về Chromium mặc định
                launch_kwargs.pop("channel", None)
                browser = p.chromium.launch(**launch_kwargs)

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1080, "height": 760},
            )
            page = context.new_page()

            login_url = "https://accounts.google.com/ServiceLogin?service=wise&passive=1209600&continue=https://drive.google.com/"
            page.goto(login_url)

            log("👉 Hãy đăng nhập email công ty trên trình duyệt vừa mở. Khi vào đến Drive, hệ thống sẽ tự lưu!")

            logged_in = False
            account_email = ""

            for _ in range(600):  # Chờ tối đa 10 phút
                if cancel_event and cancel_event.is_set():
                    log("⏹ Người dùng đã hủy đăng nhập.")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    if on_error:
                        on_error("Đã hủy thao tác đăng nhập.")
                    return

                # Nếu người dùng bấm nút [Lưu Phiên Ngay] trên giao diện app
                if manual_save_event and manual_save_event.is_set():
                    log("💾 Đang trích xuất và lưu phiên làm việc hiện tại...")
                    cookies = context.cookies()
                    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                    cookies_dict_to_netscape(cookies, GDRIVE_COOKIES_FILE)
                    logged_in = True
                    break

                try:
                    cur_url = page.url
                    import urllib.parse
                    parsed = urllib.parse.urlparse(cur_url)
                    # Chỉ kích hoạt tự động khi hostname THẬT SỰ là drive.google.com VÀ không còn ở accounts.google.com
                    if parsed.hostname == "drive.google.com" and not cur_url.startswith("https://accounts.google.com"):
                        time.sleep(2)  # Đợi thêm 2 giây để cookie thiết lập toàn bộ
                        cookies = context.cookies()
                        has_auth_cookie = any(
                            c.get("name") in ["SID", "SSID", "HSID", "OSID", "__Secure-1PSID", "__Secure-OSID"]
                            for c in cookies
                        )
                        if has_auth_cookie:
                            logged_in = True
                            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                            cookies_dict_to_netscape(cookies, GDRIVE_COOKIES_FILE)
                            break
                except Exception:
                    # Trình duyệt có thể đã bị người dùng đóng bằng tay
                    break

                time.sleep(1)

            try:
                browser.close()
            except Exception:
                pass

            if logged_in and has_valid_cookies():
                log("✅ Đã kết nối và lưu phiên đăng nhập tài khoản Google công ty thành công!")
                if on_success:
                    on_success(account_email or "Tài khoản công ty")
            else:
                log("❌ Chưa hoàn tất đăng nhập hoặc cửa sổ trình duyệt đã bị đóng.")
                if on_error:
                    on_error("Chưa hoàn tất đăng nhập tài khoản Google.")

    except Exception as e:
        err = f"Lỗi khởi động trình duyệt: {e}"
        log(f"❌ {err}")
        if on_error:
            on_error(err)

