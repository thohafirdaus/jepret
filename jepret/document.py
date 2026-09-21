"""Dokumen: gambar dasar + daftar anotasi + crop, beserta perenderannya."""

from PIL import Image

import cairo

from .effects import apply_effect, pil_to_surface


class Document:
    def __init__(self, image: Image.Image, source_path=None):
        self.base = image.convert("RGBA")
        self.base_surface = pil_to_surface(self.base)
        self.items = []
        self.crop = (0.0, 0.0, float(self.base.width), float(self.base.height))
        self.source_path = source_path
        self.saved_path = None
        self.dirty = False
        self._effect_cache = {}

    # --- ukuran ---------------------------------------------------------
    @property
    def width(self):
        return max(1, int(round(self.crop[2])))

    @property
    def height(self):
        return max(1, int(round(self.crop[3])))

    # --- efek (dipakai EffectItem lewat ctx) ----------------------------
    def effect_surface(self, item):
        key = item.cache_key()
        surface = self._effect_cache.get(key)
        if surface is None:
            region = apply_effect(self.base, item.rect(), item.effect, item.strength)
            surface = pil_to_surface(region)
            if len(self._effect_cache) > 32:
                self._effect_cache.clear()
            self._effect_cache[key] = surface
        return surface

    # --- render ---------------------------------------------------------
    def draw_content(self, cr, skip=()):
        """Gambar base + anotasi pada koordinat gambar (belum dikurangi crop)."""
        cr.save()
        cr.set_source_surface(self.base_surface, 0, 0)
        cr.paint()
        cr.restore()
        for item in self.items:
            if item in skip:
                continue
            item.draw_shadow_pass(cr, self)
            cr.new_path()
            cr.save()
            item.draw(cr, self)
            cr.restore()
            cr.new_path()

    def render_surface(self) -> cairo.ImageSurface:
        """Render final pada resolusi asli, sudah memperhitungkan crop."""
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        cr = cairo.Context(surface)
        cr.translate(-self.crop[0], -self.crop[1])
        self.draw_content(cr)
        surface.flush()
        return surface

    def to_pil(self) -> Image.Image:
        surface = self.render_surface()
        surface.flush()
        buf = bytes(surface.get_data())
        stride = surface.get_stride()
        w, h = self.width, self.height
        if stride != w * 4:
            buf = b"".join(buf[y * stride:y * stride + w * 4] for y in range(h))
        return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRa", 0, 1).convert("RGBA")

    def to_png_bytes(self) -> bytes:
        import io
        out = io.BytesIO()
        self.to_pil().save(out, "PNG")
        return out.getvalue()

    # --- manipulasi items ------------------------------------------------
    def add(self, item):
        self.items.append(item)
        self.dirty = True

    def remove(self, item):
        if item in self.items:
            self.items.remove(item)
            self.dirty = True

    def item_at(self, x, y):
        for item in reversed(self.items):
            if item.hit_test(x, y):
                return item
        return None

    def next_step_number(self):
        from .items import StepItem
        used = [i.number for i in self.items if isinstance(i, StepItem)]
        return max(used) + 1 if used else 1

    def renumber_steps(self):
        from .items import StepItem
        steps = [i for i in self.items if isinstance(i, StepItem)]
        for index, item in enumerate(steps, start=1):
            item.number = index

    def raise_item(self, item, to_top=False):
        if item not in self.items:
            return
        i = self.items.index(item)
        self.items.remove(item)
        self.items.append(item) if to_top or i >= len(self.items) else self.items.insert(i + 1, item)
        self.dirty = True

    def lower_item(self, item, to_bottom=False):
        if item not in self.items:
            return
        i = self.items.index(item)
        self.items.remove(item)
        self.items.insert(0 if to_bottom else max(0, i - 1), item)
        self.dirty = True

    def apply_crop(self, x, y, w, h):
        x = max(0.0, min(x, self.base.width - 1))
        y = max(0.0, min(y, self.base.height - 1))
        self.crop = (x, y, max(1.0, min(w, self.base.width - x)), max(1.0, min(h, self.base.height - y)))
        self.dirty = True

    # --- undo/redo -------------------------------------------------------
    def snapshot(self):
        return ([item.clone() for item in self.items], tuple(self.crop))

    def restore(self, snapshot):
        items, crop = snapshot
        self.items = [item.clone() for item in items]
        self.crop = tuple(crop)
        self.dirty = True
