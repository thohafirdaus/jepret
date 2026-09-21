"""Uji bahwa satu permintaan tangkap = satu tangkapan (tidak berulang).

Regresi untuk bug: bila portal berhasil memotret tetapi pengecekan izin tetap
melaporkan "belum diberikan" (mis. saat dijalankan lewat pintasan global, di
mana portal memakai app id yang berbeda), alur "ulangi setelah izin" saling
memicu diri sendiri dan aplikasi memotret tanpa henti.

Jalankan: python3 tests/capture_loop_test.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from jepret import app as app_module  # noqa: E402

if not Gtk.init_check():
    print("GTK tidak bisa start (tidak ada display) - uji dilewati.")
    sys.exit(0)

failures = []


def check(name, condition):
    print(("  ok  " if condition else "  GAGAL ") + name)
    if not condition:
        failures.append(name)


SCENARIO = {"n": 0}


def run_scenario(name, permission_granted, capture_fails_first, mode="full"):
    """Jalankan satu skenario tangkap dan hitung berapa kali portal dipanggil."""
    calls = {"capture": 0, "editor": 0}
    tmpdir = Path(tempfile.mkdtemp(prefix="jepret-uji-"))

    def fake_capture_with_delay(callback, delay=0, **kwargs):
        calls["capture"] += 1
        index = calls["capture"]

        def deliver():
            if capture_fails_first and index == 1:
                callback(None, app_module.capture.CaptureError("portal menolak (uji)"))
            else:
                path = tmpdir / f"tangkapan-{index}.png"
                Image.new("RGB", (120, 90), (10, 20, 30)).save(path)
                callback(str(path), None)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(10, deliver)

    real_capture = app_module.capture.capture_with_delay
    real_granted = app_module.capture.screenshot_permission_granted
    app_module.capture.capture_with_delay = fake_capture_with_delay
    app_module.capture.screenshot_permission_granted = lambda: permission_granted

    application = app_module.JepretApp()
    SCENARIO["n"] += 1
    application.set_application_id(f"id.jepret.JepretUjiLoop{SCENARIO['n']}")
    application.register(None)

    # jangan buka jendela sungguhan selama uji
    application.show_start_window = lambda: None
    application.error_dialog = lambda *a, **k: None
    application._select_area = lambda *a, **k: calls.__setitem__("editor", calls["editor"] + 1)

    def fake_open_editor(document, replace=None):
        calls["editor"] += 1
        return None

    application.open_editor = fake_open_editor

    loop = GLib.MainLoop()
    GLib.timeout_add(100, lambda: (application.start_capture(mode), GLib.SOURCE_REMOVE)[1])
    GLib.timeout_add_seconds(4, lambda: (loop.quit(), GLib.SOURCE_REMOVE)[1])
    loop.run()

    app_module.capture.capture_with_delay = real_capture
    app_module.capture.screenshot_permission_granted = real_granted
    print(f"  [{name}] panggilan portal: {calls['capture']}, editor dibuka: {calls['editor']}")
    return calls


print("Satu pintasan = satu tangkapan")

calls = run_scenario("izin sudah ada", permission_granted=True, capture_fails_first=False)
check("izin ada: portal dipanggil tepat sekali", calls["capture"] == 1)
check("izin ada: editor dibuka sekali", calls["editor"] == 1)

calls = run_scenario("izin tak terdeteksi", permission_granted=False, capture_fails_first=False)
check("izin tak terdeteksi: tidak memotret berulang", calls["capture"] <= 2)
check("izin tak terdeteksi: editor tetap dibuka sekali", calls["editor"] == 1)

# gagal -> minta izin (jendela tampil) -> potret ulang bersih: tiga panggilan
# adalah batas wajar untuk kasus terburuk, bukan perulangan
calls = run_scenario("portal menolak dulu", permission_granted=True, capture_fails_first=True)
check("gagal lalu berhasil: maksimal tiga percobaan", calls["capture"] <= 3)
check("gagal lalu berhasil: editor dibuka sekali", calls["editor"] == 1)

# Mode jendela memakai pemilih GNOME. Mengulang tangkapan di mode ini berarti
# membuka pemilih itu dua kali, jadi harus tepat satu permintaan.
calls = run_scenario("jendela, izin tak terdeteksi", permission_granted=False,
                     capture_fails_first=False, mode="window")
check("mode jendela: pemilih GNOME dibuka tepat sekali", calls["capture"] == 1)
check("mode jendela: editor dibuka sekali", calls["editor"] == 1)

print()
if failures:
    print(f"{len(failures)} uji GAGAL: {failures}")
    sys.exit(1)
print("Semua uji lolos.")
