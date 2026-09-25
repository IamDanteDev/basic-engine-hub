"""Local cache: projects/, thumbnails/ directories and the cache.json index."""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROJECTS = BASE / "projects"
THUMBNAILS = BASE / "thumbnails"
AVATARS = BASE / "avatars"
INDEX = BASE / "cache.json"

PROJECTS.mkdir(exist_ok=True)
THUMBNAILS.mkdir(exist_ok=True)
AVATARS.mkdir(exist_ok=True)


def load_index() -> dict:
    """Load the cache index; never raises (missing/corrupt -> {})."""
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_index(data: dict) -> None:
    """Write the index atomically-ish (temp file then replace)."""
    tmp = INDEX.with_name("cache.json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX)


def project_path(project_id) -> Path:
    """Canonical cache path: projects/<id>.sb3 (even when bytes are project.json)."""
    return PROJECTS / f"{project_id}.sb3"


def thumbnail_path(project_id) -> Path:
    return THUMBNAILS / f"{project_id}.png"


def avatar_path(creator_id) -> Path:
    return AVATARS / f"{creator_id}.png"


def is_cached(project_id) -> bool:
    path = project_path(project_id)
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def detect_format(data: bytes) -> str:
    """Classify downloaded bytes: sb3-zip, project-json or unknown."""
    if data.startswith(b"PK\x03\x04"):
        return "sb3-zip"
    if data.lstrip().startswith(b"{"):
        return "project-json"
    return "unknown"


def cache_status(project_id) -> str:
    return "cached" if is_cached(project_id) else "missing"


def record_entry(project_id, **fields) -> None:
    """Merge ``fields`` into the index entry for ``project_id`` and save.

    Existing keys not passed are kept, so listing refreshes never wipe
    download records.
    """
    index = load_index()
    key = str(project_id)
    entry = dict(index.get(key, {}))
    entry.update(fields)
    index[key] = entry
    save_index(index)


def update_entry(project_id, **fields) -> None:
    """Alias of :func:`record_entry` (merge-and-save behavior)."""
    record_entry(project_id, **fields)