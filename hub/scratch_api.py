"""Scratch API client: studio listing, project tokens, downloads and thumbnails.

Every network/API failure in this module raises :class:`ScratchAPIError` with a
friendly Spanish message inside ``str(exc)`` — that is the only exception the
GUI needs to catch.
"""

from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from hub import cache, i18n

API = "https://api.scratch.mit.edu"
PROJECTS_CDN = "https://projects.scratch.mit.edu"
ASSETS = "https://assets.scratch.mit.edu"
COMMENTS_API = "https://scratch.mit.edu/site-api/comments/project/{project_id}/"
USER_AGENT = "BasicEngineHub/0.2"
# The comments endpoint is a public HTML fragment; it expects a browser UA.
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TIMEOUT_LISTING = 15
TIMEOUT_DOWNLOAD = 60
TIMEOUT_THUMBNAIL = 20


def _as_int(value) -> int:
    """Coerce ``value`` to int; anything unparseable becomes 0."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _comment_block(block) -> dict | None:
    """Extract {comment_id, user, content, timestamp} from one comment <li>.

    Returns None when the block lacks any of the four expected nodes.
    """
    comment_div = block.select_one("div.comment")
    user_node = block.select_one("a#comment-user")
    content_node = block.select_one("div.content")
    time_node = block.select_one("span.time")
    if (
        comment_div is None
        or user_node is None
        or content_node is None
        or time_node is None
    ):
        return None
    return {
        "comment_id": comment_div.get("data-comment-id"),
        "user": user_node.get("data-comment-user"),
        "content": content_node.get_text(strip=True),
        "timestamp": time_node.get("title"),
    }


class ScratchAPIError(Exception):
    """Raised on any network/API failure while talking to Scratch."""


def _headers() -> dict:
    return {"User-Agent": USER_AGENT}


def _http_error(action: str, response: requests.Response) -> ScratchAPIError:
    return ScratchAPIError(
        i18n.tr("scratch_http_error", code=response.status_code, action=action)
    )


def studio_projects(studio_id, limit: int = 40, max_projects: int = 1000) -> list[dict]:
    """Return the studio's project listing, normalized per project.

    The Scratch API paginates at ``limit`` items per request, so this fetches
    pages (offset 0, limit, 2*limit, ...) until a page returns fewer items or
    ``max_projects`` is reached (safety valve against a misbehaving API).

    Each item is a dict with at least: id, title, username, creator_id, image.
    """
    url = f"{API}/studios/{studio_id}/projects"
    raw_items: list[dict] = []
    offset = 0
    while offset < max_projects:
        try:
            response = requests.get(
                url,
                params={"limit": limit, "offset": offset},
                timeout=TIMEOUT_LISTING,
                headers=_headers(),
            )
        except requests.RequestException as exc:
            raise ScratchAPIError(i18n.tr("scratch_contact", exc=exc)) from exc
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise _http_error(i18n.tr("scratch_http_action_list"), response) from exc
        try:
            items = response.json()
        except ValueError as exc:
            raise ScratchAPIError(i18n.tr("scratch_invalid_response")) from exc
        page = items or []
        raw_items.extend(page)
        if len(page) < limit:
            break
        offset += limit
    normalized: list[dict] = []
    for item in raw_items:
        try:
            raw_avatar = item.get("avatar")
            if isinstance(raw_avatar, dict):
                avatar = raw_avatar.get("90x90") or ""
            elif isinstance(raw_avatar, str):
                avatar = raw_avatar
            else:
                avatar = ""
            normalized.append(
                {
                    "id": int(item["id"]),
                    "title": item.get("title") or i18n.tr("project_default_title", pid=item["id"]),
                    "username": item.get("username") or "",
                    "creator_id": int(item.get("creator_id") or 0),
                    "image": item.get("image") or "",
                    "actor_id": item.get("actor_id"),
                    "avatar": avatar,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ScratchAPIError(i18n.tr("scratch_incomplete")) from exc
    return normalized


def _normalize_project_payload(payload: dict, username_hint: str = "") -> dict:
    """Normalize a full single-project payload (nested ``author``) to menu shape.

    The single-project and user-listing endpoints both return ``author`` as a
    nested dict and the image under ``thumbnail`` (or ``image``); the studio
    listing endpoint uses flat ``username``/``creator_id`` and is normalized
    separately in :func:`studio_projects`. ``username_hint`` covers the
    user-listing endpoint, whose ``author`` dict omits ``username`` (all listed
    projects belong to the requested user). The avatar lives at
    ``author.profile.images.90x90``. Raises KeyError when ``id`` is missing;
    callers wrap it in :class:`ScratchAPIError`.
    """
    author = payload.get("author") or {}
    raw_creator = author.get("id") if isinstance(author, dict) else None
    username = ""
    avatar = ""
    if isinstance(author, dict):
        username = author.get("username") or username_hint or ""
        profile = author.get("profile") or {}
        images = profile.get("images") if isinstance(profile, dict) else None
        if isinstance(images, dict):
            avatar = images.get("90x90") or ""
    return {
        "id": int(payload["id"]),
        "title": payload.get("title") or i18n.tr("project_default_title", pid=payload["id"]),
        "username": username,
        "creator_id": int(raw_creator or 0),
        "image": payload.get("thumbnail") or payload.get("image") or "",
        "actor_id": None,
        "avatar": avatar,
    }


def user_projects(username, limit: int = 40, max_projects: int = 1000) -> list[dict]:
    """Return the user's project listing, normalized per project.

    Paginates /users/{username}/projects (offset 0, limit, 2*limit, ...) until a
    page returns fewer items or max_projects is reached. Items use the full
    single-project payload shape, so each is normalized like fetch_project.
    """
    url = f"{API}/users/{username}/projects"
    raw_items: list[dict] = []
    offset = 0
    while offset < max_projects:
        try:
            response = requests.get(
                url,
                params={"limit": limit, "offset": offset},
                timeout=TIMEOUT_LISTING,
                headers=_headers(),
            )
        except requests.RequestException as exc:
            raise ScratchAPIError(i18n.tr("scratch_contact", exc=exc)) from exc
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise _http_error(i18n.tr("scratch_http_action_user"), response) from exc
        try:
            items = response.json()
        except ValueError as exc:
            raise ScratchAPIError(i18n.tr("scratch_invalid_response")) from exc
        page = items or []
        raw_items.extend(page)
        if len(page) < limit:
            break
        offset += limit
    normalized: list[dict] = []
    for item in raw_items:
        try:
            normalized.append(_normalize_project_payload(item, username_hint=username))
        except (KeyError, TypeError, ValueError) as exc:
            raise ScratchAPIError(i18n.tr("scratch_incomplete")) from exc
    return normalized


def fetch_project(project_id) -> dict:
    """Fetch a single project's metadata, normalized like studio_projects items.

    The single-project endpoint returns a different payload shape (author is a
    nested dict and the image lives under ``thumbnail``), so this normalizes it
    to the exact dict shape used by the menu cards.
    """
    url = f"{API}/projects/{project_id}"
    try:
        response = requests.get(url, timeout=TIMEOUT_LISTING, headers=_headers())
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_project_error", project_id=project_id, exc=exc)
        ) from exc
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _http_error(i18n.tr("scratch_http_action_project"), response) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_project_invalid", project_id=project_id)
        ) from exc
    if not isinstance(payload, dict) or not payload.get("id"):
        raise ScratchAPIError(
            i18n.tr("scratch_project_invalid", project_id=project_id)
        )
    return _normalize_project_payload(payload)


def fetch_project_detail(project_id) -> dict:
    """Fetch a single project's extended metadata for the detail dialog.

    Returns the listing fields plus instructions, description, stats and
    comments_allowed. Raises :class:`ScratchAPIError` on any network/API/JSON
    failure, mirroring :func:`fetch_project`.
    """
    url = f"{API}/projects/{project_id}"
    try:
        response = requests.get(url, timeout=TIMEOUT_LISTING, headers=_headers())
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_project_error", project_id=project_id, exc=exc)
        ) from exc
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _http_error(i18n.tr("scratch_http_action_project"), response) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_project_invalid", project_id=project_id)
        ) from exc
    if not isinstance(payload, dict) or not payload.get("id"):
        raise ScratchAPIError(
            i18n.tr("scratch_project_invalid", project_id=project_id)
        )
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    author_id = _as_int(author.get("id"))
    stats_raw = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    return {
        "id": int(payload["id"]),
        "title": payload.get("title")
        or i18n.tr("project_default_title", pid=payload["id"]),
        "username": author.get("username") or "",
        "creator_id": author_id,
        "author_id": author_id,
        "image": payload.get("thumbnail") or payload.get("image") or "",
        "instructions": str(payload.get("instructions") or ""),
        "description": str(payload.get("description") or ""),
        "stats": {
            "views": _as_int(stats_raw.get("views")),
            "loves": _as_int(stats_raw.get("loves")),
            "favorites": _as_int(stats_raw.get("favorites")),
            "remixes": _as_int(stats_raw.get("remixes")),
        },
        "comments_allowed": bool(payload.get("comments_allowed")),
    }


def fetch_user_profile(username) -> dict:
    """Fetch a Scratch user's public profile for the signed-in user's own view.

    The browser cannot call this endpoint (no CORS headers), which is why the web
    side shows a username and nothing else; the desktop app talks to it from
    Python, so the signed-in user's avatar and description live here.

    Returns id, username, avatar (the 90x90 image), bio, status, country and the
    raw joined timestamp. Raises :class:`ScratchAPIError` on any network/API/JSON
    failure, mirroring :func:`fetch_project_detail`.
    """
    url = f"{API}/users/{username}"
    try:
        response = requests.get(url, timeout=TIMEOUT_LISTING, headers=_headers())
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_profile_error", username=username, exc=exc)
        ) from exc
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _http_error(i18n.tr("scratch_http_action_profile"), response) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_profile_invalid", username=username)
        ) from exc
    if not isinstance(payload, dict) or not payload.get("username"):
        raise ScratchAPIError(i18n.tr("scratch_profile_invalid", username=username))
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    images = profile.get("images") if isinstance(profile.get("images"), dict) else {}
    history = payload.get("history") if isinstance(payload.get("history"), dict) else {}
    return {
        "id": _as_int(payload.get("id")),
        "username": str(payload.get("username") or ""),
        "avatar": str(images.get("90x90") or ""),
        "bio": str(profile.get("bio") or ""),
        "status": str(profile.get("status") or ""),
        "country": str(profile.get("country") or ""),
        "joined": str(history.get("joined") or ""),
    }


def fetch_project_comments(project_id) -> list[dict]:
    """Fetch one page of the project's public comments (best-effort).

    The public site-api endpoint returns an HTML fragment without auth; the
    api.scratch.mit.edu comments endpoint 404s without a session token, so it
    is never used. Comments are purely additive: ANY transport or parse
    failure returns [] and this never raises.
    """
    try:
        response = requests.get(
            COMMENTS_API.format(project_id=project_id),
            params={"page": 1},
            timeout=TIMEOUT_THUMBNAIL,
            headers={"User-Agent": BROWSER_UA},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        comments: list[dict] = []
        for block in soup.select("li.top-level-reply"):
            comment = _comment_block(block)
            if comment is None:
                continue
            replies: list[dict] = []
            for reply_block in block.select("li.reply"):
                reply = _comment_block(reply_block)
                if reply is not None:
                    replies.append(reply)
            comment["replies"] = replies
            comments.append(comment)
        return comments
    except Exception:  # noqa: BLE001 - comments never break the dialog
        return []


def project_token(project_id) -> str:
    """Fetch the project metadata and return its ``project_token``."""
    url = f"{API}/projects/{project_id}"
    try:
        response = requests.get(url, timeout=TIMEOUT_DOWNLOAD, headers=_headers())
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_token_error", project_id=project_id, exc=exc)
        ) from exc
    except ValueError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_token_invalid", project_id=project_id)
        ) from exc
    token = (payload or {}).get("project_token") or ""
    if not token:
        raise ScratchAPIError(
            i18n.tr("scratch_no_token", project_id=project_id)
        )
    return token


def download_project_bytes(project_id) -> bytes:
    """Download the raw project bytes (sb3 zip OR raw project.json body)."""
    token = project_token(project_id)
    url = f"{PROJECTS_CDN}/{project_id}?token={token}"
    try:
        response = requests.get(url, timeout=TIMEOUT_DOWNLOAD, headers=_headers())
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_download_error", project_id=project_id, exc=exc)
        ) from exc
    if not response.content:
        raise ScratchAPIError(
            i18n.tr("scratch_downloaded_empty", project_id=project_id)
        )
    return response.content


def download_thumbnail(project_id, image_url: str, destination: Path) -> None:
    """Download a project thumbnail PNG to ``destination``.

    A thumbnail failure raises :class:`ScratchAPIError`; the GUI catches it and
    keeps the placeholder icon.
    """
    try:
        response = requests.get(
            image_url,
            timeout=TIMEOUT_THUMBNAIL,
            stream=True,
            headers=_headers(),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_thumb_error", project_id=project_id, exc=exc)
        ) from exc
    try:
        with open(destination, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
    except OSError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_thumb_save_error", project_id=project_id, exc=exc)
        ) from exc
    try:
        empty = destination.stat().st_size == 0
    except OSError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_thumb_save2_error", project_id=project_id, exc=exc)
        ) from exc
    if empty:
        destination.unlink(missing_ok=True)
        raise ScratchAPIError(
            i18n.tr("scratch_thumb_empty", project_id=project_id)
        )


def download_avatar(creator_id, avatar_url: str, destination: Path) -> None:
    """Download a creator avatar PNG to ``destination``.

    A download failure raises :class:`ScratchAPIError`; the GUI catches it and
    keeps the placeholder avatar. Cached per creator_id, so projects sharing a
    creator dedupe to a single file.
    """
    try:
        response = requests.get(
            avatar_url,
            timeout=TIMEOUT_THUMBNAIL,
            stream=True,
            headers=_headers(),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_avatar_error", creator_id=creator_id, exc=exc)
        ) from exc
    try:
        with open(destination, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
    except OSError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_avatar_save_error", creator_id=creator_id, exc=exc)
        ) from exc
    try:
        empty = destination.stat().st_size == 0
    except OSError as exc:
        raise ScratchAPIError(
            i18n.tr("scratch_avatar_save2_error", creator_id=creator_id, exc=exc)
        ) from exc
    if empty:
        destination.unlink(missing_ok=True)
        raise ScratchAPIError(
            i18n.tr("scratch_avatar_empty", creator_id=creator_id)
        )


def ensure_downloaded(project_id, **meta) -> Path:
    """Download-once helper used by the GUI.

    Returns the cached file path. If ``projects/<id>.sb3`` already exists it is
    returned untouched (no network call, no re-download).
    """
    if cache.is_cached(project_id):
        return cache.find_project_path(project_id)
    path = cache.project_path(project_id)
    data = download_project_bytes(project_id)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    cache.record_entry(
        project_id,
        format=cache.detect_format(data),
        size=len(data),
        downloaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **meta,
    )
    return path