"""
tests/test_image_compressor.py — Unit tests cho module nén và đóng dấu ảnh
Kiểm tra tính năng tách biệt giữa Nén ảnh và Đóng dấu logo/mã sản phẩm.
"""

import os
import sys
from pathlib import Path

# Tự động chuyển sang môi trường ảo .venv nếu chạy trực tiếp bằng python ngoài
_REPO_ROOT = Path(__file__).resolve().parent.parent
_VENV_PY = _REPO_ROOT / ".venv" / "bin" / "python"
if _VENV_PY.is_file() and sys.executable != str(_VENV_PY):
    os.execv(str(_VENV_PY), [str(_VENV_PY)] + sys.argv)

import tempfile
from PIL import Image

_REPO_ROOT_STR = str(_REPO_ROOT)
if _REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, _REPO_ROOT_STR)

try:
    import pytest
    pytest_fixture = pytest.fixture
except ImportError:
    pytest = None
    def pytest_fixture(func):
        return func

from core.image_compressor import (
    CompressResult,
    CompressTask,
    ImageCompressorEngine,
    WatermarkConfig,
    _compress_single,
    apply_watermark,
    build_output_path,
    scan_images,
)


@pytest_fixture
def sample_image():
    """Tạo file ảnh test tạm thời."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name

    # Tạo ảnh RGB 800x600
    img = Image.new("RGB", (800, 600), color=(120, 180, 240))
    img.save(path, format="JPEG", quality=95)

    yield path

    if os.path.exists(path):
        os.remove(path)


@pytest_fixture
def sample_logo():
    """Tạo file logo RGBA tạm thời."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    # Tạo logo 100x100 có kênh alpha
    logo = Image.new("RGBA", (100, 100), color=(255, 0, 0, 200))
    logo.save(path, format="PNG")

    yield path

    if os.path.exists(path):
        os.remove(path)


def test_compress_task_default_compress_enabled():
    """Mặc định compress_enabled phải là True."""
    task = CompressTask(
        src_path="test.jpg",
        dst_path="test_out.jpg",
        target_kb=500,
    )
    assert task.compress_enabled is True
    assert task.watermark is None


def test_uncompressed_mode_preserves_dimensions_and_quality(sample_image, sample_logo):
    """Khi compress_enabled=False: giữ nguyên kích thước và áp dụng watermark."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dst_path = str(Path(tmp_dir) / "output.jpg")

        wm_cfg = WatermarkConfig(
            logo_enabled=True,
            logo_path=sample_logo,
            logo_scale=0.15,
            text_enabled=True,
            text_source="custom",
            text_custom="SKU-2026-TEST",
        )

        task = CompressTask(
            src_path=sample_image,
            dst_path=dst_path,
            target_kb=10,  # Cố tình đặt target cực thấp (10 KB)
            compress_enabled=False,  # Chế độ KHÔNG nén
            watermark=wm_cfg,
        )

        result = _compress_single(task)

        assert result.success is True
        assert os.path.exists(dst_path)
        # Kích thước ảnh xuất ra phải giữ nguyên 800x600 (không bị scale down)
        assert result.width == 800
        assert result.height == 600
        assert "không nén" in result.error.lower()

        # Kiểm tra ảnh lưu thực tế
        with Image.open(dst_path) as out_img:
            assert out_img.size == (800, 600)


def test_compressed_mode_targets_size(sample_image):
    """Khi compress_enabled=True: thuật toán nén phải nỗ lực đạt target_kb."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dst_path = str(Path(tmp_dir) / "compressed.jpg")

        task = CompressTask(
            src_path=sample_image,
            dst_path=dst_path,
            target_kb=50,  # Ép xuống 50 KB
            compress_enabled=True,
        )

        result = _compress_single(task)
        assert result.success is True
        assert os.path.exists(dst_path)
        # Dung lượng sau khi nén phải giảm đáng kể
        assert result.dst_size_kb <= 60  # Cho phép dung sai nhỏ


