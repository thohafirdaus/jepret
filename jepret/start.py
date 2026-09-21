"""Jendela awal: pilihan mode tangkap."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from .config import config  # noqa: E402

MODES = [
    ("area", "Area", "jepret-crop-symbolic", "Pilih area dengan mouse (A)"),
    ("window", "Jendela", "jepret-window-symbolic", "Pilih jendela lewat pemilih GNOME (W)"),
    ("full", "Layar penuh", "jepret-fullscreen-symbolic", "Tangkap seluruh layar (F)"),
]


class StartWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Jepret")
        self.app = app
        self.set_default_size(560, 420)
        # jangan dikunci: dialog preferensi butuh ruang untuk tampil
        self.set_size_request(480, 380)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Jepret", subtitle="Tangkap · Anotasi · Bagikan"))
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Riwayat screenshot", "win.history")
        menu.append("Buka gambar…", "win.open")
        menu.append("Preferensi…", "win.preferences")
        menu.append("Tentang Jepret", "win.about")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                          margin_top=26, margin_bottom=22, margin_start=22, margin_end=22)

        modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14,
                        homogeneous=True, hexpand=True)
        for mode, label, icon, tooltip in MODES:
            button = Gtk.Button()
            button.set_tooltip_text(tooltip)
            button.add_css_class("card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                            margin_top=22, margin_bottom=22)
            image = Gtk.Image.new_from_icon_name(icon)
            image.set_pixel_size(42)
            inner.append(image)
            text = Gtk.Label(label=label)
            text.add_css_class("heading")
            inner.append(text)
            button.set_child(inner)
            button.connect("clicked", self._on_mode, mode)
            modes.append(button)
        content.append(modes)

        options = Adw.PreferencesGroup()
        self.delay_row = Adw.SpinRow.new_with_range(0, 30, 1)
        self.delay_row.set_title("Jeda sebelum menangkap")
        self.delay_row.set_subtitle("Detik — berguna untuk memotret menu yang terbuka")
        self.delay_row.set_value(0)
        options.add(self.delay_row)

        self.cursor_row = Adw.SwitchRow(title="Sertakan kursor mouse")
        self.cursor_row.set_active(bool(config["include_cursor"]))
        self.cursor_row.connect("notify::active", self._on_cursor)
        options.add(self.cursor_row)
        content.append(options)

        hint = Gtk.Label(label="Pintasan: A area · W jendela · F layar penuh")
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        content.append(hint)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(content)
        self.set_content(view)

        for name, handler in (("history", self._on_history), ("open", self._on_open),
                              ("preferences", self._on_preferences),
                              ("about", self._on_about)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        keys = Gtk.EventControllerKey.new()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    def _on_cursor(self, row, _param):
        config["include_cursor"] = row.get_active()
        config.save()

    def _on_mode(self, _button, mode):
        self.app.start_capture(mode, delay=int(self.delay_row.get_value()))

    def _on_key(self, _ctrl, keyval, _code, _state):
        mapping = {Gdk.KEY_a: "area", Gdk.KEY_w: "window", Gdk.KEY_f: "full"}
        if keyval in mapping:
            self._on_mode(None, mapping[keyval])
            return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _on_history(self, *_args):
        from .gallery import GalleryWindow
        GalleryWindow(self.app, self).present()

    def _on_open(self, *_args):
        dialog = Gtk.FileDialog()
        dialog.set_title("Buka gambar")
        dialog.open(self, None, self._on_open_done)

    def _on_open_done(self, dialog, result):
        from gi.repository import GLib
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file and file.get_path():
            self.app.open_image_file(file.get_path())

    def _on_preferences(self, *_args):
        from .prefs import PreferencesDialog
        PreferencesDialog(self.app).present(self)

    def _on_about(self, *_args):
        from . import APP_NAME, VERSION
        Adw.AboutDialog(
            application_name=APP_NAME, version=VERSION,
            comments="Screenshot area/jendela dengan editor anotasi lengkap.",
            license_type=Gtk.License.MIT_X11,
        ).present(self)
