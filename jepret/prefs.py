"""Jendela Preferensi: berkas, tampilan, dan pintasan keyboard global."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import shortcuts  # noqa: E402
from .config import config  # noqa: E402

FORMATS = ["PNG", "JPEG", "WebP"]
FORMAT_KEYS = ["png", "jpg", "webp"]

MODIFIER_KEYVALS = {
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_ISO_Level3_Shift, Gdk.KEY_Caps_Lock,
}


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, app):
        super().__init__(title="Preferensi")
        self.app = app
        self.pages = {"files": self._files_page(), "shortcuts": self._shortcut_page()}
        for page in self.pages.values():
            self.add(page)

    # ------------------------------------------------------------- halaman
    def _files_page(self):
        page = Adw.PreferencesPage(title="Berkas", icon_name="document-save-symbolic")

        group = Adw.PreferencesGroup(title="Penyimpanan")
        self.folder_row = Adw.ActionRow(title="Folder simpan", subtitle=str(config.save_dir))
        choose = Gtk.Button(label="Ubah…", valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._on_choose_folder)
        self.folder_row.add_suffix(choose)
        group.add(self.folder_row)

        self.name_row = Adw.EntryRow(title="Pola nama berkas")
        self.name_row.set_text(config["filename_pattern"])
        self.name_row.connect("changed", self._on_pattern)
        group.add(self.name_row)

        self.format_row = Adw.ComboRow(title="Format bawaan",
                                       model=Gtk.StringList.new(FORMATS))
        self.format_row.set_selected(FORMAT_KEYS.index(config["default_format"])
                                     if config["default_format"] in FORMAT_KEYS else 0)
        self.format_row.connect("notify::selected", self._on_format)
        group.add(self.format_row)

        self.quality_row = Adw.SpinRow.new_with_range(50, 100, 1)
        self.quality_row.set_title("Kualitas JPEG / WebP")
        self.quality_row.set_value(config["jpeg_quality"])
        self.quality_row.connect("notify::value", self._on_quality)
        group.add(self.quality_row)
        page.add(group)

        capture_group = Adw.PreferencesGroup(title="Tangkapan")
        self.cursor_row = Adw.SwitchRow(title="Sertakan kursor mouse")
        self.cursor_row.set_active(bool(config["include_cursor"]))
        self.cursor_row.connect("notify::active", self._on_cursor)
        capture_group.add(self.cursor_row)

        self.badge_row = Adw.ComboRow(title="Bentuk badge nomor urut",
                                      model=Gtk.StringList.new(["Lingkaran", "Kotak"]))
        self.badge_row.set_selected(0 if config["badge_style"] == "circle" else 1)
        self.badge_row.connect("notify::selected", self._on_badge)
        capture_group.add(self.badge_row)
        page.add(capture_group)
        return page

    def _shortcut_page(self):
        page = Adw.PreferencesPage(title="Pintasan", icon_name="preferences-desktop-keyboard-symbolic"
                                   if Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                                   .has_icon("preferences-desktop-keyboard-symbolic") else "input-mouse-symbolic")

        group = Adw.PreferencesGroup(
            title="Pintasan keyboard global",
            description="Berlaku di seluruh desktop, juga saat Jepret belum berjalan.")
        self.shortcut_rows = {}

        if not shortcuts.available():
            group.add(Adw.ActionRow(
                title="Tidak tersedia",
                subtitle="Pengaturan pintasan GNOME tidak ditemukan di sistem ini."))
            page.add(group)
            return page

        for action_id, title, args in shortcuts.ACTIONS:
            row = Adw.ActionRow(title=title, subtitle=shortcuts.launcher_command(args))
            button = Gtk.Button(valign=Gtk.Align.CENTER)
            button.connect("clicked", self._on_record, action_id, title, args)
            clear = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
                               tooltip_text="Hapus pintasan")
            clear.add_css_class("flat")
            clear.connect("clicked", self._on_clear, action_id)
            row.add_suffix(button)
            row.add_suffix(clear)
            group.add(row)
            self.shortcut_rows[action_id] = (row, button, title, args)
            self._refresh_row(action_id)
        page.add(group)

        gnome_group = Adw.PreferencesGroup(
            title="Pintasan bawaan GNOME",
            description="Tombol Print Screen biasanya dipakai alat screenshot GNOME. "
                        "Jepret akan menawarkan pengambilalihan bila kombinasinya bentrok.")
        self.restore_row = Adw.ActionRow(
            title="Kembalikan pintasan screenshot GNOME",
            subtitle="Mengembalikan Print Screen dan kawan-kawan ke setelan pabrik")
        restore = Gtk.Button(label="Kembalikan", valign=Gtk.Align.CENTER)
        restore.connect("clicked", self._on_restore_gnome)
        self.restore_row.add_suffix(restore)
        gnome_group.add(self.restore_row)
        page.add(gnome_group)
        self._refresh_restore_row()
        return page

    # -------------------------------------------------------------- berkas
    def _on_choose_folder(self, _button):
        dialog = Gtk.FileDialog(title="Pilih folder simpan")
        try:
            dialog.set_initial_folder(Gio.File.new_for_path(str(config.save_dir)))
        except GLib.Error:
            pass
        dialog.select_folder(self._window(), None, self._on_folder_done)

    def _on_folder_done(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder and folder.get_path():
            config["save_dir"] = folder.get_path()
            config.save()
            self.folder_row.set_subtitle(str(config.save_dir))

    def _on_pattern(self, row):
        text = row.get_text().strip()
        if text:
            config["filename_pattern"] = text
            config.save()

    def _on_format(self, row, _param):
        config["default_format"] = FORMAT_KEYS[row.get_selected()]
        config.save()

    def _on_quality(self, row, _param):
        config["jpeg_quality"] = int(row.get_value())
        config.save()

    def _on_cursor(self, row, _param):
        config["include_cursor"] = row.get_active()
        config.save()

    def _on_badge(self, row, _param):
        config["badge_style"] = "circle" if row.get_selected() == 0 else "square"
        config.save()

    # ------------------------------------------------------------ pintasan
    def _window(self):
        return self.app.get_active_window()

    def _refresh_row(self, action_id):
        row, button, _title, _args = self.shortcut_rows[action_id]
        accel = shortcuts.get_binding(action_id)
        if accel:
            ok, keyval, mods = Gtk.accelerator_parse(accel)
            button.set_label(Gtk.accelerator_get_label(keyval, mods) if ok else accel)
            button.remove_css_class("dim-label")
        else:
            button.set_label("Belum diatur")
            button.add_css_class("dim-label")

    def _refresh_restore_row(self):
        self.restore_row.set_sensitive(shortcuts.gnome_defaults_modified())

    def _on_clear(self, _button, action_id):
        shortcuts.set_binding(action_id, "", "", "")
        self._refresh_row(action_id)

    def _on_record(self, _button, action_id, title, args):
        dialog = Adw.AlertDialog(
            heading=f"Pintasan untuk “{title}”",
            body="Tekan kombinasi tombol yang diinginkan.\n"
                 "Backspace menghapus pintasan, Esc membatalkan.")
        dialog.add_response("cancel", "Batal")
        dialog.set_close_response("cancel")

        controller = Gtk.EventControllerKey.new()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

        def on_key(_ctrl, keyval, _code, state):
            mods = state & Gtk.accelerator_get_default_mod_mask()
            if keyval in MODIFIER_KEYVALS:
                return True
            if keyval == Gdk.KEY_Escape and not mods:
                dialog.close()
                return True
            if keyval == Gdk.KEY_BackSpace and not mods:
                dialog.close()
                shortcuts.set_binding(action_id, "", "", "")
                self._refresh_row(action_id)
                return True
            if not Gtk.accelerator_valid(keyval, mods):
                return True
            accel = Gtk.accelerator_name(keyval, mods)
            dialog.close()
            self._apply_accel(action_id, title, args, accel)
            return True

        controller.connect("key-pressed", on_key)
        dialog.add_controller(controller)
        dialog.present(self)

    def _apply_accel(self, action_id, title, args, accel):
        gnome_clashes = shortcuts.conflicting_gnome_keys(accel)
        custom_clashes = shortcuts.custom_binding_conflicts(accel, exclude_action=action_id)
        if not gnome_clashes and not custom_clashes:
            shortcuts.set_binding(action_id, accel, title, args)
            self._refresh_row(action_id)
            return

        ok, keyval, mods = Gtk.accelerator_parse(accel)
        label = Gtk.accelerator_get_label(keyval, mods) if ok else accel
        if custom_clashes:
            pemakai = ", ".join(name for _path, name in custom_clashes)
            body = (f"{label} sedang dipakai pintasan lain: {pemakai}. "
                    "Ambil alih untuk Jepret?")
        else:
            body = (f"{label} saat ini dipakai alat screenshot bawaan GNOME. "
                    "Ambil alih untuk Jepret?")
        confirm = Adw.AlertDialog(heading="Kombinasi sudah dipakai", body=body)
        confirm.add_response("cancel", "Batal")
        confirm.add_response("take", "Ambil alih")
        confirm.set_response_appearance("take", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_dialog, response):
            if response != "take":
                return
            for path, _name in custom_clashes:
                shortcuts.release_custom_binding(path)
            shortcuts.release_gnome_keys(accel)
            shortcuts.set_binding(action_id, accel, title, args)
            for other in self.shortcut_rows:
                self._refresh_row(other)
            self._refresh_restore_row()

        confirm.connect("response", on_response)
        confirm.present(self)

    def _on_restore_gnome(self, _button):
        shortcuts.restore_gnome_defaults()
        self._refresh_restore_row()
