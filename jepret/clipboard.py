"""Salin gambar ke clipboard.

Gdk.Clipboard bekerja instan tetapi isinya hilang saat aplikasi ditutup
(sifat Wayland: tidak ada clipboard manager bawaan). Karena itu bila
`wl-copy` tersedia, gambar juga diserahkan ke proses itu supaya tetap bisa
ditempel setelah Jepret ditutup.
"""

import shutil
import subprocess

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib  # noqa: E402


def has_wl_copy():
    return shutil.which("wl-copy") is not None


def _set_gdk_clipboard(display, png_bytes):
    """Sediakan gambar sebagai texture sekaligus sebagai image/png mentah."""
    try:
        data = GLib.Bytes.new(png_bytes)
        providers = [Gdk.ContentProvider.new_for_bytes("image/png", data)]
        try:
            texture = Gdk.Texture.new_from_bytes(data)
            providers.insert(0, Gdk.ContentProvider.new_for_value(texture))
        except GLib.Error:
            pass
        display.get_clipboard().set_content(Gdk.ContentProvider.new_union(providers))
        return True
    except (GLib.Error, TypeError):
        return False


def _set_wl_copy(png_bytes):
    """wl-copy menahan isi clipboard setelah Jepret ditutup."""
    try:
        process = subprocess.Popen(
            ["wl-copy", "--type", "image/png"], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        process.stdin.write(png_bytes)
        process.stdin.close()   # tanpa EOF, wl-copy tidak pernah menyalin
        return True
    except (OSError, BrokenPipeError):
        return False


def copy_png(display, png_bytes) -> str:
    """Kembalikan pesan status untuk ditampilkan ke user."""
    persistent = _set_wl_copy(png_bytes) if has_wl_copy() else False
    in_app = _set_gdk_clipboard(display, png_bytes)
    if persistent:
        return "Disalin ke clipboard"
    if in_app:
        return "Disalin ke clipboard (pasang wl-clipboard agar tetap ada setelah ditutup)"
    return "Gagal menyalin ke clipboard"
