"""
core/image_compressor.py — Module nén ảnh thông minh cho Vietsub AI Studio
Hỗ trợ nén hàng loạt, điều chỉnh dung lượng mục tiêu, giữ chất lượng tối đa.
Hỗ trợ chèn logo watermark và text watermark (mã sản phẩm từ tên file).
"""

from __future__ import annotations

import functools
import io
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps


# ─────────────────────────────────────────────────────────────
# Định dạng ảnh được hỗ trợ
# ─────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"
}


# ─────────────────────────────────────────────────────────────
# Cấu hình Watermark (Logo + Text)
# ─────────────────────────────────────────────────────────────

@dataclass
class WatermarkConfig:
    """Cấu hình chèn logo và text watermark vào ảnh."""

    # ── Logo ──
    logo_enabled: bool = False
    logo_path: str = ""              # Đường dẫn file logo (PNG khuyến nghị)
    logo_scale: float = 0.15         # Tỉ lệ logo so với min_dim ảnh (0.02–0.80)
    logo_position: str = "bottom-right"  # topleft|topright|bottomleft|bottomright|center
    logo_opacity: int = 100          # 0–100
    logo_offset_x: float = 0.0      # Dịch ngang so với neo (-0.50 → +0.50 × img_w)
    logo_offset_y: float = 0.0      # Dịch dọc  so với neo (-0.50 → +0.50 × img_h)

    # ── Text ──
    text_enabled: bool = False
    text_source: str = "filename"    # "filename" = lấy từ stem tên file; "custom" = text_custom
    text_custom: str = ""            # Text tuỳ chỉnh khi text_source == "custom"
    text_position: str = "bottom-left"  # topleft|topright|bottomleft|bottomright|center
    text_size: int = 24              # Cỡ font (px)
    text_color: str = "#000000"      # Màu chữ hex (mặc định đen)
    text_bold: bool = False
    text_shadow: bool = False
    text_box: bool = False           # Nền hộp sau text
    text_box_color: str = "#000000"  # Màu nền hộp hex
    text_box_opacity: int = 60       # 0–100
    text_font_path: str = ""         # Rỗng = dùng font mặc định PIL
    text_offset_x: float = 0.0      # Dịch ngang so với neo (-0.50 → +0.50 × img_w)
    text_offset_y: float = 0.0      # Dịch dọc  so với neo (-0.50 → +0.50 × img_h)


# ─────────────────────────────────────────────────────────────
# Hàm tiện ích Watermark
# ─────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Chuyển chuỗi hex (#RRGGBB) sang tuple RGB."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return (255, 255, 255)


def _calc_position(
    pos: str,
    img_w: int, img_h: int,
    obj_w: int, obj_h: int,
    margin: int = 14,
) -> Tuple[int, int]:
    """Tính toạ độ (x, y) của object theo vị trí neo."""
    pos = pos.lower().replace(" ", "-")
    if pos in ("topleft", "top-left"):
        return margin, margin
    if pos in ("topright", "top-right"):
        return img_w - obj_w - margin, margin
    if pos in ("bottomleft", "bottom-left"):
        return margin, img_h - obj_h - margin
    if pos in ("bottomright", "bottom-right"):
        return img_w - obj_w - margin, img_h - obj_h - margin
    # center
    return (img_w - obj_w) // 2, (img_h - obj_h) // 2


