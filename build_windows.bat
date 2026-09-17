@echo off
chcp 65001 >nul
echo ==========================================================
echo       Bắt đầu đóng gói Vietsub AI cho Windows
echo ==========================================================

cd /d "%~dp0"

:: 1. Kiểm tra Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [LỖI] Không tìm thấy Python trên máy! Vui lòng cài đặt Python 3.10+ và tích chọn "Add Python to PATH".
    pause
    exit /b 1
)

:: 2. Kiểm tra/Tạo môi trường ảo
if not exist "venv" (
    echo [1/4] Đang tạo môi trường ảo Python venv...
    python -m venv venv
)

call venv\Scripts\activate.bat

:: 3. Cài đặt thư viện phụ thuộc
echo [2/5] Đang cài đặt thư viện phụ thuộc...
pip install -r requirements.txt
pip install pyinstaller

:: 4. Chuẩn bị FFmpeg cho Windows
echo [3/5] Đang chuẩn bị bộ giải mã FFmpeg...
if not exist "bin" mkdir "bin"
if not exist "bin\ffmpeg.exe" (
    echo Đang tải FFmpeg tĩnh cho Windows từ máy chủ...
    powershell -Command "$zip = '$env:TEMP\ffmpeg_win32.zip'; Invoke-WebRequest -Uri 'https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/win32.zip' -OutFile $zip; Expand-Archive -Path $zip -DestinationPath '$env:TEMP\ff_temp' -Force; Copy-Item '$env:TEMP\ff_temp\win32\*.exe' 'bin\' -Force; Remove-Item -Recurse -Force '$env:TEMP\ff_temp', $zip"
)

:: 5. Dọn dẹp thư mục build cũ
echo [4/5] Dọn dẹp build/dist cũ...
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"

:: 6. Chạy đóng gói với PyInstaller
echo [5/5] Đang đóng gói Vietsub AI bằng PyInstaller...
pyinstaller --noconfirm --clean VietsubAI.spec

if not exist "dist\VietsubAI\VietsubAI.exe" (
    echo [LỖI] Đóng gói thất bại! Không tìm thấy dist\VietsubAI\VietsubAI.exe
    pause
    exit /b 1
)

:: Đảm bảo FFmpeg có mặt trong thư mục dist\VietsubAI và không bị trùng lặp
if exist "bin\ffmpeg.exe" (
    if not exist "dist\VietsubAI\ffmpeg.exe" (
        if not exist "dist\VietsubAI\_internal\ffmpeg.exe" (
            copy /y "bin\ffmpeg.exe" "dist\VietsubAI\" >nul
        )
    )
    del /f /q "dist\VietsubAI\*ffprobe*" 2>nul
    del /f /q "dist\VietsubAI\_internal\*ffprobe*" 2>nul
    echo [OK] Đã tối ưu và nhúng 1 bản ffmpeg.exe duy nhất vào dist\VietsubAI!
)

echo.
echo ==========================================================
echo  HOÀN TẤT ĐÓNG GÓI CHO WINDOWS!
echo  Thư mục ứng dụng: dist\VietsubAI
echo  File chạy: dist\VietsubAI\VietsubAI.exe
echo ==========================================================
echo Sếp có thể nén thư mục "dist\VietsubAI" thành file ZIP hoặc dùng Inno Setup để tạo file Setup cài đặt nhé!
pause
