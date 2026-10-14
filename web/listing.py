"""Basic Engine Hub — build the merged web project listing.

Single source of truth for the studio+user merge. It is used both by the
local server (serve.py route /api/listing) and by the GitHub Pages build,
where it writes ``listing.json`` next to the static site so the browser
menu can load it without CORS:

    studio + user, deduped by id (first occurrence wins, studio first)
    -> blocked ids removed
    -> missing pinned projects fetched and prepended at the front
    -> the featured project and programmatic pinned inserts are flagged
       (``featured``/``pinned``) so the browser menu can order and badge them

Python stdlib only (urllib). No third-party dependencies.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
import urllib.request
from pathlib import Path

_catalog = json.loads(
    (Path(__file__).resolve().parent.parent / "catalog.json").read_text(encoding="utf-8")
)
STUDIO_ID = str(_catalog["studio_id"])
SOURCE_USER = str(_catalog["source_user"])
BLOCKED_PROJECT_IDS = frozenset(map(int, _catalog["blocked_project_ids"]))
PINNED_PROJECT_IDS = frozenset(map(int, _catalog["pinned_project_ids"]))
FEATURED_PROJECT_ID = int(_catalog["featured_project_id"])

PAGE_SIZE = 40
MAX_ITEMS = 1000  # safety cap on total items fetched per endpoint
USER_AGENT = "BasicEngineHubWeb/0.1"
TIMEOUT = 15
DETAIL_WORKERS = 8

STUDIO_ENDPOINT = f"https://api.scratch.mit.edu/studios/{STUDIO_ID}/projects"
USER_ENDPOINT = f"https://api.scratch.mit.edu/users/{SOURCE_USER}/projects"


# --- Scratch API helpers ---------------------------------------------------


def fetch_json(url: str):
    """GET a Scratch API URL and return the parsed JSON.

    Raises RuntimeError for every failure mode (network error, non-200 HTTP
    status, bad JSON), so callers degrade gracefully without crashing.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - every failure becomes a safe error
        raise RuntimeError(f"error fetching {url}: {exc}") from exc


def fetch_paged(endpoint: str) -> list:
    """Fetch one paginated endpoint (?limit=40&offset=N) until a short page.

    Stops when a page returns fewer than PAGE_SIZE items; MAX_ITEMS caps
    runaway pagination from a misbehaving API.
    """
    items = []
    offset = 0
    while offset < MAX_ITEMS:
        page = fetch_json(f"{endpoint}?limit={PAGE_SIZE}&offset={offset}")
        if not isinstance(page, list):
            raise RuntimeError(f"unexpected payload from {endpoint}")
        items.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return items[:MAX_ITEMS]


def normalize(item: dict, fallback_username: str | None = None) -> dict | None:
    """Map one Scratch API item to {id,title,username,creator_id,image,avatar}.

    Mirrors hub/scratch_api.py, which handles three endpoint shapes:
    - Studio listing: FLAT fields — username, creator_id and avatar at the
      top level (avatar may be a dict with a "90x90" key).
    - User listing: nested author WITHOUT a username (every item belongs to
      SOURCE_USER, the fallback_username hint).
    - Single project: nested author WITH a username; image under "thumbnail"
      instead of "image".
    """
    try:
        pid = int(item["id"])
    except (KeyError, TypeError, ValueError):
        return None  # malformed item: skip it, never crash

    # Both image key names exist across endpoints; pick whichever is present.
    image = item.get("image") or item.get("thumbnail") or ""

    # Flat shape first (studio listing).
    username = item.get("username") or ""
    creator_id = item.get("creator_id")
    avatar = item.get("avatar")

    # Nested shape (user listing / single project) fills in the gaps.
    author = item.get("author")
    if isinstance(author, dict):
        username = username or author.get("username") or ""
        if creator_id is None:
            creator_id = author.get("id")
        if not avatar:
            profile = author.get("profile") or {}
            images = profile.get("images")
            if isinstance(images, dict):
                avatar = images.get("90x90") or ""

    if isinstance(avatar, dict):
        avatar = avatar.get("90x90") or ""

    try:
        creator_id = int(creator_id) if creator_id is not None else 0
    except (TypeError, ValueError):
        creator_id = 0

    return {
        "id": pid,
        "title": item.get("title") or "",
        "username": username or fallback_username or "",
        "creator_id": creator_id,
        "image": image,
        "avatar": avatar or "",
    }


