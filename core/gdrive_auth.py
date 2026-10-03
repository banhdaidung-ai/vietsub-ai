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


AUTH_COOKIE_NAMES = {
    "SID", "OSID", "__Secure-OSID", "__Secure-1PSID", "__Secure-3PSID",
    "SSID", "HSID", "COMPASS", "SAPISID", "APISID"
}


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

    # Fallback kiểm tra trực tiếp các dòng Netscape trong file phòng trường hợp cookiejar parser bỏ sót
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    domain, name, val = parts[0].lower(), parts[5], parts[6]
                    if "google" in domain and name in AUTH_COOKIE_NAMES and len(val) > 10:
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
    """
    Chuyển đổi danh sách cookie từ Playwright thành tệp Netscape cookies.txt chuẩn.
    Bảo vệ an toàn tuyệt đối với mọi kiểu dữ liệu của trường expires (None, float, int, str).
    """
    try:
        lines = [
            "# Netscape HTTP Cookie File",
            "# Created by Vietsub AI Google Drive Authentication",
            "",
        ]
        now_future = int(time.time()) + 30 * 86400
        for c in cookies:
            domain = c.get("domain", "")
            tailmatch = "TRUE" if domain.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"

            exp_val = c.get("expires")
            if exp_val is None:
                expires = now_future
            else:
                try:
                    exp_float = float(exp_val)
                    expires = int(exp_float) if exp_float > 0 else now_future
                except Exception:
                    expires = now_future

            name = c.get("name", "")
            value = c.get("value", "")
            if name and value:
                lines.append(f"{domain}\t{tailmatch}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

        target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception as e:
        print(f"[gdrive_auth] Lỗi khi ghi cookie Netscape: {e}")
        return False


_browser_login_lock = threading.Lock()
_browser_login_running = False


def is_browser_login_running() -> bool:
    """Kiểm tra xem đang có phiên trình duyệt đăng nhập Google nào đang chạy hay không."""
    global _browser_login_running
    return _browser_login_running


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
    Tự động đóng trình duyệt ngay lập tức và đưa ứng dụng trở lại màn hình làm việc.
    """
    global _browser_login_running
    with _browser_login_lock:
        if _browser_login_running:
            if on_error:
                on_error("Đang có một cửa sổ trình duyệt đăng nhập được mở. Vui lòng thao tác trên cửa sổ đó.")
            return
        _browser_login_running = True

    def log(msg: str):
        if on_status:
            on_status(msg)

    try:
        log("🌐 Đang khởi động trình duyệt để đăng nhập tài khoản Google công ty...")

        # Đảm bảo đường dẫn cache Playwright
        if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
            if sys.platform == "darwin":
                _pw_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
            elif sys.platform == "win32":
                _local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                _pw_cache = Path(_local) / "ms-playwright"
            else:
                _pw_cache = Path.home() / ".cache" / "ms-playwright"
            try:
                _pw_cache.mkdir(parents=True, exist_ok=True)
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_pw_cache)
            except Exception:
                pass

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

            # Sử dụng User-Agent Chrome 133 hiện đại để tránh bị Google hiện cảnh báo unsupported browser
            modern_ua = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            )
            context = browser.new_context(
                user_agent=modern_ua,
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
                        context.close()
                    except Exception:
                        pass
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
                    # Quét qua TẤT CẢ các trang/tab đang mở trong context (phòng trường hợp Google mở tab/cửa sổ mới)
                    all_pages = list(context.pages)
                    if not all_pages:
                        # Người dùng đã tự tay đóng hết cửa sổ trình duyệt
                        break

                    import urllib.parse
                    for cur_p in all_pages:
                        try:
                            cur_url = cur_p.url
                            if not cur_url:
                                continue
                            parsed = urllib.parse.urlparse(cur_url)
                            host = (parsed.hostname or "").lower()
                            path = parsed.path or ""

                            # Kiểm tra nếu bất kỳ tab nào đã chuyển tới drive.google.com hoặc docs.google.com
                            if ("drive.google.com" in host or "docs.google.com" in host) and not cur_url.startswith("https://accounts.google.com"):
                                # Chờ 1 giây để cookie phiên được ghi nhận đầy đủ
                                time.sleep(1)
                                cookies = context.cookies()
                                has_auth_cookie = any(
                                    c.get("name") in [
                                        "SID", "SSID", "HSID", "OSID", "__Secure-1PSID", "__Secure-3PSID",
                                        "__Secure-OSID", "COMPASS", "SAPISID", "APISID", "LOGIN_INFO"
                                    ]
                                    for c in cookies
                                )
                                # Nếu đã vào trang chủ Drive hoặc đã có cookie xác thực
                                if has_auth_cookie or ("/drive" in path) or ("folders" in path):
                                    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                                    saved = cookies_dict_to_netscape(cookies, GDRIVE_COOKIES_FILE)
                                    if saved:
                                        logged_in = True
                                        break
                        except Exception as e_page:
                            print(f"[gdrive_auth] Lỗi kiểm tra trang: {e_page}")
                            continue

                    if logged_in:
                        break

                except Exception:
                    # Trình duyệt có thể đã bị người dùng đóng bằng tay
                    break

                time.sleep(1)

            # Đóng trình duyệt ngay lập tức khi phát hiện đăng nhập thành công hoặc người dùng đóng
            try:
                context.close()
            except Exception:
                pass
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
    finally:
        with _browser_login_lock:
            _browser_login_running = False

