"""Blur & pixelate area, dihitung dari gambar dasar memakai Pillow."""

from PIL import Image, ImageFilter

import cairo


def pil_to_surface(image: Image.Image) -> cairo.ImageSurface:
    """PIL RGBA -> cairo ARGB32 (premultiplied)."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    stride = surface.get_stride()
    data = image.tobytes("raw", "BGRa")
    buf = surface.get_data()
    row = w * 4
    if stride == row:
        buf[:] = data
    else:
        for y in range(h):
            buf[y * stride:y * stride + row] = data[y * row:(y + 1) * row]
    surface.mark_dirty()
    return surface


def apply_effect(base: Image.Image, rect, effect="pixelate", strength=12) -> Image.Image:
    x, y, w, h = (int(round(v)) for v in rect)
    x = max(0, min(x, base.width - 1))
    y = max(0, min(y, base.height - 1))
    w = max(1, min(w, base.width - x))
    h = max(1, min(h, base.height - y))
    region = base.crop((x, y, x + w, y + h))
    if effect == "blur":
        radius = max(1.0, strength * 0.9)
        return region.filter(ImageFilter.GaussianBlur(radius))
    block = max(2, int(strength))
    small = region.resize(
        (max(1, w // block), max(1, h // block)), Image.Resampling.BILINEAR
    )
    return small.resize((w, h), Image.Resampling.NEAREST)
