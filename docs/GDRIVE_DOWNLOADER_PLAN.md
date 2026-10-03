# KẾ HOẠCH TRIỂN KHAI: TÍNH NĂNG TẢI TRỰC TIẾP TỪ GOOGLE DRIVE (KHÔNG NÉN ZIP)
**Dự án:** Vietsub AI Pro Studio (Desktop App)  
**Công nghệ:** Python 3.10+, CustomTkinter, Dark Mode Apple Design System  
**Mục tiêu chính:** Tải trọn vẹn thư mục/tệp hình ảnh từ Google Drive về máy tính mà **KHÔNG bị Google Drive tự động nén thành các file zip phân mảnh**, giữ nguyên 100% cây thư mục gốc, hỗ trợ tải đa luồng tốc độ cao và tự động bỏ qua file đã tải.

---

## 1. VẤN ĐỀ CẦN GIẢI QUYẾT (PAIN POINTS)
- Team thường xuyên tải album/thư mục ảnh lớn từ Google Drive về máy tính.
- Giao diện Web của Google Drive khi tải folder hoặc nhiều file sẽ tự động nén zip trên máy chủ.
- Nếu dung lượng > 2GB hoặc nhiều tệp, Google tự động cắt thành nhiều file zip: `drive-download-....part1.zip`, `part2.zip`...
- Quy trình hiện tại: Chờ Google nén -> Tải từng file zip -> Giải nén thủ công -> Sắp xếp lại file. Rất mất thời gian, dễ thiếu sót file hoặc lỗi đường truyền.

---

## 2. GIẢI PHÁP KỸ THUẬT (DIRECT STREAM & MULTI-THREADING)
1. **Cơ chế cốt lõi:**
   - Người dùng dán link thư mục Google Drive (hoặc link tệp đơn).
   - Hệ thống bóc tách `Folder ID` hoặc `File ID`.
   - Quét đệ quy toàn bộ danh sách tệp và thư mục con (File Tree).
   - Tự động tạo cấu trúc thư mục tương ứng trên ổ cứng máy tính.
   - Tải song song (Multi-threading với `ThreadPoolExecutor`, mặc định 3–5 luồng) trực tiếp từng file ảnh nguyên bản về đúng thư mục.
2. **Chống đứt đoạn (Resume / Skip Existing):**
   - Trước khi tải một file, kiểm tra xem file đã tồn tại ở đích với cùng dung lượng chưa. Nếu có rồi -> Tự động Skip để tiết kiệm thời gian và băng thông.
3. **Bộ lọc định dạng (Smart Extension Filter):**
   - Tùy chọn lọc: Chỉ tải tệp hình ảnh (`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.raw`, `.psd`, `.svg`, `.gif`) hoặc tải toàn bộ tệp.
4. **Thư viện đề xuất:**
   - `gdown>=5.1.0` (hỗ trợ crawl và tải folder Google Drive cực tốt, không bị zip) kết hợp với `requests` / `curl_cffi` (đã có sẵn trong dự án).

---

## 3. CÁC TỆP CẦN TẠO MỚI & CHỈNH SỬA

### 📁 Tệp 1: `requirements.txt`
- Thêm thư viện: `gdown>=5.1.0`

### 📁 Tệp 2: `core/gdrive_downloader.py` (Mới)
Module backend phụ trách toàn bộ logic tải:
- `parse_gdrive_url(url: str) -> tuple[str, str]`: Bóc tách ID và loại link (`folder` hoặc `file`).
- `class GDriveDownloader`:
  - `__init__(self, output_dir: str, max_workers: int = 3, filter_images_only: bool = True)`
  - `scan_folder(folder_url_or_id: str) -> list[dict]`: Lấy danh sách file và đường dẫn tương đối.
  - `download(self, url: str, progress_callback: Callable, cancel_event: threading.Event) -> dict`:
    - Quản lý `ThreadPoolExecutor`.
    - Gọi callback báo tiến độ: `(current_index, total_files, filename, percent, speed_str, status)`.
    - Bắt sự kiện hủy (`cancel_event.is_set()`).
    - Trả về thống kê: `{success_count, skipped_count, failed_count, total_size_mb, output_dir}`.

### 📁 Tệp 3: `gui/gdrive_download_dialog.py` (Mới)
Hộp thoại giao diện người dùng theo chuẩn thiết kế Apple Dark Mode của app:
- Kế thừa `ctk.CTkToplevel`, modal window, center trên parent.
- **Tokens thiết kế đồng bộ:** `BG_WINDOW = "#141518"`, `BG_CARD = "#1C1F27"`, `BG_INSET = "#121419"`, `APPLE_BLUE = "#0A84FF"`, `APPLE_GREEN = "#30D158"`, `TEXT_PRIMARY = "#F5F5F7"`.
- **Thành phần giao diện:**
  - **Header:** Icon Google Drive + Tiêu đề *"Tải File & Thư Mục Google Drive (Không Zip)"* + Nút đóng.
  - **Input Link:** `CTkEntry` dán link Drive + Nút "Dán nhanh (Paste)".
  - **Output Folder:** `CTkEntry` đường dẫn máy tính + Nút "Chọn thư mục... (Browse)".
  - **Tùy chọn:**
    - `CTkCheckBox`: "Chỉ tải hình ảnh (JPG, PNG, WEBP, PSD...)" (mặc định Bật).
    - `CTkComboBox` / `CTkSlider`: Số luồng tải song song (3 - 5 luồng).
    - `CTkCheckBox`: "Bỏ qua file đã có sẵn (Skip existing)" (mặc định Bật).
  - **Tiến độ & Trạng thái:**
    - `CTkProgressBar` hiển thị tiến độ tổng thể.
    - Nhãn trạng thái: *"Đang tải: image_01.jpg (15/120 ảnh) — 45% (3.2 MB/s)"*.
    - Hộp nhật ký (Scrollable Log Box / Terminal mini) để hiển thị chi tiết tiến trình.
  - **Hành động:**
    - Nút `[🚀 Bắt đầu tải]` (Màu xanh Apple Blue).
    - Nút `[⏹ Hủy / Dừng]` (Disable khi chưa chạy).
    - Nút `[📂 Mở thư mục tải về]` (Xuất hiện/Enable khi tải xong).

