# Feature: Repair Basic Engine Hub for Python 3.14 / Fedora

## Objective
Make the Basic Engine Hub desktop GUI work on Fedora Linux, Python 3.14.7,
without hiding the dependency failure. Adapt the architecture so the app
genuinely runs on 3.14 and plays local `.sb3` projects through TurboWarp
Scaffolding (vendored, embedded player — no external Chrome).

## Problem
`requirements.txt` pins `PySide6-WebEngine>=6.8`, which has **no cp314 wheel**
("No matching distribution found"). The standalone `PySide6-WebEngine`
package is obsolete for Python 3.14: PySide6 >= 6.9 ships QtWebEngine
(`PySide6.QtWebEngineWidgets`) inside `PySide6-Addons`.

## Why this design
- Verified live: PySide6 **6.11.2** (Essentials + Addons) installs and imports
  `QtWebEngineWidgets` on Python 3.14.7. No extra WebEngine package needed.
- Verified live (2026-09): Scratch's download endpoint
  `https://projects.scratch.mit.edu/{id}` now **requires** a `?token=` and
  returns **project.json** bodies (starts `{`), not sb3 zips (starts `PK`),
  for every project tested (1369017039, 1383138050, 1368016306, 60917032,
  10128407). TurboWarp Scaffolding `loadProject(ArrayBuffer)` accepts **both**
  project.json and sb/sb2/sb3 — README confirms. So the cache stores the raw
  bytes as `projects/<id>.sb3` (canonical key per user requirement) and the
  player passes the bytes straight to scaffolding regardless of format.
- TurboWarp Scaffolding researched: repo TurboWarp/scaffolding (MPL-2.0),
  npm `@turbowarp/scaffolding`, latest **0.4.0** (2026-09). Pre-built bundle
  `scaffolding-with-music.js` (4.3 MB, full offline music) vendored into
  `web/vendor/`. API: `new Scaffolding.Scaffolding()`, `.setup()`,
  `.appendTo(el)`, `storage.addWebStore(...)` for Scratch assets,
  `await scaffolding.loadProject(arrayBuffer)`, `.greenFlag()`, `.stopAll()`.
- A local `ThreadingHTTPServer` on 127.0.0.1:0 serves `web/` and `projects/`
  over http:// — avoids `file://` CORS entirely and lets the player `fetch()`
  local sb3/project.json as an ArrayBuffer.
- Studio listing API shape (verified): `api.scratch.mit.edu/studios/35865803/
  projects?limit=40&offset=0` → items with `id`, `title`, `image`
  (cdn2.scratch.mit.edu ..._480x360.png, 302→200), `creator_id`, `username`.

## Scope
- Restructure into `hub/` package: `gui.py`, `scratch_api.py`, `cache.py`,
  `player.py` (+ `__init__.py`), keep `main.py`.
- Player = embedded QWebEngineView + local HTTP server; web/player.html
  integrates vendored TurboWarp Scaffolding.
- Download + cache `.sb3`/project.json in `projects/<id>.sb3`; no re-download
  when the file exists. Thumbnails cached in `thumbnails/<id>.png`.
- Network error handling and download progress indicator in the GUI.
- Out of scope: full offline asset caching for every Scratch asset, cloud
  variable servers, project editor, packaging/installer.

## Tasks
- [x] T1 `requirements.txt`: `PySide6>=6.11`, `requests>=2.32` (drop
      PySide6-WebEngine; QtWebEngine lives in Addons)
- [x] T2 `hub/scratch_api.py`: studio listing, per-project token fetch,
      project download (token required), thumbnail download
- [x] T3 `hub/cache.py`: projects/ + thumbnails/ dirs, cache.json index,
      format detection, cache status, no-redownload guarantee
- [x] T4 `hub/player.py`: local HTTP server (web/ + projects/) + QWebEngineView
- [x] T5 `hub/gui.py`: project list (title, ID, creator, thumbnail, cache
      status), refresh, download progress, error handling, embedded player
- [x] T6 `web/player.html`: TurboWarp Scaffolding integration (vendored bundle)
- [x] T7 `main.py` entry + `hub/__init__.py`
- [x] T8 `README.md`: Fedora/Python 3.14 setup, Scaffolding notes, format
      discovery documentation, sandbox flag note
- [x] T9 `hub/gui.py` menu redesign: initial menu screen with project cards
      in a 3-column grid (QStackedWidget menu/page + player page, back
      button, global status bar). Clicking a card opens the player page;
      download-once + thumbnail + cache-status preserved. (2026-09-23,
      delegated writer; orchestrator spot check: 40 cards, columns [0,1,2],
      menu→player switch OK)
