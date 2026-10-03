"""
core/gdrive_downloader.py — Module tải tệp và thư mục Google Drive trực tiếp (Không nén ZIP)
Hỗ trợ quét cây thư mục đệ quy, tải đa luồng, lọc ảnh, bỏ qua file trùng và báo tiến độ realtime.
"""

import os
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import gdown
from gdown.exceptions import DownloadCancelled, DownloadError

from core.gdrive_auth import get_cookies_path, has_valid_cookies

# ── Monkey-patch gdown download_folder để chặn chuyển hướng login giả 200 OK ──
try:
    import importlib
    import sys
    df_mod = sys.modules.get("gdown.download_folder")
    if not df_mod:
        df_mod = importlib.import_module("gdown.download_folder")
    if hasattr(df_mod, "_parse_embedded_folder_view"):
        _orig_parse = df_mod._parse_embedded_folder_view

        def _safe_parse_embedded_folder_view(*args, **kwargs):
            folder_name, children = _orig_parse(*args, **kwargs)
            if folder_name in ["Redirecting...", "Sign in - Google Accounts", "Đăng nhập - Tài khoản Google"]:
                raise DownloadError(
                    "AUTHENTICATION_REQUIRED: Google Drive yêu cầu xác thực email công ty để truy cập."
                )
            return folder_name, children

        df_mod._parse_embedded_folder_view = _safe_parse_embedded_folder_view
except Exception:
    pass
# ─────────────────────────────────────────────────────────────────────────────

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif",
    ".svg",
    ".raw",
    ".cr2",
    ".nef",
    ".arw",
    ".dng",
    ".psd",
    ".heic",
    ".heif",
}


def parse_gdrive_url(url: str) -> Tuple[Optional[str], str]:
    """
    Phân tích đường link Google Drive để trích xuất ID và phân loại.
    
    Returns:
        (item_id, item_type) với item_type là 'folder', 'file', hoặc 'unknown'.
    """
    if not url:
        return None, "unknown"

    url = url.strip()

    # Nếu truyền thẳng một ID dạng chuỗi (25 - 60 ký tự không có slash/space)
    if re.fullmatch(r"[a-zA-Z0-9_-]{25,60}", url):
        return url, "unknown"

    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in ["drive.google.com", "docs.google.com"]:
        # Fallback thử regex tìm ID trong URL
        match_folder = re.search(r"folders/([a-zA-Z0-9_-]{25,})", url)
        if match_folder:
            return match_folder.group(1), "folder"
        match_file = re.search(r"file/d/([a-zA-Z0-9_-]{25,})", url)
        if match_file:
            return match_file.group(1), "file"
        return None, "unknown"

    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)

    # 1. Thư mục (Folder)
    # /drive/folders/{id} hoặc /drive/u/{num}/folders/{id} hoặc /drive/mobile/folders/{id}
    folder_match = re.search(r"/folders/([a-zA-Z0-9_-]{25,})", path)
    if folder_match:
        return folder_match.group(1), "folder"

    # 2. Tệp đơn (File)
    # /file/d/{id}/view hoặc /file/u/{num}/d/{id}
    file_match = re.search(r"/file/(?:u/\d+/)?d/([a-zA-Z0-9_-]{25,})", path)
    if file_match:
        return file_match.group(1), "file"

    # 3. Google Docs, Sheets, Slides
    doc_match = re.search(r"/(?:document|spreadsheets|presentation)/(?:u/\d+/)?d/([a-zA-Z0-9_-]{25,})", path)
    if doc_match:
        return doc_match.group(1), "file"

    # 4. Tham số truy vấn ?id={id}
    if "id" in query and query["id"]:
        item_id = query["id"][0]
        if path.endswith("/folders"):
            return item_id, "folder"
        return item_id, "unknown"

    return None, "unknown"


