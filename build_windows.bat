@echo off
chcp 65001 >nul
echo ==========================================================
echo       Đóng gói Vietsub AI v1.1.1 cho Windows
echo ========================================================
echo.

:: 1. Kiểm tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python 3.10+ va them vao PATH.
    pause
    exit /b 1
)

:: 2. Kiểm tra môi trường ảo
if not exist ".venv\Scripts\activate.bat" (
    echo [1/6] Dang tao virtual environment .venv...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [2/6] Dang cai dat cac thu vien can thiet...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pip install pyinstaller
) else (
    echo [1/6] Kich hoat virtual environment .venv...
    call .venv\Scripts\activate.bat
)

:: 3. Tải ffmpeg.exe & ffprobe.exe cho Windows nếu chưa có
echo [3/6] Kiem tra ffmpeg.exe va ffprobe.exe...
if not exist "bin" mkdir bin

if not exist "bin\ffmpeg.exe" (
    echo     Dang tai ffmpeg.exe tu GitHub release...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip' -OutFile 'bin\ffmpeg.zip'"
    echo     Dang giai nen ffmpeg...
    powershell -Command "Expand-Archive -Path 'bin\ffmpeg.zip' -DestinationPath 'bin\temp_ffmpeg' -Force"
    copy "bin\temp_ffmpeg\ffmpeg-*\bin\ffmpeg.exe" "bin\ffmpeg.exe" >nul
    copy "bin\temp_ffmpeg\ffmpeg-*\bin\ffprobe.exe" "bin\ffprobe.exe" >nul
    rd /s /q "bin\temp_ffmpeg" >nul 2>nul
    del /q "bin\ffmpeg.zip" >nul 2>nul
    echo     [OK] Da tai ffmpeg va ffprobe thanh cong!
) else (
    echo     [OK] Da co san bin\ffmpeg.exe va bin\ffprobe.exe!
)

:: 4. Build bằng PyInstaller
echo [4/6] Bat dau dong goi bang PyInstaller...
pyinstaller --clean VietsubAI.spec
if errorlevel 1 (
    echo [LOI] PyInstaller gap loi trong qua trinh dong goi!
    pause
    exit /b 1
)

:: 5. Copy ffmpeg.exe & ffprobe.exe vào thư mục dist\VietsubAI\
echo [5/6] Chep ffmpeg.exe va ffprobe.exe vao thu muc dist\VietsubAI...
if exist "bin\ffmpeg.exe" (
    copy /y "bin\ffmpeg.exe" "dist\VietsubAI\" >nul
)
if exist "bin\ffprobe.exe" (
    copy /y "bin\ffprobe.exe" "dist\VietsubAI\" >nul
)
echo     [OK] Đã nhúng đầy đủ ffmpeg.exe & ffprobe.exe vào dist\VietsubAI!

:: Dọn rác để giảm dung lượng (chỉ xóa __pycache__ và .pyc, giữ nguyên .dist-info để bảo toàn metadata package)
echo [6/6] Đang dọn rác để tối ưu dung lượng...
for /d /r "dist\VietsubAI" %%d in (__pycache__) do (
    if exist "%%d" rd /s /q "%%d" >nul 2>nul
)
del /s /q "dist\VietsubAI\*.pyc" >nul 2>nul

:: Tạo file ZIP để dễ chia sẻ
echo.
echo     Đang nén thành VietsubAI_Windows_v1.1.1.zip...
if exist "dist\VietsubAI_Windows_v1.1.1.zip" del /q "dist\VietsubAI_Windows_v1.1.1.zip"
powershell -Command "Compress-Archive -Path 'dist\VietsubAI' -DestinationPath 'dist\VietsubAI_Windows_v1.1.1.zip' -CompressionLevel Optimal" 2>nul
if exist "dist\VietsubAI_Windows_v1.1.1.zip" (
    echo     [OK] Da tao thanh cong: dist\VietsubAI_Windows_v1.1.1.zip
    powershell -Command "Write-Host ('    Dung luong ZIP: ' + [math]::Round((Get-Item dist\VietsubAI_Windows_v1.1.1.zip).Length / 1MB, 1) + ' MB')"
)

echo.
echo ========================================================
echo  HOÀN TẤT ĐÓNG GÓI WINDOWS v1.1.1!
echo  Thư mục app : dist\VietsubAI\VietsubAI.exe
echo  File ZIP    : dist\VietsubAI_Windows_v1.1.1.zip
echo ==========================================================
echo Sếp chạy thẳng VietsubAI.exe hoặc nén ZIP gửi đi test nhé!
pause
