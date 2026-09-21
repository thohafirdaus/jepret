"""Canvas editor: menggambar dokumen + menangani interaksi tool."""

import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .history import History  # noqa: E402
from .items import (ArrowItem, EffectItem, EllipseItem, HighlightItem,  # noqa: E402
                    LineItem, PenItem, RectItem, StepItem, TextItem, HANDLE_SIZE)

TOOLS = ("select", "arrow", "step", "rect", "ellipse", "line", "pen",
         "highlight", "text", "effect", "crop")

HANDLE_CURSORS = {
    "nw": "nw-resize", "n": "n-resize", "ne": "ne-resize", "e": "e-resize",
    "se": "se-resize", "s": "s-resize", "sw": "sw-resize", "w": "w-resize",
    "start": "crosshair", "end": "crosshair", "curve": "grab",
}
TOOL_CURSORS = {"select": "default", "text": "text", "step": "copy"}


class Canvas(Gtk.DrawingArea):
    def __init__(self, document, config):
        super().__init__()
        self.doc = document
        self.config = config
        self.history = History()
        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.tool = "select"

        self.color = config["color"]
        self.width = float(config["stroke_width"])
        self.font_size = float(config["font_size"])
        self.filled = False
        self.effect_kind = "pixelate"
        self.effect_strength = 14
        self.badge_style = config["badge_style"]

        self.selected = None
        self.editing_text = None
        self.caret = 0
        self.crop_rect = None

        self._drag = None
        self._pending = None
        self._pointer = (0.0, 0.0)
        self._snapshot_before = None
        self._cursor_name = None

        self.on_changed = None          # dipanggil saat dokumen berubah
        self.on_selection_changed = None
        self.on_zoom_changed = None
        self.on_status = None

        self.set_focusable(True)
        self.set_draw_func(self._draw)

        click = Gtk.GestureClick.new()
        click.set_button(0)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_motion)
        self.add_controller(motion)

        self._im = Gtk.IMMulticontext()
        self._im.connect("commit", self._on_im_commit)

        self.update_size()

    # ------------------------------------------------------------------ util
    def doc_size(self):
        return self.doc.width, self.doc.height

    def update_size(self):
        w, h = self.doc_size()
        self.set_content_width(int(w * self.zoom))
        self.set_content_height(int(h * self.zoom))
        self.queue_draw()

    def set_zoom(self, zoom, notify=True):
        self.zoom = max(0.1, min(8.0, zoom))
        self.update_size()
        if notify and self.on_zoom_changed:
            self.on_zoom_changed(self.zoom)

    def zoom_to_fit(self, width, height):
        w, h = self.doc_size()
        if w and h and width > 40 and height > 40:
            self.fit_zoom = min(1.0, min((width - 24) / w, (height - 24) / h))
            self.set_zoom(self.fit_zoom)

    def to_image(self, wx, wy):
        return wx / self.zoom + self.doc.crop[0], wy / self.zoom + self.doc.crop[1]

    def to_widget(self, ix, iy):
        return (ix - self.doc.crop[0]) * self.zoom, (iy - self.doc.crop[1]) * self.zoom

    def changed(self, status=None):
        self.doc.dirty = True
        self.queue_draw()
        if self.on_changed:
            self.on_changed()
        if status and self.on_status:
            self.on_status(status)

    # --------------------------------------------------------------- history
    def begin_change(self):
        self._snapshot_before = self.doc.snapshot()

    def commit_change(self, status=None):
        if self._snapshot_before is not None:
            self.history.push(self._snapshot_before)
            self._snapshot_before = None
        self.changed(status)

    def undo(self):
        state = self.history.undo(self.doc.snapshot())
        if state is None:
            return False
        self._restore(state)
        return True

    def redo(self):
        state = self.history.redo(self.doc.snapshot())
        if state is None:
            return False
        self._restore(state)
        return True

    def _restore(self, state):
        self.finish_text_edit(commit=True, record=False)
        self.doc.restore(state)
        self.selected = None
        self.update_size()
        self.changed()
        if self.on_selection_changed:
            self.on_selection_changed(None)

    # ------------------------------------------------------------------ tool
    def set_tool(self, tool):
        if tool == self.tool:
            return
        self.finish_text_edit(commit=True)
        self.tool = tool
        if tool != "select":
            self.select(None)
        if tool == "crop" and self.crop_rect is None:
            self.crop_rect = [self.doc.crop[0], self.doc.crop[1],
                              float(self.doc.width), float(self.doc.height)]
            # kotak awal menutupi seluruh gambar: seretan pertama harus
            # membuat area baru, bukan menggeser kotak penuh itu
            self._crop_pristine = True
        if tool != "crop":
            self.crop_rect = None
        self.config["last_tool"] = tool
        self._set_cursor(self._cursor_for(*self._pointer))
        self.queue_draw()

    def select(self, item):
        if self.selected is item:
            return
        self.finish_text_edit(commit=True)
        self.selected = item
        self.queue_draw()
        if self.on_selection_changed:
            self.on_selection_changed(item)

    def delete_selected(self):
        if not self.selected:
            return
        self.begin_change()
        self.doc.remove(self.selected)
        self.doc.renumber_steps()
        self.select(None)
        self.commit_change("Objek dihapus")

    def duplicate_selected(self):
        if not self.selected:
            return
        self.begin_change()
        clone = self.selected.clone()
        clone.move(16, 16)
        if isinstance(clone, StepItem):
            clone.number = self.doc.next_step_number()
        self.doc.add(clone)
        self.select(clone)
        self.commit_change("Objek diduplikasi")

    def apply_property(self, **kwargs):
        """Ubah properti tool aktif; bila ada objek terpilih, ubah objeknya juga."""
        for key, value in kwargs.items():
            setattr(self, key, value)
        item = self.selected
        if item is None:
            return
        self.begin_change()
        mapping = {
            "color": "color", "width": "width", "font_size": "font_size",
            "filled": "filled", "effect_kind": "effect", "effect_strength": "strength",
            "badge_style": "style",
        }
        for key, value in kwargs.items():
            attr = mapping.get(key)
            if attr and hasattr(item, attr):
                setattr(item, attr, value)
        self.doc._effect_cache.clear()
        self.commit_change()

    # --------------------------------------------------------------- drawing
    def _draw(self, _area, cr, width, height):
        cr.save()
        cr.scale(self.zoom, self.zoom)
        cr.translate(-self.doc.crop[0], -self.doc.crop[1])
        skip = (self.editing_text,) if self.editing_text else ()
        self.doc.draw_content(cr, skip=skip)
        if self._pending is not None:
            self._pending.draw_shadow_pass(cr, self.doc)
            cr.new_path()
            cr.save()
            self._pending.draw(cr, self.doc)
            cr.restore()
            cr.new_path()
        if self.editing_text is not None:
            cr.save()
            self.editing_text.draw(cr, self.doc, caret=self.caret)
            cr.restore()
            cr.new_path()
        cr.restore()

        if self.selected is not None and self.selected is not self.editing_text:
            self._draw_handles(cr, self.selected)
        if self.tool == "crop" and self.crop_rect:
            self._draw_crop(cr, width, height)

    def _draw_handles(self, cr, item):
        bx, by, bw, bh = item.bbox()
        x, y = self.to_widget(bx, by)
        cr.save()
        cr.set_source_rgba(0.28, 0.56, 1.0, 0.95)
        cr.set_line_width(1.0)
        cr.set_dash([4.0, 3.0])
        cr.rectangle(x, y, bw * self.zoom, bh * self.zoom)
        cr.stroke()
        cr.set_dash([])
        for _name, (hx, hy) in item.handles().items():
            wx, wy = self.to_widget(hx, hy)
            cr.arc(wx, wy, HANDLE_SIZE, 0, 2 * math.pi)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(0.18, 0.45, 0.95)
            cr.set_line_width(2.0)
            cr.stroke()
        cr.restore()

    def _draw_crop(self, cr, width, height):
        x, y, w, h = self.crop_rect
        wx, wy = self.to_widget(x, y)
        ww, wh = w * self.zoom, h * self.zoom
        cr.save()
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.rectangle(0, 0, width, height)
        cr.rectangle(wx, wy, ww, wh)
        cr.set_fill_rule(cairo.FillRule.EVEN_ODD)
        cr.fill()
        cr.set_fill_rule(cairo.FillRule.WINDING)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(1.5)
        cr.rectangle(wx, wy, ww, wh)
        cr.stroke()
        for hx, hy in self._crop_handles().values():
            px, py = self.to_widget(hx, hy)
            cr.rectangle(px - 5, py - 5, 10, 10)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(0.18, 0.45, 0.95)
            cr.set_line_width(2)
            cr.stroke()
        cr.restore()

    def _crop_handles(self):
        x, y, w, h = self.crop_rect
        return {"nw": (x, y), "n": (x + w / 2, y), "ne": (x + w, y),
                "e": (x + w, y + h / 2), "se": (x + w, y + h),
                "s": (x + w / 2, y + h), "sw": (x, y + h), "w": (x, y + h / 2)}

    # ---------------------------------------------------------------- events
    def _handle_at(self, item, wx, wy):
        for name, (hx, hy) in item.handles().items():
            px, py = self.to_widget(hx, hy)
            if math.hypot(wx - px, wy - py) <= HANDLE_SIZE + 4:
                return name
        return None

    def _new_item(self, x, y):
        common = dict(color=self.color, width=self.width)
        if self.tool == "arrow":
            return ArrowItem(x, y, x, y, **common)
        if self.tool == "line":
            return LineItem(x, y, x, y, **common)
        if self.tool == "rect":
            item = RectItem(x, y, x, y, **common)
            item.filled = self.filled
            return item
        if self.tool == "ellipse":
            item = EllipseItem(x, y, x, y, **common)
            item.filled = self.filled
            return item
        if self.tool == "highlight":
            return HighlightItem(x, y, x, y, color=self.color)
        if self.tool == "effect":
            return EffectItem(x, y, x, y, effect=self.effect_kind, strength=self.effect_strength)
        if self.tool == "pen":
            item = PenItem([(x, y)], **common)
            return item
        return None

    def _on_pressed(self, gesture, n_press, wx, wy):
        self.grab_focus()
        button = gesture.get_current_button()
        state = gesture.get_current_event_state()
        ix, iy = self.to_image(wx, wy)

        if button == 3:  # klik kanan = pilih objek di bawah kursor
            self.set_tool("select")
            self.select(self.doc.item_at(ix, iy))
            return

        if self.editing_text is not None and not self.editing_text.hit_test(ix, iy):
            self.finish_text_edit(commit=True)

        if self.tool == "crop":
            self._press_crop(wx, wy, ix, iy)
            return

        if self.tool == "select":
            item = self.selected
            if item is not None:
                handle = self._handle_at(item, wx, wy)
                if handle:
                    self.begin_change()
                    self._drag = ("resize", item, handle, ix, iy)
                    return
            hit = self.doc.item_at(ix, iy)
            if hit is not None:
                self.select(hit)
                if n_press == 2 and isinstance(hit, TextItem):
                    self.start_text_edit(hit)
                    return
                self.begin_change()
                self._drag = ("move", hit, None, ix, iy)
            else:
                self.select(None)
            return

        if self.tool == "text":
            self.begin_change()
            item = TextItem(ix, iy, "", font_size=self.font_size, color=self.color)
            self.start_text_edit(item, is_new=True)
            return

        if self.tool == "step":
            self.begin_change()
            item = StepItem(ix, iy, self.doc.next_step_number(),
                            font_size=self.font_size, color=self.color, style=self.badge_style)
            self.doc.add(item)
            self.select(item)
            self._drag = ("move", item, None, ix, iy)
            self.changed(f"Nomor {item.number} ditambahkan")
            return

        item = self._new_item(ix, iy)
        if item is not None:
            self.begin_change()
            self._pending = item
            self._drag = ("create", item, None, ix, iy)
            self.queue_draw()

    # ----------------------------------------------------------------- kursor
    def _set_cursor(self, name):
        if name != self._cursor_name:
            self._cursor_name = name
            self.set_cursor(Gdk.Cursor.new_from_name(name, None))

    def _cursor_for(self, wx, wy):
        if self.editing_text is not None:
            return "text"
        if self._drag is not None:
            kind, _item, handle, _sx, _sy = self._drag
            if kind in ("move", "crop-move"):
                return "move"
            if kind in ("resize", "crop-resize"):
                return HANDLE_CURSORS.get(handle, "crosshair")
            return "crosshair"
        ix, iy = self.to_image(wx, wy)
        if self.tool == "crop" and self.crop_rect:
            for name, (hx, hy) in self._crop_handles().items():
                px, py = self.to_widget(hx, hy)
                if math.hypot(wx - px, wy - py) <= 9:
                    return HANDLE_CURSORS.get(name, "crosshair")
            x, y, w, h = self.crop_rect
            return "move" if (x <= ix <= x + w and y <= iy <= y + h) else "crosshair"
        if self.tool == "select":
            if self.selected is not None:
                handle = self._handle_at(self.selected, wx, wy)
                if handle:
                    return HANDLE_CURSORS.get(handle, "crosshair")
            return "move" if self.doc.item_at(ix, iy) is not None else "default"
        return TOOL_CURSORS.get(self.tool, "crosshair")

    def _on_motion(self, ctrl, wx, wy):
        self._pointer = (wx, wy)
        self._set_cursor(self._cursor_for(wx, wy))
        if self._drag is None:
            return
        ix, iy = self.to_image(wx, wy)
        kind, item, handle, sx, sy = self._drag
        shift = bool(ctrl.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK)

        if kind == "create":
            if isinstance(item, PenItem):
                item.add_point(ix, iy)
            elif shift and isinstance(item, (ArrowItem, LineItem)):
                item.set_handle("end", ix, iy, constrain=True)
            elif hasattr(item, "rect") and shift:
                size = max(abs(ix - item.x1), abs(iy - item.y1))
                item.x2 = item.x1 + math.copysign(size, ix - item.x1 or 1)
                item.y2 = item.y1 + math.copysign(size, iy - item.y1 or 1)
            else:
                item.x2, item.y2 = ix, iy
            self.queue_draw()
        elif kind == "move":
            item.move(ix - sx, iy - sy)
            self._drag = (kind, item, handle, ix, iy)
            self.doc._effect_cache.clear()
            self.queue_draw()
        elif kind == "resize":
            item.set_handle(handle, ix, iy, constrain=shift)
            self.doc._effect_cache.clear()
            self.queue_draw()
        elif kind == "crop-move":
            self.crop_rect[0] += ix - sx
            self.crop_rect[1] += iy - sy
            self._clamp_crop()
            self._drag = (kind, item, handle, ix, iy)
            self.queue_draw()
        elif kind in ("crop-resize", "crop-new"):
            self._resize_crop(handle, ix, iy)
            self.queue_draw()

    def _on_released(self, _gesture, _n_press, wx, wy):
        if self._drag is None:
            self._set_cursor(self._cursor_for(wx, wy))
            return
        kind, item, _handle, _sx, _sy = self._drag
        self._drag = None
        if kind == "create":
            self._pending = None
            if self._item_is_meaningful(item):
                self.doc.add(item)
                self.select(item)
                self.commit_change(f"{item.label} ditambahkan")
            else:
                self._snapshot_before = None
                self.queue_draw()
        elif kind in ("move", "resize"):
            self.commit_change()
        elif kind.startswith("crop"):
            self._clamp_crop()
            self.queue_draw()
        self._set_cursor(self._cursor_for(wx, wy))

    @staticmethod
    def _item_is_meaningful(item):
        """Abaikan klik tak sengaja yang menghasilkan objek sangat kecil."""
        if isinstance(item, PenItem):
            return len(item.points) > 1
        if isinstance(item, (ArrowItem, LineItem)):
            return math.hypot(item.x2 - item.x1, item.y2 - item.y1) > 8
        if hasattr(item, "rect"):
            _x, _y, w, h = item.rect()
            return w > 6 and h > 6
        return True

    # ------------------------------------------------------------------ crop
    def _press_crop(self, wx, wy, ix, iy):
        for name, (hx, hy) in self._crop_handles().items():
            px, py = self.to_widget(hx, hy)
            if math.hypot(wx - px, wy - py) <= 9:
                self._crop_pristine = False
                self._drag = ("crop-resize", None, name, ix, iy)
                return
        x, y, w, h = self.crop_rect
        inside = x <= ix <= x + w and y <= iy <= y + h
        if inside and not getattr(self, "_crop_pristine", False):
            self._drag = ("crop-move", None, None, ix, iy)
        else:
            self.crop_rect = [ix, iy, 1.0, 1.0]
            self._drag = ("crop-new", None, "se", ix, iy)
        self._crop_pristine = False

    def _resize_crop(self, handle, ix, iy):
        x, y, w, h = self.crop_rect
        left, top, right, bottom = x, y, x + w, y + h
        if "n" in handle:
            top = iy
        if "s" in handle:
            bottom = iy
        if "w" in handle:
            left = ix
        if "e" in handle:
            right = ix
        self.crop_rect = [min(left, right), min(top, bottom),
                          max(4.0, abs(right - left)), max(4.0, abs(bottom - top))]
        self._clamp_crop()

    def _clamp_crop(self):
        bw, bh = self.doc.base.width, self.doc.base.height
        x, y, w, h = self.crop_rect
        w = min(w, bw)
        h = min(h, bh)
        x = max(0.0, min(x, bw - w))
        y = max(0.0, min(y, bh - h))
        self.crop_rect = [x, y, w, h]

    def apply_crop(self):
        if not self.crop_rect:
            return
        self.begin_change()
        self.doc.apply_crop(*self.crop_rect)
        self.crop_rect = None
        self.set_tool("select")
        self.update_size()
        self.commit_change("Gambar dipotong")

    def cancel_crop(self):
        self.crop_rect = None
        self._crop_pristine = False
        self.set_tool("select")
        self.queue_draw()

    # ------------------------------------------------------------- teks
    def start_text_edit(self, item, is_new=False):
        if self.editing_text is not None and self.editing_text is not item:
            self.finish_text_edit(commit=True)
        # pilih langsung, jangan lewat select(): select() menutup mode edit
        self.selected = item
        if self.on_selection_changed:
            self.on_selection_changed(item)
        self.editing_text = item
        self._text_is_new = is_new
        self.caret = len(item.text)
        self._im.set_client_widget(self)
        self._im.focus_in()
        self.queue_draw()
        if self.on_status:
            self.on_status("Ketik teks — Esc untuk selesai")

    def finish_text_edit(self, commit=True, record=True):
        item = self.editing_text
        if item is None:
            return
        self.editing_text = None
        self._im.focus_out()
        if commit and item.text.strip():
            if getattr(self, "_text_is_new", False):
                self.doc.add(item)
            if record:
                self.commit_change("Teks ditambahkan")
            else:
                self.changed()
        else:
            if getattr(self, "_text_is_new", False):
                self._snapshot_before = None
            if item in self.doc.items:
                self.doc.remove(item)
            self.select(None)
            self.changed()
        self._text_is_new = False
        self.queue_draw()

    def _on_im_commit(self, _im, text):
        if self.editing_text is None:
            return
        item = self.editing_text
        item.text = item.text[:self.caret] + text + item.text[self.caret:]
        self.caret += len(text)
        self.queue_draw()

    def _text_key(self, keyval, state):
        item = self.editing_text
        if keyval == Gdk.KEY_Escape:
            self.finish_text_edit(commit=True)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.CONTROL_MASK:
                self.finish_text_edit(commit=True)
            else:
                item.text = item.text[:self.caret] + "\n" + item.text[self.caret:]
                self.caret += 1
            self.queue_draw()
            return True
        if keyval == Gdk.KEY_BackSpace:
            if self.caret > 0:
                item.text = item.text[:self.caret - 1] + item.text[self.caret:]
                self.caret -= 1
            self.queue_draw()
            return True
        if keyval == Gdk.KEY_Delete:
            item.text = item.text[:self.caret] + item.text[self.caret + 1:]
            self.queue_draw()
            return True
        if keyval == Gdk.KEY_Left:
            self.caret = max(0, self.caret - 1)
            self.queue_draw()
            return True
        if keyval == Gdk.KEY_Right:
            self.caret = min(len(item.text), self.caret + 1)
            self.queue_draw()
            return True
        if keyval == Gdk.KEY_Home:
            self.caret = 0
            self.queue_draw()
            return True
        if keyval == Gdk.KEY_End:
            self.caret = len(item.text)
            self.queue_draw()
            return True
        return False

    def handle_key(self, keyval, keycode, state, event=None):
        if self.editing_text is not None:
            if event is not None and self._im.filter_keypress(event):
                return True
            return self._text_key(keyval, state)

        if keyval == Gdk.KEY_Escape:
            if self.tool == "crop":
                self.cancel_crop()
            elif self.selected is not None:
                self.select(None)
            else:
                self.set_tool("select")
            return True
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self.delete_selected()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.tool == "crop":
            self.apply_crop()
            return True
        if self.selected is not None and keyval in (
            Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down
        ):
            step = 10 if state & Gdk.ModifierType.SHIFT_MASK else 1
            dx = -step if keyval == Gdk.KEY_Left else step if keyval == Gdk.KEY_Right else 0
            dy = -step if keyval == Gdk.KEY_Up else step if keyval == Gdk.KEY_Down else 0
            self.begin_change()
            self.selected.move(dx, dy)
            self.commit_change()
            return True
        if keyval == Gdk.KEY_bracketleft and self.selected is not None:
            self.begin_change()
            self.doc.lower_item(self.selected)
            self.commit_change()
            return True
        if keyval == Gdk.KEY_bracketright and self.selected is not None:
            self.begin_change()
            self.doc.raise_item(self.selected)
            self.commit_change()
            return True
        return False
