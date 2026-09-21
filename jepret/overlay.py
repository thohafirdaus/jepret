"""Overlay pemilih area di atas screenshot beku (fullscreen tiap monitor)."""

import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .effects import pil_to_surface  # noqa: E402

HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
BTN_R = 22.0

# bentuk kursor per handle, supaya arah perubahan ukuran terbaca jelas
HANDLE_CURSORS = {
    "nw": "nw-resize", "n": "n-resize", "ne": "ne-resize", "e": "e-resize",
    "se": "se-resize", "s": "s-resize", "sw": "sw-resize", "w": "w-resize",
}


class Selection:
    """Status seleksi bersama antar monitor (koordinat piksel gambar)."""

    def __init__(self, width, height):
        self.image_w, self.image_h = width, height
        self.rect = None  # [x, y, w, h]

    def set_from_points(self, x1, y1, x2, y2):
        self.rect = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]

    def clamp(self):
        if not self.rect:
            return
        x, y, w, h = self.rect
        w = max(1.0, min(w, self.image_w))
        h = max(1.0, min(h, self.image_h))
        x = max(0.0, min(x, self.image_w - w))
        y = max(0.0, min(y, self.image_h - h))
        self.rect = [x, y, w, h]

    def handles(self):
        if not self.rect:
            return {}
        x, y, w, h = self.rect
        return {"nw": (x, y), "n": (x + w / 2, y), "ne": (x + w, y),
                "e": (x + w, y + h / 2), "se": (x + w, y + h),
                "s": (x + w / 2, y + h), "sw": (x, y + h), "w": (x, y + h / 2)}


class AreaSelector:
    def __init__(self, app, image, on_done, on_cancel=None):
        self.app = app
        self.image = image
        self.surface = pil_to_surface(image)
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.selection = Selection(image.width, image.height)
        self.windows = []
        self._finished = False

        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        geos = [monitors.get_item(i).get_geometry() for i in range(monitors.get_n_items())]
        ox = min(g.x for g in geos)
        oy = min(g.y for g in geos)
        total_w = max(g.x + g.width for g in geos) - ox
        self.ratio = image.width / total_w if total_w else 1.0
        self.origin = (ox, oy)

        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            self.windows.append(_OverlayWindow(self, monitor))

    def present(self):
        for win in self.windows:
            win.present()

    def redraw(self):
        for win in self.windows:
            win.area.queue_draw()

    def finish(self):
        if self._finished:
            return
        self._finished = True
        rect = self.selection.rect
        self._close()
        if rect and rect[2] >= 2 and rect[3] >= 2:
            self.on_done(tuple(rect))
        elif self.on_cancel:
            self.on_cancel()

    def cancel(self):
        if self._finished:
            return
        self._finished = True
        self._close()
        if self.on_cancel:
            self.on_cancel()

    def select_all(self):
        self.selection.rect = [0.0, 0.0, float(self.image.width), float(self.image.height)]
        self.redraw()

    def _close(self):
        for win in self.windows:
            win.destroy()
        self.windows = []