def _detail_fields(project_id: int) -> dict:
    payload = fetch_json(f"https://api.scratch.mit.edu/projects/{project_id}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected project detail payload: {project_id}")
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}

    def count(name: str) -> int:
        try:
            return int(stats.get(name) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "description": str(payload.get("description") or ""),
        "instructions": str(payload.get("instructions") or ""),
        "comments_allowed": bool(payload.get("comments_allowed")),
        "stats": {
            "views": count("views"),
            "loves": count("loves"),
            "favorites": count("favorites"),
            "remixes": count("remixes"),
        },
    }


def _enrich_details(projects: list[dict]) -> list[dict]:
    """Add detail data best-effort for static hosting, where Scratch CORS blocks fetches."""
    if not projects:
        return projects
    with ThreadPoolExecutor(max_workers=min(DETAIL_WORKERS, len(projects))) as pool:
        futures = {
            pool.submit(_detail_fields, int(project["id"])): project
            for project in projects
        }
        for future in as_completed(futures):
            try:
                futures[future].update(future.result())
            except Exception:  # noqa: BLE001 - metadata should not block Pages deployment
                continue
    return projects


def build_listing(include_details: bool = False) -> list:
    """Build the final ordered listing (see module docstring for the order).

    Best-effort per source, like the desktop worker: one failing source must
    not hide the other. Raises RuntimeError only when nothing at all could be
    fetched (the HTTP route then answers 502; the Pages build fails loudly).
    """
    seen = set()
    unique = []
    any_error = ""
    for endpoint, fallback in (
        (STUDIO_ENDPOINT, None),
        (USER_ENDPOINT, SOURCE_USER),
    ):
        try:
            page = fetch_paged(endpoint)
        except RuntimeError as exc:
            any_error = str(exc)
            continue
        for item in page:
            project = normalize(item, fallback)
            if project is None or project["id"] in seen:
                continue  # dedupe by id, keeping the first occurrence
            seen.add(project["id"])
            unique.append(project)

    if not unique and any_error:
        raise RuntimeError(any_error)

    listing = [p for p in unique if p["id"] not in BLOCKED_PROJECT_IDS]
    existing = {p["id"] for p in listing}
    for pid in sorted(PINNED_PROJECT_IDS):
        if pid in existing:
            continue
        try:
            pinned = normalize(
                fetch_json(f"https://api.scratch.mit.edu/projects/{pid}")
            )
        except RuntimeError:
            continue  # best-effort: a failed pinned fetch must not hide the listing
        if pinned is not None:
            pinned["pinned"] = True
            listing.insert(0, pinned)
    for project in listing:
        if project["id"] == FEATURED_PROJECT_ID:
            project["featured"] = True
    return _enrich_details(listing) if include_details else listing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the merged Basic Engine Hub web listing (JSON)."
    )
    parser.add_argument(
        "--out",
        default="listing.json",
        help="output path for the merged listing (default: listing.json)",
    )
    parser.add_argument(
        "--with-details",
        action="store_true",
        help="include descriptions, instructions, and stats for static hosting",
    )
    args = parser.parse_args()

    try:
        listing = build_listing(include_details=args.with_details)
    except RuntimeError as exc:
        print(f"error building listing: {exc}", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(listing, handle, ensure_ascii=False, indent=1)
    print(f"wrote {len(listing)} projects to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())