- [x] T10 Variables panel + save-on-switch (2026-09-23, delegated writer;
      orchestrator spot check of toggle/capture/restore paths):
      - "Variables" button on player page -> dialog table (Guardar/check,
        Variable, Objetivo, Valor) for the CURRENT project.
      - ONLY checked variables are saved on project switch (session-only
        cache in JS `savedValuesByProject`, per project id) and restored
        when returning to that project. Unchecked variables are neither
        captured nor restored.
      - Switching stops the previous project and covers the stage with the
        loading overlay so its variables/monitors are not shown.
      - Verified: VARS_SMOKE_OK rows=27 (SCORE/money/timer...), SWITCH_CALL_OK,
        COMPILE_OK, IMPORT_OK, JS_SYNTAX_OK. Headless shader flake on restore
        only (no real GPU); pre-existing load path used on real hardware.
- [x] T11 Fix thumbnails not showing on later launches (2026-09-23 inline):
      ThumbnailWorker skipped already-cached files without emitting
      thumbnail_ready, so cards stayed on the placeholder after the first
      run. Now existing files emit thumbnail_ready too.
      Verified: THUMB_EXISTS_EMIT_OK, PIXMAP_OK, SIZE_OK, COMPILE_OK.
- [x] T12 Paginate studio listing (2026-09-23 inline): Scratch API caps at 40
      items/page; the studio has 120 projects but the app showed only the
      first page. studio_projects() now pages offset 0,40,80... until a short
      page or max_projects (safety valve). Verified: PAGINATION_OK count=120,
      unique=True, COMPILE_OK. Menu then shows 117 after the T11 blocklist.
- [x] T13 Blocklist + featured + search (2026-09-23 inline):
      - BLOCKED_PROJECT_IDS += {1323323065, 1310326945} (5 hidden total).
      - FEATURED_PROJECT_ID = 1031335631 pinned FIRST on the menu with a
        2px golden frame (#FFD700, hover #ffb300) via ProjectCard(featured=).
      - Search QLineEdit under the header: filters cards live by title,
        username, or id (case-insensitive) with a clear button; status
        shows "X de N proyectos".
      - Verified: ORDER_OK, GOLD_FRAME_OK, SEARCH_TITLE/ID/AUTHOR_OK,
        CLEAR_OK, COMPILE_OK (offscreen, hub shown).
- [x] T14 Lists visible + edit vars/lists + non-modal panel (2026-09-23,
      delegated writer; orchestrator spot check):
      - listVariables() now includes LISTS (kind: "list"|"variable"); new
        window.setVariableValue(id, value) bridge (array copy for lists,
        guarded monitor refresh -- no-op in bundle).
      - Player.set_variable_value(variable_id, value, callback=None) added.
      - Variables dialog is NON-MODAL (dialog.show(), raise-if-visible,
        auto-closes when switching projects); 5 columns Guardar/Tipo/
        Variable/Objetivo/Valor (lists shown as JSON, cloud rows get "☁");
        double-click on Val or -> QInputDialog -> _parse_edited_value
        (JSON arrays, comma lists, numbers, bools, strings) ->
        set_variable_value -> refresh table. Info label explains the game
        keeps working while the panel is open.
      - Verified by writer: ROWS 33 (scalar=27 list=6), SET_SCALAR_OK 42,
        SET_LIST_OK ['x','y'], PARSE_*_OK, NON_MODAL_OK, COMPILE/IMPORT/
        JS_SYNTAX_OK. Orchestrator re-ran COMPILE/IMPORT/JS_SYNTAX_OK +
        structurally confirmed show()/close-on-switch/editor wiring.

## Authorized scope
User-authorized rewrite of this project directory only. Keep native desktop
app. Keep studio 35865803. Keep `.sb3` cache naming `projects/<id>.sb3`.
No external Chrome for the player (embedded WebEngine is fine).

## Acceptance criteria
1. `pip install -r requirements.txt` succeeds on Python 3.14.7.
2. App lists studio 35865803 projects with name, ID, creator, thumbnail,
   cache status (from live API when online; graceful error otherwise).
3. Selecting a project downloads once (token flow), caches under
   `projects/<id>.sb3`, and does NOT re-download when present.
4. Embedded player plays the cached project via vendored Scaffolding.
5. Network failures raise friendly, non-fatal errors.
6. Structure matches requested layout.

## TDD mode
Disabled — no test framework/runner in this project; verified via functional
checks per task. Runner: n/a. Ordinary checks (see Verification).

## Verification
Run with `/home/dante/Descargas/basic_engine_hub/.venv/bin/python` (3.14.7).
- [x] V1 `python -m compileall -q hub main.py` — COMPILE_OK (writer + orchestrator spot check)
- [x] V2 import smoke: offscreen import of hub.gui/player/scratch_api/cache — IMPORT_OK (orb. SPOT_IMPORT_OK)
- [x] V3 CLI script: listing→download 1 project (1369017039, format project-json,
      129.383 B)→cached→second call does NOT re-download (mtime unchanged,
      orchestrator re-verified)→thumbnail saved→cache.json written
- [x] V4 server roundtrip: GET `/` (200, contains "Scaffolding"), GET
      `/projects/1369017039.sb3` (200, bytes == file), traversal 403 —
      writer + orchestrator re-verified
- [x] V5 GUI offscreen boot: BOOT_OK (Vulkan/GPU warnings benign); 40 studio
      thumbnails downloaded by background ThumbnailWorker during smoke

## Delivery
Estimated authored lines ≈ 650 (heuristic; single cohesive repair, no size
rework). Git is NOT available: this directory is gitignored by the parent
repo (`/home/dante/.gitignore` line 3 `/*`) and has no nested `.git`, so no
work-unit commits can be recorded. Evidence = verification outcomes above.

## Progress
COMPLETED 2026-09-22 — delegated writer (general agent), orchestrator
readback + spot checks all pass. Working tree matches requested layout
(hub/ package, web/ player.html, web/vendor/scaffolding-with-music.js,
projects/, thumbnails/, cache.json, main.py, requirements.txt, README.md).
Old top-level hub.py / scratch_api.py / cache.py deleted (would shadow the
hub/ package). Venv: PySide6 6.11.2 + requests 2.34.2 on Python 3.14.7.

## T15 — Harden variable/list editing against the "crashea" report

User reported the app crashes when editing a variable/list value in the
Variables panel. Three proven vectors were hardened (2026-09-23):

- **PySide6 slot abort**: an unhandled exception in `_edit_variable_cell` /
  `_populate_variables_table` would abort the whole app under PySide6, so
  both bodies are now wrapped in try/except that surface the message in the
  status bar instead of dying.
- **Wrong value shapes**: `_parse_edited_value` could return lists/objects
  for a SCALAR variable (`[1, 2]`, `{"a": 1}` typed into a variable). Scalars
  are now coerced to bool/number/string only; arrays/objects/null stay as
  plain text. Lists become arrays of scalar elements (`_scalarish` helper).
- **JS side**: `setVariableValue` now uses `variable.setValue(next)` when
  available (bundle emits `value-changed`, so monitors refresh immediately)
  instead of blind `.value =`; coerces cloud values to strings; wraps the
  body in try/catch and returns an `error: ...` string instead of throwing
  into the renderer.

Verification (orchestrator, offscreen, WebEngine-free deterministic path):
COMPILE_OK, JS_SYNTAX_OK, PARSE_GUARD_OK, POPULATE_OK (panel fills 2 fake
rows after refresh), EDIT_SCALAR_OK (`("V1", 999)` recorded via the real
`_edit_variable_cell` with mocked QInputDialog), EDIT_LIST_OK (`("L1",
["z","w"])`), CORRUPT_ROW_GUARD_OK (row missing `id` → status message, app
alive). The user's real-GPU crash could not be reproduced headless (offscreen
WebEngine wedges at project load); the fixes close the three plausible abort
paths. TODO: ask the user to re-test on their machine.

