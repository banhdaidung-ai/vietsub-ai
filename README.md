# Vietsub AI

Ứng dụng Desktop tự động dịch video tiếng Trung sang tiếng Việt, lồng tiếng (TTS) và ghép phụ đề cứng.

## Tính năng
- Hỗ trợ tải video từ **YouTube, Bilibili** hoặc dùng **file có sẵn**
- Dịch siêu tốc bằng **Gemini 2.0 Flash AI** (Chất lượng cao, không cần tách âm thanh trước)
- Tạo giọng đọc tự nhiên bằng **edge-tts** (Giọng Microsoft Neural)
- Hỗ trợ mix âm thanh (giữ nhạc nền) hoặc thay thế hoàn toàn
- Giao diện đẹp, dễ dùng, chạy trên mọi hệ điều hành (Windows, macOS, Linux)

## Cài đặt (Dành cho Developer)

**1. Cài FFmpeg (Bắt buộc)**
- **macOS:** `brew install ffmpeg`
- **Windows:** `winget install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

**2. Cài Python packages**
```bash
python -m venv venv
source venv/bin/activate  # Trên Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Chạy ứng dụng**
```bash
python main.py
```

## Đóng gói ứng dụng (Tạo file cài đặt)

### 🍎 Dành cho macOS (.app & .dmg):
Chạy lệnh sau trong terminal:
```bash
./build_macos.sh
```
File cài đặt sẽ được tạo tại:
- `dist/VietsubAI.app` (Ứng dụng chạy trực tiếp)
- `dist/VietsubAI.dmg` (File cài đặt kéo-thả vào Applications)

### 🪟 Dành cho Windows (.exe):
Nhấp đúp chuột vào file `build_windows.bat` hoặc mở Command Prompt chạy:
```cmd
build_windows.bat
```
File thực thi sẽ được xuất ra tại:
- `dist\VietsubAI\VietsubAI.exe`

### ☁️ Đóng gói tự động bằng GitHub Actions:
Dự án đã tích hợp sẵn GitHub Actions workflow tại `.github/workflows/build.yml`. Mỗi khi push code lên GitHub hoặc tạo Release tag, hệ thống sẽ tự động build cả bản macOS (`.dmg`) và Windows (`.zip`) tại mục **Actions**.