@functools.lru_cache(maxsize=32)
def _load_font(font_path: str, size: int, bold: bool) -> ImageFont.FreeTypeFont:
    """Load font PIL; fallback về default nếu không tìm thấy file."""
    if font_path and Path(font_path).is_file():
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    # Thử tìm font system phổ biến theo thứ tự ưu tiên
    candidates = []
    import sys as _sys
    if _sys.platform == "darwin":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]
    elif _sys.platform == "win32":
        import os as _os
        windir = _os.environ.get("WINDIR", "C:/Windows")
        candidates = [
            f"{windir}/Fonts/arialbd.ttf" if bold else f"{windir}/Fonts/arial.ttf",
            f"{windir}/Fonts/calibrib.ttf" if bold else f"{windir}/Fonts/calibri.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for cand in candidates:
        if Path(cand).is_file():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    # Fallback cuối cùng
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def apply_watermark(img: Image.Image, cfg: WatermarkConfig, src_path: str) -> Image.Image:
    """
    Áp dụng logo và/hoặc text watermark lên ảnh PIL.
    Trả về ảnh đã được composite (không sửa ảnh gốc in-place).
    """
    # Chuyển về RGBA để dễ composite có alpha
    base_mode = img.mode
    working = img.convert("RGBA")
    img_w, img_h = working.size
    base_dim = max(img_w, img_h)
    min_dim = min(img_w, img_h)
    margin = max(8, int(min_dim * 0.025))

    # ── 1. Chèn Logo ──
    if cfg.logo_enabled and cfg.logo_path and Path(cfg.logo_path).is_file():
        try:
            logo_raw = Image.open(cfg.logo_path).convert("RGBA")
            # Scale theo cạnh ngắn nhất (min_dim) để đảm bảo kích thước nhất quán
            # trên mọi tỉ lệ ảnh (ngang/dọc/vuông)
            scale = max(0.02, min(0.80, cfg.logo_scale))
            logo_w = max(10, int(min_dim * scale))
            ratio = logo_w / logo_raw.width
            logo_h = max(10, int(logo_raw.height * ratio))
            logo = logo_raw.resize((logo_w, logo_h), Image.LANCZOS)

            # Áp dụng opacity vào kênh alpha của logo
            if cfg.logo_opacity < 100:
                r, g, b, a = logo.split()
                a = a.point(lambda p: int(p * cfg.logo_opacity / 100))
                logo = Image.merge("RGBA", (r, g, b, a))

            lx, ly = _calc_position(cfg.logo_position, img_w, img_h, logo_w, logo_h, margin=margin)
            # Áp dụng offset tinh chỉnh (clamp để logo không ra ngoài biên ảnh)
            lx = int(max(0, min(img_w - logo_w, lx + cfg.logo_offset_x * img_w)))
            ly = int(max(0, min(img_h - logo_h, ly + cfg.logo_offset_y * img_h)))
            # Paste logo lên layer mới để không ảnh hưởng vùng ngoài logo
            overlay = Image.new("RGBA", working.size, (0, 0, 0, 0))
            overlay.paste(logo, (lx, ly))
            working = Image.alpha_composite(working, overlay)
        except Exception:
            pass  # Bỏ qua lỗi logo, không dừng pipeline

    # ── 2. Chèn Text ──
    if cfg.text_enabled:
        try:
            # Xác định nội dung text
            if cfg.text_source == "filename":
                text_content = Path(src_path).stem
            else:
                text_content = cfg.text_custom.strip() or Path(src_path).stem

            if text_content:
                # Tính font size tỉ lệ theo cạnh ngắn nhất (min_dim) để nhất quán
                # trên mọi tỉ lệ ảnh (chuẩn 800px tham chiếu cho min_dim)
                actual_font_size = max(10, int(cfg.text_size * (min_dim / 800.0)))
                font = _load_font(cfg.text_font_path, actual_font_size, cfg.text_bold)
                draw_probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
                bbox = draw_probe.textbbox((0, 0), text_content, font=font)
                txt_w = bbox[2] - bbox[0]
                txt_h = bbox[3] - bbox[1]
                pad = max(4, int(actual_font_size * 0.28))  # Padding cho box nền

                tx, ty = _calc_position(
                    cfg.text_position, img_w, img_h,
                    txt_w + pad * 2, txt_h + pad * 2,
                    margin=margin,
                )
                # Áp dụng offset tinh chỉnh (clamp để text không ra ngoài biên ảnh)
                box_w = txt_w + pad * 2
                box_h = txt_h + pad * 2
                tx = int(max(0, min(img_w - box_w, tx + cfg.text_offset_x * img_w)))
                ty = int(max(0, min(img_h - box_h, ty + cfg.text_offset_y * img_h)))

                text_layer = Image.new("RGBA", working.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(text_layer)

                # Nền hộp (box)
                if cfg.text_box:
                    br, bg, bb = _hex_to_rgb(cfg.text_box_color)
                    box_alpha = int(255 * cfg.text_box_opacity / 100)
                    box_rect = [
                        tx, ty,
                        tx + txt_w + pad * 2, ty + txt_h + pad * 2
                    ]
                    draw.rectangle(box_rect, fill=(br, bg, bb, box_alpha))

                # Vị trí text thực sự (bên trong box nếu có)
                real_tx = tx + pad
                real_ty = ty + pad

                tr, tg, tb = _hex_to_rgb(cfg.text_color)

                # Shadow
                if cfg.text_shadow:
                    shadow_offset = max(1, int(actual_font_size * 0.06))
                    draw.text(
                        (real_tx + shadow_offset, real_ty + shadow_offset),
                        text_content,
                        font=font,
                        fill=(0, 0, 0, 180),
                    )

                # Bold giả (vẽ nhiều lần offset ±1 nếu không có font bold)
                if cfg.text_bold:
                    bold_offset = max(1, int(actual_font_size * 0.02))
                    for ox, oy in [(-bold_offset, 0), (bold_offset, 0), (0, -bold_offset), (0, bold_offset)]:
                        draw.text(
                            (real_tx + ox, real_ty + oy),
                            text_content, font=font,
                            fill=(tr, tg, tb, 255),
                        )

                # Text chính
                draw.text(
                    (real_tx, real_ty),
                    text_content, font=font,
                    fill=(tr, tg, tb, 255),
                )

                working = Image.alpha_composite(working, text_layer)
        except Exception:
            pass  # Bỏ qua lỗi text, không dừng pipeline

    # Chuyển về mode ban đầu nếu không phải RGBA gốc
    if base_mode == "RGB":
        final = Image.new("RGB", working.size, (255, 255, 255))
        final.paste(working, mask=working.split()[3])
        return final
    if base_mode in ("L", "P"):
        return working.convert(base_mode)
    return working


@dataclass
class CompressTask:
    """Thông tin một tác vụ nén ảnh."""
    src_path: str
    dst_path: str
    target_kb: int            # Dung lượng mục tiêu (KB)
    compress_enabled: bool = True  # Bật/tắt nén dung lượng (False = chỉ chèn watermark, giữ chất lượng gốc 100%)
    keep_exif: bool = True    # Giữ metadata EXIF gốc
    output_format: str = "auto"  # auto | JPEG | PNG | WEBP
    watermark: Optional[WatermarkConfig] = None  # Cấu hình watermark (None = không chèn)


@dataclass
class CompressResult:
    """Kết quả sau khi nén một ảnh."""
    src_path: str
    dst_path: str
    src_size_kb: float
    dst_size_kb: float
    width: int
    height: int
    success: bool
    error: str = ""

    @property
    def reduction_pct(self) -> float:
        if self.src_size_kb <= 0:
            return 0.0
        return (1 - self.dst_size_kb / self.src_size_kb) * 100


# ─────────────────────────────────────────────────────────────
# Thuật toán nén thông minh
# ─────────────────────────────────────────────────────────────

def _get_output_format(src_path: str, requested: str) -> str:
    """Xác định định dạng đầu ra phù hợp."""
    if requested.upper() in ("JPEG", "PNG", "WEBP"):
        return requested.upper()
    ext = Path(src_path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "JPEG"
    if ext == ".png":
        return "PNG"
    if ext == ".webp":
        return "WEBP"
    return "JPEG"


def _encode_to_bytes(
    img: Image.Image,
    fmt: str,
    quality: int,
    exif_bytes,
    lossless: bool = False,
    method: int = 4,
) -> bytes:
    """Encode ảnh PIL ra bytes với quality chỉ định."""
    buf = io.BytesIO()
    save_kwargs: dict = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
        save_kwargs["progressive"] = False
        if exif_bytes:
            save_kwargs["exif"] = exif_bytes
    elif fmt == "WEBP":
        if lossless:
            # Lossless WebP: chất lượng tuyệt đối như PNG, nhưng file nhỏ hơn ~25%
            save_kwargs["lossless"] = True
            save_kwargs["quality"] = 100  # không ảnh hưởng ở lossless nhưng set để rõ ý
            save_kwargs["method"] = min(method, 4)  # method=4 cho lossless cực nhanh và kích thước tương đương method=6
        else:
            save_kwargs["quality"] = quality
            # method=2: siêu tốc khi thăm dò binary search, method=4: chuẩn vàng xuất file của Google
            save_kwargs["method"] = method
        if exif_bytes:
            save_kwargs["exif"] = exif_bytes
    elif fmt == "PNG":
        compress = max(1, min(9, 9 - quality // 11))
        save_kwargs["compress_level"] = compress
        save_kwargs["optimize"] = True
    img.save(buf, **save_kwargs)
    return buf.getvalue()


def _scale_down_to_target(
    img: Image.Image,
    fmt: str,
    target_bytes: int,
    exif_bytes,
) -> Tuple[Image.Image, bytes]:
    """Thu nhỏ kích thước ảnh thông minh theo tỉ lệ hình học để đạt dung lượng mục tiêu siêu tốc."""
    from PIL import ImageFilter
    current = img

    # Đo nhanh dung lượng ở mức chất lượng thấp (quality=25) bằng method=2 siêu tốc
    probe_bytes = _encode_to_bytes(current, fmt, quality=25, exif_bytes=exif_bytes, method=2)
    if len(probe_bytes) <= target_bytes:
        final_bytes = _encode_to_bytes(current, fmt, quality=25, exif_bytes=exif_bytes, method=4)
        return current, final_bytes

    # Tính toán tỉ lệ co 1 bước dựa trên căn bậc hai tỉ lệ dung lượng byte
    # Nhân hệ số an toàn 0.92 để chắc chắn đạt mục tiêu
    ratio = max(0.05, min(0.95, ((target_bytes / len(probe_bytes)) ** 0.5) * 0.92))
    w = max(1, int(current.width * ratio))
    h = max(1, int(current.height * ratio))
    resized = current.resize((w, h), Image.LANCZOS)
    resized = resized.filter(ImageFilter.UnsharpMask(radius=0.5, percent=120, threshold=3))

    # Mã hoá ảnh đã thu nhỏ với mức chất lượng tốt (quality=78)
    result_bytes = _encode_to_bytes(resized, fmt, quality=78, exif_bytes=exif_bytes, method=4)
    if len(result_bytes) <= target_bytes:
        return resized, result_bytes

    # Nếu vẫn chưa đạt do ảnh có độ entropy/nhiễu quá cao, co thêm 1 bước phụ với quality=65
    ratio2 = max(0.05, min(0.90, ((target_bytes / len(result_bytes)) ** 0.5) * 0.90))
    w2 = max(1, int(resized.width * ratio2))
    h2 = max(1, int(resized.height * ratio2))
    resized2 = resized.resize((w2, h2), Image.LANCZOS)
    result_bytes2 = _encode_to_bytes(resized2, fmt, quality=65, exif_bytes=exif_bytes, method=4)
    return resized2, result_bytes2


def _compress_single(task: CompressTask) -> CompressResult:
    """
    Nén một ảnh về dung lượng mục tiêu (KB).
    Binary search quality để đạt target size chính xác nhất.
    """
    src_size_kb = os.path.getsize(task.src_path) / 1024.0

    try:
        img = Image.open(task.src_path)
        img = ImageOps.exif_transpose(img)
        width, height = img.size

        # Lấy EXIF
        exif_bytes = None
        if task.keep_exif:
            try:
                exif_bytes = img.info.get("exif", None)
            except Exception:
                exif_bytes = None

        fmt = _get_output_format(task.src_path, task.output_format)

        # Đảm bảo đuôi file đích khớp đúng định dạng xuất thực tế (ví dụ: WEBP -> .webp)
        ext_map = {"WEBP": ".webp", "JPEG": ".jpg", "PNG": ".png"}
        target_ext = ext_map.get(fmt)
        final_dst_path = task.dst_path
        if target_ext:
            curr_ext = Path(final_dst_path).suffix.lower()
            if not (curr_ext in (".jpg", ".jpeg") and target_ext == ".jpg"):
                if curr_ext != target_ext:
                    final_dst_path = str(Path(final_dst_path).with_suffix(target_ext))

        # Chuẩn hoá mode màu
        if fmt == "PNG":
            if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                img = img.convert("RGBA")
        else:
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
                background.paste(img, mask=mask)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

        # ── Áp dụng Watermark (logo + text) trước khi nén ──
        if task.watermark is not None:
            img = apply_watermark(img, task.watermark, task.src_path)
            # Cập nhật kích thước nếu watermark thay đổi
            width, height = img.size
            # Đảm bảo mode màu vẫn phù hợp sau watermark
            if fmt == "PNG":
                if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    img = img.convert("RGBA")
            else:
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
                    background.paste(img, mask=mask)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

        # ── Nếu TẮT nén dung lượng (Chỉ đóng dấu, giữ nguyên chất lượng gốc) ──
        if not task.compress_enabled:
            is_lossless = (fmt in ("PNG", "WEBP"))
            result_bytes = _encode_to_bytes(img, fmt, quality=100 if is_lossless else 98, exif_bytes=exif_bytes, lossless=is_lossless)
            Path(final_dst_path).parent.mkdir(parents=True, exist_ok=True)
            with open(final_dst_path, "wb") as f:
                f.write(result_bytes)
            dst_size_kb = os.path.getsize(final_dst_path) / 1024.0
            return CompressResult(
                src_path=task.src_path, dst_path=final_dst_path,
                src_size_kb=src_size_kb, dst_size_kb=dst_size_kb,
                width=width, height=height, success=True,
                error="(Giữ nguyên độ phân giải & chất lượng gốc, không nén)"
            )

        target_bytes = task.target_kb * 1024

        # Nếu ảnh gốc đã nhỏ hơn mục tiêu → giữ chất lượng cao nhất có thể
        if src_size_kb <= task.target_kb:
            if fmt == "WEBP":
                # WebP lossless khi ảnh vừa dưới target
                result_bytes = _encode_to_bytes(img, fmt, 100, exif_bytes, lossless=True, method=4)
            else:
                result_bytes = _encode_to_bytes(img, fmt, quality=95, exif_bytes=exif_bytes)
            Path(final_dst_path).parent.mkdir(parents=True, exist_ok=True)
            with open(final_dst_path, "wb") as f:
                f.write(result_bytes)
            dst_size_kb = os.path.getsize(final_dst_path) / 1024.0
            return CompressResult(
                src_path=task.src_path, dst_path=final_dst_path,
                src_size_kb=src_size_kb, dst_size_kb=dst_size_kb,
                width=width, height=height, success=True,
                error="(Ảnh đã nhỏ hơn mục tiêu, giữ chất lượng cao)"
            )

        # ── Chiến lược riêng cho WEBP: chỉ thử Lossless khi dung lượng gốc xấp xỉ mục tiêu ──
        # (Nếu ảnh gốc > target_kb * 1.25, lossless chắc chắn sẽ vượt target nên bỏ qua để tránh mất ~8s)
        if fmt == "WEBP" and (src_size_kb <= task.target_kb * 1.25):
            lossless_bytes = _encode_to_bytes(img, fmt, 100, exif_bytes, lossless=True, method=4)
            if len(lossless_bytes) <= target_bytes:
                Path(final_dst_path).parent.mkdir(parents=True, exist_ok=True)
                with open(final_dst_path, "wb") as f:
                    f.write(lossless_bytes)
                dst_size_kb = os.path.getsize(final_dst_path) / 1024.0
                return CompressResult(
                    src_path=task.src_path, dst_path=final_dst_path,
                    src_size_kb=src_size_kb, dst_size_kb=dst_size_kb,
                    width=width, height=height, success=True,
                    error="(WebP Lossless — chất lượng tuyệt đối, không mất pixel nào)"
                )

        if fmt == "WEBP":
            lo, hi = 30, 95
        else:
            lo, hi = 10, 95

        best_quality = lo
        best_result_bytes: Optional[bytes] = None

        # Binary search 6 lần (2^6 = 64 mức, đủ quét toàn bộ dải quality)
        # Sử dụng method=2 cho WebP trong lúc dò để tăng tốc 400%
        probe_method = 2 if fmt == "WEBP" else 4
        for _ in range(6):
            mid = (lo + hi) // 2
            result_bytes = _encode_to_bytes(img, fmt, mid, exif_bytes, method=probe_method)
            if len(result_bytes) <= target_bytes:
                best_quality = mid
                best_result_bytes = result_bytes
                lo = mid + 1
            else:
                hi = mid - 1
            if lo > hi:
                break

        # Nếu tìm thấy quality phù hợp, mã hoá bản cuối cùng với method=4 để tối ưu độ nét và kích thước
        if best_result_bytes is not None and len(best_result_bytes) <= target_bytes:
            if fmt == "WEBP":
                best_result_bytes = _encode_to_bytes(img, fmt, best_quality, exif_bytes, method=4)
        else:
            # Nếu quality thấp nhất vẫn lớn hơn target → scale down kích thước thông minh 1 bước
            img, best_result_bytes = _scale_down_to_target(
                img, fmt, target_bytes, exif_bytes
            )
            width, height = img.size

        Path(final_dst_path).parent.mkdir(parents=True, exist_ok=True)
        with open(final_dst_path, "wb") as f:
            f.write(best_result_bytes)

        dst_size_kb = os.path.getsize(final_dst_path) / 1024.0
        return CompressResult(
            src_path=task.src_path, dst_path=final_dst_path,
            src_size_kb=src_size_kb, dst_size_kb=dst_size_kb,
            width=width, height=height, success=True,
        )

    except Exception as e:
        return CompressResult(
            src_path=task.src_path, dst_path=task.dst_path,
            src_size_kb=src_size_kb, dst_size_kb=0.0,
            width=0, height=0, success=False, error=str(e),
        )


# ─────────────────────────────────────────────────────────────
# Batch Compressor Engine (Đa Luồng / Multi-Core)
# ─────────────────────────────────────────────────────────────

class ImageCompressorEngine:
    """Engine nén ảnh hàng loạt đa luồng (multi-core) với callback tiến độ. Hỗ trợ cancel."""

    def __init__(self):
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def reset(self):
        self._cancel_event.clear()

    def compress_batch(
        self,
        tasks: List[CompressTask],
        on_progress: Callable[[int, int, CompressResult], None],
        on_done: Callable[[List[CompressResult]], None],
    ):
        """Nén hàng loạt trong background thread sử dụng đa luồng (multi-core)."""
        self.reset()
        threading.Thread(
            target=self._run,
            args=(tasks, on_progress, on_done),
            daemon=True,
        ).start()

    def _worker_task(self, task: CompressTask) -> CompressResult:
        if self._cancel_event.is_set():
            return CompressResult(
                src_path=task.src_path,
                dst_path=task.dst_path,
                src_size_kb=0.0,
                dst_size_kb=0.0,
                width=0,
                height=0,
                success=False,
                error="Đã dừng theo yêu cầu của người dùng",
            )
        return _compress_single(task)

    def _run(self, tasks: List[CompressTask], on_progress, on_done):
        total = len(tasks)
        if total == 0:
            try:
                on_done([])
            except Exception:
                pass
            return

        results: List[Optional[CompressResult]] = [None] * total
        completed_count = 0
        lock = threading.Lock()

        # Số luồng song song: Tận dụng số core CPU, tối đa 8 luồng để kiểm soát RAM
        max_workers = min(8, max(1, os.cpu_count() or 4))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {}
            for idx, task in enumerate(tasks):
                if self._cancel_event.is_set():
                    break
                future = executor.submit(self._worker_task, task)
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                if self._cancel_event.is_set():
                    try:
                        res = future.result()
                        results[idx] = res
                    except Exception:
                        pass
                    continue

                try:
                    res = future.result()
                except Exception as e:
                    res = CompressResult(
                        src_path=tasks[idx].src_path,
                        dst_path=tasks[idx].dst_path,
                        src_size_kb=0.0,
                        dst_size_kb=0.0,
                        width=0,
                        height=0,
                        success=False,
                        error=str(e),
                    )

                results[idx] = res
                with lock:
                    completed_count += 1
                    curr_done = completed_count

                try:
                    on_progress(curr_done, total, res)
                except Exception:
                    pass

        final_results = [r for r in results if r is not None]
        try:
            on_done(final_results)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def scan_images(paths: List[str]) -> List[str]:
    """Quét danh sách ảnh hợp lệ từ file/thư mục."""
    found: List[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    found.append(str(child))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            found.append(str(path))
    return found


def build_output_path(
    src: str,
    output_dir: str,
    suffix: str = "_compressed",
    output_format: str = "auto",
) -> str:
    """Tạo đường dẫn file đầu ra theo định dạng được chọn."""
    p = Path(src)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = output_format.upper()
    if fmt == "WEBP":
        ext = ".webp"
    elif fmt in ("JPEG", "JPG"):
        ext = ".jpg"
    elif fmt == "PNG":
        ext = ".png"
    else:
        ext = p.suffix.lower()
        if not ext:
            ext = ".jpg"
    new_name = p.stem + suffix + ext
    return str(out_dir / new_name)