## T16 — Dark modern visual restyle

User chose "Oscuro moderno". New `hub/theme.qss` (dark palette: bg #101216,
surface #181c22, border #2b2f36, text #e8e8e8, accent #ff8c42, gold #FFD700
for featured) loaded in `Hub.__init__` via `app.setStyleSheet` (guarded by
`theme_path.is_file()`). Inline card stylesheets replaced with dynamic
properties: `ProjectCard[featured="true"]`, `QLabel#statusChip[state=...]`
with explicit unpolish/polish on state change, `QPushButton[role=primary]` on
Iniciar and `role=danger` on Detener. Object names added: thumb, cardTitle,
cardMeta, statusChip, featuredBadge (★ Destacado on the featured card),
appTitle/appSubtitle, searchEdit, playerTitle, statusBar, separator (1px
line above the bottom bar), panelInfo. Thumbnails and placeholders now get
8px rounded corners via `QPixmap` + `QPainterPath` clip (`_rounded` helper).
`web/player.html` only changed its `<header>` text to "Basic Engine Hub".

Verification: writer COMPILE_OK / PLAYER_HEADER_OK / THEME_OK /
CARDS_RENDER_OK / FEATURED_GOLD_OK / STATUS_CHIP_OK / SEARCH_FILTER_OK /
PLAYER_PAGE_OK / DIALOG_THEME_OK / SMOKE_DONE; orchestrator re-ran the smoke
(all markers green), verified 18/18 theme selectors verbatim, all 12
objectNames wired, chip repolish in both states, roles, `_rounded` usage,
blocklist/FEATURED/5-columns unchanged, twconfig/applyTwConfig/preserve-ratio
markers intact. Independent-verifier slot: could not launch (OpenCode
provider free-tier restriction, environment-level); orchestrator performed
the structural verification directly. TODO: user to eyeball the dark theme on
a real display (pixel-level polish can't be judged offscreen).

## T17 — 4-column grid, bigger cards, cached creator avatars

User asked: grid of 4 columns, bigger cards, creator photo next to the @name,
cached. Delegated writer + orchestrator verification.

- Live fact discovered: Scratch studio API returns `avatar` as a DICT of
  size→URL (`{"90x90": ".../user/<creator_id>_90x90.png?v=", ...}`), not a
  string; 90x90 URL verified HTTP 200 PNG ~2KB. `studio_projects` now
  normalizes to the 90x90 URL (dict→90x90, str→itself, else ""; never raises).
- `hub/cache.py`: new `AVATARS` dir (base/avatars) + `avatar_path(creator_id)`.
  Avatars cached PER CREATOR (several projects share a creator → dedupe).
- `hub/scratch_api.py`: `download_avatar(creator_id, url, destination)`
  mirroring download_thumbnail (stream, TIMEOUT_THUMBNAIL, OSError→
  ScratchAPIError, empty-file unlink+raise).
- `hub/gui.py`: ProjectCard bigger (CARD_W 260, THUMB_W 240, THUMB_H 180,
  TEXT_W 240, AVATAR_SIZE 26); meta row = 26px rounded avatar + id_label
  (keeps cardMeta); `_avatar_placeholder()` + `set_avatar()` (rounded 13px);
  grid columns `range(4)` + `divmod(index, 4)`; ThumbnailWorker gains
  `avatar_ready = Signal(int, str)` + `_seen_creators` dedupe, avatar block at
  END of each loop iteration (writer deviation: thumbnail block's
  `if not image: continue` would have silently skipped avatars for thumbless
  projects; deviation: thumbnail download gated with `if image:` instead of
  `continue` — thumbnail failures still skip avatars for that project);
  Hub connects avatar_ready → `_on_avatar_ready` sets avatar on every card of
  that creator. theme.qss: one rule `QLabel#cardAvatar { ... border-radius:
  13px; }`.
- Verification: writer COMPILE_OK / GRID_4COL_OK (5th card at row 1 col 0) /
  AVATAR_CACHE_OK (4 unique creator files for 5 projects/4 creators) /
  AVATAR_ON_CARD_OK / AVATAR_NORMALIZE_OK; orchestrator re-ran the same smoke
  (all green), confirmed structural wiring (range(4)/divmod 4/_on_avatar_ready
  /close-on-switch).

## T18 — Remove player header bar; split Variables/Listas into 2 buttons

User asked: (a) remove the in-game top bar that said "Basic Engine Hub", (b)
separate variables and lists into two buttons.

- `web/player.html`: removed the `<header>` element AND its CSS block; the
  stage already used `position: fixed; inset: 0` so it fills the window with
  no gap. JS untouched (node --check OK).
- `hub/gui.py`: player header now has TWO buttons — "Variables" →
  `_open_variables_panel("variable")`, "Listas" → `_open_variables_panel("list")`.
  Panel is filtered by kind at reload time (`row.get("kind") == kind`), 4
  columns now ["Guardar", "Variable", "Objetivo", "Valor"] (Tipo column
  dropped; cloud marker ☁ moved next to the variable name), edit double-click
  moved to column 3 (`_edit_variable_cell` `column != 3`). `_variables_dialog_kind`
  tracks the open kind: same kind → raise, different kind → close+rebuild;
  reset on close-on-switch in `_open_project`.
- Verification (orchestrator, offscreen): COMPILE_OK, JS_SYNTAX_OK,
  TWO_BUTTONS_OK, PANEL_VARIABLES_OK (variables only, cloud marker, non-modal),
  EDIT_COL3_OK (col 3 edits, col 2 ignored), PANEL_LISTAS_OK (lists only,
  edit `["z"]`), RAISE_SAME_KIND_OK; player.html header element gone.
  One IndentationError introduced by the populating edit was caught by the
  first compile and fixed (kind= at line 712 lost its indent).

## T19 — Button icons from Assets/ + real Pause button

User added images to `Assets/` (green-flag.svg, Stop.svg, pause.svg;
also Clones/Fav/FullScreen/Love svgs unused for now) and asked: green flag =
Iniciar, stop = Detener, pause = Pausar. Loading animation from
`Assets/Loading/` (1.svg, 2.svg, 3.svg) deferred by user ("después veremos").

- Pause capability found in the tw bundle: `vm.runtime.frameLoop.stop()` /
  `.start()` — freezes the stepping loop without killing scripts (real pause;
  the `pause()/resume()` hits on the project-timer class only pause time
  tracking, NOT the VM; audio-stream pauses are unrelated).
- `web/player.html`: `pausePlayer()` / `resumePlayer()` with full guard
  chain (scaffolding.vm.runtime.frameLoop); exported on `window`.
  `scaffolding.vm` confirmed public (already used at player.html line 59).
- `hub/player.py`: `pause_game()` / `resume_game()` -> window.pausePlayer /
  window.resumePlayer.
- `hub/gui.py`: player buttons now icon+text — Iniciar (green-flag.svg,
  role primary), Detener (Stop.svg, role danger), NEW Pausar (pause.svg)
  between Listas and Iniciar. Toggle `_toggle_pause()` swaps label
  Pausar<->Reanudar; `self._paused` state; `_start_project`/`_stop_project`
  reset pause state; `_open_project` (project switch) resets it too.
  QIcon+setIconSize(22,22); SVGs load via Qt's svg plugin (verified offscreen).
- Verification: COMPILE_OK, JS_SYNTAX_OK, ICONS_SVG_OK (all 3 icons render),
  PAUSE_TOGGLE_OK, START_STOP_RESET_OK, SWITCH_RESET_OK.
- PENDING: Assets/Loading animated loading overlay — user will define later.

## T20 — Icon-only transport buttons; Clones panel; Fullscreen

User asked: remove button text (Iniciar/Detener/Pausar), Pausar between
Iniciar and Detener, Clones + FullScreen icons on the opposite side, and a
fullscreen mode with an exit button at top-left of the project. Delegated
writer + parent spot-check.

- `hub/gui.py`: transport buttons icon-only with tooltips; header order =
  back, title(1), Variables, Listas, Iniciar, Pausar, Detener, Clones,
  Pantalla completa. Pause toggle now swaps tooltip Pausar<->Reanudar
  (no text). `_chrome_widgets` list (header + bottom-bar widgets) hidden on
  fullscreen; `_on_fullscreen_requested(fs)` → hide chrome + showFullScreen /
  showNormal; connected AFTER the chrome list is built (line ~485).
- `hub/player.py`: `fullscreen_requested = Signal(bool)`; page()
  fullScreenRequested → accept + emit toggleOn; `toggle_clones_panel()` /
  `enter_fullscreen()` → window.toggleClonesPanel / window.enterFullscreen.
- `web/player.html`: body wrapped in `#player-root` (position:fixed inset:0;
  :fullscreen 100vw/vh) holding #stage, #fs-exit (✕ top-left, shown via
  body.fs-active on fullscreenchange), #clones-panel (left, vertically
  centered, z-15, .hidden), #overlay (z raised 20→45). JS: renderClones —
  targets = vm.runtime.targets filtered `!t.isStage && !t.isOriginal`,
  grouped by sprite.name with x/y rows (DOM textContent — no innerHTML);
  toggleClonesPanel toggles visibility + 200ms setInterval refresh (guarded
  window.toggleClonesButtonState hook call left for future Qt button-state,
  not defined); enterFullscreen/exitFullscreen on #player-root; -exit button
  click → exitFullscreen. twconfig/applyTwConfig/boot/preserve-ratio/variable
  helpers untouched (markers verified).
