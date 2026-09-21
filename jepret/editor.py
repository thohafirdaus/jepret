"""Jendela editor: toolbar tool, bar properti, kanvas, simpan & salin."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import export
from .canvas import Canvas  # noqa: E402
from .clipboard import copy_png  # noqa: E402
from .config import config  # noqa: E402
from .items import EffectItem, RectItem, EllipseItem, StepItem, TextItem  # noqa: E402

PALETTE = ["#e01b24", "#ff7800", "#f6d32d", "#33d17a", "#3584e4",
           "#9141ac", "#ffffff", "#000000"]

TOOLBAR = [
    ("select", "Pilih & geser", "jepret-select-symbolic", "V"),
    ("arrow", "Panah", "jepret-arrow-symbolic", "A"),
    ("step", "Nomor urut", "jepret-step-symbolic", "N"),
    ("rect", "Kotak", "jepret-rect-symbolic", "R"),
    ("ellipse", "Elips", "jepret-ellipse-symbolic", "E"),
    ("line", "Garis", "jepret-line-symbolic", "L"),
    ("pen", "Pena bebas", "jepret-pen-symbolic", "P"),
    ("highlight", "Stabilo", "jepret-highlight-symbolic", "H"),
    ("text", "Teks", "jepret-text-symbolic", "T"),
    ("effect", "Blur / Pixelate", "jepret-blur-symbolic", "B"),
    ("crop", "Potong", "jepret-crop-symbolic", "C"),
]

CSS = b"""
.jepret-toolbox { padding: 6px; }
.jepret-toolbox button { min-width: 34px; min-height: 34px; margin: 1px; }
.jepret-swatch { min-width: 24px; min-height: 24px; padding: 0; border-radius: 6px; }
.jepret-canvas-bg { background-color: @view_bg_color; }
.jepret-props { padding: 6px 10px; }
"""


class EditorWindow(Adw.ApplicationWindow):
    def __init__(self, app, document, source_label=None):
        super().__init__(application=app, title="Jepret")
        self.app = app
        self.doc = document
        self.set_default_size(1150, 780)

        self.toast = Adw.ToastOverlay()
        self.canvas = Canvas(document, config)
        self.canvas.on_changed = self._on_doc_changed
        self.canvas.on_selection_changed = self._on_selection_changed
        self.canvas.on_zoom_changed = self._on_zoom_changed
        self.canvas.on_status = self.notify_user
        self.canvas.history.on_change = self._update_actions

        view = Adw.ToolbarView()
        view.add_top_bar(self._build_header())
        view.set_content(self._build_body())
        view.add_bottom_bar(self._build_props())
        self.toast.set_child(view)
        self.set_content(self.toast)

        self._install_actions()
        self._install_keys()
        # crop/select bukan tool gambar; mulai dengan panah agar langsung pakai
        last = config["last_tool"]
        self.set_tool(last if last in {t[0] for t in TOOLBAR} - {"crop", "select"} else "arrow")
        self.source_label = source_label
        self._update_title()
        self.connect("close-request", self._on_close)
        GLib.idle_add(self._fit_once)

    # ------------------------------------------------------------- bangun UI
    def _build_header(self):
        header = Adw.HeaderBar()

        capture = Gtk.MenuButton(icon_name="applets-screenshooter-symbolic",
                                 tooltip_text="Tangkap baru")
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Area…", "win.capture-area")
        section.append("Jendela…", "win.capture-window")
        section.append("Layar penuh", "win.capture-full")
        menu.append_section(None, section)
        delayed = Gio.Menu()
        delayed.append("Area setelah 3 detik", "win.capture-area-3")
        delayed.append("Layar penuh setelah 5 detik", "win.capture-full-5")
        menu.append_section("Dengan jeda", delayed)
        capture.set_menu_model(menu)
        header.pack_start(capture)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        nav.add_css_class("linked")
        self.btn_undo = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Urungkan (Ctrl+Z)")
        self.btn_undo.set_action_name("win.undo")
        self.btn_redo = Gtk.Button(icon_name="edit-redo-symbolic", tooltip_text="Ulangi (Ctrl+Shift+Z)")
        self.btn_redo.set_action_name("win.redo")
        nav.append(self.btn_undo)
        nav.append(self.btn_redo)
        header.pack_start(nav)

        self.title_widget = Adw.WindowTitle(title="Jepret", subtitle="")
        header.set_title_widget(self.title_widget)

        save = Gtk.Button(label="Simpan")
        save.add_css_class("suggested-action")
        save.set_action_name("win.save")
        save.set_tooltip_text("Simpan ke folder Screenshots (Ctrl+S)")
        header.pack_end(save)

        copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Salin ke clipboard (Ctrl+C)")
        copy.set_action_name("win.copy")
        header.pack_end(copy)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Menu")
        app_menu = Gio.Menu()
        files = Gio.Menu()
        files.append("Simpan sebagai…", "win.save-as")
        files.append("Buka gambar…", "win.open")
        files.append("Riwayat screenshot", "win.history")
        app_menu.append_section(None, files)
        misc = Gio.Menu()
        misc.append("Preferensi…", "win.preferences")
        misc.append("Pintasan keyboard", "win.shortcuts")
        misc.append("Tentang Jepret", "win.about")
        app_menu.append_section(None, misc)
        menu_btn.set_menu_model(app_menu)
        header.pack_end(menu_btn)
        return header

    def _build_body(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self.toolbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.toolbox.add_css_class("jepret-toolbox")
        self.toolbox.add_css_class("toolbar")
        self.tool_buttons = {}
        first = None
        for name, label, icon, key in TOOLBAR:
            btn = Gtk.ToggleButton(icon_name=icon)
            btn.set_tooltip_text(f"{label} ({key})")
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.connect("toggled", self._on_tool_toggled, name)
            self.tool_buttons[name] = btn
            self.toolbox.append(btn)

        self.toolbox.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Hapus objek terpilih (Del)")
        delete.set_action_name("win.delete")
        self.toolbox.append(delete)

        box.append(self.toolbox)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self.scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scroller.add_css_class("jepret-canvas-bg")
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER,
                         valign=Gtk.Align.CENTER, margin_top=12, margin_bottom=12,
                         margin_start=12, margin_end=12)
        holder.append(self.canvas)
        self.scroller.set_child(holder)

        zoom_ctrl = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        zoom_ctrl.connect("scroll", self._on_scroll)
        self.scroller.add_controller(zoom_ctrl)

        box.append(self.scroller)
        return box

    def _build_props(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("jepret-props")
        bar.add_css_class("toolbar")

        self.color_box = Gtk.Box(spacing=3)
        for color in PALETTE:
            btn = Gtk.Button()
            btn.add_css_class("jepret-swatch")
            swatch = Gtk.DrawingArea()
            swatch.set_content_width(22)
            swatch.set_content_height(22)
            swatch.set_draw_func(self._draw_swatch, color)
            btn.set_child(swatch)
            btn.set_tooltip_text(color)
            btn.connect("clicked", lambda _b, c=color: self._set_color(c))
            self.color_box.append(btn)

        self.custom_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        self.custom_color.connect("notify::rgba", self._on_custom_color)
        self.color_box.append(self.custom_color)
        bar.append(self.color_box)

        self.width_box = Gtk.Box(spacing=6)
        self.width_box.append(Gtk.Label(label="Tebal"))
        self.width_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 24, 1)
        self.width_scale.set_size_request(120, -1)
        self.width_scale.set_value(config["stroke_width"])
        self.width_scale.set_draw_value(True)
        self.width_scale.connect("value-changed",
                                 lambda s: self.canvas.apply_property(width=s.get_value()))
        self.width_box.append(self.width_scale)
        bar.append(self.width_box)

        self.font_box = Gtk.Box(spacing=6)
        self.font_box.append(Gtk.Label(label="Ukuran"))
        self.font_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 96, 1)
        self.font_scale.set_size_request(120, -1)
        self.font_scale.set_value(config["font_size"])
        self.font_scale.set_draw_value(True)
        self.font_scale.connect("value-changed",
                                lambda s: self.canvas.apply_property(font_size=s.get_value()))
        self.font_box.append(self.font_scale)
        bar.append(self.font_box)

        self.fill_toggle = Gtk.ToggleButton(label="Isi penuh")
        self.fill_toggle.connect("toggled",
                                 lambda b: self.canvas.apply_property(filled=b.get_active()))
        bar.append(self.fill_toggle)

        self.effect_box = Gtk.Box(spacing=6)
        self.effect_kind = Gtk.DropDown.new_from_strings(["Pixelate", "Blur"])
        self.effect_kind.connect("notify::selected", self._on_effect_kind)
        self.effect_box.append(self.effect_kind)
        self.effect_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 4, 40, 1)
        self.effect_scale.set_size_request(110, -1)
        self.effect_scale.set_value(14)
        self.effect_scale.set_draw_value(True)
        self.effect_scale.connect(
            "value-changed", lambda s: self.canvas.apply_property(effect_strength=int(s.get_value())))
        self.effect_box.append(self.effect_scale)
        bar.append(self.effect_box)

        self.badge_box = Gtk.Box(spacing=6)
        self.badge_kind = Gtk.DropDown.new_from_strings(["Lingkaran", "Kotak"])
        self.badge_kind.connect("notify::selected", self._on_badge_kind)
        self.badge_box.append(self.badge_kind)
        reset = Gtk.Button(label="Reset nomor")
        reset.set_tooltip_text("Mulai penomoran dari 1 lagi")
        reset.connect("clicked", self._on_reset_numbers)
        self.badge_box.append(reset)
        bar.append(self.badge_box)

        self.crop_box = Gtk.Box(spacing=6)
        apply_btn = Gtk.Button(label="Potong sekarang")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", lambda _b: self.canvas.apply_crop())
        cancel_btn = Gtk.Button(label="Batal")
        cancel_btn.connect("clicked", lambda _b: self.canvas.cancel_crop())
        self.crop_box.append(apply_btn)
        self.crop_box.append(cancel_btn)
        bar.append(self.crop_box)

        bar.append(Gtk.Box(hexpand=True))

        zoom = Gtk.Box(spacing=0)
        zoom.add_css_class("linked")
        out = Gtk.Button(icon_name="zoom-out-symbolic", tooltip_text="Perkecil (Ctrl+-)")
        out.set_action_name("win.zoom-out")
        self.zoom_label = Gtk.Button(label="100%", tooltip_text="Ukuran asli")
        self.zoom_label.set_action_name("win.zoom-reset")
        in_btn = Gtk.Button(icon_name="zoom-in-symbolic", tooltip_text="Perbesar (Ctrl++)")
        in_btn.set_action_name("win.zoom-in")
        fit = Gtk.Button(icon_name="zoom-fit-best-symbolic", tooltip_text="Sesuaikan jendela")
        fit.set_action_name("win.zoom-fit")
        for widget in (out, self.zoom_label, in_btn, fit):
            zoom.append(widget)
        bar.append(zoom)
        return bar

    @staticmethod
    def _draw_swatch(_area, cr, width, height, color):
        from .items import hex_to_rgb
        r, g, b = hex_to_rgb(color)
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, width - 1, height - 1)
        cr.stroke()

    # --------------------------------------------------------------- actions
    def _install_actions(self):
        specs = [
            ("save", self.on_save), ("save-as", self.on_save_as), ("copy", self.on_copy),
            ("undo", lambda *_: self.canvas.undo()), ("redo", lambda *_: self.canvas.redo()),
            ("delete", lambda *_: self.canvas.delete_selected()),
            ("duplicate", lambda *_: self.canvas.duplicate_selected()),
            ("zoom-in", lambda *_: self.canvas.set_zoom(self.canvas.zoom * 1.25)),
            ("zoom-out", lambda *_: self.canvas.set_zoom(self.canvas.zoom / 1.25)),
            ("zoom-reset", lambda *_: self.canvas.set_zoom(1.0)),
            ("zoom-fit", lambda *_: self._fit_once()),
            ("capture-area", lambda *_: self.app.start_capture("area", parent=self)),
            ("capture-window", lambda *_: self.app.start_capture("window", parent=self)),
            ("capture-full", lambda *_: self.app.start_capture("full", parent=self)),
            ("capture-area-3", lambda *_: self.app.start_capture("area", delay=3, parent=self)),
            ("capture-full-5", lambda *_: self.app.start_capture("full", delay=5, parent=self)),
            ("open", self.on_open), ("history", self.on_history),
            ("preferences", self.on_preferences),
            ("about", self.on_about), ("shortcuts", self.on_shortcuts),
        ]
        for name, handler in specs:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)
        self._update_actions()

    def _install_keys(self):
        keys = Gtk.EventControllerKey.new()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        app = self.get_application()
        accels = {
            "win.save": ["<Control>s"], "win.save-as": ["<Control><Shift>s"],
            "win.copy": ["<Control>c"], "win.undo": ["<Control>z"],
            "win.redo": ["<Control><Shift>z", "<Control>y"],
            "win.duplicate": ["<Control>d"], "win.open": ["<Control>o"],
            "win.zoom-in": ["<Control>plus", "<Control>equal"],
            "win.zoom-out": ["<Control>minus"], "win.zoom-reset": ["<Control>0"],
            "win.zoom-fit": ["<Control>9"], "win.history": ["<Control>h"],
            "win.preferences": ["<Control>comma"],
            "win.capture-area": ["<Control>n"], "win.capture-window": ["<Control><Shift>n"],
        }
        for action, binding in accels.items():
            app.set_accels_for_action(action, binding)

    def _on_key(self, controller, keyval, keycode, state):
        event = controller.get_current_event()
        if self.canvas.editing_text is not None:
            return self.canvas.handle_key(keyval, keycode, state, event)
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        shortcuts = {Gdk.KEY_v: "select", Gdk.KEY_a: "arrow", Gdk.KEY_n: "step",
                     Gdk.KEY_r: "rect", Gdk.KEY_e: "ellipse", Gdk.KEY_l: "line",
                     Gdk.KEY_p: "pen", Gdk.KEY_h: "highlight", Gdk.KEY_t: "text",
                     Gdk.KEY_b: "effect", Gdk.KEY_c: "crop"}
        tool = shortcuts.get(keyval)
        if tool:
            self.set_tool(tool)
            return True
        return self.canvas.handle_key(keyval, keycode, state, event)

    def _on_scroll(self, controller, _dx, dy):
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.canvas.set_zoom(self.canvas.zoom * (0.9 if dy > 0 else 1.1))
            return True
        return False

    # -------------------------------------------------------------- tool/props
    def set_tool(self, name):
        button = self.tool_buttons.get(name)
        if button and not button.get_active():
            button.set_active(True)
        else:
            self._apply_tool(name)

    def _on_tool_toggled(self, button, name):
        if button.get_active():
            self._apply_tool(name)

    def _apply_tool(self, name):
        self.canvas.set_tool(name)
        show = {
            "color": name in ("arrow", "step", "rect", "ellipse", "line", "pen", "highlight", "text"),
            "width": name in ("arrow", "rect", "ellipse", "line", "pen"),
            "font": name in ("text", "step"),
            "fill": name in ("rect", "ellipse"),
            "effect": name == "effect",
            "badge": name == "step",
            "crop": name == "crop",
        }
        self.color_box.set_visible(show["color"])
        self.width_box.set_visible(show["width"])
        self.font_box.set_visible(show["font"])
        self.fill_toggle.set_visible(show["fill"])
        self.effect_box.set_visible(show["effect"])
        self.badge_box.set_visible(show["badge"])
        self.crop_box.set_visible(show["crop"])
        if name == "crop":
            self.notify_user("Atur kotak potong, lalu tekan Enter")

    def _set_color(self, color):
        self.canvas.apply_property(color=color)
        config["color"] = color

    def _on_custom_color(self, button, _param):
        rgba = button.get_rgba()
        color = "#%02x%02x%02x" % (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))
        self._set_color(color)

    def _on_effect_kind(self, dropdown, _param):
        kind = "pixelate" if dropdown.get_selected() == 0 else "blur"
        self.canvas.apply_property(effect_kind=kind)

    def _on_badge_kind(self, dropdown, _param):
        style = "circle" if dropdown.get_selected() == 0 else "square"
        self.canvas.apply_property(badge_style=style)
        config["badge_style"] = style

    def _on_reset_numbers(self, _btn):
        self.canvas.begin_change()
        for item in self.doc.items:
            if isinstance(item, StepItem):
                item.number = 0
        self.doc.items = [i for i in self.doc.items if not (isinstance(i, StepItem) and i.number == 0)]
        self.canvas.commit_change("Penomoran direset")

    # ------------------------------------------------------------- callbacks
    def _on_doc_changed(self):
        self._update_title()
        self._update_actions()

    def _on_selection_changed(self, item):
        if item is None:
            return
        if hasattr(item, "color"):
            self.custom_color.set_rgba(self._rgba(item.color))
        if hasattr(item, "width"):
            self.width_scale.set_value(item.width)
        if isinstance(item, (TextItem, StepItem)):
            self.font_scale.set_value(item.font_size)
        if isinstance(item, (RectItem, EllipseItem)):
            self.fill_toggle.set_active(item.filled)
        if isinstance(item, EffectItem):
            self.effect_kind.set_selected(0 if item.effect == "pixelate" else 1)
            self.effect_scale.set_value(item.strength)

    @staticmethod
    def _rgba(color):
        rgba = Gdk.RGBA()
        rgba.parse(color)
        return rgba

    def _on_zoom_changed(self, zoom):
        self.zoom_label.set_label(f"{int(round(zoom * 100))}%")

    def _update_actions(self):
        self.lookup_action("undo").set_enabled(self.canvas.history.can_undo)
        self.lookup_action("redo").set_enabled(self.canvas.history.can_redo)

    def _update_title(self):
        name = Path(self.doc.saved_path).name if self.doc.saved_path else "Screenshot belum disimpan"
        mark = " •" if self.doc.dirty else ""
        self.title_widget.set_title(f"{name}{mark}")
        self.title_widget.set_subtitle(
            f"{self.doc.width} × {self.doc.height} px · {len(self.doc.items)} anotasi")

    def _fit_once(self):
        self.canvas.zoom_to_fit(self.scroller.get_width() or 1100,
                                self.scroller.get_height() or 640)
        return GLib.SOURCE_REMOVE

    def notify_user(self, message):
        self.toast.add_toast(Adw.Toast.new(message))

    # ------------------------------------------------------------- simpan/salin
    def on_save(self, *_args):
        self.canvas.finish_text_edit(commit=True)
        try:
            if self.doc.saved_path:
                path = export.save_image(self.doc.to_pil(), self.doc.saved_path)
            else:
                path = export.quick_save(self.doc.to_pil())
        except OSError as exc:
            self.notify_user(f"Gagal menyimpan: {exc}")
            return
        self.doc.saved_path = str(path)
        self.doc.dirty = False
        self._update_title()
        self.notify_user(f"Tersimpan: {path}")

    def on_save_as(self, *_args):
        self.canvas.finish_text_edit(commit=True)
        dialog = Gtk.FileDialog()
        dialog.set_title("Simpan screenshot")
        dialog.set_initial_name(Path(self.doc.saved_path).name if self.doc.saved_path
                                else export.default_name())
        try:
            dialog.set_initial_folder(Gio.File.new_for_path(str(config.save_dir)))
        except GLib.Error:
            pass
        filters = Gio.ListStore.new(Gtk.FileFilter)
        for label, pattern, mime in (("PNG", "*.png", "image/png"),
                                     ("JPEG", "*.jpg", "image/jpeg"),
                                     ("WebP", "*.webp", "image/webp")):
            f = Gtk.FileFilter()
            f.set_name(label)
            f.add_pattern(pattern)
            f.add_mime_type(mime)
            filters.append(f)
        dialog.set_filters(filters)
        dialog.save(self, None, self._on_save_as_done)

    def _on_save_as_done(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        if file is None:
            return
        try:
            path = export.save_image(self.doc.to_pil(), file.get_path())
        except (OSError, KeyError) as exc:
            self.notify_user(f"Gagal menyimpan: {exc}")
            return
        self.doc.saved_path = str(path)
        self.doc.dirty = False
        self._update_title()
        self.notify_user(f"Tersimpan: {path}")

    def on_copy(self, *_args):
        self.canvas.finish_text_edit(commit=True)
        message = copy_png(self.get_display(), self.doc.to_png_bytes())
        self.notify_user(message)

    # --------------------------------------------------------------- dialogs
    def on_open(self, *_args):
        dialog = Gtk.FileDialog()
        dialog.set_title("Buka gambar")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name("Gambar")
        for mime in ("image/png", "image/jpeg", "image/webp", "image/bmp"):
            f.add_mime_type(mime)
        filters.append(f)
        dialog.set_filters(filters)
        dialog.open(self, None, self._on_open_done)

    def _on_open_done(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file and file.get_path():
            self.app.open_image_file(file.get_path())

    def on_history(self, *_args):
        from .gallery import GalleryWindow
        GalleryWindow(self.app, self).present()

    def on_preferences(self, *_args):
        from .prefs import PreferencesDialog
        PreferencesDialog(self.app).present(self)

    def on_shortcuts(self, *_args):
        text = (
            "<b>Tangkap</b>\n"
            "Ctrl+N area · Ctrl+Shift+N jendela\n\n"
            "<b>Tool</b>\n"
            "V pilih · A panah · N nomor urut · R kotak · E elips\n"
            "L garis · P pena · H stabilo · T teks · B blur · C potong\n\n"
            "<b>Objek</b>\n"
            "Del hapus · Ctrl+D duplikat · [ / ] urutan tumpuk\n"
            "Panah geser 1px · Shift+panah 10px · Shift saat menggambar = lurus/persegi\n\n"
            "<b>Berkas</b>\n"
            "Ctrl+S simpan · Ctrl+Shift+S simpan sebagai · Ctrl+C salin\n"
            "Ctrl+Z urungkan · Ctrl+Shift+Z ulangi · Ctrl+H riwayat\n"
            "Ctrl+, preferensi (termasuk pintasan global)\n\n"
            "<b>Tampilan</b>\n"
            "Ctrl+scroll atau Ctrl+± zoom · Ctrl+0 100% · Ctrl+9 sesuaikan"
        )
        dialog = Adw.AlertDialog(heading="Pintasan keyboard", body=text, body_use_markup=True)
        dialog.add_response("ok", "Tutup")
        dialog.present(self)

    def on_about(self, *_args):
        from . import APP_NAME, VERSION
        about = Adw.AboutDialog(
            application_name=APP_NAME, version=VERSION,
            developer_name="Dibuat untuk GNOME/Wayland",
            comments="Screenshot area/jendela dengan editor anotasi: panah, nomor urut, "
                     "teks, stabilo, blur/pixelate, crop — lalu simpan atau salin.",
            license_type=Gtk.License.MIT_X11,
        )
        about.present(self)

    def _on_close(self, *_args):
        config["stroke_width"] = self.canvas.width
        config["font_size"] = self.canvas.font_size
        config.save()
        if not self.doc.dirty or not self.doc.items:
            return False
        dialog = Adw.AlertDialog(
            heading="Tutup tanpa menyimpan?",
            body="Anotasi pada screenshot ini belum disimpan.")
        dialog.add_response("cancel", "Batal")
        dialog.add_response("save", "Simpan")
        dialog.add_response("discard", "Buang")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_close_response)
        dialog.present(self)
        return True

    def _on_close_response(self, dialog, response):
        if response == "save":
            self.on_save()
            self.doc.dirty = False
            self.destroy()
        elif response == "discard":
            self.doc.dirty = False
            self.destroy()