def test_build_output_path_suffixes():
    """Kiểm tra đường dẫn file xuất: mặc định giữ nguyên tên file gốc, và hỗ trợ suffix khi truyền vào."""
    out_dir = "/tmp/test_export"
    # Mặc định không truyền suffix -> giữ nguyên tên file gốc
    p_default = build_output_path("/photos/sample.jpg", out_dir)
    assert p_default == "/tmp/test_export/sample.jpg"

    p_comp = build_output_path("/photos/sample.jpg", out_dir, "_compressed")
    assert p_comp == "/tmp/test_export/sample_compressed.jpg"

    p_wm = build_output_path("/photos/sample.png", out_dir, "_watermarked")
    assert p_wm == "/tmp/test_export/sample_watermarked.png"


def test_batch_engine_uncompressed(sample_image, sample_logo):
    """Kiểm tra ImageCompressorEngine chạy batch với chế độ compress_enabled=False."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dst1 = str(Path(tmp_dir) / "out1.jpg")
        dst2 = str(Path(tmp_dir) / "out2.jpg")

        wm_cfg = WatermarkConfig(
            text_enabled=True,
            text_source="filename",
        )

        tasks = [
            CompressTask(sample_image, dst1, target_kb=100, compress_enabled=False, watermark=wm_cfg),
            CompressTask(sample_image, dst2, target_kb=100, compress_enabled=False, watermark=wm_cfg),
        ]

        engine = ImageCompressorEngine()
        import threading
        done_event = threading.Event()
        batch_results = []

        def on_progress(curr, total, res):
            pass

        def on_done(results):
            batch_results.extend(results)
            done_event.set()

        engine.compress_batch(tasks, on_progress, on_done)
        assert done_event.wait(timeout=5)
        assert len(batch_results) == 2
        assert all(r.success for r in batch_results)


def test_watermark_default_black_text():
    """Mặc định màu text watermark phải là màu đen #000000."""
    cfg = WatermarkConfig()
    assert cfg.text_color == "#000000"


def test_dialog_defaults_and_responsiveness():
    """Kiểm tra các giá trị mặc định của dialog nén ảnh: 500KB, chữ đen, có thanh cuộn và nút Bắt đầu luôn hiển thị."""
    import customtkinter as ctk
    from gui.image_compressor_dialog import ImageCompressorDialog

    root = ctk.CTk()
    root.withdraw()
    dlg = ImageCompressorDialog(root)
    assert dlg._target_var.get() == "500", "Mặc định dung lượng nén phải là 500KB"
    assert dlg._wm_text_color == "#000000", "Mặc định màu mã SP phải là màu đen #000000"
    assert hasattr(dlg, "_time_badge"), "Phải có huy hiệu hiển thị thời gian khi chạy nén"
    assert hasattr(dlg, "_scroll_content"), "Phải có CTkScrollableFrame chống che lấp khi thu nhỏ"
    assert hasattr(dlg, "_btn_start"), "Phải có nút Bắt đầu nén"
    assert hasattr(dlg, "_zoom_slider"), "Phải có thanh trượt điều chỉnh kích thước preview"
    assert hasattr(dlg, "_btn_zoom_fit"), "Phải có nút Vừa Khung preview"
    assert hasattr(dlg, "_preview_zoom_var"), "Phải có biến lưu tỉ lệ zoom preview"

    # Kiểm tra nút luôn nằm trong khung nhìn của cửa sổ ngay cả ở kích thước nhỏ 700px
    dlg.state("normal")
    dlg.geometry("1000x700")
    dlg.update()
    h = dlg.winfo_height()
    btn_y = dlg._btn_start.winfo_rooty() - dlg.winfo_rooty()
    assert 0 < btn_y < h, f"Nút Bắt Đầu ({btn_y}px) phải nằm hoàn toàn trong cửa sổ ({h}px)"

    dlg.destroy()
    root.destroy()


def test_build_output_path_format_extension():
    """Kiểm tra build_output_path tự động đổi đuôi file theo output_format."""
    out_dir = "/tmp/test_export"
    # Nguồn là .jpg nhưng chọn xuất WEBP -> .webp
    p_webp = build_output_path("/photos/sample.jpg", out_dir, "_compressed", output_format="WEBP")
    assert p_webp == "/tmp/test_export/sample_compressed.webp"

    # Nguồn là .png nhưng chọn xuất WEBP -> .webp
    p_webp2 = build_output_path("/photos/logo.png", out_dir, "_watermarked", output_format="WEBP")
    assert p_webp2 == "/tmp/test_export/logo_watermarked.webp"

    # Nguồn là .jpg chọn xuất PNG -> .png
    p_png = build_output_path("/photos/sample.jpg", out_dir, "_compressed", output_format="PNG")
    assert p_png == "/tmp/test_export/sample_compressed.png"

    # Nguồn là .png chọn xuất JPEG -> .jpg
    p_jpg = build_output_path("/photos/sample.png", out_dir, "_compressed", output_format="JPEG")
    assert p_jpg == "/tmp/test_export/sample_compressed.jpg"

    # Chế độ 'auto' -> giữ nguyên đuôi gốc
    p_auto = build_output_path("/photos/sample.png", out_dir, "_compressed", output_format="auto")
    assert p_auto == "/tmp/test_export/sample_compressed.png"


