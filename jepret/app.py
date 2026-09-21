"""Aplikasi: alur tangkap -> (pilih area) -> editor."""

import os
import re
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from . import APP_ID, APP_NAME, VERSION, capture  # noqa: E402
from .config import _pictures_dir, config  # noqa: E402
from .document import Document  # noqa: E402
from .editor import CSS, EditorWindow  # noqa: E402
from .overlay import AreaSelector  # noqa: E402

def _data_dirs():
    """Lokasi folder `data` untuk semua cara pemasangan.

    Urutan: menjalankan langsung dari sumber, lalu pemasangan sistem
    (paket .deb / install.sh dengan prefix), lalu folder data milik user.
    """
    candidates = [
        Path(__file__).resolve().parent.parent / "data",
        Path("/usr/share/jepret/data"),
        Path("/usr/local/share/jepret/data"),
        Path.home() / ".local/share/jepret/data",
    ]
    return [path for path in candidates if path.is_dir()]


DATA_DIR = next(iter(_data_dirs()), Path(__file__).resolve().parent.parent / "data")


class JepretApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.start_window = None
        self._busy = False
        self._permission_ok = False      # satu tangkapan sukses = izin pasti ada
        self._permission_runs = 0        # batas keras, agar tak bisa berulang
        self.add_main_option("area", ord("a"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Tangkap area lalu edit", None)
        self.add_main_option("window", ord("w"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Tangkap jendela (pemilih GNOME)", None)
        self.add_main_option("full", ord("f"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Tangkap seluruh layar", None)
        self.add_main_option("delay", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.INT,
                             "Jeda sebelum menangkap (detik)", "N")
        self.add_main_option("open", ord("o"), GLib.OptionFlags.NONE, GLib.OptionArg.FILENAME,
                             "Buka berkas gambar di editor", "FILE")
        self.add_main_option("version", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Tampilkan versi", None)

    # ------------------------------------------------------------ lifecycle
    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        for data_dir in _data_dirs():
            theme.add_search_path(str(data_dir / "icons"))
        # pindahkan pintasan yang masih memakai nama aplikasi lama
        from . import shortcuts
        shortcuts.migrate_legacy()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if options.get("version"):
            command_line.print_literal(f"{APP_NAME} {VERSION}\n")
            return 0
        delay = int(options.get("delay") or 0)
        target = options.get("open")
        if isinstance(target, bytes):
            target = target.decode("utf-8", "surrogateescape")
        args = command_line.get_arguments()[1:]
        if not target:
            for arg in args:
                if not arg.startswith("-") and Path(arg).is_file():
                    target = arg
                    break
        self.activate()
        if target:
            self.open_image_file(target)
        elif options.get("area"):
            self.start_capture("area", delay=delay)
        elif options.get("window"):
            self.start_capture("window", delay=delay)
        elif options.get("full"):
            self.start_capture("full", delay=delay)
        else:
            self.show_start_window()
        return 0

    def do_activate(self):
        Adw.Application.do_activate(self)

    # ------------------------------------------------------------- tampilan
    def show_start_window(self):
        if self.start_window is None:
            from .start import StartWindow
            self.start_window = StartWindow(self)
            self.start_window.connect("close-request", self._on_start_closed)
        self.start_window.present()

    def _on_start_closed(self, _win):
        self.start_window = None
        return False

    def open_image_file(self, path):
        try:
            image = Image.open(path)
            image.load()
        except (OSError, ValueError) as exc:
            self.error_dialog(f"Tidak bisa membuka gambar:\n{exc}")
            return
        document = Document(image, source_path=str(path))
        document.saved_path = str(path)
        self.open_editor(document)

    def open_editor(self, document, replace=None):
        window = EditorWindow(self, document)
        window.present()
        if self.start_window is not None:
            self.start_window.close()
        if replace is not None and not replace.doc.items and not replace.doc.dirty:
            replace.doc.dirty = False
            replace.destroy()
        return window

    def error_dialog(self, message, parent=None):
        parent = parent or self.get_active_window()
        dialog = Adw.AlertDialog(heading="Jepret", body=message)
        dialog.add_response("ok", "Tutup")
        dialog.present(parent)

    # -------------------------------------------------------------- capture
    def start_capture(self, mode="area", delay=0, parent=None, permission_run=None):
        """Tangkap layar.

        permission_run=True dipakai saat portal perlu menampilkan dialog izin:
        GNOME hanya mengizinkan dialog itu muncul untuk aplikasi yang sedang
        fokus, jadi jendela Jepret justru harus tetap terlihat. Setelah izin
        diberikan, tangkapan diulang dengan jendela disembunyikan supaya
        jendela Jepret sendiri tidak ikut terpotret.

        permission_run=None berarti "tentukan sendiri". Nilai True/False yang
        diberikan pemanggil selalu dihormati: tangkapan ulang setelah izin
        harus tetap False walau pengecekan izin masih bilang belum, kalau tidak
        keduanya saling memicu dan aplikasi memotret tanpa henti.
        """
        if self._busy:
            return
        if permission_run is None:
            permission_run = not (self._permission_ok
                                  or capture.screenshot_permission_granted())
        if permission_run:
            if self._permission_runs >= 1:
                permission_run = False   # sudah pernah dicoba; jangan diulang
            else:
                self._permission_runs += 1
        self._busy = True
        # tahan aplikasi selama menunggu portal + overlay, kalau tidak
        # GApplication akan keluar sendiri karena tidak ada jendela terbuka
        self.hold()
        released = {"done": False}

        def release():
            if not released["done"]:
                released["done"] = True
                self.release()

        hidden = []
        if permission_run:
            # pastikan ada jendela yang fokus supaya dialog izin boleh tampil
            window = parent or self.get_active_window()
            if window is None or not window.get_visible():
                self.show_start_window()
                window = self.start_window
            if window is not None:
                window.present()
        else:
            for window in (parent, self.start_window):
                if window is not None and window.get_visible():
                    window.set_visible(False)
                    hidden.append(window)

        def restore():
            for window in hidden:
                window.set_visible(True)

        def cancelled():
            self._busy = False
            restore()
            if not any(w.get_visible() for w in self.get_windows()):
                self.show_start_window()
            release()

        def retry(as_permission_run):
            """Ulangi sekali lagi setelah state busy bersih.

            Urutannya penting: hold baru diambil oleh start_capture dulu, baru
            hold lama dilepas. Kalau dibalik, jumlah hold sempat nol tanpa
            jendela terbuka dan GApplication langsung keluar.
            """
            def again():
                self._busy = False
                self.start_capture(mode, delay=0, parent=parent,
                                   permission_run=as_permission_run)
                release()
                return GLib.SOURCE_REMOVE

            GLib.timeout_add(300, again)

        def on_captured(path, error):
            self._busy = False
            if error is not None:
                restore()
                if isinstance(error, capture.CaptureCancelled):
                    if not any(w.get_visible() for w in self.get_windows()):
                        self.show_start_window()
                    release()
                    return
                if not permission_run:
                    # kemungkinan besar portal ingin menampilkan dialog izin;
                    # tampilkan jendela dulu lalu coba sekali lagi
                    retry(True)
                    return
                self.error_dialog(
                    f"{error}\n\nJepret butuh izin screenshot dari sistem. Klik dulu "
                    "jendela Jepret ini supaya menjadi jendela aktif, lalu tekan "
                    "tombol tangkap sekali lagi — dialog izin akan muncul dan "
                    "cukup dijawab sekali.", parent)
                release()
                return
            try:
                image = Image.open(path)
                image.load()
            except (OSError, ValueError) as exc:
                restore()
                self.error_dialog(f"Gambar hasil tangkapan tidak terbaca:\n{exc}", parent)
                release()
                return
            finally:
                _cleanup_portal_file(path)

            # portal memberi gambar => izin pasti ada, apa pun kata pengecekan
            self._permission_ok = True

            if permission_run and mode != "window":
                # izin baru saja diberikan: gambar ini masih memuat jendela
                # Jepret sendiri, jadi ambil ulang dengan jendela disembunyikan.
                # Mode jendela dikecualikan: gambarnya berasal dari pemilih
                # GNOME (bukan tangkapan layar penuh), jadi mengulang hanya
                # akan membuka pemilih itu untuk kedua kalinya.
                retry(False)
                return

            if mode == "area":
                self._select_area(image, parent, restore, release)
            else:
                self.open_editor(Document(image), replace=parent)
                release()

        def do_capture():
            capture.capture_with_delay(
                on_captured, delay=delay, interactive=(mode == "window"),
                include_cursor=bool(config["include_cursor"]))

        def fire():
            if permission_run:
                window = parent or self.get_active_window() or self.start_window
                # dialog izin hanya boleh tampil untuk aplikasi yang sedang
                # fokus; kalau jendela kita belum aktif, minta satu klik dulu
                if window is not None and not window.is_active():
                    self._ask_permission(window, do_capture, cancelled)
                    return GLib.SOURCE_REMOVE
            do_capture()
            return GLib.SOURCE_REMOVE

        # jeda: jendela yang disembunyikan perlu benar-benar hilang, dan pada
        # permission_run jendela perlu waktu untuk tampil & mendapat fokus
        GLib.timeout_add(900 if permission_run else (250 if hidden else 1), fire)

    def _ask_permission(self, window, proceed, cancel):
        """Satu klik untuk memberi fokus, supaya dialog izin sistem boleh tampil."""
        dialog = Adw.AlertDialog(
            heading="Izinkan Jepret memotret layar",
            body="Sistem akan menanyakan izin screenshot satu kali saja. "
                 "Tekan Lanjutkan, lalu pilih Bagikan/Izinkan pada dialog sistem.")
        dialog.add_response("cancel", "Batal")
        dialog.add_response("continue", "Lanjutkan")
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("continue")

        def on_response(_dialog, response):
            if response == "continue":
                # jendela sudah aktif karena baru saja diklik
                GLib.timeout_add(150, lambda: (proceed(), GLib.SOURCE_REMOVE)[1])
            else:
                cancel()

        dialog.connect("response", on_response)
        window.present()
        dialog.present(window)

    def _select_area(self, image, parent, restore, release=lambda: None):
        def on_done(rect):
            x, y, w, h = (int(round(v)) for v in rect)
            cropped = image.crop((x, y, x + max(1, w), y + max(1, h)))
            self.open_editor(Document(cropped), replace=parent)
            release()

        def on_cancel():
            restore()
            if not any(w.get_visible() for w in self.get_windows()):
                self.show_start_window()
            release()

        selector = AreaSelector(self, image, on_done, on_cancel)
        selector.present()


def _cleanup_portal_file(path):
    """Buang berkas sementara milik portal, jangan sentuh berkas user.

    Portal non-interaktif GNOME menulis hasilnya ke <Pictures>/Screenshot.png.
    Mode interaktif bisa mengembalikan berkas yang justru sengaja disimpan user
    di <Pictures>/Screenshots/, jadi yang dihapus hanya lokasi sementara yang
    benar-benar dikenali.
    """
    try:
        file = Path(path).resolve()
        if not file.is_file():
            return
        if time.time() - file.stat().st_mtime > 120:
            return

        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()))
        temp_roots = [cache, runtime, Path("/tmp"), Path(tempfile.gettempdir())]
        in_temp = any(file.is_relative_to(root) for root in temp_roots if root)

        # berkas milik portal di folder Pictures: Screenshot.png, dan bila
        # nama itu sudah terpakai, Screenshot-1.png, Screenshot-2.png, dst.
        # Hanya di root Pictures — folder Pictures/Screenshots milik user.
        pictures = _pictures_dir().resolve(strict=False)
        is_portal_output = (
            file.parent == pictures
            and re.fullmatch(r"Screenshot(-\d+)?\.png", file.name) is not None
        )
        if in_temp or is_portal_output:
            file.unlink()
    except OSError:
        pass


def check_dependencies():
    """Pesan jelas bila jembatan cairo<->GTK belum terpasang."""
    missing = []
    try:
        gi.require_foreign("cairo")
    except Exception:
        missing.append("python3-gi-cairo")
    if missing:
        sys.stderr.write(
            "Jepret butuh paket berikut:\n  sudo apt install -y " + " ".join(missing) + "\n")
        return False
    return True


def main(argv=None):
    if not check_dependencies():
        return 1
    app = JepretApp()
    return app.run(argv if argv is not None else sys.argv)
