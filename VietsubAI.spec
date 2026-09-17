# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Thu thập toàn bộ dependencies quan trọng
datas = []
binaries = []
hiddenimports = [
    'certifi',
    'pydantic',
    'pydantic_core',
    'pydantic.deprecated.decorator',
]

for pkg in ['customtkinter', 'edge_tts', 'google.genai', 'yt_dlp']:
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Lọc bỏ các module test và file rác của thư viện để giảm dung lượng
hiddenimports = [h for h in set(hiddenimports) if not any(t in h for t in ['.tests', '.test_', 'testing', 'tests'])]
datas = [d for d in datas if not any(t in str(d[0]).replace('\\', '/') for t in ['/tests/', '/test/', '/testing/'])]

# Thêm thư mục assets (chứa icon, hình ảnh)
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))

# Thêm cacert.pem từ certifi để tránh lỗi SSL khi tải video / gọi API
try:
    import certifi
    datas.append((certifi.where(), 'certifi'))
except Exception:
    pass

# Tự động nhúng DUY NHẤT 1 bản ffmpeg (không cần ffprobe) vào thư mục gốc của bản build nếu có sẵn
for search_dir in ['.', 'bin', 'assets/bin']:
    for ext in ['.exe', '']:
        cand = os.path.join(search_dir, f"ffmpeg{ext}")
        if os.path.isfile(cand) and not any(cand == b[0] for b in binaries):
            binaries.append((cand, '.'))
            break

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test', 'unittest', 'test',
        'email.test', 'xmlrpc', 'pydoc', 'sqlite3',
        'matplotlib', 'scipy', 'numpy', 'pandas',
        'static_ffmpeg',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

is_mac = sys.platform == 'darwin'
is_win = sys.platform.startswith('win')

icon_file = None
if is_mac and os.path.exists('assets/icon.icns'):
    icon_file = 'assets/icon.icns'
elif is_win and os.path.exists('assets/icon.ico'):
    icon_file = 'assets/icon.ico'
elif os.path.exists('assets/icon.png'):
    icon_file = 'assets/icon.png'

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VietsubAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VietsubAI',
)

if is_mac:
    app = BUNDLE(
        coll,
        name='VietsubAI.app',
        icon=icon_file,
        bundle_identifier='com.vietsubai.app',
        info_plist={
            'CFBundleName': 'Vietsub AI',
            'CFBundleDisplayName': 'Vietsub AI',
            'CFBundleIdentifier': 'com.vietsubai.app',
            'CFBundleVersion': '1.0.4',
            'CFBundleShortVersionString': '1.0.4',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '11.0',
            'NSHumanReadableCopyright': 'Copyright © 2026 Vietsub AI',
        },
    )
