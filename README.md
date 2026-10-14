# Basic Engine Hub

Desktop GUI (PySide6) that browses a Scratch studio, caches projects and plays
them locally with an embedded TurboWarp Scaffolding player. Cached projects
remain available when Scratch's listing API is offline. No external browser
needed.

```
Scratch Studio → project list → download once → local user cache → TurboWarp Scaffolding → play locally
```

## Requirements

- Fedora Linux (or similar) with Python 3.14+
- `pip install -r requirements.txt` (PySide6 >= 6.11, requests >= 2.32,
  beautifulsoup4 >= 4.12)

PySide6 declares the matching QtWebEngine bindings for its release, making
`PySide6.QtWebEngineWidgets` available after installing the requirements. No
separate WebEngine version needs to be pinned.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Playback architecture

The web view cannot `fetch()` local files from a `file://` page (browser CORS
blocks it), so the app starts a local HTTP server on `127.0.0.1` with a random
port. The player page, the vendored Scaffolding bundle and cached projects are
served from that server. The player uses the vendored
`@turbowarp/scaffolding@0.4.0` bundle (`web/vendor/scaffolding-with-music.js`,
MPL-2.0, https://github.com/TurboWarp/scaffolding) which ships the music
extension as embedded data URLs, so it works offline.

### Download format

As of 2026, Scratch's project endpoint
(`projects.scratch.mit.edu/<id>?token=...`) can return either an sb3 ZIP or a
raw project.json body. Both are accepted by Scaffolding's `loadProject()`.
Files are cached as `<id>.sb3`; the real format is recorded in `cache.json`.
The download requires a `project_token` fetched from the Scratch API.

## Cache behavior

- No re-download while a cached project exists (download-once).
- Thumbnails and creator avatars are cached and reused.
- The project index stores title, author, format, size and download date.
- Settings and cache live in the XDG user directories by default:
  `~/.config/basic-engine-hub/` and `~/.local/share/basic-engine-hub/`.
  `XDG_CONFIG_HOME` and `XDG_DATA_HOME` are honored when set.
- Existing project-local `projects/`, `thumbnails/`, `avatars/`, `cache.json`
  and `settings.json` are read in place; they are not copied or deleted during
  startup. New downloads and settings use the XDG directories.
- Settings includes an explicit action to clear downloaded projects. It keeps
  thumbnails and favorites, and removes project files from both old and new
  cache locations.

Cached projects appear in the menu even if they are no longer returned by
Scratch. Their cached copy can be played without contacting the project
download endpoint.

## Tests

```bash
python -m unittest discover -s tests -v
node --test
```

## Web version

GitHub Pages serves the root `index.html`; the Actions workflow builds
`listing.json` at the repository root and includes project descriptions,
instructions and stats so the browser does not need cross-origin Scratch API
access for project details. The same frontend is available at `web/index.html`
and through `python web/serve.py` for local use.

The web frontend stores its own data in browser storage: favorites, search,
the last project listing and checked variable values use `localStorage`, while
downloaded project bytes use IndexedDB. Its service worker caches the site
shell for return visits. The local web server streams Scratch downloads into
the browser; it does not write `.sb3` files to disk. On GitHub Pages, playback
uses the TurboWarp embed because static hosting cannot proxy Scratch's
token-protected project downloads. Project assets and comments still require
an internet connection.

### Scratch sign-in

The web menu can sign in with Scratch through Scratch Auth, using this
repository's own auth project
(https://scratch.mit.edu/projects/1391621033/). The browser talks to the
service directly (`https://auth-api.itinerary.eu.org`), so the same flow works
on GitHub Pages and from the local server, with no proxy.

`web/auth.js` asks the service for a code pair, the dialog shows the public
code and links to the auth project, and the page polls
`/auth/verifyToken/<privateCode>` until the service confirms the username. Only
the username is kept in `localStorage`; the private code is never persisted,
and a confirmation that points at another site is rejected.

The session is identity only: the header shows who is signed in, and the author
name of your own projects gets `(You)`. The auth project id and the supported
methods (`cloud`, `comment`, `profile-comment`) live in `web/auth.js`.
`tests/auth.test.js` covers the rules with `node --test`.

## Fedora / headless notes

If the WebEngine view does not start (sandbox/Vulkan issues), try:

```bash
QTWEBENGINE_DISABLE_SANDBOX=1 python main.py
QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu" python main.py
```

For CI/headless smoke runs use `QT_QPA_PLATFORM=offscreen`. Vulkan/GPU and
sandbox warnings from QtWebEngine are benign.

## Known limitations

- Project assets (images/sounds inside projects) are fetched from
  `assets.scratch.mit.edu` at runtime, so first playback needs internet.
- Cloud variables need internet.
- Online project details and comments need internet; opening details does not
  block the desktop while those requests are in progress.
- There is no project editor — playback only.

## License

The vendored `@turbowarp/scaffolding` bundle is MPL-2.0
(https://github.com/TurboWarp/scaffolding). Everything else in this repo is
yours to use.