"""Preferensi sederhana, disimpan sebagai JSON di ~/.config/jepret/config.json."""

import json
import os
import subprocess
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jepret"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "save_dir": "",              # kosong = <Pictures>/Screenshots
    "filename_pattern": "Screenshot_%Y-%m-%d_%H-%M-%S",
    "default_format": "png",
    "jpeg_quality": 92,
    "include_cursor": False,
    "color": "#e01b24",
    "stroke_width": 4.0,
    "font_size": 24.0,
    "badge_style": "circle",
    "copy_after_save": False,
    "close_after_copy": False,
    "last_tool": "arrow",
}


def _pictures_dir():
    try:
        out = subprocess.run(
            ["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
        if out:
            return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Pictures"


LEGACY_FILE = CONFIG_DIR.parent / "snapix" / "config.json"


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        source = CONFIG_FILE if CONFIG_FILE.exists() else LEGACY_FILE
        try:
            self.update(json.loads(source.read_text()))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self, indent=2))
        except OSError:
            pass

    @property
    def save_dir(self) -> Path:
        path = Path(self["save_dir"]).expanduser() if self["save_dir"] else _pictures_dir() / "Screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path


config = Config()
