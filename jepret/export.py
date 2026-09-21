"""Simpan gambar ke berkas."""

from datetime import datetime
from pathlib import Path

from .config import config

FORMATS = {
    "png": ("PNG", ".png", "image/png"),
    "jpg": ("JPEG", ".jpg", "image/jpeg"),
    "webp": ("WEBP", ".webp", "image/webp"),
}


def default_name(fmt=None):
    fmt = fmt or config["default_format"]
    stamp = datetime.now().strftime(config["filename_pattern"])
    return f"{stamp}{FORMATS[fmt][1]}"


def unique_path(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for n in range(2, 1000):
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
    return path


def format_for_path(path) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in ("jpeg", "jpg"):
        return "jpg"
    return suffix if suffix in FORMATS else "png"


def save_image(image, path) -> Path:
    path = Path(path)
    fmt = format_for_path(path)
    pil_format = FORMATS[fmt][0]
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jpg":
        image.convert("RGB").save(path, pil_format, quality=int(config["jpeg_quality"]), subsampling=0)
    elif fmt == "webp":
        image.save(path, pil_format, quality=int(config["jpeg_quality"]), method=4)
    else:
        image.save(path, pil_format)
    return path


def quick_save(image) -> Path:
    path = unique_path(config.save_dir, default_name())
    return save_image(image, path)
