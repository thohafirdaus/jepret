# Jepret

![lisensi](https://img.shields.io/badge/lisensi-MIT-blue) ![platform](https://img.shields.io/badge/platform-GNOME%20Wayland-orange) ![python](https://img.shields.io/badge/python-3.10%2B-green)

Aplikasi screenshot + editor anotasi untuk **Ubuntu/GNOME di Wayland**.
Tangkap area atau jendela, beri panah & nomor urut, blur bagian sensitif,
lalu simpan atau salin ke clipboard.

![tool](data/icons/id.jepret.Jepret.svg)

## Fitur

**Tangkap**
- Area (overlay sendiri: magnifier 6×, koordinat piksel, garis bantu sepertiga, handle 8 arah)
- Jendela (memakai pemilih jendela bawaan GNOME — akurat di Wayland)
- Layar penuh, dengan atau tanpa jeda (0–30 detik)
- Opsi menyertakan kursor mouse

**Editor (sebelum disimpan)**
- Panah (bisa dibengkokkan), garis, kotak, elips, pena bebas, stabilo
- **Nomor urut** otomatis bertambah — gaya lingkaran atau kotak, bisa direset
- Teks dengan latar kontras, diketik langsung di kanvas
- Blur / pixelate area, kekuatan bisa diatur
- Crop non-destruktif
- Semua objek tetap bisa dipilih, digeser, di-resize, dan diganti warna/tebalnya
- Undo/redo tanpa batas, atur urutan tumpukan, duplikat objek
- Zoom 10–800%

**Pintasan global & preferensi** (`Ctrl+,`)
- Atur pintasan keyboard desktop untuk Tangkap area / jendela / layar penuh —
  tinggal tekan kombinasinya, Jepret menuliskannya ke pengaturan GNOME
- Deteksi bentrok: bila kombinasi dipakai alat screenshot bawaan GNOME
  (mis. Print Screen), Jepret menawarkan pengambilalihan, dan bisa dikembalikan lagi
- Folder simpan, pola nama berkas, format bawaan, kualitas JPEG/WebP,
  kursor mouse, bentuk badge nomor

**Keluaran**
- Simpan PNG / JPEG / WebP (`Ctrl+S` cepat ke folder Screenshots, `Ctrl+Shift+S` pilih lokasi)
- Salin ke clipboard (`Ctrl+C`)
- Riwayat screenshot dengan thumbnail: buka lagi, salin, hapus

## Unduh & pasang

### Ubuntu / Debian (paling mudah)

Ambil `jepret_<versi>_all.deb` dari [halaman Releases](https://github.com/thohafirdaus/jepret/releases), lalu:

```bash
sudo apt install ./jepret_1.0.0_all.deb
```

`apt` akan menarik sendiri semua paket yang dibutuhkan. Setelah itu Jepret ada
di menu aplikasi, dan perintah `jepret` tersedia di terminal.

Menghapusnya: `sudo apt remove jepret`

### Distro lain

Unduh `jepret-<versi>.tar.gz` dari Releases, lalu:

```bash
tar -xzf jepret-1.0.0.tar.gz
cd jepret-1.0.0
./install.sh          # memasang ke ~/.local, tanpa root
```

Pastikan paket berikut sudah ada lewat manajer paket distro Anda:
`python3-gi`, `python3-gi-cairo`, GTK 4, libadwaita, Pillow, dan
`xdg-desktop-portal` beserta backend desktop Anda.

### Dari kode sumber

```bash
git clone https://github.com/thohafirdaus/jepret.git
cd jepret && ./install.sh
```

### Membangun paketnya sendiri

```bash
./packaging/build.sh   # menghasilkan dist/*.deb dan dist/*.tar.gz
```

## Prasyarat

```bash
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-pil wl-clipboard
```

`python3-gi-cairo` wajib (jembatan cairo–GTK4).
`wl-clipboard` opsional tetapi disarankan: tanpa itu, isi clipboard hilang
begitu jendela Jepret ditutup — batasan Wayland, bukan bug aplikasi.

## Pasang

```bash
./install.sh
```

Memasang ikon + entri menu GNOME (termasuk aksi klik-kanan: Area / Jendela /
Layar penuh) dan tautan `~/.local/bin/jepret`.

## Pakai

```bash
jepret              # jendela awal
jepret --area       # langsung pilih area
jepret --window     # pilih jendela
jepret --full -d 3  # layar penuh setelah 3 detik
jepret foto.png     # buka gambar yang sudah ada di editor
```

Ingin tombol Print Screen memanggil Jepret? Buka **Preferensi → Pintasan**
(`Ctrl+,`), klik tombol di baris "Tangkap area", lalu tekan `Print`. Jepret
mendeteksi bahwa GNOME masih memakai tombol itu dan menawarkan pengambilalihan;
tombol "Kembalikan" mengembalikan pintasan GNOME kapan saja.

## Pintasan keyboard

| | |
|---|---|
| `V` `A` `N` `R` `E` | pilih · panah · nomor urut · kotak · elips |
| `L` `P` `H` `T` `B` `C` | garis · pena · stabilo · teks · blur · crop |
| `Del` / `Ctrl+D` | hapus / duplikat objek |
| panah / `Shift`+panah | geser 1 px / 10 px |
| `Shift` saat menggambar | garis lurus 15° atau bentuk persegi |
| `[` `]` | turunkan / naikkan urutan tumpukan |
| `Ctrl+S` `Ctrl+Shift+S` `Ctrl+C` | simpan · simpan sebagai · salin |
| `Ctrl+Z` `Ctrl+Shift+Z` | urungkan · ulangi |
| `Ctrl+N` `Ctrl+Shift+N` | tangkap area · tangkap jendela |
| `Ctrl+scroll` `Ctrl+0` `Ctrl+9` | zoom · 100% · sesuaikan jendela |

Di overlay pemilih area: seret untuk memilih, `Enter` atau tombol ✓ untuk
lanjut, `Esc` batal, `Ctrl+A` seluruh layar, panah untuk menggeser 1 px.

Catatan: titik di **tengah panah** yang sedang terpilih adalah handle pembengkok
(tarik untuk melengkungkan panah). Untuk menggeser panah, seret bagian batangnya
yang lain.

## Izin screenshot (sekali saja)

Saat pertama kali dipakai, sistem menanyakan **"Allow Jepret to Take Screenshots?"** —
pilih **Allow**. Jawaban itu disimpan permanen, dan tangkapan berikutnya berjalan senyap.

Detail teknis yang membuat ini tidak sepele: GNOME hanya mengizinkan dialog itu tampil
untuk aplikasi yang **sedang fokus**, sedangkan Jepret menyembunyikan jendelanya supaya
tidak ikut terpotret. Karena itu Jepret memeriksa dulu apakah izin sudah tersimpan
(lewat PermissionStore, memakai app id dari systemd scope). Bila belum, jendelanya
sengaja dibiarkan tampil agar dialog bisa muncul, lalu tangkapan diulang otomatis
dengan jendela disembunyikan.

Identitas aplikasi berbeda antara menjalankan dari menu GNOME (`id.jepret.Jepret`)
dan dari terminal (kosong), jadi dialog izin bisa muncul sekali untuk masing-masing.

## Cara kerja di Wayland

GNOME memblokir `org.gnome.Shell.Screenshot` untuk aplikasi biasa, jadi Jepret
memakai **xdg-desktop-portal** (`org.freedesktop.portal.Screenshot`).
Izin diminta sekali, lalu diingat sistem. Untuk mencabut izin itu:

```bash
gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore \
  --object-path /org/freedesktop/impl/portal/PermissionStore \
  --method org.freedesktop.impl.portal.PermissionStore.Delete screenshot screenshot
```

Karena Wayland tidak membuka geometri jendela ke aplikasi lain, mode **Jendela**
sengaja memakai pemilih bawaan GNOME agar batas jendela akurat.

## Struktur kode

| Berkas | Isi |
|---|---|
| `jepret/capture.py` | klien portal screenshot (pola request-handle D-Bus) |
| `jepret/overlay.py` | overlay pemilih area, satu jendela per monitor |
| `jepret/canvas.py` | kanvas editor + state machine interaksi tool |
| `jepret/items.py` | model objek anotasi (vektor, bisa diedit ulang) |
| `jepret/document.py` | gambar dasar + anotasi + crop, render resolusi penuh |
| `jepret/effects.py` | blur/pixelate via Pillow, konversi PIL↔cairo |
| `jepret/editor.py` | jendela editor, toolbar, bar properti, simpan/salin |
| `jepret/start.py` `gallery.py` | jendela awal dan riwayat |

## Menjalankan uji

```bash
python3 tests/selftest.py          # geometri, undo/redo, crop, ekspor
python3 tests/interaction_test.py  # alur tiap tool lewat gesture tiruan
python3 tests/capture_loop_test.py # satu permintaan = satu tangkapan
```

Uji interaksi dan uji tangkap memerlukan sesi grafis (GTK), dan akan melewati
dirinya sendiri bila dijalankan tanpa display.

## Lisensi

MIT — lihat [LICENSE](LICENSE).
