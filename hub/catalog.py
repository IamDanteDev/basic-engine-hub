"""Shared project-listing configuration for the desktop and web menus."""

import json

from hub.paths import APP_ROOT

with (APP_ROOT / "catalog.json").open(encoding="utf-8") as _catalog_file:
    _catalog = json.load(_catalog_file)

STUDIO_ID = str(_catalog["studio_id"])
SOURCE_USER = str(_catalog["source_user"])
BLOCKED_PROJECT_IDS = frozenset(map(int, _catalog["blocked_project_ids"]))
PINNED_PROJECT_IDS = frozenset(map(int, _catalog["pinned_project_ids"]))
FEATURED_PROJECT_ID = int(_catalog["featured_project_id"])