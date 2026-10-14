"""Per-user cache with read compatibility for the previous project-local paths."""

import json
from pathlib import Path

from hub.paths import APP_ROOT, DATA_DIR

BASE = APP_ROOT
PROJECTS = DATA_DIR / "projects"
THUMBNAILS = DATA_DIR / "thumbnails"
AVATARS = DATA_DIR / "avatars"
INDEX = DATA_DIR / "cache.json"
LEGACY_PROJECTS = BASE / "projects"
LEGACY_THUMBNAILS = BASE / "thumbnails"
LEGACY_AVATARS = BASE / "avatars"
LEGACY_INDEX = BASE / "cache.json"

for directory in (PROJECTS, THUMBNAILS, AVATARS):
    directory.mkdir(parents=True, exist_ok=True)


def load_index() -> dict:
    """Load XDG metadata over legacy metadata without losing old entries."""
    merged = {}
    for path in (LEGACY_INDEX, INDEX):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(data, dict):
            merged.update(data)
    return merged


def save_index(data: dict) -> None:
    """Write the index atomically."""
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_name("cache.json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX)


def project_path(project_id) -> Path:
    """Canonical per-user path, even when the bytes are project.json."""
    return PROJECTS / f"{project_id}.sb3"


def find_project_path(project_id) -> Path:
    """Find a project in the new cache or the legacy project-local directory."""
    current = project_path(project_id)
    if current.is_file():
        return current
    legacy = LEGACY_PROJECTS / current.name
    return legacy if legacy.is_file() else current


def thumbnail_path(project_id) -> Path:
    return THUMBNAILS / f"{project_id}.png"


def find_thumbnail_path(project_id) -> Path:
    current = thumbnail_path(project_id)
    if current.is_file():
        return current
    legacy = LEGACY_THUMBNAILS / current.name
    return legacy if legacy.is_file() else current


def avatar_path(creator_id) -> Path:
    return AVATARS / f"{creator_id}.png"


def find_avatar_path(creator_id) -> Path:
    current = avatar_path(creator_id)
    if current.is_file():
        return current
    legacy = LEGACY_AVATARS / current.name
    return legacy if legacy.is_file() else current


def is_cached(project_id) -> bool:
    path = find_project_path(project_id)
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


def cached_projects() -> list[dict]:
    """Return project cards from disk, including projects absent from the API."""
    index = load_index()
    found: dict[int, Path] = {}
    for directory in (PROJECTS, LEGACY_PROJECTS):
        try:
            for path in directory.glob("*.sb3"):
                if path.is_file() and path.stat().st_size > 0 and path.stem.isdigit():
                    found.setdefault(int(path.stem), path)
        except OSError:
            continue
    projects = []
    for project_id in sorted(found):
        entry = index.get(str(project_id), {})
        if not isinstance(entry, dict):
            entry = {}
        projects.append(
            {
                "id": project_id,
                "title": entry.get("title") or f"Proyecto {project_id}",
                "username": entry.get("username") or "",
                "creator_id": entry.get("creator_id") or 0,
                "image": entry.get("image") or "",
                "avatar": "",
            }
        )
    return projects


def clear_project_cache() -> int:
    """Delete cached project files while retaining thumbnails and avatars."""
    removed = 0
    for directory in (PROJECTS, LEGACY_PROJECTS):
        try:
            for path in directory.glob("*.sb3"):
                if path.is_file():
                    path.unlink()
                    removed += 1
        except OSError:
            continue
    save_index({})
    return removed


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