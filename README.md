# Vietsub AI — Dịch & Tạo Phụ Đề Video Chuyên Nghiệp

Ứng dụng Desktop tự động dịch video đa ngôn ngữ (Tiếng Trung, Tiếng Anh) sang Tiếng Việt, lồng tiếng AI (TTS), phiên âm và tạo phụ đề text cho video Tiếng Việt.

## Tính năng nổi bật
- 🌐 **Đa ngôn ngữ nguồn:**
  - 🇨🇳 **Tiếng Trung → Tiếng Việt:** Dịch thuật ngữ cảnh, lồng tiếng AI và ghép phụ đề chuẩn xác.
  - 🇺🇸 **Tiếng Anh → Tiếng Việt:** Dịch tự nhiên, xử lý thành ngữ (idioms), tiếng lóng, khẩu ngữ đời thường.
  - 🇻🇳 **Tạo phụ đề Tiếng Việt:** Lắng nghe và phiên âm chuẩn xác 100% tiếng Việt có dấu, xuất file `.srt`, `.txt` và gắn phụ đề vào video (giữ nguyên 100% âm thanh gốc).
- 📥 **Tải video đa nền tảng:** Hỗ trợ link TikTok, Facebook Reels, YouTube Shorts/Video, Bilibili hoặc chọn file video trên máy.
- 🤖 **Trí tuệ nhân tạo Gemini AI:** Phiên âm và dịch thuật tốc độ cao, timestamp khớp từng mili-giây.
- 🎙️ **Giọng đọc AI tự nhiên:** Sử dụng công nghệ Microsoft Edge Neural (giọng Hoài My truyền cảm, Nam Minh trầm ấm) với tuỳ chọn bật/tắt linh hoạt.
- 🎬 **Ghép video chuyên nghiệp:** Hỗ trợ mix âm lượng nhạc nền/giọng đọc hoặc giữ âm thanh gốc chỉ ghép phụ đề chữ.
- 🌓 **Giao diện hiện đại (Studio Dark/Light):** Tích hợp Pipeline Step Tracker và Studio Terminal theo dõi tiến độ chi tiết.

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