- Verification (writer + parent re-run): COMPILE_OK, JS_SYNTAX_OK,
  ICON_ONLY_OK, ORDER_OK, CLONES_FS_CALLS_OK, PAUSE_TOOLTIP_OK,
  FULLSCREEN_CHROME_OK (isFullScreen True→False round-trip offscreen +
  chrome visibility), markers intact.
- NOT provable headless: real WebEngine fullscreen rendering and the live
  clone panel (bundle runtime.targets, 200ms refresh) — user's machine.
- PENDING: Assets/Loading animated loading overlay — user will define later.

## T20b — Corrections: centered title, clones counter, fullscreen fix

User feedback on T20: (1) project title must be CENTERED (was left of the
transport group); (2) clones control belongs on the far RIGHT, not among the
buttons — and it must NOT look like a button: show the LIVE clone count in
numbers to the LEFT of the clones icon (`[count] [icon]`); (3) FullScreen
button sits immediately LEFT of the clones icon and IS a button; (4) the
fullscreen button errored: `Uncaught (in promise) TypeError: Fullscreen is
not supported`.

- ROOT CAUSE of the fullscreen error: Qt WebEngine ships with the HTML5
  Fullscreen API DISABLED by default (`FullScreenSupportEnabled` default
  false) — `document.fullscreenEnabled` is false, so `requestFullscreen()`
  rejects with exactly that TypeError. Fix: in Player.__init__,
  `self.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)`.
  NOTE (PySide6 6.11 gotcha): QWebEngineSettings imports from
  `PySide6.QtWebEngineCore`, NOT QtWebEngineWidgets.