def test_compress_single_webp_format_generates_valid_webp(sample_image):
    """Kiểm tra khi chọn output_format='WEBP' thì file xuất ra phải đúng đuôi .webp và đúng định dạng WEBP."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dst_path = str(Path(tmp_dir) / "output.webp")

        task = CompressTask(
            src_path=sample_image,
            dst_path=dst_path,
            target_kb=50,
            compress_enabled=True,
            output_format="WEBP",
        )

        result = _compress_single(task)
        assert result.success is True
        assert result.dst_path.endswith(".webp")
        assert os.path.exists(result.dst_path)

        with Image.open(result.dst_path) as out_img:
            assert out_img.format == "WEBP"


def test_compress_single_jpeg_no_stream_crash(sample_image):
    """Kiểm tra nén JPEG đạt target dung lượng và không bị lỗi stream crash trong Pillow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dst_path = str(Path(tmp_dir) / "output.jpg")
        task = CompressTask(
            src_path=sample_image,
            dst_path=dst_path,
            target_kb=50,
            compress_enabled=True,
            output_format="JPEG",
        )
        result = _compress_single(task)
        assert result.success is True
        assert os.path.exists(result.dst_path)
        assert result.dst_size_kb <= 60
        with Image.open(result.dst_path) as out_img:
            assert out_img.format == "JPEG"


def test_batch_engine_multi_core_parallel(sample_image):
    """Kiểm tra ImageCompressorEngine chạy song song đa luồng thành công và hoàn trả đầy đủ kết quả."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tasks = [
            CompressTask(
                src_path=sample_image,
                dst_path=str(Path(tmp_dir) / f"out_{i}.webp"),
                target_kb=60,
                output_format="WEBP",
            )
            for i in range(4)
        ]

        engine = ImageCompressorEngine()
        import threading
        done_event = threading.Event()
        batch_results = []
        progress_calls = []

        def on_progress(curr, total, res):
            progress_calls.append((curr, total, res.success))

        def on_done(results):
            batch_results.extend(results)
            done_event.set()

        engine.compress_batch(tasks, on_progress, on_done)
        assert done_event.wait(timeout=10), "Quá trình nén batch đa luồng phải hoàn thành trong 10s"
        assert len(batch_results) == 4
        assert len(progress_calls) == 4
        assert all(r.success for r in batch_results)


if __name__ == "__main__":
    import sys
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        import pytest
        sys.exit(pytest.main(["-v", __file__]))
    except ImportError:
        print("⚡ Đang chạy kiểm thử trực tiếp không qua pytest...")
        # Tạo sample fixture tạm thời
        import tempfile
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            p_img = f.name
        Image.new("RGB", (800, 600), (120, 180, 240)).save(p_img, "JPEG")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            p_logo = f.name
        Image.new("RGBA", (100, 100), (255, 0, 0, 200)).save(p_logo, "PNG")

        try:
            test_compress_task_default_compress_enabled()
            test_uncompressed_mode_preserves_dimensions_and_quality(p_img, p_logo)
            test_compressed_mode_targets_size(p_img)
            test_build_output_path_suffixes()
            test_batch_engine_uncompressed(p_img, p_logo)
            test_watermark_default_black_text()
            test_dialog_defaults_and_responsiveness()
            test_build_output_path_format_extension()
            test_compress_single_webp_format_generates_valid_webp(p_img)
            print("🎉 TẤT CẢ 9 BÀI KIỂM THỬ ĐÃ VƯỢT QUA THÀNH CÔNG (PASSED 100%)!")
        finally:
            if os.path.exists(p_img):
                os.remove(p_img)
            if os.path.exists(p_logo):
                os.remove(p_logo)



