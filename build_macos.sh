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

# 3. Chuẩn bị FFmpeg cho macOS (chỉ cần ffmpeg, không cần ffprobe)
echo "⚡ Đang chuẩn bị bộ giải mã FFmpeg cho macOS..."
mkdir -p bin
"$PYTHON_BIN" -c "import static_ffmpeg.run; ffmpeg, _ = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise(); import shutil; shutil.copy(ffmpeg, 'bin/ffmpeg');" 2>/dev/null || true
if [ ! -f "bin/ffmpeg" ] && which ffmpeg >/dev/null 2>&1; then
    cp "$(which ffmpeg)" bin/ffmpeg 2>/dev/null || true
fi
rm -f bin/ffprobe bin/ffprobe.exe 2>/dev/null || true

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

# Đảm bảo chỉ có DUY NHẤT 1 file ffmpeg trong toàn bộ bundle, khử trùng lặp triệt để
if [ -f "dist/VietsubAI.app/Contents/Frameworks/ffmpeg" ]; then
    echo "⚡ FFmpeg đã có sẵn trong Contents/Frameworks/ffmpeg."
    rm -f "dist/VietsubAI.app/Contents/MacOS/ffmpeg" 2>/dev/null || true
elif [ -f "bin/ffmpeg" ]; then
    cp bin/ffmpeg "dist/VietsubAI.app/Contents/MacOS/" 2>/dev/null || true
fi
# Loại bỏ triệt để mọi file ffprobe thừa nếu có trong bundle
find "dist/VietsubAI.app" -name "*ffprobe*" -delete 2>/dev/null || true

echo "✅ Đã tạo thành công: dist/VietsubAI.app (Dung lượng siêu nhẹ, 1 bản FFmpeg duy nhất)"

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
