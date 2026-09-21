"""Model objek anotasi.

Semua item bersifat vektor dan tetap bisa dipilih, digeser, diubah ukuran,
dan diubah propertinya setelah digambar. Koordinat memakai piksel gambar
(bukan koordinat layar), sehingga hasil ekspor selalu resolusi penuh.
"""

import math

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

HANDLE_SIZE = 5.0


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c * 255))) for c in rgb[:3])


def _dist_to_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


class Item:
    """Basis semua anotasi."""

    kind = "item"
    label = "Item"
    # properti yang relevan untuk bar properti kontekstual
    supports = ("color", "width")

    def __init__(self, color="#e01b24", width=4.0, alpha=1.0):
        self.color = color
        self.width = float(width)
        self.alpha = float(alpha)
        self.shadow = True

    # --- menggambar -----------------------------------------------------
    def set_source(self, cr, alpha=None):
        r, g, b = hex_to_rgb(self.color)
        cr.set_source_rgba(r, g, b, self.alpha if alpha is None else alpha)

    def draw(self, cr, ctx=None):  # pragma: no cover - diimplementasi subclass
        raise NotImplementedError

    def draw_shadow_pass(self, cr, ctx=None):
        """Bayangan tipis agar anotasi terbaca di latar apa pun."""
        if not self.shadow:
            return
        cr.new_path()
        cr.save()
        cr.translate(1.5, 1.5)
        cr.push_group()
        self.draw(cr, ctx)
        pattern = cr.pop_group()
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.mask(pattern)
        cr.restore()

    # --- geometri -------------------------------------------------------
    def bbox(self):  # pragma: no cover
        raise NotImplementedError

    def handles(self):
        return {}

    def move(self, dx, dy):  # pragma: no cover
        raise NotImplementedError

    def set_handle(self, name, x, y, constrain=False):
        pass

    def hit_test(self, x, y):  # pragma: no cover
        raise NotImplementedError

    def bbox_contains(self, x, y, pad=0.0):
        bx, by, bw, bh = self.bbox()
        return bx - pad <= x <= bx + bw + pad and by - pad <= y <= by + bh + pad

    # --- serialisasi ----------------------------------------------------
    def state(self):
        return {k: (list(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()}

    def restore(self, state):
        for key, value in state.items():
            setattr(self, key, list(value) if isinstance(value, list) else value)

    def clone(self):
        item = type(self).__new__(type(self))
        item.__dict__.update({
            k: (list(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()
        })
        return item


class TwoPointItem(Item):
    """Item yang ditentukan dua titik (garis, panah, kotak, elips)."""

    def __init__(self, x1, y1, x2, y2, **kwargs):
        super().__init__(**kwargs)
        self.x1, self.y1, self.x2, self.y2 = float(x1), float(y1), float(x2), float(y2)

    def bbox(self):
        x, y = min(self.x1, self.x2), min(self.y1, self.y2)
        pad = self.width
        return x - pad, y - pad, abs(self.x2 - self.x1) + 2 * pad, abs(self.y2 - self.y1) + 2 * pad

    def move(self, dx, dy):
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy

    def handles(self):
        return {"start": (self.x1, self.y1), "end": (self.x2, self.y2)}

    def set_handle(self, name, x, y, constrain=False):
        if name == "start":
            self.x1, self.y1 = x, y
        elif name == "end":
            if constrain:
                x, y = self._snap(self.x1, self.y1, x, y)
            self.x2, self.y2 = x, y

    @staticmethod
    def _snap(x1, y1, x, y, step=math.pi / 12):
        angle = math.atan2(y - y1, x - x1)
        dist = math.hypot(x - x1, y - y1)
        angle = round(angle / step) * step
        return x1 + dist * math.cos(angle), y1 + dist * math.sin(angle)


class LineItem(TwoPointItem):
    kind = "line"
    label = "Garis"

    def draw(self, cr, ctx=None):
        cr.save()
        self.set_source(cr)
        cr.set_line_width(self.width)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.move_to(self.x1, self.y1)
        cr.line_to(self.x2, self.y2)
        cr.stroke()
        cr.restore()

    def hit_test(self, x, y):
        return _dist_to_segment(x, y, self.x1, self.y1, self.x2, self.y2) <= max(self.width, 8)


class ArrowItem(TwoPointItem):
    kind = "arrow"
    label = "Panah"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.curve = None  # (cx, cy) bila dibengkokkan

    def _control(self):
        if self.curve:
            return self.curve
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def _path_points(self, n=24):
        cx, cy = self._control()
        pts = []
        for i in range(n + 1):
            t = i / n
            mt = 1 - t
            pts.append((
                mt * mt * self.x1 + 2 * mt * t * cx + t * t * self.x2,
                mt * mt * self.y1 + 2 * mt * t * cy + t * t * self.y2,
            ))
        return pts

    def draw(self, cr, ctx=None):
        cr.save()
        self.set_source(cr)
        cr.set_line_width(self.width)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_join(cairo.LineJoin.ROUND)
        head = max(self.width * 3.6, 12.0)
        pts = self._path_points()
        # titik pangkal kepala panah: mundur sepanjang kurva sejauh head
        tip = pts[-1]
        base = pts[0]
        acc = 0.0
        for i in range(len(pts) - 1, 0, -1):
            acc += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
            if acc >= head:
                base = pts[i - 1]
                break
        angle = math.atan2(tip[1] - base[1], tip[0] - base[0])
        shaft_end = (tip[0] - head * 0.82 * math.cos(angle), tip[1] - head * 0.82 * math.sin(angle))

        cr.move_to(*pts[0])
        if self.curve:
            cx, cy = self.curve
            cr.curve_to(
                self.x1 + 2 / 3 * (cx - self.x1), self.y1 + 2 / 3 * (cy - self.y1),
                shaft_end[0] + 2 / 3 * (cx - shaft_end[0]), shaft_end[1] + 2 / 3 * (cy - shaft_end[1]),
                shaft_end[0], shaft_end[1],
            )
        else:
            cr.line_to(*shaft_end)
        cr.stroke()

        spread = math.radians(24)
        cr.move_to(*tip)
        cr.line_to(tip[0] - head * math.cos(angle - spread), tip[1] - head * math.sin(angle - spread))
        cr.line_to(shaft_end[0], shaft_end[1])
        cr.line_to(tip[0] - head * math.cos(angle + spread), tip[1] - head * math.sin(angle + spread))
        cr.close_path()
        cr.fill()
        cr.restore()

    def handles(self):
        h = super().handles()
        h["curve"] = self._control()
        return h

    def set_handle(self, name, x, y, constrain=False):
        if name == "curve":
            mx, my = (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2
            self.curve = None if math.hypot(x - mx, y - my) < 6 else (x, y)
        else:
            super().set_handle(name, x, y, constrain)

    def move(self, dx, dy):
        super().move(dx, dy)
        if self.curve:
            self.curve = (self.curve[0] + dx, self.curve[1] + dy)

    def bbox(self):
        xs = [self.x1, self.x2]
        ys = [self.y1, self.y2]
        if self.curve:
            xs.append(self.curve[0])
            ys.append(self.curve[1])
        pad = max(self.width * 4, 14)
        return min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad

    def hit_test(self, x, y):
        pts = self._path_points()
        tol = max(self.width * 1.6, 10)
        return any(
            _dist_to_segment(x, y, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) <= tol
            for i in range(len(pts) - 1)
        )


class BoxItem(TwoPointItem):
    """Basis kotak/elips/efek: punya handle 8 arah."""

    supports = ("color", "width", "fill")

    def __init__(self, *args, filled=False, radius=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.filled = filled
        self.radius = radius

    def rect(self):
        x = min(self.x1, self.x2)
        y = min(self.y1, self.y2)
        return x, y, abs(self.x2 - self.x1), abs(self.y2 - self.y1)

    def handles(self):
        x, y, w, h = self.rect()
        return {
            "nw": (x, y), "n": (x + w / 2, y), "ne": (x + w, y),
            "e": (x + w, y + h / 2), "se": (x + w, y + h),
            "s": (x + w / 2, y + h), "sw": (x, y + h), "w": (x, y + h / 2),
        }

    def set_handle(self, name, x, y, constrain=False):
        rx, ry, rw, rh = self.rect()
        left, top, right, bottom = rx, ry, rx + rw, ry + rh
        if "n" in name:
            top = y
        if "s" in name:
            bottom = y
        if "w" in name:
            left = x
        if "e" in name:
            right = x
        if name == "end":
            right, bottom = x, y
        self.x1, self.y1, self.x2, self.y2 = left, top, right, bottom

    def _path(self, cr):
        x, y, w, h = self.rect()
        r = min(self.radius, w / 2, h / 2)
        if r <= 0.5:
            cr.rectangle(x, y, w, h)
            return
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()


class RectItem(BoxItem):
    kind = "rect"
    label = "Kotak"

    def draw(self, cr, ctx=None):
        cr.save()
        self._path(cr)
        if self.filled:
            self.set_source(cr)
            cr.fill()
        else:
            self.set_source(cr)
            cr.set_line_width(self.width)
            cr.stroke()
        cr.restore()

    def hit_test(self, x, y):
        rx, ry, rw, rh = self.rect()
        tol = max(self.width, 8)
        if self.filled:
            return rx - tol <= x <= rx + rw + tol and ry - tol <= y <= ry + rh + tol
        inside = rx - tol <= x <= rx + rw + tol and ry - tol <= y <= ry + rh + tol
        core = rx + tol <= x <= rx + rw - tol and ry + tol <= y <= ry + rh - tol
        return inside and not core


class EllipseItem(BoxItem):
    kind = "ellipse"
    label = "Elips"

    def draw(self, cr, ctx=None):
        x, y, w, h = self.rect()
        if w <= 0 or h <= 0:
            return
        cr.save()
        cr.new_path()
        cr.translate(x + w / 2, y + h / 2)
        cr.scale(w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.save()
        if self.filled:
            self.set_source(cr)
            cr.fill()
        else:
            self.set_source(cr)
            cr.set_line_width(self.width)
            cr.stroke()
        cr.restore()

    def hit_test(self, x, y):
        rx, ry, rw, rh = self.rect()
        if rw <= 0 or rh <= 0:
            return False
        nx = (x - (rx + rw / 2)) / (rw / 2)
        ny = (y - (ry + rh / 2)) / (rh / 2)
        d = nx * nx + ny * ny
        if self.filled:
            return d <= 1.15
        tol = max(self.width, 8)
        inner = (1 - 2 * tol / max(rw, 1)) ** 2
        return d <= 1.2 and d >= min(inner, 0.98) * 0.6


class HighlightItem(BoxItem):
    kind = "highlight"
    label = "Stabilo"
    supports = ("color",)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("color", "#f6d32d")
        super().__init__(*args, **kwargs)
        self.alpha = 0.35
        self.shadow = False

    def draw(self, cr, ctx=None):
        x, y, w, h = self.rect()
        if w <= 0 or h <= 0:
            return
        cr.save()
        cr.set_operator(cairo.Operator.MULTIPLY)
        r, g, b = hex_to_rgb(self.color)
        cr.set_source_rgba(r, g, b, self.alpha)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.restore()

    def hit_test(self, x, y):
        rx, ry, rw, rh = self.rect()
        return rx <= x <= rx + rw and ry <= y <= ry + rh


class EffectItem(BoxItem):
    """Blur atau pixelate sebuah area, dihitung dari gambar dasar."""

    kind = "effect"
    label = "Blur / Pixelate"
    supports = ("effect", "strength")

    def __init__(self, *args, effect="pixelate", strength=12, **kwargs):
        super().__init__(*args, **kwargs)
        self.effect = effect
        self.strength = strength
        self.shadow = False

    @property
    def label_dynamic(self):
        return "Pixelate" if self.effect == "pixelate" else "Blur"

    def draw(self, cr, ctx=None):
        x, y, w, h = self.rect()
        if w < 2 or h < 2:
            return
        surface = ctx.effect_surface(self) if ctx else None
        cr.save()
        self._path(cr)
        cr.clip()
        if surface is not None:
            cr.set_source_surface(surface, x, y)
            cr.paint()
        else:
            cr.set_source_rgba(0.5, 0.5, 0.5, 0.9)
            cr.paint()
        cr.restore()

    def hit_test(self, x, y):
        rx, ry, rw, rh = self.rect()
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def cache_key(self):
        x, y, w, h = self.rect()
        return (round(x), round(y), round(w), round(h), self.effect, self.strength)


class PenItem(Item):
    kind = "pen"
    label = "Pena"

    def __init__(self, points=None, **kwargs):
        super().__init__(**kwargs)
        self.points = list(points or [])

    def add_point(self, x, y):
        if not self.points or math.hypot(x - self.points[-1][0], y - self.points[-1][1]) > 1.2:
            self.points.append((x, y))

    def draw(self, cr, ctx=None):
        if len(self.points) < 2:
            if self.points:
                cr.save()
                self.set_source(cr)
                cr.new_sub_path()
                cr.arc(self.points[0][0], self.points[0][1], self.width / 2, 0, 2 * math.pi)
                cr.fill()
                cr.restore()
            return
        cr.save()
        self.set_source(cr)
        cr.set_line_width(self.width)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_join(cairo.LineJoin.ROUND)
        cr.move_to(*self.points[0])
        # smoothing: titik tengah sebagai simpul kurva kuadratik
        for i in range(1, len(self.points) - 1):
            x0, y0 = self.points[i]
            x1, y1 = self.points[i + 1]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            cx, cy = cr.get_current_point()
            cr.curve_to(
                cx + 2 / 3 * (x0 - cx), cy + 2 / 3 * (y0 - cy),
                mx + 2 / 3 * (x0 - mx), my + 2 / 3 * (y0 - my), mx, my,
            )
        cr.line_to(*self.points[-1])
        cr.stroke()
        cr.restore()

    def bbox(self):
        xs = [p[0] for p in self.points] or [0]
        ys = [p[1] for p in self.points] or [0]
        pad = self.width
        return min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad

    def move(self, dx, dy):
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def hit_test(self, x, y):
        tol = max(self.width, 8)
        return any(
            _dist_to_segment(x, y, self.points[i][0], self.points[i][1],
                             self.points[i + 1][0], self.points[i + 1][1]) <= tol
            for i in range(len(self.points) - 1)
        ) or (len(self.points) == 1 and math.hypot(x - self.points[0][0], y - self.points[0][1]) <= tol)


class TextItem(Item):
    kind = "text"
    label = "Teks"
    supports = ("color", "font_size", "text_bg")

    def __init__(self, x, y, text="", font_size=24.0, **kwargs):
        super().__init__(**kwargs)
        self.x, self.y = float(x), float(y)
        self.text = text
        self.font_size = float(font_size)
        self.background = True
        self.shadow = False
        self._size = (0.0, 0.0)

    def _layout(self, cr):
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription()
        desc.set_family("Sans")
        desc.set_absolute_size(self.font_size * Pango.SCALE)
        desc.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(desc)
        layout.set_text(self.text or " ", -1)
        return layout

    def draw(self, cr, ctx=None, caret=None):
        cr.save()
        layout = self._layout(cr)
        w, h = layout.get_pixel_size()
        self._size = (w, h)
        pad = max(4.0, self.font_size * 0.22)
        if self.background:
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.rectangle(self.x - pad, self.y - pad, w + 2 * pad, h + 2 * pad)
            cr.fill()
        cr.move_to(self.x, self.y)
        self.set_source(cr)
        PangoCairo.show_layout(cr, layout)
        cr.new_path()
        if caret is not None:
            index = min(caret, len(self.text))
            strong, _weak = layout.get_cursor_pos(len(self.text[:index].encode("utf-8")))
            cx = self.x + strong.x / Pango.SCALE
            cy = self.y + strong.y / Pango.SCALE
            ch = strong.height / Pango.SCALE
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(max(1.5, self.font_size * 0.06))
            cr.move_to(cx, cy)
            cr.line_to(cx, cy + ch)
            cr.stroke()
        cr.new_path()
        cr.restore()

    def bbox(self):
        w, h = self._size
        pad = max(4.0, self.font_size * 0.22)
        return self.x - pad, self.y - pad, max(w, self.font_size) + 2 * pad, max(h, self.font_size) + 2 * pad

    def move(self, dx, dy):
        self.x += dx
        self.y += dy

    def hit_test(self, x, y):
        return self.bbox_contains(x, y, pad=2)


class StepItem(Item):
    """Badge nomor urut."""

    kind = "step"
    label = "Nomor Urut"
    supports = ("color", "font_size", "badge_style")

    def __init__(self, x, y, number=1, font_size=24.0, style="circle", **kwargs):
        super().__init__(**kwargs)
        self.x, self.y = float(x), float(y)
        self.number = number
        self.font_size = float(font_size)
        self.style = style

    def radius(self):
        digits = max(1, len(str(self.number)))
        return self.font_size * (0.95 + 0.22 * (digits - 1))

    def draw(self, cr, ctx=None):
        r = self.radius()
        cr.save()
        cr.new_path()
        # cincin putih tipis agar kontras di latar apa pun
        cr.set_source_rgba(1, 1, 1, 0.9)
        if self.style == "square":
            cr.rectangle(self.x - r, self.y - r, 2 * r, 2 * r)
        else:
            cr.new_sub_path()
            cr.arc(self.x, self.y, r, 0, 2 * math.pi)
        cr.set_line_width(max(2.0, r * 0.14))
        cr.stroke_preserve()
        self.set_source(cr)
        cr.fill()

        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription()
        desc.set_family("Sans")
        desc.set_absolute_size(self.font_size * 1.15 * Pango.SCALE)
        desc.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(desc)
        layout.set_text(str(self.number), -1)
        tw, th = layout.get_pixel_size()
        cr.move_to(self.x - tw / 2, self.y - th / 2)
        cr.set_source_rgba(1, 1, 1, 1)
        PangoCairo.show_layout(cr, layout)
        cr.new_path()   # teks meninggalkan current point; jangan diwariskan
        cr.restore()

    def bbox(self):
        r = self.radius() + 2
        return self.x - r, self.y - r, 2 * r, 2 * r

    def move(self, dx, dy):
        self.x += dx
        self.y += dy

    def hit_test(self, x, y):
        return math.hypot(x - self.x, y - self.y) <= self.radius() + 3


KINDS = {
    cls.kind: cls
    for cls in (LineItem, ArrowItem, RectItem, EllipseItem, HighlightItem,
                EffectItem, PenItem, TextItem, StepItem)
}