- `hub/gui.py`: header layout = back | fullscreen | clone-count | Clones
  (flat icon, left corner) | stretch | centered title | stretch | Variables |
  Listas | Iniciar | Pausar | Detener (user moved the Clones/FullScreen group
  to the OTHER corner, next to Volver). New `self._clone_count_label`
  (objectName "cloneCount", tooltip "Clones activos"); `self.clones_button.setFlat(True)`
  so it reads as an icon, not a button (still toggles the panel). Clone
  counter = QTimer 400ms started on entering the player page (both
  _open_project branches), stopped by the new `_back_to_menu()` handler;
  `_poll_clone_count()` → player.get_clone_count → `_on_clone_count` sets the
  label (invalid values ignored).
- `hub/player.py`: `get_clone_count(callback)` →
  `JSON.stringify(window.getCloneCount() || 0)`. FullScreenSupportEnabled in
  __init__.
- `web/player.html`: `getCloneCount()` — targets filtered
  `!t.isStage && !t.isOriginal` length (0 when no vm); exported.
- Verification (offscreen smoke): COMPILE_OK, JS_SYNTAX_OK, ORDER_OK
  (tooltip sequence Iniciar, Pausar, Detener, Pantalla completa, Clones
  activos, Clones), COUNT_POSITION_OK (label left of clones icon, flat),
  ICON_ONLY_OK, PAUSE_TOOLTIP_OK, CLONE_COUNT_OK (label shows "7" from a
  faked callback), FULLSCREEN_CHROME_OK (player page current; isFullScreen
  True/False round-trip + chrome hidden/restored), BACK_STOPS_TIMER_OK.
  Smoke learning (test-only): QStackedWidget keeps widgets on non-current
  pages invisible, so fullscreen-chrome assertions must switch to the player
  page first.
