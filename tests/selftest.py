"""Uji logika inti tanpa GUI: geometri item, hit-test, undo, crop, ekspor.

Jalankan: python3 tests/selftest.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from jepret.document import Document  # noqa: E402
from jepret.export import format_for_path, save_image  # noqa: E402
from jepret.history import History  # noqa: E402
from jepret.items import (ArrowItem, EffectItem, EllipseItem, PenItem,  # noqa: E402
                          RectItem, StepItem, TextItem)

failures = []


def check(name, condition):
    print(("  ok  " if condition else "  GAGAL ") + name)
    if not condition:
        failures.append(name)


def make_doc(w=800, h=600):
    return Document(Image.new("RGB", (w, h), (30, 40, 60)))


print("Geometri & hit-test")
arrow = ArrowItem(100, 100, 300, 250)
check("panah kena di sepanjang garis", arrow.hit_test(200, 175))
check("panah tidak kena jauh dari garis", not arrow.hit_test(400, 100))
arrow.move(50, 0)
check("panah bergeser", (arrow.x1, arrow.x2) == (150, 350))

rect = RectItem(100, 100, 300, 300)
check("kotak outline: tepi kena", rect.hit_test(100, 200))
check("kotak outline: tengah tidak kena", not rect.hit_test(200, 200))
rect.filled = True
check("kotak terisi: tengah kena", rect.hit_test(200, 200))

rect.set_handle("nw", 50, 60)
check("resize handle nw", rect.rect() == (50, 60, 250, 240))

ellipse = EllipseItem(0, 0, 200, 100)
check("elips: titik di garis kena", ellipse.hit_test(100, 0))
pen = PenItem([(0, 0), (50, 50), (100, 0)])
check("pena: kena di jalur", pen.hit_test(50, 50))

step = StepItem(400, 400, 7)
check("badge: klik di tengah kena", step.hit_test(400, 400))
check("badge: klik jauh tidak kena", not step.hit_test(500, 500))

print("\nDokumen, undo/redo, penomoran")
doc = make_doc()
doc.add(ArrowItem(10, 10, 100, 100))
doc.add(StepItem(200, 200, doc.next_step_number()))
doc.add(StepItem(300, 200, doc.next_step_number()))
doc.add(StepItem(400, 200, doc.next_step_number()))
check("nomor berurut 1,2,3", [i.number for i in doc.items if isinstance(i, StepItem)] == [1, 2, 3])

history = History()
snapshot = doc.snapshot()
history.push(snapshot)
doc.remove([i for i in doc.items if isinstance(i, StepItem)][1])
doc.renumber_steps()
check("setelah hapus nomor 2 -> 1,2", [i.number for i in doc.items if isinstance(i, StepItem)] == [1, 2])
state = history.undo(doc.snapshot())
doc.restore(state)
check("undo mengembalikan 3 badge", len([i for i in doc.items if isinstance(i, StepItem)]) == 3)
state = history.redo(doc.snapshot())
doc.restore(state)
check("redo menghapusnya lagi", len([i for i in doc.items if isinstance(i, StepItem)]) == 2)

print("\nCrop & ekspor resolusi penuh")
doc = make_doc(1000, 800)
doc.add(RectItem(10, 10, 200, 200, color="#ff0000", width=6))
doc.add(EffectItem(300, 300, 500, 500, effect="blur", strength=8))
doc.apply_crop(100, 100, 400, 300)
check("ukuran dokumen mengikuti crop", (doc.width, doc.height) == (400, 300))
image = doc.to_pil()
check("hasil render sesuai ukuran crop", image.size == (400, 300))

doc2 = make_doc(300, 200)
doc2.add(TextItem(20, 20, "uji"))
check("teks masuk dokumen", len(doc2.items) == 1)

with tempfile.TemporaryDirectory() as tmp:
    for ext in ("png", "jpg", "webp"):
        path = save_image(image, Path(tmp) / f"x.{ext}")
        reopened = Image.open(path)
        check(f"simpan {ext} ({path.stat().st_size // 1024} KB)", reopened.size == (400, 300))
check("deteksi format .JPEG", format_for_path("/a/b.JPEG") == "jpg")

print("\nEfek")
base = Image.new("RGB", (100, 100), (255, 0, 0))
doc3 = Document(base)
item = EffectItem(0, 0, 50, 50, effect="pixelate", strength=10)
surface_a = doc3.effect_surface(item)
surface_b = doc3.effect_surface(item)
check("cache efek dipakai ulang", surface_a is surface_b)
item.strength = 20
check("ganti kekuatan -> surface baru", doc3.effect_surface(item) is not surface_a)

print("\nRegresi: garis nyasar antar objek")
# cairo mewariskan current point lintas objek; dulu ini memunculkan garis
# penghubung abu-abu antar badge nomor
canvas_doc = Document(Image.new("RGB", (600, 300), (255, 255, 255)))
canvas_doc.add(StepItem(100, 150, 1, font_size=26))
canvas_doc.add(StepItem(500, 150, 2, font_size=26))
canvas_doc.add(EllipseItem(200, 40, 400, 90, width=4))
rendered = canvas_doc.to_pil().convert("RGB")
between = [rendered.getpixel((x, 150)) for x in range(160, 440)]
check("tidak ada garis penghubung antar badge",
      all(pixel == (255, 255, 255) for pixel in between))

print()
if failures:
    print(f"{len(failures)} uji GAGAL: {failures}")
    sys.exit(1)
print("Semua uji lolos.")