def is_image_file(filepath: str) -> bool:
    """Kiểm tra đường dẫn tệp có phải định dạng hình ảnh hay không."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in IMAGE_EXTENSIONS


def format_bytes(bytes_count: float) -> str:
    """Định dạng số byte thành chuỗi dung lượng dễ đọc."""
    if bytes_count < 1024:
        return f"{bytes_count:.0f} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


class GDriveDownloader:
    """
    Trình tải Google Drive chuyên biệt cho hình ảnh & thư mục lớn:
    - Không bao giờ nén zip
    - Giữ trọn cấu trúc cây thư mục con
    - Tải song song đa luồng (Multi-threading)
    - Tự động bỏ qua file đã có (Skip existing)
    - Hỗ trợ dừng/hủy an toàn
    """

    def __init__(self, max_workers: int = 3):
        self.max_workers = max(1, min(max_workers, 8))

    def scan_folder(self, folder_id: str, output_dir: str) -> List[Dict[str, Any]]:
        """
        Quét cây thư mục Google Drive mà không tải file (skip_download=True).
        Trả về danh sách các tệp cùng đường dẫn lưu trữ.
        """
        cookie_path = get_cookies_path()
        use_cookies = bool(cookie_path and has_valid_cookies())
        raw_files = gdown.download_folder(
            id=folder_id,
            output=output_dir,
            skip_download=True,
            quiet=True,
            use_cookies=use_cookies,
            cookies_file=cookie_path if use_cookies else None,
        )

        items = []
        for f in raw_files:
            # f có các trường: id, path (đường dẫn tương đối), local_path
            f_id = getattr(f, "id", None)
            rel_path = getattr(f, "path", "")
            local_path = getattr(f, "local_path", "")
            if not local_path and rel_path:
                local_path = os.path.join(output_dir, rel_path)

            items.append({
                "id": f_id,
                "rel_path": rel_path,
                "local_path": local_path,
                "name": os.path.basename(rel_path or local_path),
                "is_image": is_image_file(rel_path or local_path),
            })
        return items

    def download(
        self,
        url_or_id: str,
        output_dir: str,
        images_only: bool = True,
        skip_existing: bool = True,
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        Thực hiện toàn bộ quy trình quét và tải file từ Google Drive.
        
        Args:
            url_or_id: URL hoặc ID Google Drive
            output_dir: Thư mục lưu trên máy tính
            images_only: Chỉ tải ảnh nếu True
            skip_existing: Bỏ qua nếu file đã tồn tại và có dung lượng > 0
            max_workers: Số luồng tải song song (mặc định 3)
            progress_callback: Hàm nhận cập nhật tiến độ
            cancel_event: Tín hiệu yêu cầu dừng
        """
        if cancel_event is None:
            cancel_event = threading.Event()

        workers = max_workers or self.max_workers
        workers = max(1, min(workers, 8))

        stats = {
            "total": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "output_dir": output_dir,
            "cancelled": False,
            "errors": [],
        }

        def report(status: str, msg: str, **kwargs):
            if progress_callback:
                payload = {
                    "status": status,
                    "message": msg,
                    "success": stats["success"],
                    "skipped": stats["skipped"],
                    "failed": stats["failed"],
                    "total": stats["total"],
                }
                payload.update(kwargs)
                try:
                    progress_callback(payload)
                except Exception:
                    pass

        cookie_path = get_cookies_path()
        if cookie_path and has_valid_cookies():
            report("scanning", "🔐 Đang sử dụng phiên xác thực tài khoản Google công ty (Cookies kích hoạt)...")
        else:
            report("scanning", "⚪ Đang quét ở chế độ công khai (Chưa đăng nhập tài khoản công ty)...")

        # 1. Bóc tách URL
        report("scanning", "🔍 Đang phân tích đường dẫn Google Drive...")
        item_id, item_type = parse_gdrive_url(url_or_id)
        if not item_id:
            err = "❌ Không tìm thấy ID Google Drive hợp lệ từ đường dẫn đã cung cấp."
            stats["errors"].append(err)
            report("error", err)
            return stats

        os.makedirs(output_dir, exist_ok=True)

        # 2. Xử lý quét danh sách tệp
        items_to_download: List[Dict[str, Any]] = []

        if item_type == "folder" or item_type == "unknown":
            report("scanning", f"📂 Đang quét cấu trúc thư mục Drive ({item_id})...")
            try:
                items_to_download = self.scan_folder(item_id, output_dir)
            except DownloadError as e:
                err_msg = str(e)
                if (
                    "AUTHENTICATION_REQUIRED" in err_msg
                    or "404" in err_msg
                    or "permission" in err_msg.lower()
                    or "public link" in err_msg.lower()
                ):
                    if has_valid_cookies():
                        friendly_err = (
                            "❌ LỖI QUYỀN TRUY CẬP TÀI KHOẢN CÔNG TY\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "💡 Phiên làm việc tài khoản công ty hiện tại không có quyền xem thư mục này,\n"
                            "   hoặc cookie đăng nhập đã hết hạn.\n"
                            "👉 Cách khắc phục:\n"
                            "   1. Đảm bảo email công ty của Sếp đã được cấp quyền Xem trên Drive.\n"
                            "   2. Bấm '⚙️ Quản lý Tài Khoản' ở góc trên để Đăng nhập lại làm mới phiên."
                        )
                    else:
                        friendly_err = (
                            "❌ THƯ MỤC NỘI BỘ CÔNG TY (Yêu Cầu Đăng Nhập Mail Công Ty)\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "💡 Đây là thư mục nội bộ (chỉ thành viên có mail công ty mới mở được).\n"
                            "👉 HƯỚNG DẪN TẢI NHANH:\n"
                            "   1. Sếp bấm nút '🔐 Đăng Nhập Mail Công Ty' ở thanh trên cùng.\n"
                            "   2. Đăng nhập tài khoản email công ty của Sếp (hoặc dán Cookie từ Chrome).\n"
                            "   3. Sau đó bấm '🚀 Bắt Đầu Tải' lại là tải được toàn bộ ảnh ngay ạ!"
                        )
                    stats["errors"].append(friendly_err)
                    report("error", friendly_err)
                    return stats
                elif item_type == "unknown":
                    report("scanning", "ℹ️ Thử tải dưới dạng tệp đơn lẻ...")
                    single_path = os.path.join(output_dir, f"gdrive_file_{item_id}")
                    items_to_download = [{
                        "id": item_id,
                        "rel_path": f"gdrive_file_{item_id}",
                        "local_path": single_path,
                        "name": f"gdrive_file_{item_id}",
                        "is_image": False,
                    }]
                else:
                    err = f"❌ Lỗi khi quét thư mục: {err_msg}"
                    stats["errors"].append(err)
                    report("error", err)
                    return stats
            except Exception as e:
                err = f"❌ Lỗi ngoài dự kiến khi quét thư mục: {e}"
                stats["errors"].append(err)
                report("error", err)
                return stats
        else:
            # item_type == "file"
            single_path = os.path.join(output_dir, f"gdrive_file_{item_id}")
            items_to_download = [{
                "id": item_id,
                "rel_path": f"gdrive_file_{item_id}",
                "local_path": single_path,
                "name": f"gdrive_file_{item_id}",
                "is_image": False,
            }]

        if cancel_event.is_set():
            stats["cancelled"] = True
            report("cancelled", "⏹ Đã dừng tiến trình theo yêu cầu của bạn.")
            return stats

        # 3. Lọc danh sách nếu chọn chỉ tải hình ảnh
        if images_only and item_type == "folder":
            filtered_items = [it for it in items_to_download if it["is_image"]]
            total_scanned = len(items_to_download)
            items_to_download = filtered_items
            report(
                "scanning",
                f"🎯 Đã tìm thấy {len(items_to_download)} tệp hình ảnh (trên tổng số {total_scanned} tệp trong thư mục).",
            )
        else:
            report("scanning", f"📋 Tổng số tệp cần tải: {len(items_to_download)} tệp.")

        if not items_to_download:
            if not has_valid_cookies():
                msg = (
                    "❌ THƯ MỤC NỘI BỘ CÔNG TY (Yêu Cầu Đăng Nhập Mail Công Ty)\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "💡 Thư mục này chỉ dành cho tài khoản email công ty và hiện đang bị khóa truy cập.\n"
                    "👉 HƯỚNG DẪN TẢI NHANH:\n"
                    "   1. Sếp bấm nút '🔐 Đăng Nhập Mail Công Ty' ở thanh trên cùng.\n"
                    "   2. Đăng nhập email công ty (hoặc dán mã Cookie từ Chrome).\n"
                    "   3. Sau đó bấm '🚀 Bắt Đầu Tải' lại là tải về toàn bộ ảnh ngay ạ!"
                )
                stats["errors"].append(msg)
                report("error", msg)
            else:
                msg = (
                    "⚠️ Không tìm thấy tệp nào trong thư mục (Thư mục trống hoặc tài khoản chưa được phân quyền xem tệp).\n"
                    "👉 Hãy kiểm tra lại quyền truy cập trên Google Drive hoặc đăng nhập lại."
                )
                report("completed", msg)
            return stats

        stats["total"] = len(items_to_download)
        total_count = stats["total"]

        # 4. Tiến hành tải đa luồng
        completed_lock = threading.Lock()
        completed_count = 0

        def download_single_item(item: Dict[str, Any]) -> Tuple[bool, str, str]:
            nonlocal completed_count
            if cancel_event.is_set():
                return False, item["name"], "cancelled"

            file_id = item["id"]
            target_path = item["local_path"]
            filename = item["name"]

            # Đảm bảo thư mục cha tồn tại
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Kiểm tra Skip Existing
            if skip_existing and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                with completed_lock:
                    stats["skipped"] += 1
                    completed_count += 1
                    idx = completed_count
                report(
                    "downloading",
                    f"⏩ Bỏ qua (đã có): {filename}",
                    file_name=filename,
                    file_index=idx,
                    percent=int((idx / total_count) * 100),
                )
                return True, filename, "skipped"

            # Tải tệp bằng gdown.download
            try:
                report(
                    "downloading",
                    f"⬇️ Đang tải: {filename}...",
                    file_name=filename,
                    file_index=completed_count + 1,
                    percent=int((completed_count / total_count) * 100),
                )
                
                # gdown download
                download_kwargs = {
                    "id": file_id,
                    "output": target_path,
                    "quiet": True,
                    "resume": True,
                    "use_cookies": bool(cookie_path),
                    "cancel": cancel_event,
                }
                if cookie_path:
                    download_kwargs["cookies_file"] = cookie_path

                dl_result = gdown.download(**download_kwargs)

                if cancel_event.is_set():
                    return False, filename, "cancelled"

                if dl_result is None:
                    raise DownloadError(f"Không thể tải hoặc ghi file {filename}")
                if isinstance(dl_result, str) and not os.path.exists(dl_result) and not os.path.exists(target_path):
                    raise DownloadError(f"Không tìm thấy file sau khi tải: {filename}")

                with completed_lock:
                    stats["success"] += 1
                    completed_count += 1
                    idx = completed_count

                report(
                    "downloading",
                    f"✅ Đã tải xong ({idx}/{total_count}): {filename}",
                    file_name=filename,
                    file_index=idx,
                    percent=int((idx / total_count) * 100),
                )
                return True, filename, "success"

            except DownloadCancelled:
                return False, filename, "cancelled"
            except Exception as e:
                with completed_lock:
                    stats["failed"] += 1
                    completed_count += 1
                    err_str = str(e)
                    if "permission" in err_str.lower() or "public link" in err_str.lower() or "404" in err_str:
                        display_err = f"❌ {filename}: Thư mục/tệp đang ở chế độ 'Bị hạn chế'. Vui lòng bật 'Bất kỳ ai có đường liên kết'."
                    else:
                        display_err = f"❌ Lỗi khi tải {filename}: {err_str}"
                    stats["errors"].append(display_err)
                    idx = completed_count
                report(
                    "downloading",
                    display_err,
                    file_name=filename,
                    file_index=idx,
                    percent=int((idx / total_count) * 100),
                )
                return False, filename, display_err

        # Chạy ThreadPoolExecutor
        report("downloading", f"🚀 Bắt đầu tải đa luồng ({workers} luồng song song)...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_item = {executor.submit(download_single_item, it): it for it in items_to_download}
            for future in as_completed(future_to_item):
                if cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    stats["cancelled"] = True
                    break
                try:
                    future.result()
                except Exception:
                    pass

        if cancel_event.is_set():
            stats["cancelled"] = True
            report("cancelled", f"⏹ Đã dừng tải. Thành công: {stats['success']}, Đã bỏ qua: {stats['skipped']}, Lỗi: {stats['failed']}.")
        else:
            report(
                "completed",
                f"🎉 Hoàn tất! Đã tải thành công: {stats['success']}/{total_count} tệp (Bỏ qua: {stats['skipped']}, Lỗi: {stats['failed']}).",
                file_index=total_count,
                percent=100,
            )

        return stats
