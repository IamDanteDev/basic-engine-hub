"""Scratch sign-in core for the desktop app (Scratch Auth, custom frontend).

The Python port of the rules web/auth.js already pins for the browser, so both
halves sign in the same way against the same service and the same auth project:

  1. GET {AUTH_API_BASE}/auth/getTokens?method=&redirect=<base64>&authProject=
     -> {publicCode, privateCode, redirectLocation, method, authProject}
  2. The user enters ``publicCode`` in AUTH_PROJECT_URL (or comments it).
  3. GET {AUTH_API_BASE}/auth/verifyToken/<privateCode>
     -> {valid:false} while pending, {valid:true, username, redirect} once done.

What the codes buy is the **username** and nothing else: the service grants no
Scratch session, so this module must never be used as if it could comment,
favourite, upload or publish.

The base64 ``redirect`` is percent-encoded on the wire. Raw base64 is not safe:
a "+" decodes as a space and silently corrupts the URL (evidence L6 in
odd/tasks/scratch-auth.md).

No Qt imports: hub/gui.py owns the widgets and the polling timer, and
tests/test_auth.py exercises every rule without PySide6 — CI installs only
requests + beautifulsoup4.
"""

import base64
import binascii
import time
import urllib.parse

import requests

from hub import i18n, settings

AUTH_API_BASE = "https://auth-api.itinerary.eu.org"
AUTH_PROJECT_ID = 1391621033
AUTH_PROJECT_URL = f"https://scratch.mit.edu/projects/{AUTH_PROJECT_ID}/"
AUTH_METHODS = ("cloud", "comment", "profile-comment")
AUTH_METHOD_DEFAULT = "cloud"
# The desktop app has no callback page to come back to, so the redirect the
# service returns the browser to is the auth project itself — the one page the
# user is already visiting. What matters is that it is *our* value and that a
# different one coming back rejects the sign-in (is_trusted_redirect).
AUTH_REDIRECT = AUTH_PROJECT_URL
# The user's own key in settings.json. It holds {username, method, at}; the
# privateCode has nowhere to live, by design (S4).
AUTH_SESSION_KEY = "scratch_user"
# The service's own frontend refreshes tokens every 5 minutes (TOKEN_VALIDITY).
AUTH_CODE_TTL = 5 * 60
TIMEOUT_AUTH = 15
USER_AGENT = "BasicEngineHub/0.2"


class AuthError(Exception):
    """Raised on any failure while talking to the sign-in service."""


def is_known_method(method) -> bool:
    """True when ``method`` is one of the three the auth project documents."""
    return str(method) in AUTH_METHODS


def encode_redirect(url) -> str:
    """Base64-encode the URL the service will send the user back to."""
    return base64.b64encode(str(url).encode("utf-8")).decode("ascii")


def decode_redirect(value):
    """Decode a base64 redirect, or None when it is not base64 at all."""
    if not value:
        return None
    try:
        return base64.b64decode(str(value).encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeEncodeError, UnicodeDecodeError, ValueError):
        return None


def build_tokens_url(
    redirect,
    method=AUTH_METHOD_DEFAULT,
    username="",
    *,
    api_base=AUTH_API_BASE,
    auth_project=AUTH_PROJECT_ID,
) -> str:
    """Build the getTokens URL, with the redirect percent-encoded (never raw)."""
    chosen = str(method) if is_known_method(method) else AUTH_METHOD_DEFAULT
    params = {
        "method": chosen,
        "redirect": encode_redirect(redirect),
        "authProject": str(auth_project),
    }
    # Only profile-comment needs it: the service reads the user's own profile
    # comments, and the official frontend asks for the username there too.
    if chosen == "profile-comment" and str(username).strip():
        params["username"] = str(username).strip()
    return f"{api_base}/auth/getTokens?{urllib.parse.urlencode(params)}"


def verify_url(private_code, *, api_base=AUTH_API_BASE) -> str:
    """Build the verifyToken URL for a privateCode."""
    return f"{api_base}/auth/verifyToken/{urllib.parse.quote(str(private_code), safe='')}"


def _normalize_url(url) -> str:
    parts = urllib.parse.urlsplit(str(url or ""))
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}" + (
        f"?{parts.query}" if parts.query else ""
    )


def is_trusted_redirect(returned, expected) -> bool:
    """Check the returned redirect against the one we asked for.

    Absent is accepted: with our own privateCode requested by our own app the
    token is already bound to us, and rejecting an absent field would break
    every legitimate sign-in. A value that is present and points somewhere else
    rejects the sign-in (the anti-phishing rule the docs ask for).
    """
    if returned is None or returned == "":
        return True
    target = _normalize_url(expected)
    if not target:
        return False
    for candidate in (str(returned), decode_redirect(returned)):
        if candidate and _normalize_url(candidate) == target:
            return True
    return False


