#!/usr/bin/env bash
set -e

# build_macos.sh — Script đóng gói Vietsub AI thành .app và .dmg cho macOS

echo "=========================================================="
echo "    Bắt đầu đóng gói Vietsub AI cho macOS"
echo "=========================================================="

cd "$(dirname "$0")"

# 1. Kiểm tra môi trường Python
PYTHON_BIN="./.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    echo "⚠️ Không tìm thấy .venv. Đang tạo môi trường ảo qua uv..."
    uv venv .venv
    uv pip install --python "$PYTHON_BIN" -r requirements.txt
fi

# 2. Cài đặt PyInstaller nếu chưa có
echo "📦 Kiểm tra PyInstaller..."
uv pip install --python "$PYTHON_BIN" pyinstaller

# 3. Chuẩn bị FFmpeg và FFprobe cho macOS
echo "⚡ Đang chuẩn bị bộ giải mã FFmpeg & FFprobe cho macOS..."
mkdir -p bin
"$PYTHON_BIN" -c "import static_ffmpeg.run; ffmpeg, ffprobe = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise(); import shutil; shutil.copy(ffmpeg, 'bin/ffmpeg'); shutil.copy(ffprobe, 'bin/ffprobe');" 2>/dev/null || true
if [ ! -f "bin/ffmpeg" ] && which ffmpeg >/dev/null 2>&1; then
    cp "$(which ffmpeg)" bin/ffmpeg 2>/dev/null || true
fi
if [ ! -f "bin/ffprobe" ] && which ffprobe >/dev/null 2>&1; then
    cp "$(which ffprobe)" bin/ffprobe 2>/dev/null || true
fi
chmod +x bin/ffmpeg bin/ffprobe 2>/dev/null || true

# 4. Dọn dẹp thư mục build cũ
echo "🧹 Dọn dẹp thư mục build cũ..."
rm -rf build dist || (sleep 1 && rm -rf build dist) || true

# 5. Chạy PyInstaller
echo "🚀 Đang đóng gói Vietsub AI với PyInstaller..."
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean VietsubAI.spec

if [ ! -d "dist/VietsubAI.app" ]; then
    echo "❌ Lỗi: Không tìm thấy dist/VietsubAI.app sau khi đóng gói!"
    exit 1
fi

# Đảm bảo ffmpeg và ffprobe có mặt đầy đủ trong bundle
if [ ! -f "dist/VietsubAI.app/Contents/MacOS/ffmpeg" ] && [ -f "bin/ffmpeg" ]; then
    cp bin/ffmpeg "dist/VietsubAI.app/Contents/MacOS/" 2>/dev/null || true
fi
if [ ! -f "dist/VietsubAI.app/Contents/MacOS/ffprobe" ] && [ -f "bin/ffprobe" ]; then
    cp bin/ffprobe "dist/VietsubAI.app/Contents/MacOS/" 2>/dev/null || true
fi
chmod +x "dist/VietsubAI.app/Contents/MacOS/ffmpeg" "dist/VietsubAI.app/Contents/MacOS/ffprobe" 2>/dev/null || true

# Dọn dẹp thư mục trung gian dist/VietsubAI (chỉ dùng cho bản raw, macOS chỉ cần .app và .dmg)
if [ -d "dist/VietsubAI" ]; then
    rm -rf "dist/VietsubAI"
    echo "✂️  Đã dọn dẹp thư mục trung gian dist/VietsubAI (~700MB) để tối ưu ổ đĩa."
fi

# 6. DỌN RÁC AN TOÀN — Giảm dung lượng bundle mà không ảnh hưởng chức năng
echo "🧹 Đang dọn rác để tối ưu dung lượng..."

APP_FW="dist/VietsubAI.app/Contents/Frameworks"
APP_RES="dist/VietsubAI.app/Contents/Resources"

# 6a. Xóa protoc binaries trong torch/bin (không cần cho inference)
rm -rf "$APP_FW/torch/bin/protoc"* 2>/dev/null || true
echo "   ✂️  Đã xóa protoc (~7.6MB)"

# 6c. Giữ nguyên .dist-info để bảo toàn metadata cho importlib (curl_cffi)

# 6d. Xóa __pycache__ (Python tự tạo lại khi cần)
find "dist/VietsubAI.app" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "   ✂️  Đã xóa __pycache__"

# 6e. Xóa icon trùng lặp (đã có trong Resources/icon.icns)
rm -f "$APP_RES/assets/icon.icns" 2>/dev/null || true
echo "   ✂️  Đã xóa icon trùng lặp (~1.9MB)"

# 6f. Xóa file .pyc rời rạc không trong __pycache__
find "dist/VietsubAI.app" -name "*.pyc" -delete 2>/dev/null || true

# Hiển thị dung lượng sau khi dọn
AFTER_SIZE=$(du -sh "dist/VietsubAI.app" | cut -f1)
echo "   📦 Dung lượng .app sau khi dọn rác: $AFTER_SIZE"

echo "✅ Đã tạo thành công: dist/VietsubAI.app (Đã tích hợp đầy đủ FFmpeg & FFprobe và Demucs AI)"

# 5. Đóng gói thành file đĩa cài đặt .dmg (Drag & Drop vào Applications)
echo "💿 Đang tạo file cài đặt dist/VietsubAI.dmg..."
DMG_TEMP="dist/dmg_temp"
rm -rf "$DMG_TEMP" "dist/VietsubAI.dmg"
mkdir -p "$DMG_TEMP"

# Copy App vào thư mục tạm
cp -R "dist/VietsubAI.app" "$DMG_TEMP/"

# Tạo symlink Applications để người dùng kéo thả
ln -s /Applications "$DMG_TEMP/Applications"

# Tạo file DMG nén chuẩn UDZO
hdiutil create -volname "Vietsub AI" -srcfolder "$DMG_TEMP" -ov -format UDZO "dist/VietsubAI.dmg"

# Dọn dẹp thư mục tạm
rm -rf "$DMG_TEMP"

echo ""
echo "=========================================================="
echo "🎉 HOÀN TẤT ĐÓNG GÓI MACOS!"
echo "📍 Ứng dụng: dist/VietsubAI.app"
echo "📍 File cài đặt: dist/VietsubAI.dmg"
echo "=========================================================="
ls -lh dist/VietsubAI.dmg
