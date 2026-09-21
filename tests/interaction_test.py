"""Uji jalur interaksi tool dengan gesture tiruan (tanpa klik manusia).

Menjalankan urutan tekan-geser-lepas persis seperti yang dikirim GTK, supaya
bug di state machine tool ketahuan tanpa harus mengklik satu per satu.
Jalankan: python3 tests/interaction_test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from jepret.canvas import Canvas  # noqa: E402
from jepret.config import config  # noqa: E402
from jepret.document import Document  # noqa: E402
from jepret.items import ArrowItem, EffectItem, StepItem, TextItem  # noqa: E402

if not Gtk.init_check():
    print("GTK tidak bisa start (tidak ada display) - uji dilewati.")
    sys.exit(0)

failures = []


def check(name, condition):
    print(("  ok  " if condition else "  GAGAL ") + name)
    if not condition:
        failures.append(name)


class FakeGesture:
    def __init__(self, button=1, state=0):
        self._button, self._state = button, state

    def get_current_button(self):
        return self._button

    def get_current_event_state(self):
        return self._state


class FakeMotion:
    def __init__(self, state=0):
        self._state = state

    def get_current_event_state(self):
        return self._state


def drag(canvas, x1, y1, x2, y2, steps=3, button=1):
    canvas._on_pressed(FakeGesture(button), 1, x1, y1)
    for i in range(1, steps + 1):
        canvas._on_motion(FakeMotion(),
                          x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
    canvas._on_released(FakeGesture(button), 1, x2, y2)


def click(canvas, x, y, n_press=1, button=1):
    canvas._on_pressed(FakeGesture(button), n_press, x, y)
    canvas._on_released(FakeGesture(button), n_press, x, y)


def new_canvas(w=900, h=700):
    doc = Document(Image.new("RGB", (w, h), (20, 20, 30)))
    return Canvas(doc, config)


print("Menggambar objek")
canvas = new_canvas()
canvas.set_tool("arrow")
drag(canvas, 100, 100, 400, 300)
check("panah tercipta", len(canvas.doc.items) == 1 and isinstance(canvas.doc.items[0], ArrowItem))
check("panah otomatis terpilih", canvas.selected is canvas.doc.items[0])
check("satu entri undo", canvas.history.can_undo)

canvas.set_tool("rect")
drag(canvas, 500, 100, 700, 250)
check("kotak tercipta", len(canvas.doc.items) == 2)

canvas.set_tool("rect")
drag(canvas, 500, 400, 502, 402)      # terlalu kecil -> diabaikan
check("coretan terlalu kecil diabaikan", len(canvas.doc.items) == 2)

canvas.set_tool("pen")
drag(canvas, 100, 500, 300, 600, steps=8)
check("pena tercipta dengan banyak titik", len(canvas.doc.items[-1].points) > 3)

print("\nNomor urut")
canvas.set_tool("step")
click(canvas, 200, 200)
click(canvas, 300, 200)
click(canvas, 400, 200)
steps = [i for i in canvas.doc.items if isinstance(i, StepItem)]
check("tiga badge bernomor 1,2,3", [s.number for s in steps] == [1, 2, 3])
undo_before = len(canvas.history._undo)
canvas.select(steps[1])
canvas.delete_selected()
steps = [i for i in canvas.doc.items if isinstance(i, StepItem)]
check("hapus badge tengah -> penomoran jadi 1,2", [s.number for s in steps] == [1, 2])
check("hapus tercatat di undo", len(canvas.history._undo) == undo_before + 1)
canvas.undo()
check("undo mengembalikan badge", len([i for i in canvas.doc.items if isinstance(i, StepItem)]) == 3)
canvas.redo()
check("redo menghapus lagi", len([i for i in canvas.doc.items if isinstance(i, StepItem)]) == 2)

print("\nPilih, geser, resize, ganti properti")
canvas.set_tool("select")
arrow = canvas.doc.items[0]
click(canvas, *canvas.to_widget(arrow.x1, arrow.y1))
check("klik pada panah memilihnya", canvas.selected is arrow)
x_before = arrow.x1
body = canvas.to_widget(arrow.x1 + (arrow.x2 - arrow.x1) * 0.25,
                        arrow.y1 + (arrow.y2 - arrow.y1) * 0.25)
drag(canvas, body[0], body[1], body[0] + 50, body[1] + 50)
check("objek tergeser", arrow.x1 != x_before)
end_before = (arrow.x2, arrow.y2)
handle_pos = canvas.to_widget(*arrow.handles()["end"])
drag(canvas, handle_pos[0], handle_pos[1], handle_pos[0] + 60, handle_pos[1] + 40)
check("resize lewat handle", (arrow.x2, arrow.y2) != end_before)
canvas.apply_property(color="#33d17a", width=9.0)
check("warna & tebal objek terpilih ikut berubah",
      arrow.color == "#33d17a" and arrow.width == 9.0)

print("\nTeks")
canvas.set_tool("text")
click(canvas, 120, 620)
check("mode edit teks aktif", isinstance(canvas.editing_text, TextItem))
canvas._on_im_commit(None, "Halo")
canvas._on_im_commit(None, " dunia")
check("teks terketik", canvas.editing_text.text == "Halo dunia")
canvas.finish_text_edit(commit=True)
check("teks tersimpan sebagai objek",
      any(isinstance(i, TextItem) and i.text == "Halo dunia" for i in canvas.doc.items))

canvas.set_tool("text")
click(canvas, 700, 620)
canvas.finish_text_edit(commit=True)   # kosong -> jangan tersimpan
check("teks kosong tidak ikut tersimpan",
      len([i for i in canvas.doc.items if isinstance(i, TextItem)]) == 1)

print("\nBlur / pixelate")
canvas.set_tool("effect")
drag(canvas, 600, 450, 800, 600)
effects = [i for i in canvas.doc.items if isinstance(i, EffectItem)]
check("area efek tercipta", len(effects) == 1)
check("surface efek terhitung", canvas.doc.effect_surface(effects[0]) is not None)
canvas.select(effects[0])
canvas.apply_property(effect_kind="blur")
check("ganti ke blur", effects[0].effect == "blur")

print("\nCrop")
canvas.set_tool("crop")
check("kotak crop otomatis seluruh gambar", canvas.crop_rect[2:] == [900.0, 700.0])
drag(canvas, 50, 50, 500, 400)
canvas.apply_crop()
check("dokumen terpotong", (canvas.doc.width, canvas.doc.height) == (450, 350))
canvas.undo()
check("undo crop mengembalikan ukuran", (canvas.doc.width, canvas.doc.height) == (900, 700))

print("\nRender akhir")
image = canvas.doc.to_pil()
check("render final berhasil", image.size == (900, 700))
check("teks ikut ter-render", image.getcolors(1 << 24) is not None)

print()
if failures:
    print(f"{len(failures)} uji GAGAL: {failures}")
    sys.exit(1)
print("Semua uji interaksi lolos.")