def request_tokens(
    redirect,
    method=AUTH_METHOD_DEFAULT,
    username="",
    *,
    api_base=AUTH_API_BASE,
    auth_project=AUTH_PROJECT_ID,
) -> dict:
    """Ask the service for a code pair. Raises :class:`AuthError` on any failure."""
    if str(method) == "profile-comment" and not str(username).strip():
        raise AuthError(i18n.tr("auth_username_required"))
    url = build_tokens_url(
        redirect, method=method, username=username, api_base=api_base, auth_project=auth_project
    )
    try:
        response = requests.get(url, timeout=TIMEOUT_AUTH, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        raise AuthError(i18n.tr("auth_contact_error", exc=exc)) from exc
    if not response.ok:
        raise AuthError(i18n.tr("auth_http_error", code=response.status_code))
    try:
        tokens = response.json()
    except ValueError as exc:
        raise AuthError(i18n.tr("auth_invalid_response")) from exc
    if not isinstance(tokens, dict) or not tokens.get("privateCode"):
        raise AuthError(i18n.tr("auth_invalid_response"))
    return tokens


def verify_code(private_code, *, api_base=AUTH_API_BASE) -> dict:
    """Ask whether the sign-in was completed.

    A pending sign-in answers 403 with ``{"valid": false}``; that is not an
    error, so it comes back as the same shape and the caller keeps waiting.
    """
    try:
        response = requests.get(
            verify_url(private_code, api_base=api_base),
            timeout=TIMEOUT_AUTH,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as exc:
        raise AuthError(i18n.tr("auth_contact_error", exc=exc)) from exc
    if not response.ok:
        return {"valid": False, "username": None, "redirect": None}
    try:
        data = response.json()
    except ValueError as exc:
        raise AuthError(i18n.tr("auth_invalid_response")) from exc
    username = data.get("username") if isinstance(data, dict) else None
    username = username if isinstance(username, str) else ""
    valid = bool(isinstance(data, dict) and data.get("valid") is True and username)
    return {
        "valid": valid,
        "username": username if valid else None,
        "redirect": (data.get("redirect") or None) if isinstance(data, dict) else None,
    }


# Session ----------------------------------------------------------------


def read_session():
    """Return the stored session, or None when nobody is signed in.

    Anything malformed (a string, a list, a blank username) reads as signed out
    rather than raising: a hand-edited settings.json must not break the app.
    """
    stored = settings.get(AUTH_SESSION_KEY)
    if not isinstance(stored, dict):
        return None
    username = str(stored.get("username") or "").strip()
    if not username:
        return None
    try:
        at = int(stored.get("at") or 0)
    except (TypeError, ValueError):
        at = 0
    method = stored.get("method")
    return {
        "username": username,
        "method": method if isinstance(method, str) else "",
        "at": at,
    }


def current_username() -> str:
    """The signed-in username, or "" when nobody is signed in.

    Read on demand instead of cached here: the card painting `(You)` and the
    header must never disagree with what the sign-in dialog just wrote.
    """
    session = read_session()
    return session["username"] if session else ""


def write_session(username, method="") -> dict | None:
    """Persist the signed-in username; a blank one is never written."""
    name = str(username or "").strip()
    if not name:
        return None
    value = {"username": name, "method": str(method or ""), "at": int(time.time())}
    settings.set(AUTH_SESSION_KEY, value)
    return value


def clear_session() -> None:
    """Sign out: the key stays with a null value, which reads as signed out."""
    settings.set(AUTH_SESSION_KEY, None)


def is_own_project(project_username, session_username="") -> bool:
    """True when the project's author is the signed-in user.

    Scratch usernames are case-insensitive, and an empty author or an empty
    session never matches — nobody owns an uncredited project.
    """
    author = str(project_username or "").strip().lower()
    viewer = str(session_username or "").strip().lower()
    return author != "" and viewer != "" and author == viewer


def author_name(username, session_username="") -> str:
    """The author as the card shows it: the name, plus the marker when yours.

    ``(You)`` stays literal in every language, the same rule the web pinned, so
    one person reading both halves sees the same word. The card's own wording
    supplies the "@", which is why this returns the bare name.
    """
    name = str(username or "").strip()
    if not name:
        return ""
    return f"{name} (You)" if is_own_project(name, session_username) else name


def author_label(username, session_username="") -> str:
    """The author with its "@", for the places that show the full label."""
    name = author_name(username, session_username)
    return f"@{name}" if name else ""
