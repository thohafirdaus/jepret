#!/usr/bin/env bash
# Bangun paket siap edar: .deb (Ubuntu/Debian) dan tarball (distro lain).
# Tidak perlu root, tidak perlu toolchain khusus — aplikasinya murni Python.
#
#   ./packaging/build.sh            -> dist/jepret_<versi>_all.deb + dist/jepret-<versi>.tar.gz
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$SRC/dist"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$SRC'); import jepret; print(jepret.VERSION)")"
PKG="jepret_${VERSION}_all"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

echo "Membangun Jepret $VERSION"
rm -rf "$DIST"
mkdir -p "$DIST"

# ---------------------------------------------------------------- isi paket
ROOT="$BUILD/$PKG"
install -d "$ROOT/usr/share/jepret/jepret" \
           "$ROOT/usr/share/jepret/data" \
           "$ROOT/usr/bin" \
           "$ROOT/usr/share/applications" \
           "$ROOT/usr/share/icons/hicolor/scalable/apps" \
           "$ROOT/usr/share/doc/jepret" \
           "$ROOT/DEBIAN"

install -m 644 "$SRC"/jepret/*.py "$ROOT/usr/share/jepret/jepret/"
cp -r "$SRC/data/icons" "$ROOT/usr/share/jepret/data/"
install -m 644 "$SRC/data/icons/id.jepret.Jepret.svg" \
               "$ROOT/usr/share/icons/hicolor/scalable/apps/id.jepret.Jepret.svg"
install -m 644 "$SRC/README.md" "$SRC/LICENSE" "$ROOT/usr/share/doc/jepret/"

cat > "$ROOT/usr/bin/jepret" <<'LAUNCHER'
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/jepret${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m jepret "$@"
LAUNCHER
chmod 755 "$ROOT/usr/bin/jepret"

sed 's|JEPRET_EXEC|/usr/bin/jepret|g' "$SRC/data/jepret.desktop" \
    > "$ROOT/usr/share/applications/id.jepret.Jepret.desktop"
chmod 644 "$ROOT/usr/share/applications/id.jepret.Jepret.desktop"

# ------------------------------------------------------------------ kontrol
cat > "$ROOT/DEBIAN/control" <<CONTROL
Package: jepret
Version: $VERSION
Section: graphics
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0,
 gir1.2-adw-1, python3-pil, xdg-desktop-portal
Recommends: wl-clipboard, xdg-desktop-portal-gnome
Maintainer: Thoha Firdaus <fius.28januari@gmail.com>
Homepage: https://github.com/thohafirdaus/jepret
Description: Screenshot dengan editor anotasi untuk GNOME/Wayland
 Tangkap area, jendela, atau layar penuh lewat xdg-desktop-portal, lalu
 anotasi sebelum disimpan: panah, nomor urut otomatis, teks, kotak, elips,
 pena, stabilo, blur/pixelate, dan crop non-destruktif. Setiap objek tetap
 bisa dipilih, digeser, dan diubah, dengan undo/redo tak terbatas.
 .
 Hasilnya disimpan sebagai PNG/JPEG/WebP pada resolusi penuh, atau disalin
 langsung ke clipboard.
CONTROL

cat > "$ROOT/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    [ -x "$(command -v update-desktop-database)" ] && \
        update-desktop-database -q /usr/share/applications || true
    [ -x "$(command -v gtk-update-icon-cache)" ] && \
        gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
fi
exit 0
POSTINST
chmod 755 "$ROOT/DEBIAN/postinst"

cp "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"

# --------------------------------------------------------------------- deb
dpkg-deb --build --root-owner-group "$ROOT" "$DIST/$PKG.deb" >/dev/null
echo "  dist/$PKG.deb"

# ----------------------------------------------------------------- tarball
TAR="jepret-$VERSION"
install -d "$BUILD/$TAR"
cp -r "$SRC/jepret" "$SRC/data" "$SRC/tests" "$SRC/install.sh" \
      "$SRC/jepret-run" "$SRC/README.md" "$SRC/LICENSE" "$BUILD/$TAR/"
rm -rf "$BUILD/$TAR/jepret/__pycache__" "$BUILD/$TAR/tests/__pycache__"
tar -czf "$DIST/$TAR.tar.gz" -C "$BUILD" "$TAR"
echo "  dist/$TAR.tar.gz"

( cd "$DIST" && sha256sum ./*.deb ./*.tar.gz > SHA256SUMS )
echo "  dist/SHA256SUMS"
