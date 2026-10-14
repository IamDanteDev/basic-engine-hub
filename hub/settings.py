"""Persistent app settings stored in the user's XDG config directory."""

import json
import os
from hub.paths import APP_ROOT, CONFIG_DIR

PATH = CONFIG_DIR / "settings.json"
LEGACY_PATH = APP_ROOT / "settings.json"
DEFAULTS = {"language": "es"}


def get(key, default=None):
    """Read ``key`` from settings.json; missing file/keys fall back to DEFAULTS.

    Read-only: never creates or modifies the file.
    """
    try:
        source = PATH if PATH.is_file() else LEGACY_PATH
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    return data.get(key, DEFAULTS.get(key, default))


def set(key, value) -> None:
    """Persist ``key`` atomically (temp file + os.replace).

    Creates settings.json on first write; single-process, UI-thread writes
    only, so no locking is needed.
    """
    try:
        source = PATH if PATH.is_file() else LEGACY_PATH
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[key] = value
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_name("settings.json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, PATH)