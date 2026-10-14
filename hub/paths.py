"""Application resource and per-user data locations."""

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent


def _xdg_path(variable: str, fallback: Path) -> Path:
    configured = os.environ.get(variable)
    path = Path(configured).expanduser() if configured else fallback
    return path if path.is_absolute() else fallback


DATA_DIR = _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share") / "basic-engine-hub"
CONFIG_DIR = _xdg_path("XDG_CONFIG_HOME", Path.home() / ".config") / "basic-engine-hub"