### 📁 Tệp 4: `gui/app_window.py` (Chỉnh sửa)
Tích hợp nút kích hoạt vào giao diện chính:
- Thêm nút `btn_gdrive_download = ctk.CTkButton(...)`:
  - Đặt tại `file_action_bar` (cạnh nút `btn_separate_audio` và `btn_extract_audio` trong tab 1).
  - Text: `📥 Tải Google Drive`.
  - Icon/Màu sắc: Pill button với viền tinh tế `APPLE_BLUE_BORDER` hoặc text màu Cyan.
- Thêm phương thức `_on_gdrive_download_clicked(self)` để khởi tạo và hiển thị `GDriveDownloadDialog`.
- Cập nhật trạng thái enable/disable khi app đang bận xử lý pipeline chính.

### 📁 Tệp 5: `tests/test_gdrive_downloader.py` (Mới)
Bộ unit test kiểm thử tự động với `pytest`:
- Test regex phân tích URL Google Drive (`drive.google.com/drive/folders/...`, `drive.google.com/file/d/...`, link rút gọn).
- Test bộ lọc phần mở rộng ảnh (Image extensions filter).
- Test logic phát hiện file trùng và bỏ qua (Skip existing logic).
- Test cơ chế phát tín hiệu hủy (`cancel_event`).

---

## 4. QUY TRÌNH THỰC HIỆN TỪNG BƯỚC (STEP-BY-STEP FOR CLAUDE CODE)

### Bước 1: Khởi tạo Dependency
```bash
pip install gdown>=5.1.0
```
Cập nhật tệp `requirements.txt`.

### Bước 2: Xây dựng Module Lõi `core/gdrive_downloader.py`
- Triển khai phân tích link Google Drive: Trích xuất chính xác ID từ các dạng link:
  - `https://drive.google.com/drive/folders/{id}`
  - `https://drive.google.com/drive/u/0/folders/{id}`
  - `https://drive.google.com/file/d/{id}/view`
  - `https://drive.google.com/open?id={id}`
- Triển khai logic quét và tải:
  - Sử dụng `gdown.download_folder` hoặc duyệt API/HTML metadata để lấy danh sách.
  - Lưu ý cờ `remaining_ok=True`, `quiet=True` để bắt progress stream về callback.
  - Hỗ trợ tải tệp đơn (`gdown.download`) nếu người dùng dán link file đơn.
  - Bọc trong `threading.Thread` để không bao giờ block Main GUI Thread.

### Bước 3: Xây dựng Giao diện `gui/gdrive_download_dialog.py`
- Đảm bảo tuân thủ thiết kế dark mode của macOS (Apple Sequoia UI):
  - Bo góc mềm mại (`corner_radius=10` hoặc `12`).
  - Viền mỏng 1px với các màu token định nghĩa sẵn.
  - Thông báo lỗi/thành công rõ ràng bằng tiếng Việt.
  - Tự động nhớ thư mục tải gần nhất (lưu vào config nếu cần, hoặc mặc định `output/gdrive_downloads`).

### Bước 4: Tích hợp vào `gui/app_window.py`
- Import `GDriveDownloadDialog` từ `gui.gdrive_download_dialog`.
- Thêm nút bấm vào thanh công cụ `file_action_bar`.
- Đấu nối sự kiện click và quản lý lifecycle của dialog.

### Bước 5: Chạy Kiểm Thử & Kiểm Tra Biên Dịch
- Chạy kiểm tra cú pháp toàn dự án:
  ```bash
  python3 -m compileall -q main.py core gui
  ```
- Chạy unit tests:
  ```bash
  pytest tests/test_gdrive_downloader.py -v
  ```

---

## 5. CÂU LỆNH (PROMPT) CHUẨN ĐỂ CHẠY TRÊN CLAUDE CODE

```bash
claude "Hãy đọc kỹ bản kế hoạch tại docs/GDRIVE_DOWNLOADER_PLAN.md và triển khai đầy đủ tính năng tải Google Drive trực tiếp (không bị chia file zip) cho App Vietsub. Thực hiện tuần tự từ core/gdrive_downloader.py, gui/gdrive_download_dialog.py, tích hợp vào gui/app_window.py, viết test tests/test_gdrive_downloader.py và chạy kiểm tra compileall + pytest thành công."
```
