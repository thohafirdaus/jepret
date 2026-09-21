"""Riwayat screenshot: grid thumbnail dari folder simpan."""

import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from .config import config  # noqa: E402

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
LIMIT = 120


class GalleryWindow(Adw.Window):
    def __init__(self, app, parent=None):
        super().__init__(title="Riwayat screenshot", transient_for=parent)
        self.app = app
        self.set_default_size(880, 620)
        self.paths = []

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Riwayat screenshot",
                                                subtitle=str(config.save_dir)))
        folder = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Buka folder")
        folder.connect("clicked", self._on_open_folder)
        header.pack_end(folder)

        self.flow = Gtk.FlowBox(valign=Gtk.Align.START, max_children_per_line=5,
                                selection_mode=Gtk.SelectionMode.SINGLE,
                                row_spacing=12, column_spacing=12,
                                margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.flow.connect("child-activated", self._on_activated)

        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_child(self.flow)

        self.status = Adw.StatusPage(
            title="Belum ada screenshot", icon_name="applets-screenshooter-symbolic",
            description=f"Screenshot yang disimpan akan muncul di sini\n({config.save_dir})")

        self.stack = Gtk.Stack()
        self.stack.add_named(scroller, "grid")
        self.stack.add_named(self.status, "empty")

        actions = Gtk.Box(spacing=8, margin_top=8, margin_bottom=8,
                          margin_start=12, margin_end=12, halign=Gtk.Align.END)
        for label, handler, css in (("Buka di editor", self._on_open_selected, "suggested-action"),
                                    ("Salin", self._on_copy_selected, None),
                                    ("Hapus", self._on_delete_selected, "destructive-action")):
            button = Gtk.Button(label=label)
            if css:
                button.add_css_class(css)
            button.connect("clicked", handler)
            actions.append(button)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.stack)
        view.add_bottom_bar(actions)
        self.set_content(view)

        self._load()

    # -------------------------------------------------------------- memuat
    def _load(self):
        directory = config.save_dir
        files = [p for p in directory.iterdir()
                 if p.is_file() and p.suffix.lower() in EXTENSIONS] if directory.exists() else []
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        self.paths = files[:LIMIT]
        self.stack.set_visible_child_name("grid" if self.paths else "empty")
        for path in self.paths:
            GLib.idle_add(self._add_thumb, path)

    def _add_thumb(self, path):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("card")
        box.set_size_request(160, 150)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 150, 100, True)
            picture = Gtk.Picture.new_for_pixbuf(pixbuf)
        except GLib.Error:
            picture = Gtk.Image.new_from_icon_name("image-missing-symbolic")
        picture.set_size_request(150, 100)
        picture.set_margin_top(8)
        box.append(picture)
        label = Gtk.Label(label=path.name, ellipsize=3, max_width_chars=20)
        label.add_css_class("caption")
        label.set_margin_bottom(8)
        box.append(label)
        box.set_tooltip_text(f"{path.name}\n{path.stat().st_size // 1024} KB")
        child = Gtk.FlowBoxChild()
        child.set_child(box)
        child._path = path
        self.flow.append(child)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------- tindakan
    def _selected_path(self):
        children = self.flow.get_selected_children()
        return getattr(children[0], "_path", None) if children else None

    def _on_activated(self, _flow, child):
        self._open(getattr(child, "_path", None))

    def _on_open_selected(self, _button):
        self._open(self._selected_path())

    def _open(self, path):
        if path is None:
            return
        self.app.open_image_file(str(path))
        self.close()

    def _on_copy_selected(self, _button):
        path = self._selected_path()
        if path is None:
            return
        from .clipboard import copy_png
        from PIL import Image
        import io
        buffer = io.BytesIO()
        Image.open(path).convert("RGBA").save(buffer, "PNG")
        copy_png(self.get_display(), buffer.getvalue())

    def _on_delete_selected(self, _button):
        path = self._selected_path()
        if path is None:
            return
        dialog = Adw.AlertDialog(heading="Hapus screenshot?",
                                 body=f"{path.name} akan dipindahkan ke tempat sampah.")
        dialog.add_response("cancel", "Batal")
        dialog.add_response("delete", "Hapus")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_delete_response, path)
        dialog.present(self)

    def _on_delete_response(self, _dialog, response, path):
        if response != "delete":
            return
        try:
            Gio.File.new_for_path(str(path)).trash(None)
        except GLib.Error:
            try:
                path.unlink()
            except OSError:
                return
        child = self.flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if getattr(child, "_path", None) == path:
                self.flow.remove(child)
            child = nxt

    def _on_open_folder(self, _button):
        try:
            subprocess.Popen(["xdg-open", str(config.save_dir)])
        except OSError:
            pass
