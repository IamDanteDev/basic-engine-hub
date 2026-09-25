# Basic Engine Hub

Desktop GUI (PySide6) that browses a Scratch studio, downloads projects once
and plays them locally with an embedded TurboWarp Scaffolding player. No
external browser needed.

```
Scratch Studio → project list → download once → projects/<id>.sb3 → TurboWarp Scaffolding → play locally
```

## Requirements

- Fedora Linux (or similar) with Python 3.14+
- `pip install -r requirements.txt` (PySide6 >= 6.11, requests >= 2.32)

PySide6 >= 6.11 bundles QtWebEngine inside `PySide6-Addons` (drawn in by the
`PySide6` package), so `PySide6.QtWebEngineWidgets` is available out of the
box. The old separate `PySide6-WebEngine` package has no Python 3.14 wheels
and is NOT used.

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
port. The player page, the vendored Scaffolding bundle and the cached projects
under `projects/` are all served from that server. The player uses the vendored
`@turbowarp/scaffolding@0.4.0` bundle (`web/vendor/scaffolding-with-music.js`,
MPL-2.0, https://github.com/TurboWarp/scaffolding) which ships the music
extension as embedded data URLs, so it works offline.

### Download format

As of 2026, Scratch's project endpoint
(`projects.scratch.mit.edu/<id>?token=...`) can return either an sb3 ZIP or a
raw project.json body. Both are accepted by Scaffolding's `loadProject()`.
Files are always cached under `projects/<id>.sb3`; the real format is recorded
in `cache.json`. The download requires a `project_token` fetched from the
Scratch API.

## Cache behavior

- No re-download while `projects/<id>.sb3` exists (download-once).
- Thumbnails are cached as `thumbnails/<id>.png` (only downloaded when missing).
- `cache.json` keeps the index: title, author, format, size, download date.

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
- There is no project editor — playback only.

## License

The vendored `@turbowarp/scaffolding` bundle is MPL-2.0
(https://github.com/TurboWarp/scaffolding). Everything else in this repo is
yours to use.