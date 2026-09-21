"""Pintasan keyboard global lewat pengaturan GNOME.

GNOME menyimpan pintasan khusus di dua tempat:

* daftar path di `org.gnome.settings-daemon.plugins.media-keys custom-keybindings`
* isi tiap pintasan di schema relokatable `...media-keys.custom-keybinding`
  pada path tersebut (name, command, binding)

Modul ini membungkus keduanya, plus tombol Print Screen bawaan GNOME yang
harus dikosongkan dulu kalau mau dipakai Jepret.
"""

import os
import shutil
from pathlib import Path

from gi.repository import Gio, GLib

MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
CUSTOM_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
SHELL_SCHEMA = "org.gnome.shell.keybindings"

# aksi yang bisa diberi pintasan: (id, judul, argumen CLI)
ACTIONS = [
    ("area", "Tangkap area", "--area"),
    ("window", "Tangkap jendela", "--window"),
    ("full", "Tangkap layar penuh", "--full"),
]

# pintasan bawaan GNOME yang memakai tombol Print Screen
SHELL_SCREENSHOT_KEYS = ("show-screenshot-ui", "screenshot", "screenshot-window")

# nama aplikasi sebelumnya; pintasannya perlu dipindahkan ke path baru
LEGACY_NAMES = ("snapix",)


def _schema_exists(schema_id):
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(schema_id, True) is not None


def available() -> bool:
    """Apakah pengaturan pintasan GNOME bisa diubah dari sini?"""
    return _schema_exists(MEDIA_KEYS_SCHEMA) and _schema_exists(CUSTOM_SCHEMA)


def launcher_command(action_args: str) -> str:
    """Perintah yang dijalankan pintasan.

    Pakai `jepret` di ~/.local/bin bila sudah dipasang install.sh, kalau tidak
    pakai path absolut ke launcher di folder sumber.
    """
    installed = Path.home() / ".local" / "bin" / "jepret"
    if installed.exists():
        base = shutil.which("jepret") or str(installed)
    else:
        base = str(Path(__file__).resolve().parent.parent / "jepret-run")
    return f"{base} {action_args}".strip()


def _path_for(action_id):
    return f"{CUSTOM_PATH}jepret-{action_id}/"


def _custom_settings(action_id):
    return Gio.Settings.new_with_path(CUSTOM_SCHEMA, _path_for(action_id))


def _registered_paths():
    return list(Gio.Settings.new(MEDIA_KEYS_SCHEMA).get_strv("custom-keybindings"))


def _register(path, present=True):
    settings = Gio.Settings.new(MEDIA_KEYS_SCHEMA)
    paths = list(settings.get_strv("custom-keybindings"))
    if present and path not in paths:
        paths.append(path)
    elif not present and path in paths:
        paths.remove(path)
    else:
        return
    settings.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()


def _settings_at(path):
    return Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)


def _clear_path(path):
    settings = _settings_at(path)
    for key in ("name", "command", "binding"):
        settings.reset(key)
    _register(path, present=False)


def custom_binding_conflicts(accelerator, exclude_action=None):
    """Pintasan khusus lain (milik aplikasi apa pun) yang memakai kombinasi sama."""
    if not available() or not accelerator:
        return []
    skip = _path_for(exclude_action) if exclude_action else None
    found = []
    for path in _registered_paths():
        if path == skip:
            continue
        settings = _settings_at(path)
        if settings.get_string("binding") == accelerator:
            found.append((path, settings.get_string("name") or path))
    return found


def release_custom_binding(path):
    """Kosongkan satu pintasan khusus supaya kombinasinya bisa dipakai ulang."""
    _clear_path(path)


def migrate_legacy() -> list:
    """Pindahkan pintasan dari nama aplikasi lama ke path & perintah sekarang.

    Entri lama tidak cuma mati (perintahnya sudah tidak ada), tapi juga
    menahan kombinasi tombolnya sehingga tidak bisa dipasang ulang.
    """
    if not available():
        return []
    moved = []
    registered = _registered_paths()
    for action_id, title, args in ACTIONS:
        for legacy in LEGACY_NAMES:
            old_path = f"{CUSTOM_PATH}{legacy}-{action_id}/"
            if old_path not in registered:
                continue
            accelerator = _settings_at(old_path).get_string("binding")
            _clear_path(old_path)          # bebaskan kombinasinya dulu
            if accelerator and not get_binding(action_id):
                set_binding(action_id, accelerator, title, args)
                moved.append((title, accelerator))
    return moved


def get_binding(action_id) -> str:
    """Kembalikan akselerator terpasang, atau string kosong."""
    if not available() or _path_for(action_id) not in _registered_paths():
        return ""
    return _custom_settings(action_id).get_string("binding")


def set_binding(action_id, accelerator, title, args) -> None:
    """Pasang (atau hapus bila accelerator kosong) pintasan untuk satu aksi."""
    if not available():
        return
    path = _path_for(action_id)
    if not accelerator:
        settings = _custom_settings(action_id)
        for key in ("name", "command", "binding"):
            settings.reset(key)
        _register(path, present=False)
        return
    settings = _custom_settings(action_id)
    settings.set_string("name", f"Jepret — {title}")
    settings.set_string("command", launcher_command(args))
    settings.set_string("binding", accelerator)
    _register(path, present=True)
    Gio.Settings.sync()


def conflicting_gnome_keys(accelerator):
    """Pintasan screenshot bawaan GNOME yang memakai kombinasi sama."""
    if not accelerator or not _schema_exists(SHELL_SCHEMA):
        return []
    settings = Gio.Settings.new(SHELL_SCHEMA)
    clashes = []
    for key in SHELL_SCREENSHOT_KEYS:
        try:
            if accelerator in settings.get_strv(key):
                clashes.append(key)
        except GLib.Error:
            continue
    return clashes


def release_gnome_keys(accelerator) -> list:
    """Kosongkan pintasan bawaan GNOME yang bentrok; kembalikan yang diubah."""
    released = []
    if not _schema_exists(SHELL_SCHEMA):
        return released
    settings = Gio.Settings.new(SHELL_SCHEMA)
    for key in conflicting_gnome_keys(accelerator):
        values = [v for v in settings.get_strv(key) if v != accelerator]
        settings.set_strv(key, values)
        released.append(key)
    Gio.Settings.sync()
    return released


def restore_gnome_defaults() -> None:
    """Kembalikan pintasan screenshot bawaan GNOME ke setelan pabrik."""
    if not _schema_exists(SHELL_SCHEMA):
        return
    settings = Gio.Settings.new(SHELL_SCHEMA)
    for key in SHELL_SCREENSHOT_KEYS:
        settings.reset(key)
    Gio.Settings.sync()


def gnome_defaults_modified() -> bool:
    if not _schema_exists(SHELL_SCHEMA):
        return False
    settings = Gio.Settings.new(SHELL_SCHEMA)
    return any(settings.get_user_value(key) is not None for key in SHELL_SCREENSHOT_KEYS)


def clear_all() -> None:
    for action_id, _title, _args in ACTIONS:
        set_binding(action_id, "", "", "")
    restore_gnome_defaults()
