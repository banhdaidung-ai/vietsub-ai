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
echo [2/4] Đang cài đặt thư viện phụ thuộc...
pip install -r requirements.txt
pip install pyinstaller

:: 4. Dọn dẹp thư mục build cũ
echo [3/4] Dọn dẹp build/dist cũ...
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"

:: 5. Chạy đóng gói với PyInstaller
echo [4/4] Đang đóng gói Vietsub AI bằng PyInstaller...
pyinstaller --noconfirm --clean VietsubAI.spec

if not exist "dist\VietsubAI\VietsubAI.exe" (
    echo [LỖI] Đóng gói thất bại! Không tìm thấy dist\VietsubAI\VietsubAI.exe
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo  HOÀN TẤT ĐÓNG GÓI CHO WINDOWS!
echo  Thư mục ứng dụng: dist\VietsubAI
echo  File chạy: dist\VietsubAI\VietsubAI.exe
echo ==========================================================
echo Sếp có thể nén thư mục "dist\VietsubAI" thành file ZIP hoặc dùng Inno Setup để tạo file Setup cài đặt nhé!
pause
