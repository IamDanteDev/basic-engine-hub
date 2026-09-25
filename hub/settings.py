"""Persistent app settings stored as JSON at the project root."""

import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PATH = BASE / "settings.json"
DEFAULTS = {"language": "es"}


def get(key, default=None):
    """Read ``key`` from settings.json; missing file/keys fall back to DEFAULTS.

    Read-only: never creates or modifies the file.
    """
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
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
        data = json.loads(PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[key] = value
    tmp = PATH.with_name("settings.json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, PATH)