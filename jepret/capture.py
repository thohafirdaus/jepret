"""Capture layar lewat xdg-desktop-portal.

Di sesi Wayland, org.gnome.Shell.Screenshot menolak pemanggil biasa
("AccessDenied: Screenshot is not allowed"), jadi satu-satunya jalur yang
tersedia adalah org.freedesktop.portal.Screenshot. Portal memakai pola
request-handle: panggilan mengembalikan object path, hasilnya datang lewat
sinyal Response pada path tersebut.
"""

import random
import re
import string
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PERMISSION_BUS = "org.freedesktop.impl.portal.PermissionStore"
PERMISSION_PATH = "/org/freedesktop/impl/portal/PermissionStore"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
REQUEST_IFACE = "org.freedesktop.portal.Request"


class CaptureError(Exception):
    pass


class CaptureCancelled(CaptureError):
    """User menutup/menolak dialog portal."""


def current_app_id() -> str:
    """Tebak app id seperti yang dipakai xdg-desktop-portal.

    Saat dijalankan dari menu GNOME, prosesnya ada di scope systemd
    `app-gnome-<desktop-id>-<pid>.scope`, dan portal memakai <desktop-id>
    sebagai identitas aplikasi. Dari terminal biasa, app id-nya kosong.
    """
    try:
        cgroup = open("/proc/self/cgroup").read()
    except OSError:
        return ""
    match = re.search(r"app-(?:gnome|flatpak)-(.+?)-\d+\.scope", cgroup)
    if not match:
        return ""
    # systemd meng-escape karakter, mis. \x2d untuk tanda hubung
    return re.sub(r"\\x([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), match.group(1))


def screenshot_permission_granted() -> bool:
    """Apakah izin screenshot untuk aplikasi ini sudah tersimpan?

    Dipakai untuk memutuskan boleh-tidaknya menyembunyikan jendela sebelum
    memotret: GNOME hanya mengizinkan dialog izin muncul untuk aplikasi yang
    sedang fokus, jadi saat izin belum ada jendela harus tetap terlihat.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync(
            PERMISSION_BUS, PERMISSION_PATH,
            "org.freedesktop.impl.portal.PermissionStore", "Lookup",
            GLib.Variant("(ss)", ("screenshot", "screenshot")),
            GLib.VariantType("(a{sas}v)"), Gio.DBusCallFlags.NONE, 2000, None,
        )
        permissions = result.unpack()[0]
    except GLib.Error:
        return True   # tidak bisa dicek -> anggap sudah, jaring pengaman tetap ada
    return any("yes" in permissions.get(app_id, [])
               for app_id in {current_app_id(), ""})


def _token():
    return "jepret_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


def uri_to_path(uri: str) -> str:
    return unquote(urlparse(uri).path)


def screenshot_async(callback, interactive=False, parent_window="", include_cursor=False):
    """Minta screenshot ke portal.

    callback(path: str | None, error: Exception | None) dipanggil di main loop.
    interactive=True membuka UI screenshot bawaan GNOME (pilih jendela/area).
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error as exc:
        GLib.idle_add(callback, None, CaptureError(f"Tidak bisa terhubung ke D-Bus: {exc}"))
        return

    token = _token()
    sender = bus.get_unique_name().lstrip(":").replace(".", "_")
    handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    state = {"sub": None, "done": False}

    def finish(path, error):
        if state["done"]:
            return
        state["done"] = True
        if state["sub"] is not None:
            bus.signal_unsubscribe(state["sub"])
            state["sub"] = None
        callback(path, error)

    def on_response(_conn, _sender, _path, _iface, _signal, params):
        response, results = params.unpack()
        if response == 1:
            finish(None, CaptureCancelled("Screenshot dibatalkan."))
        elif response != 0:
            finish(None, CaptureError("Portal menolak permintaan screenshot."))
        else:
            uri = results.get("uri")
            if not uri:
                finish(None, CaptureError("Portal tidak mengembalikan gambar."))
            else:
                finish(uri_to_path(uri), None)

    state["sub"] = bus.signal_subscribe(
        PORTAL_BUS, REQUEST_IFACE, "Response", handle, None,
        Gio.DBusSignalFlags.NONE, on_response,
    )

    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", interactive),
        "modal": GLib.Variant("b", True),
    }
    if include_cursor:
        options["cursor_mode"] = GLib.Variant("u", 2)

    def on_call_done(source, res):
        try:
            source.call_finish(res)
        except GLib.Error as exc:
            finish(None, CaptureError(f"Portal screenshot gagal: {exc.message}"))

    bus.call(
        PORTAL_BUS, PORTAL_PATH, SCREENSHOT_IFACE, "Screenshot",
        GLib.Variant("(sa{sv})", (parent_window, options)),
        GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None, on_call_done,
    )


def capture_with_delay(callback, delay=0, **kwargs):
    """Sama seperti screenshot_async, dengan jeda detik sebelum memotret."""
    if delay <= 0:
        screenshot_async(callback, **kwargs)
        return

    def fire():
        screenshot_async(callback, **kwargs)
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(delay, fire)


def total_logical_geometry():
    """Bounding box semua monitor dalam koordinat logis (x, y, w, h)."""
    display = Gdk.Display.get_default()
    monitors = display.get_monitors()
    x0 = y0 = 10**9
    x1 = y1 = -(10**9)
    for i in range(monitors.get_n_items()):
        geo = monitors.get_item(i).get_geometry()
        x0, y0 = min(x0, geo.x), min(y0, geo.y)
        x1, y1 = max(x1, geo.x + geo.width), max(y1, geo.y + geo.height)
    if x1 < x0:
        return 0, 0, 1920, 1080
    return x0, y0, x1 - x0, y1 - y0