class _OverlayWindow(Gtk.Window):
    def __init__(self, selector, monitor):
        super().__init__(application=selector.app)
        self.selector = selector
        self.monitor = monitor
        geo = monitor.get_geometry()
        ox, oy = selector.origin
        ratio = selector.ratio
        # offset region gambar milik monitor ini (piksel gambar)
        self.img_off = ((geo.x - ox) * ratio, (geo.y - oy) * ratio)

        self.set_decorated(False)
        self.set_deletable(False)
        self.add_css_class("jepret-overlay")
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)
        self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))
        self.fullscreen_on_monitor(monitor)

        self._drag = None
        self._pointer = None
        self._cursor_name = "crosshair"

        click = Gtk.GestureClick.new()
        click.set_button(0)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        self.area.add_controller(click)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.area.add_controller(motion)

        keys = Gtk.EventControllerKey.new()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    # -------------------------------------------------- konversi koordinat
    def to_image(self, wx, wy):
        r = self.selector.ratio
        return self.img_off[0] + wx * r, self.img_off[1] + wy * r

    def to_widget(self, ix, iy):
        r = self.selector.ratio
        return (ix - self.img_off[0]) / r, (iy - self.img_off[1]) / r

    # ---------------------------------------------------------------- draw
    def _draw(self, _area, cr, width, height):
        selector = self.selector
        r = selector.ratio
        cr.save()
        cr.scale(1 / r, 1 / r)
        cr.set_source_surface(selector.surface, -self.img_off[0], -self.img_off[1])
        cr.paint()
        cr.restore()

        rect = selector.selection.rect
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.rectangle(0, 0, width, height)
        if rect:
            x, y = self.to_widget(rect[0], rect[1])
            cr.rectangle(x, y, rect[2] / r, rect[3] / r)
            cr.set_fill_rule(cairo.FillRule.EVEN_ODD)
        cr.fill()
        cr.set_fill_rule(cairo.FillRule.WINDING)

        if rect:
            self._draw_selection(cr, rect, width, height)
        else:
            self._draw_hint(cr, width, height)
        if self._pointer and (not rect or self._drag):
            self._draw_loupe(cr, width, height)

    def _draw_selection(self, cr, rect, width, height):
        r = self.selector.ratio
        x, y = self.to_widget(rect[0], rect[1])
        w, h = rect[2] / r, rect[3] / r
        cr.set_source_rgba(0.35, 0.65, 1.0, 1.0)
        cr.set_line_width(2.0)
        cr.rectangle(x, y, w, h)
        cr.stroke()
        # garis bantu sepertiga
        cr.set_source_rgba(1, 1, 1, 0.18)
        cr.set_line_width(1.0)
        for i in (1, 2):
            cr.move_to(x + w * i / 3, y)
            cr.line_to(x + w * i / 3, y + h)
            cr.move_to(x, y + h * i / 3)
            cr.line_to(x + w, y + h * i / 3)
        cr.stroke()

        for _name, (hx, hy) in self.selector.selection.handles().items():
            px, py = self.to_widget(hx, hy)
            cr.arc(px, py, 5.5, 0, 2 * math.pi)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(0.2, 0.5, 1.0)
            cr.set_line_width(2)
            cr.stroke()

        label = f"{int(rect[2])} × {int(rect[3])}"
        cr.select_font_face("Sans")
        cr.set_font_size(14)
        ext = cr.text_extents(label)
        lx, ly = x, y - 12
        if ly < 20:
            ly = y + h + 26
        cr.set_source_rgba(0, 0, 0, 0.75)
        cr.rectangle(lx - 6, ly - ext.height - 6, ext.width + 12, ext.height + 12)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(lx, ly)
        cr.show_text(label)

        self._draw_buttons(cr, x, y, w, h, width, height)

    def button_positions(self, x, y, w, h, width, height):
        cy = y + h + 12 + BTN_R
        if cy + BTN_R > height:
            cy = max(BTN_R + 4, y - 12 - BTN_R)
        cx = min(width - BTN_R - 6, x + w - BTN_R)
        return {"ok": (cx, cy), "cancel": (cx - 2 * BTN_R - 10, cy)}

    def _draw_buttons(self, cr, x, y, w, h, width, height):
        for name, (cx, cy) in self.button_positions(x, y, w, h, width, height).items():
            cr.arc(cx, cy, BTN_R, 0, 2 * math.pi)
            if name == "ok":
                cr.set_source_rgba(0.15, 0.62, 0.35, 0.96)
            else:
                cr.set_source_rgba(0.2, 0.2, 0.22, 0.92)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(3)
            cr.set_line_cap(1)
            if name == "ok":
                cr.move_to(cx - 8, cy)
                cr.line_to(cx - 2, cy + 7)
                cr.line_to(cx + 9, cy - 7)
            else:
                cr.move_to(cx - 7, cy - 7)
                cr.line_to(cx + 7, cy + 7)
                cr.move_to(cx + 7, cy - 7)
                cr.line_to(cx - 7, cy + 7)
            cr.stroke()

    def _draw_hint(self, cr, width, height):
        text = "Seret untuk memilih area  ·  Enter: seluruh layar  ·  Esc: batal"
        cr.select_font_face("Sans")
        cr.set_font_size(16)
        ext = cr.text_extents(text)
        bx = (width - ext.width) / 2
        by = height * 0.12
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(bx - 18, by - ext.height - 14, ext.width + 36, ext.height + 28)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(bx, by)
        cr.show_text(text)

    def _draw_loupe(self, cr, width, height):
        wx, wy = self._pointer
        ix, iy = self.to_image(wx, wy)
        size, zoom = 110.0, 6.0
        lx = wx + 24 if wx + 24 + size < width else wx - 24 - size
        ly = wy + 24 if wy + 24 + size < height else wy - 24 - size
        cr.save()
        cr.rectangle(lx, ly, size, size)
        cr.clip()
        cr.translate(lx + size / 2, ly + size / 2)
        cr.scale(zoom, zoom)
        cr.translate(-ix, -iy)
        cr.set_source_surface(self.selector.surface, 0, 0)
        cr.get_source().set_filter(cairo.Filter.NEAREST)
        cr.paint()
        cr.restore()
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(2)
        cr.rectangle(lx, ly, size, size)
        cr.stroke()
        cr.move_to(lx + size / 2, ly)
        cr.line_to(lx + size / 2, ly + size)
        cr.move_to(lx, ly + size / 2)
        cr.line_to(lx + size, ly + size / 2)
        cr.set_source_rgba(0.35, 0.65, 1.0, 0.9)
        cr.set_line_width(1)
        cr.stroke()
        label = f"{int(ix)}, {int(iy)}"
        cr.select_font_face("Sans")
        cr.set_font_size(12)
        cr.set_source_rgba(0, 0, 0, 0.75)
        ext = cr.text_extents(label)
        cr.rectangle(lx, ly + size, ext.width + 10, 18)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(lx + 5, ly + size + 13)
        cr.show_text(label)

    # -------------------------------------------------------------- kursor
    def _set_cursor(self, name):
        if name != self._cursor_name:
            self._cursor_name = name
            self.set_cursor(Gdk.Cursor.new_from_name(name, None))

    def _cursor_for(self, wx, wy):
        if self._drag is not None:
            kind, handle, _sx, _sy = self._drag
            if kind == "move":
                return "move"
            if kind == "resize":
                return HANDLE_CURSORS.get(handle, "crosshair")
            return "crosshair"
        if self._hit_button(wx, wy):
            return "pointer"
        sel = self.selector.selection
        if sel.rect:
            for name, (hx, hy) in sel.handles().items():
                px, py = self.to_widget(hx, hy)
                if math.hypot(wx - px, wy - py) <= 10:
                    return HANDLE_CURSORS.get(name, "crosshair")
            x, y, w, h = sel.rect
            ix, iy = self.to_image(wx, wy)
            if x <= ix <= x + w and y <= iy <= y + h:
                return "move"
        return "crosshair"

    # -------------------------------------------------------------- events
    def _hit_button(self, wx, wy):
        rect = self.selector.selection.rect
        if not rect:
            return None
        r = self.selector.ratio
        x, y = self.to_widget(rect[0], rect[1])
        w, h = rect[2] / r, rect[3] / r
        width = self.area.get_width()
        height = self.area.get_height()
        for name, (cx, cy) in self.button_positions(x, y, w, h, width, height).items():
            if math.hypot(wx - cx, wy - cy) <= BTN_R:
                return name
        return None

    def _on_pressed(self, gesture, n_press, wx, wy):
        if gesture.get_current_button() == 3:
            self.selector.cancel()
            return
        button = self._hit_button(wx, wy)
        if button == "ok":
            self.selector.finish()
            return
        if button == "cancel":
            self.selector.cancel()
            return

        sel = self.selector.selection
        ix, iy = self.to_image(wx, wy)
        if n_press == 2 and sel.rect:
            self.selector.finish()
            return
        if sel.rect:
            for name, (hx, hy) in sel.handles().items():
                px, py = self.to_widget(hx, hy)
                if math.hypot(wx - px, wy - py) <= 10:
                    self._drag = ("resize", name, ix, iy)
                    return
            x, y, w, h = sel.rect
            if x <= ix <= x + w and y <= iy <= y + h:
                self._drag = ("move", None, ix, iy)
                self._set_cursor("move")
                return
        self._drag = ("new", "se", ix, iy)
        sel.rect = [ix, iy, 0.0, 0.0]
        self.selector.redraw()

    def _on_motion(self, _ctrl, wx, wy):
        self._pointer = (wx, wy)
        self._set_cursor(self._cursor_for(wx, wy))
        if self._drag is None:
            self.area.queue_draw()
            return
        kind, handle, sx, sy = self._drag
        ix, iy = self.to_image(wx, wy)
        sel = self.selector.selection
        if kind == "new":
            sel.set_from_points(sx, sy, ix, iy)
        elif kind == "move":
            sel.rect[0] += ix - sx
            sel.rect[1] += iy - sy
            self._drag = (kind, handle, ix, iy)
        elif kind == "resize":
            x, y, w, h = sel.rect
            left, top, right, bottom = x, y, x + w, y + h
            if "n" in handle:
                top = iy
            if "s" in handle:
                bottom = iy
            if "w" in handle:
                left = ix
            if "e" in handle:
                right = ix
            sel.set_from_points(left, top, right, bottom)
        sel.clamp()
        self.selector.redraw()

    def _on_leave(self, _ctrl):
        self._pointer = None
        self.area.queue_draw()

    def _on_released(self, _gesture, _n, wx, wy):
        self._drag = None
        self._set_cursor(self._cursor_for(wx, wy))
        self.selector.redraw()

    def _on_key(self, _ctrl, keyval, _keycode, state):
        sel = self.selector.selection
        if keyval == Gdk.KEY_Escape:
            self.selector.cancel()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if not sel.rect:
                self.selector.select_all()
            self.selector.finish()
            return True
        if keyval == Gdk.KEY_a and state & Gdk.ModifierType.CONTROL_MASK:
            self.selector.select_all()
            return True
        if sel.rect and keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down):
            step = 10 if state & Gdk.ModifierType.SHIFT_MASK else 1
            dx = -step if keyval == Gdk.KEY_Left else step if keyval == Gdk.KEY_Right else 0
            dy = -step if keyval == Gdk.KEY_Up else step if keyval == Gdk.KEY_Down else 0
            if state & Gdk.ModifierType.CONTROL_MASK:
                sel.rect[2] = max(1.0, sel.rect[2] + dx)
                sel.rect[3] = max(1.0, sel.rect[3] + dy)
            else:
                sel.rect[0] += dx
                sel.rect[1] += dy
            sel.clamp()
            self.selector.redraw()
            return True
        return False
