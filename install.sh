#!/usr/bin/env bash
# Pasang Jepret ke menu aplikasi GNOME (tanpa root).
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$BIN" "$APPS" "$ICONS"

ln -sf "$SRC/jepret-run" "$BIN/jepret"
install -m 644 "$SRC/data/icons/id.jepret.Jepret.svg" "$ICONS/id.jepret.Jepret.svg"
sed "s|JEPRET_EXEC|$SRC/jepret-run|g" "$SRC/data/jepret.desktop" > "$APPS/id.jepret.Jepret.desktop"
chmod 644 "$APPS/id.jepret.Jepret.desktop"

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -qtf "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Jepret terpasang."
echo "  Menu aplikasi : cari 'Jepret'"
echo "  Terminal      : jepret --area | --window | --full"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "  Catatan: tambahkan $BIN ke PATH agar perintah 'jepret' dikenali." ;;
esac
