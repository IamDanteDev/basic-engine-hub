"""Basic Engine Hub — build the merged web project listing.

Single source of truth for the studio+user merge. It is used both by the
local server (serve.py route /api/listing) and by the GitHub Pages build,
where it writes ``listing.json`` next to the static site so the browser
menu can load it without CORS:

    studio + user, deduped by id (first occurrence wins, studio first)
    -> blocked ids removed
    -> missing pinned projects fetched and prepended at the front

Python stdlib only (urllib). No third-party dependencies.
"""

import argparse
import json
import sys
import urllib.request

# --- Constants (mirror hub/gui.py) ----------------------------------------

STUDIO_ID = "35865803"
SOURCE_USER = "Alvaro_Games19"

# Test/scratch projects the user asked to hide from the menu.
BLOCKED_PROJECT_IDS = frozenset(
    {
        1383138050, 1369017039, 1368016306, 1323323065, 1310326945,
        1198347181, 1189578716, 1186588783, 1198685482, 1174546565, 1245982356,
        1187594776, 1220979078, 1121241960, 400240654, 1201842653,
    }
)

# Extra projects to pin at the front of the menu even when NOT in the studio.
PINNED_PROJECT_IDS = frozenset({1192855606})

PAGE_SIZE = 40
MAX_ITEMS = 1000  # safety cap on total items fetched per endpoint
USER_AGENT = "BasicEngineHubWeb/0.1"
TIMEOUT = 15

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


def build_listing() -> list:
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
            listing.insert(0, pinned)
    return listing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the merged Basic Engine Hub web listing (JSON)."
    )
    parser.add_argument(
        "--out",
        default="listing.json",
        help="output path for the merged listing (default: listing.json)",
    )
    args = parser.parse_args()

    try:
        listing = build_listing()
    except RuntimeError as exc:
        print(f"error building listing: {exc}", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(listing, handle, ensure_ascii=False, indent=1)
    print(f"wrote {len(listing)} projects to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())