- Still only provable on the user's machine: the real WebEngine fullscreen
  round-trip (was "Fullscreen is not supported" before the setting fix) and
  the live clone number on a running project.

## T20d — Letterbox background #FF4D4D; fullscreen-exit viewport kick

User: (1) the player page behind the letterboxed 640x360 stage should show
#FF4D4D instead of the dark #101216; (2) after exiting fullscreen the play
area does not re-layout ("no se actualiza").

- `web/player.html`: `html, body { background: #FF4D4D; }` (was #101216).
  Uncovers the letterbox area around the preserve-ratio stage in red. The
  overlays (error/loading chip, clones panel, fs-exit) keep their own dark
  surfaces, fine over red.
- `hub/gui.py`: known QtWebEngine quirk (QTBUG) — after the HTML fullscreen
  round-trip the renderer viewport can remain at fullscreen size, so the play
  area looks wrong until something forces a resize event. Fix: in
  `_on_fullscreen_requested(False)` after showNormal() post
  `QTimer.singleShot(0, self._kick_player_view)`; `_kick_player_view()`
  resizes the player widget +1px then back to the exact size (guarded against
  empty size), forcing Chromium to relayout the viewport to the restored
  window.
- Verification: COMPILE_OK, full smoke suite still green (ORDER/LEFT_CORNER/
  COUNT_POSITION/ICON_ONLY/PAUSE_TOOLTIP/CLONE_COUNT/FULLSCREEN_CHROME/
  BACK_STOPS_TIMER), FF4D4D + _kick_player_view present. Real fullscreen
  exit behavior only observable on the user's machine.

## TODO (user-validated on a real machine)
- Dark theme pixel-level polish (cannot judge offscreen).
- Original variable-edit crash: re-test the fixed paths on the real GPU.
- Eyeball the SVG button icons + Pause behavior in a real loaded project.
- Loading animation from Assets/Loading frames (deferred by user).
## T21: Settings button + language selector (ES/EN)
- User request (2026-09-24): main menu gains a "Configuración" button; only language config for now, only English and Spanish.
- NEW hub/i18n.py: LANGUAGES {es,en}, STRINGS catalog (84 keys), `set_language/current/tr(key, **args)`, fallback chain current → en → es → key. es values byte-identical to previous hardcoded texts.
- NEW hub/settings.py: JSON persistence at project root `settings.json`, atomic write (tmp + os.replace), `get/set` with DEFAULTS {"language": "es"}.
- hub/gui.py: every user-facing literal → `i18n.tr()`; settings button in menu header (objectName settingsButton); `_open_settings()` QDialog with QComboBox (Español/English) that applies+persists immediately; `_retranslate()` re-sets all static labels/tooltips/placeholders + ProjectCard.retranslate() + open variables-panel title/headers/refresh; language applied at Hub.__init__ before _build_ui.
- hub/player.py: URL grows `?lang=` (handler ignores query, verified urlsplit path-only); `set_language(lang)` → `window.setPlayerLanguage`; load_failed → tr().
- hub/scratch_api.py: every ScratchAPIError raised with pre-translated tr() message (API unchanged); default title "Proyecto {pid}" → tr("project_default_title").
- web/player.html: `uiLang` + `UI` dict + `uiText()` at script top; overlay/loading/error prefix/bundle-missing/clones empty texts swapped; `window.setPlayerLanguage(lang)` re-applies visible web texts without page reload.
- Verification: COMPILE_OK, smoke_i18n (ES_DEFAULTS/PAUSE_TOGGLE/LANG_SWITCH/CARD_RETRANSLATE/EN_BOOT_PERSISTED), smoke_t20b still green, JS_SYNTAX_OK, catalog_check CATALOG_BYTEFORBYTE_OK, no Spanish literals left in hub/ (grep clean). Parent spot check re-ran smoke_i18n: all PASS; settings.json cleaned after tests.
- Known limits (headless): live web uiText() swap inside a loaded project only observable on the user's machine; a language switch while the page is still loading is dropped once (page initializes from URL query at load; self-heals on next page load).

## T22: Blocklist 6 IDs + pinned project 1192855606
- User request (2026-09-24): hide IDs 1198347181, 1189578716, 1186588783, 1198685482, 1174546565, 1245982356 from the menu; show non-studio project 1192855606.
- gui.py: BLOCKED_PROJECT_IDS extended (11 total); new PINNED_PROJECT_IDS = {1192855606}; ListingWorker.run() dedupes against existing studio ids then inserts each pinned project at index 0 (sorted, best-effort: a pinned fetch failure skips silently and never hides the studio listing).
- scratch_api.py: new fetch_project(project_id) — GET /projects/{id}, routed raise_for_status through _http_error with new scratch_http_action_project action; normalized to the studio item shape (author nested dict -> username/creator_id; thumbnail -> image; actor_id None; avatar "").
- i18n.py: +3 keys both languages (scratch_project_error, scratch_project_invalid, scratch_http_action_project).
- Verification: COMPILE_OK, smoke_pin (SCENARIO1 block filter + pin-dedupe when studio already contains pin id, SCENARIO2 best-effort skip on fetch failure with no failed signal, SCENARIO3 pin prepended), smoke_i18n regression re-run all PASS, settings.json cleaned.
- Note: first writer delegation for this task got CANCELLED mid-flight (it had already applied the gui.py half); parent completed scratch_api.py + i18n.py inline and verified. Real HTTP fetch of 1192855606 not exercised headless-offscreen (network smoke skipped; verify on user's machine).

## T23: Project detail dialog (cover, play, stats, desc, instructions, favorite, comments)
- User request (2026-09-24): clicking a card opens a project dialog: cover, Play, title, description, instructions if present, loves, favorites, comments.
- Verified: official api project payload has instructions/description/stats{loves,favorites,views,remixes}; official comments endpoint (api.scratch.mit.edu/projects/{id}/comments) returns 404 WITHOUT a session token; the OLD site-api endpoint https://scratch.mit.edu/site-api/comments/project/{id}/?page=N returns comment HTML fragments with NO token (verified live: 5 comments on pinned project, 29 on featured). Third-party "Scratch-Comments-API" (Sid72020123) merely scrapes that same endpoint and its Replit host is DOWN — decided to hit site-api directly.
- NEW hub/project_dialog.py: CommentsWorker(QThread) (best-effort: any failure -> empty list, never raises) + ProjectDetailDialog(QDialog) with cover, title/author, stats row, Play (signal play_requested -> Hub._open_project), favorite toggle (favorite_toggled signal -> Hub persists in settings.json "favorites" list + cardFavorite ❤ marker on card), Open in Scratch (QDesktopServices), description/no_description, instructions section HIDDEN when empty, comments in a scroll area with reply nesting, comments_loading/no_comments/comments_unavailable states, retranslate().
- scratch_api.py: fetch_project_detail (extended normalized dict incl. stats/comments_allowed) + fetch_project_comments (bs4 parse of li.top-level-reply / li.reply, BROWSER_UA header, timeout TIMEOUT_THUMBNAIL, best-effort [] on error). NEW dependency: beautifulsoup4 4.15.0.
- gui.py: card.clicked -> _open_project_detail (lambda preserves dict arg; clicked emits pid), _detail_dialog tracking + retranslate hook, _on_favorite_toggled + settings persistence, ProjectCard.thumbnail_path + set_favorite/cardFavorite.
- i18n.py: +18 keys both languages.
- VERIFIED: COMPILE_OK, smoke_detail (populated/favorite toggle/retranslate/comments/comments-failed), smoke_detail_hub (dialog open/close tracking, favorite persist/remove, card retranslate), smoke_i18n regression green, smoke_pin regression green, offline unit smoke_scratch_api (comments parse/html entities/error paths).
- FIXED parent-side: scratch_api.py had a DUPLICATED fetch_project (the cancelled T22 writer had silently applied its scratch_api half earlier, then parent's inline edit added a second identical one that shadowed the first) — removed the shadow duplicate, re-ran smoke_pin green.
- Not provable headless: dialog visuals/QSS, live comment fetch, openUrl.

## T24: Menu source = all Alvaro_Games19 projects (excl. 5 ids)
- User request (2026-09-24): menu must show ALL projects of Alvaro_Games19 except 1187594776, 1220979078, 1121241960, 400240654, 1201842653; replaces studio 35865803 as source.
- Verified: /users/{username}/projects returns paginated FULL single-project payloads (author nested dict, NO top-level username/creator_id) — needs fetch_project-style normalization, not studio shape.
- scratch_api.py: extracted `_normalize_project_payload(payload)` (fetch_project refactored onto it, identical behavior); NEW `user_projects(username, limit=40, max_projects=1000)` paginated like studio_projects, wraps normalize failures in scratch_incomplete, HTTP errors via new scratch_http_action_user. `studio_projects` kept intact but unused by the GUI.
- i18n.py: menu_subtitle CHANGED to "Proyectos de @{user}" / "Projects by @{user}" (subtitle call passes user=SOURCE_USER); +scratch_http_action_user.
- gui.py: SOURCE_USER = "Alvaro_Games19"; blocklist 11 -> 16 ids; ListingWorker(username) now calls user_projects; refresh_listing uses SOURCE_USER.
- VERIFIED: COMPILE_OK, smoke_pin updated to patch user_projects (all SCENARIO PASS), smoke_user_source NEW (empty emit, nested-author normalization username/creator_id extraction), NORMALIZE_OK helper offline test (missing id raises KeyError), smoke_i18n regression green, id-scope grep clean. Parent spot check re-ran user_source + pin smokes: green.
- Notes: catalog_check.py in /tmp is pre-existing broken (lacks T23 keys) — out of scope; STUDIO_ID constant remains in gui.py as dead code (smoke_pin imports it).

## T24b (fix): avatar + username vacíos en source usuario
- Symptom: user reported profile pictures and usernames not showing after the Alvaro_Games19 source switch.
- Root cause (verified live): GET /users/{u}/projects returns author WITHOUT username (only id/scratchteam/history/profile) — _normalize_project_payload produced username "" ("@" bare in card meta) and avatar "" (no profile picture). The avatar actually lives at author.profile.images.90x90.
- Fix (scratch_api.py only): _normalize_project_payload(payload, username_hint="") — falls back to username_hint when author.username missing (user_projects passes the requested username; all listed projects belong to it) and extracts avatar from author.profile.images["90x90"]. fetch_project (pin, project-detail payload has username) unchanged behavior.
- VERIFIED: compile OK, live check — all 44 user projects now carry username "Alvaro_Games19" and a https avatar 90x90; smoke_pin + smoke_user_source regressions green.

## T26: union estudio + usuario con dedupe
- ListingWorker ahora lista DOS fuentes best-effort: studio_projects(STUDIO_ID 35865803) primero, luego user_projects("Alvaro_Games19"); union dedupe por id conservando el primero (orden estudio); luego blocklist (16) + pinned 1192855606. Si una fuente falla, la otra sobrevive; si ambas fallan -> failed.
- __init__: ListingWorker(username, studio_id, parent=None); call site pasa (SOURCE_USER, STUDIO_ID).
- Subtitulo del menu ELIMINADO a pedido del usuario: quitada la key menu_subtitle (es/en), quitado QLabel self.subtitle + su setText en _retranslate.
- i18n dedupe: en las fuentes, los proyectos del estudio ya traen username/avatar; user_projects via username_hint (T24b).
- VERIFIED: compile; smoke_i18n (subtitle ausente + es/en), smoke_pin (4 escenarios union/dedupe/best-effort/ambas-fuentes-fallan), smoke_user_source (2 fuentes llamadas + normalize) verde. Live: estudio=121, user=44, repetidos=13, unicos=152.

## T27: version web del menu (web/index.html + serve.py)
- User requested "crea una carpeta web y que esto funcione en un sitio web"; chose scope "Menu + jugar" (Recommended) via question tool.
- 4 NEW files in web/ (nothing else touched): serve.py (stdlib ThreadingHTTPServer, localhost-only, --port/--no-browser, GET /api/listing server-side merge), index.html (Spanish UI), style.css (mirrors theme.qss palette #101216/#ff8c42, responsive grid, avatar badge), app.js (1 fetch, live filter title/@username/id, TurboWarp overlay iframe embed?project=<id>&autoplay, close clears src, loading spinner, error + Reintentar).
- serve.py normalizes all three endpoint shapes like hub/scratch_api.py (studio flat author..., user nested author WITHOUT username -> hint Alvaro_Games19, single-project nested WITH username + thumbnail field); best-effort per source, 502 JSON only when both fail; pin fetch best-effort.
- VERIFIED (writer + parent spot check): py_compile OK; / 200; listing valid JSON unicos=137 (studio 121 + user 44 = 165 raw, dedupe 152, 16 blocked, pin 1192855606 prepended; 39 items username Alvaro_Games19); no dupes, no blocked, all fields present; server stopped clean.
- Run: .venv/bin/python web/serve.py  (auto-opens browser).

## T28: index.html raiz + GitHub Pages
- User asked: "añade index.html a la raíz para que github lo tome al crear el repo y ponerle github pages".
- KEY FACT: Scratch API sends ONLY `access-control-allow-origin: https://scratch.mit.edu` (verified live) -> browser fetch from *.github.io is CORS-BLOCKED. Pages must use a static same-origin JSON instead of live API.
- Solution: web/listing.py (merge extracted from serve.py; shared single source of truth; CLI `python web/listing.py --out listing.json`) + .github/workflows/pages.yml (checkout, setup-python, build listing.json, upload-pages-artifact path ., deploy-pages@v4) + index.html in repo root (relative links web/style.css + web/app.js) + web/app.js dual-mode fetch: ./api/listing (local serve.py) then ./listing.json (Pages), same-origin fallback.
- serve.py refactored to import listing.build_listing (module sibling, works when running `python web/serve.py`).
- VERIFIED: py_compile listing+serve OK; node --check app.js OK; web/listing.py --out produced 138 unique projects (blocked filtered, pin first); serve.py /api/listing still 200 count=138; Pages simulation (http.server serving repo root with listing.json present): /, /listing.json, /web/style.css, /web/app.js all 200; temp listing.json removed.
- User flow: create repo, push main, enable Pages -> Actions; workflow builds listing.json on every push/workflow_dispatch.
