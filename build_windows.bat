@echo off
chcp 65001 >nul
echo ==========================================================
echo       Đóng gói Vietsub AI v1.1.0 cho Windows
echo ==========================================================

cd /d "%~dp0"

:: 1. Kiểm tra Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [LỖI] Không tìm thấy Python! Vui lòng cài Python 3.10+ và tích "Add Python to PATH".
    pause
    exit /b 1
)
python --version

:: 2. Kiểm tra/Tạo môi trường ảo
if not exist "venv" (
    echo [1/6] Đang tạo môi trường ảo Python venv...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [LỖI] Không thể tạo venv!
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

:: 3. Nâng cấp pip và cài đặt thư viện
echo [2/6] Đang cài đặt thư viện phụ thuộc...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [LỖI] Cài thư viện thất bại!
    pause
    exit /b 1
)
pip install pyinstaller --quiet

:: 4. Chuẩn bị FFmpeg cho Windows
echo [3/6] Đang chuẩn bị bộ giải mã FFmpeg...
if not exist "bin" mkdir "bin"
if not exist "bin\ffmpeg.exe" (
    echo     Đang tải FFmpeg tĩnh cho Windows...
    powershell -Command "$zip = '$env:TEMP\ffmpeg_win32.zip'; Invoke-WebRequest -Uri 'https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/win32.zip' -OutFile $zip -UseBasicParsing; Expand-Archive -Path $zip -DestinationPath '$env:TEMP\ff_temp' -Force; Copy-Item '$env:TEMP\ff_temp\win32\*.exe' 'bin\' -Force; Remove-Item -Recurse -Force '$env:TEMP\ff_temp', $zip" 2>nul
    if not exist "bin\ffmpeg.exe" (
        echo     [CẢNH BÁO] Không tải được FFmpeg tự động. Vui lòng đặt ffmpeg.exe và ffprobe.exe vào thư mục bin\
    )
) else (
    echo     FFmpeg đã có sẵn.
)

:: 5. Dọn dẹp thư mục build cũ
echo [4/6] Dọn dẹp build/dist cũ...
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"

:: 6. Chạy đóng gói với PyInstaller
echo [5/6] Đang đóng gói Vietsub AI bằng PyInstaller...
pyinstaller --noconfirm --clean VietsubAI.spec

if not exist "dist\VietsubAI\VietsubAI.exe" (
    echo [LỖI] Đóng gói thất bại! Không tìm thấy dist\VietsubAI\VietsubAI.exe
    pause
    exit /b 1
)

:: Đảm bảo FFmpeg và FFprobe có mặt trong thư mục dist\VietsubAI
if exist "bin\ffmpeg.exe" (
    if not exist "dist\VietsubAI\ffmpeg.exe" (
        copy /y "bin\ffmpeg.exe" "dist\VietsubAI\" >nul
    )
)
if exist "bin\ffprobe.exe" (
    if not exist "dist\VietsubAI\ffprobe.exe" (
        copy /y "bin\ffprobe.exe" "dist\VietsubAI\" >nul
    )
)
echo     [OK] Đã nhúng đầy đủ ffmpeg.exe & ffprobe.exe vào dist\VietsubAI!

:: Dọn rác để giảm dung lượng
echo [6/6] Đang dọn rác để tối ưu dung lượng...
for /d /r "dist\VietsubAI" %%d in (__pycache__) do (
    if exist "%%d" rd /s /q "%%d" >nul 2>nul
)
for /d /r "dist\VietsubAI" %%d in (*.dist-info) do (
    if exist "%%d" rd /s /q "%%d" >nul 2>nul
)
del /s /q "dist\VietsubAI\*.pyc" >nul 2>nul

:: Tạo file ZIP để dễ chia sẻ
echo     Đang nén thành VietsubAI_Windows_v1.1.0.zip...
if exist "dist\VietsubAI_Windows_v1.1.0.zip" del /q "dist\VietsubAI_Windows_v1.1.0.zip"
powershell -Command "Compress-Archive -Path 'dist\VietsubAI' -DestinationPath 'dist\VietsubAI_Windows_v1.1.0.zip' -CompressionLevel Optimal" 2>nul
if exist "dist\VietsubAI_Windows_v1.1.0.zip" (
    echo     [OK] Đã tạo file ZIP thành công!
    powershell -Command "Write-Host ('    Dung luong ZIP: ' + [math]::Round((Get-Item dist\VietsubAI_Windows_v1.1.0.zip).Length / 1MB, 1) + ' MB')"
)

echo.
echo ==========================================================
echo  HOÀN TẤT ĐÓNG GÓI WINDOWS v1.1.0!
echo  File chạy   : dist\VietsubAI\VietsubAI.exe
echo  File ZIP    : dist\VietsubAI_Windows_v1.1.0.zip
echo ==========================================================
echo Sếp chạy thẳng VietsubAI.exe hoặc nén ZIP gửi đi test nhé!
pause
