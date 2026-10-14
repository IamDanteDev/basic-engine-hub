"""Main window: menu grid of project cards, thumbnails, download-once cache
and an embedded player page.

UI strings come from the i18n catalog (es default, en selectable); code and
comments are English.
"""

import json
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hub import cache, i18n, scratch_api, settings
from hub.catalog import (
    BLOCKED_PROJECT_IDS,
    FEATURED_PROJECT_ID as CATALOG_FEATURED_PROJECT_ID,
    PINNED_PROJECT_IDS,
    SOURCE_USER,
    STUDIO_ID,
)
from hub.cache import is_cached, thumbnail_path
from hub.player import Player
from hub.project_dialog import ProjectDetailDialog


class ListingWorker(QThread):
    """One-shot user listing; runs user_projects off the GUI thread."""

    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, username: str, studio_id, parent=None) -> None:
        super().__init__(parent)
        self._username = username
        self._studio_id = studio_id

    def run(self) -> None:
        try:
            projects: list[dict] = []
            last_error = ""
            for fetch in (
                lambda: scratch_api.studio_projects(self._studio_id),
                lambda: scratch_api.user_projects(self._username),
            ):
                try:
                    projects.extend(fetch())
                except scratch_api.ScratchAPIError as exc:
                    last_error = str(exc)  # best-effort per source: one failing source must not hide the other
            # Union with dedupe by id, keeping the first occurrence (studio order first).
            seen: set[int] = set()
            unique: list[dict] = []
            for project in projects:
                pid = int(project["id"])
                if pid in seen:
                    continue
                seen.add(pid)
                unique.append(project)
            projects = [
                project
                for project in unique
                if int(project["id"]) not in BLOCKED_PROJECT_IDS
            ]
            existing = {int(project["id"]) for project in projects}
            for pid in sorted(PINNED_PROJECT_IDS):
                if pid in existing:
                    continue
                try:
                    projects.insert(0, scratch_api.fetch_project(pid))
                except scratch_api.ScratchAPIError:
                    continue  # best-effort: a failed pinned fetch must not hide the listing
            projects.extend(cache.cached_projects())
            if not projects and last_error:
                self.failed.emit(last_error)
                return
            # Keep remote metadata/order, then add disk-only projects.
            seen.clear()
            unique = []
            for project in projects:
                pid = int(project["id"])
                if pid in seen or pid in BLOCKED_PROJECT_IDS:
                    continue
                seen.add(pid)
                unique.append(project)
            self.finished_ok.emit(unique)
        except Exception as exc:  # noqa: BLE001 - keep the app alive on anything
            self.failed.emit(i18n.tr("unexpected_error", exc=exc))


class DownloadWorker(QThread):
    """Download-once per selection; skips the network when already cached."""

    done = Signal(int)
    failed = Signal(int, str)

    def __init__(self, project: dict, parent=None) -> None:
        super().__init__(parent)
        self._project = dict(project)
        self._pid = int(project["id"])

    def run(self) -> None:
        try:
            meta = {
                key: self._project[key]
                for key in ("title", "username", "creator_id", "image")
                if key in self._project
            }
            scratch_api.ensure_downloaded(self._pid, **meta)
            self.done.emit(self._pid)
        except scratch_api.ScratchAPIError as exc:
            self.failed.emit(self._pid, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self._pid, i18n.tr("unexpected_error", exc=exc))


class ThumbnailWorker(QThread):
    """Downloads missing thumbnails after a listing refresh."""

    thumbnail_ready = Signal(int, str)
    avatar_ready = Signal(int, str)
    done = Signal()

    def __init__(self, projects: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._projects = [dict(project) for project in projects]
        self._seen_creators: set[int] = set()

    def run(self) -> None:
        for project in self._projects:
            if self.isInterruptionRequested():
                break
            try:
                pid = int(project["id"])
                destination = thumbnail_path(pid)
                image = project.get("image")
                if image:
                    cached = cache.find_thumbnail_path(pid)
                    if cached.is_file() and cached.stat().st_size > 0:
                        self.thumbnail_ready.emit(pid, str(cached))
                    else:
                        scratch_api.download_thumbnail(pid, image, destination)
                        self.thumbnail_ready.emit(pid, str(destination))
            except scratch_api.ScratchAPIError:
                continue  # placeholder stays
            except Exception:  # noqa: BLE001
                continue
            try:
                creator_id = int(project.get("creator_id") or 0)
            except (TypeError, ValueError):
                creator_id = 0
            if creator_id <= 0 or creator_id in self._seen_creators:
                continue
            self._seen_creators.add(creator_id)
            destination = cache.avatar_path(creator_id)
            try:
                cached = cache.find_avatar_path(creator_id)
                if cached.is_file() and cached.stat().st_size > 0:
                    self.avatar_ready.emit(creator_id, str(cached))
                    continue
                avatar_url = project.get("avatar") or ""
                if not avatar_url:
                    continue
                scratch_api.download_avatar(creator_id, avatar_url, destination)
                self.avatar_ready.emit(creator_id, str(destination))
            except scratch_api.ScratchAPIError:
                continue
            except Exception:  # noqa: BLE001
                continue
        self.done.emit()


class ProjectCard(QFrame):
    """Clickable card for the menu grid: thumbnail, title, author, cache state."""

    clicked = Signal(int)

    _CARD_W = 260
    _THUMB_W = 240
    _THUMB_H = 180
    _TEXT_W = 240
    _AVATAR_SIZE = 26

    def __init__(self, project: dict, parent=None, featured: bool = False) -> None:
        super().__init__(parent)
        self.project = dict(project)
        self.pid = int(project["id"])
        # Raw card data: the title/author stay untouched (API data); only the
        # generated meta line and badge are re-translated via retranslate().
        self.project_title = project.get("title") or ""
        self.author = project.get("username") or ""
        self.featured = featured
        self._featured_badge: QLabel | None = None
        self._placeholder_pixmap: QPixmap | None = None
        self._avatar_placeholder_pixmap: QPixmap | None = None
        self._favorite = False
        self.thumbnail_path: str | None = None

        self.setFixedWidth(self._CARD_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # QSS selectors (ProjectCard[featured="true"]) handle all card borders.
        self.setProperty("featured", featured)

        box = QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        box.setSpacing(6)

        if featured:
            badge = QLabel(i18n.tr("featured_badge"))
            badge.setObjectName("featuredBadge")
            self._featured_badge = badge
            box.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)

        self._thumb_label = QLabel()
        self._thumb_label.setObjectName("thumb")
        self._thumb_label.setFixedSize(self._THUMB_W, self._THUMB_H)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setPixmap(self._placeholder())
        box.addWidget(self._thumb_label, 0, Qt.AlignmentFlag.AlignHCenter)

        title = self.project_title or i18n.tr("project_default_title", pid=self.pid)
        self.title_label = QLabel()
        self.title_label.setObjectName("cardTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setText(self._elide(title))
        self.title_label.setToolTip(title)
        box.addWidget(self.title_label)

        meta = self._meta_text()
        self.id_label = QLabel()
        self.id_label.setObjectName("cardMeta")
        self.id_label.setTextFormat(Qt.TextFormat.PlainText)
        self.id_label.setText(self._elide(meta))
        self.id_label.setToolTip(meta)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(self._AVATAR_SIZE, self._AVATAR_SIZE)
        self.avatar_label.setObjectName("cardAvatar")
        self.avatar_label.setPixmap(self._avatar_placeholder())
        meta_row.addWidget(self.avatar_label, 0, Qt.AlignmentFlag.AlignVCenter)
        meta_row.addWidget(self.id_label, 1, Qt.AlignmentFlag.AlignVCenter)
        self._favorite_label = QLabel("❤")
        self._favorite_label.setObjectName("cardFavorite")
        self._favorite_label.setVisible(False)
        meta_row.addWidget(self._favorite_label, 0, Qt.AlignmentFlag.AlignVCenter)
        box.addLayout(meta_row)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusChip")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.status_label)
        if is_cached(self.pid):
            self.set_cached()
        else:
            self.set_missing()

    # Public card updates ------------------------------------------------

    def set_cached(self) -> None:
        self.status_label.setText(i18n.tr("card_cached"))
        self.status_label.setProperty("state", "ok")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_missing(self) -> None:
        self.status_label.setText(i18n.tr("card_missing"))
        self.status_label.setProperty("state", "missing")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_thumbnail(self, path: str) -> None:
        self.thumbnail_path = path
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            self._THUMB_W,
            self._THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_label.setPixmap(self._rounded(scaled, 8))

    def set_favorite(self, fav: bool) -> None:
        """Show/hide the small "❤" marker under the card meta."""
        self._favorite = bool(fav)
        self._favorite_label.setVisible(self._favorite)
        self._favorite_label.setText("❤")

    def set_avatar(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            self._AVATAR_SIZE, self._AVATAR_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.avatar_label.setPixmap(self._rounded(scaled, self._AVATAR_SIZE // 2))

    def retranslate(self) -> None:
        """Re-apply the translatable card texts in the current language."""
        if is_cached(self.pid):
            self.set_cached()
        else:
            self.set_missing()
        meta = self._meta_text()
        self.id_label.setText(self._elide(meta))
        self.id_label.setToolTip(meta)
        if self._featured_badge is not None:
            self._featured_badge.setText(i18n.tr("featured_badge"))
        if self._thumb_label.pixmap() is self._placeholder_pixmap:
            # The placeholder canvas embeds text: redraw it in the new language.
            self._placeholder_pixmap = None
            self._thumb_label.setPixmap(self._placeholder())
        if not self.project_title:
            title = i18n.tr("project_default_title", pid=self.pid)
            self.title_label.setText(self._elide(title))
            self.title_label.setToolTip(title)

    def _meta_text(self) -> str:
        return i18n.tr(
            "card_meta", pid=self.pid, author=self.author or i18n.tr("no_author")
        )

    # Events --------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.pid)
        super().mousePressEvent(event)

    # Internals ------------------------------------------------------------

    def _elide(self, text: str) -> str:
        return self.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, self._TEXT_W
        )

    def _placeholder(self) -> QPixmap:
        if self._placeholder_pixmap is None:
            pixmap = QPixmap(self._THUMB_W, self._THUMB_H)
            pixmap.fill(QColor("#3a3f46"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#8b939c"))
            painter.drawText(
                pixmap.rect(), Qt.AlignmentFlag.AlignCenter, i18n.tr("no_thumbnail")
            )
            painter.end()
            self._placeholder_pixmap = self._rounded(pixmap, 8)
        return self._placeholder_pixmap

    def _avatar_placeholder(self) -> QPixmap:
        if self._avatar_placeholder_pixmap is None:
            pixmap = QPixmap(self._AVATAR_SIZE, self._AVATAR_SIZE)
            pixmap.fill(QColor("#1f242c"))
            self._avatar_placeholder_pixmap = self._rounded(pixmap, self._AVATAR_SIZE // 2)
        return self._avatar_placeholder_pixmap

    def _rounded(self, pixmap: QPixmap, radius: int) -> QPixmap:
        out = QPixmap(pixmap.size())
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(pixmap.rect()), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return out


class Hub(QWidget):
    """Basic Engine Hub main window: menu grid page + player page."""

    # Project pinned first on the menu with a golden frame.
    FEATURED_PROJECT_ID = CATALOG_FEATURED_PROJECT_ID

    def __init__(self) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            theme_path = Path(__file__).resolve().parent / "theme.qss"
            if theme_path.is_file():
                app.setStyleSheet(theme_path.read_text(encoding="utf-8"))
        self.setWindowTitle("Basic Engine Hub")
        self.resize(1280, 800)
        self.setMinimumWidth(780)
        self._downloading = False
        self._current_pid: int | None = None
        self._saved_ids: dict[int, set[str]] = {}  # per project: variable ids the user chose to save
        self._pending_switch: tuple[int | None, list[str]] | None = None
        self._variables_dialog: QDialog | None = None
        self._variables_dialog_kind: str | None = None
        self._detail_dialog: ProjectDetailDialog | None = None
        self._paused = False
        self._clone_count_timer = QTimer(self)
        self._clone_count_timer.setInterval(400)
        self._clone_count_timer.timeout.connect(self._poll_clone_count)
        self._items: dict[int, ProjectCard] = {}
        self._column_count = 0
        self._spacer_row: int | None = None
        self._listing: ListingWorker | None = None
        self._download: DownloadWorker | None = None
        self._thumbnails: ThumbnailWorker | None = None
        # Apply the persisted language before any widget reads i18n.tr().
        i18n.set_language(settings.get("language", i18n.DEFAULT))
        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        self.refresh_listing()

    # UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        self._stack = QStackedWidget()

        # Page 0: menu -------------------------------------------------
        menu = QWidget()
        menu_box = QVBoxLayout(menu)
        menu_box.setContentsMargins(12, 12, 12, 12)
        menu_box.setSpacing(12)

        header = QHBoxLayout()
        title_group = QVBoxLayout()
        title = QLabel("Basic Engine Hub")
        title.setObjectName("appTitle")
        title_group.addWidget(title)
        header.addLayout(title_group)
        header.addStretch(1)
        self.refresh_button = QPushButton(i18n.tr("refresh"))
        self.refresh_button.clicked.connect(self.refresh_listing)
        header.addWidget(self.refresh_button)
        self.settings_button = QPushButton(i18n.tr("menu_settings"))
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.clicked.connect(self._open_settings)
        header.addWidget(self.settings_button)
        menu_box.addLayout(header)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchEdit")
        self.search_edit.setPlaceholderText(i18n.tr("search_placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filter_cards)
        menu_box.addWidget(self.search_edit)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        for col in range(4):
            self._grid.setColumnStretch(col, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._grid_container)
        menu_box.addWidget(self._scroll, 1)

        self._stack.addWidget(menu)

        # Page 1: player ------------------------------------------------
        self.player = Player()
        self.player.load_failed.connect(self._on_player_failed)

        player_page = QWidget()
        player_box = QVBoxLayout(player_page)
        player_box.setContentsMargins(12, 12, 12, 12)
        player_box.setSpacing(8)

        player_header = QHBoxLayout()
        self.back_button = QPushButton(i18n.tr("back"))
        self.back_button.clicked.connect(self._back_to_menu)
        player_header.addWidget(self.back_button)
        # Left corner (other side from the transport controls): Fullscreen
        # button, then the live clone count and the clones icon.
        self.clones_button = QPushButton()
        self.clones_button.setIcon(QIcon(str(cache.BASE / "Assets" / "Clones.svg")))
        self.clones_button.setIconSize(QSize(22, 22))
        self.clones_button.setToolTip(i18n.tr("clones"))
        self.clones_button.setFlat(True)
        self.clones_button.clicked.connect(self.player.toggle_clones_panel)
        self._clone_count_label = QLabel("0")
        self._clone_count_label.setObjectName("cloneCount")
        self._clone_count_label.setToolTip(i18n.tr("clones_active"))
        self.fullscreen_button = QPushButton()
        self.fullscreen_button.setIcon(QIcon(str(cache.BASE / "Assets" / "FullScreen.svg")))
        self.fullscreen_button.setIconSize(QSize(22, 22))
        self.fullscreen_button.setToolTip(i18n.tr("fullscreen"))
        self.fullscreen_button.clicked.connect(self.player.enter_fullscreen)
        player_header.addWidget(self.fullscreen_button)
        player_header.addWidget(self._clone_count_label)
        player_header.addWidget(self.clones_button)
        player_header.addStretch(1)
        self.player_title = QLabel()
        self.player_title.setObjectName("playerTitle")
        self.player_title.setTextFormat(Qt.TextFormat.PlainText)
        player_header.addWidget(self.player_title)
        player_header.addStretch(1)
        self.variables_button = QPushButton(i18n.tr("variables"))
        self.variables_button.clicked.connect(lambda: self._open_variables_panel("variable"))
        player_header.addWidget(self.variables_button)
        self.lists_button = QPushButton(i18n.tr("lists"))
        self.lists_button.clicked.connect(lambda: self._open_variables_panel("list"))
        player_header.addWidget(self.lists_button)
        self.start_button = QPushButton()
        self.start_button.setIcon(QIcon(str(cache.BASE / "Assets" / "green-flag.svg")))
        self.start_button.setIconSize(QSize(22, 22))
        self.start_button.setToolTip(i18n.tr("iniciar"))
        self.start_button.clicked.connect(self._start_project)
        self.pause_button = QPushButton()
        self.pause_button.setIcon(QIcon(str(cache.BASE / "Assets" / "pause.svg")))
        self.pause_button.setIconSize(QSize(22, 22))
        self.pause_button.setToolTip(i18n.tr("pausar"))
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button = QPushButton()
        self.stop_button.setIcon(QIcon(str(cache.BASE / "Assets" / "Stop.svg")))
        self.stop_button.setIconSize(QSize(22, 22))
        self.stop_button.setToolTip(i18n.tr("detener"))
        self.stop_button.clicked.connect(self._stop_project)
        self.start_button.setProperty("role", "primary")
        self.stop_button.setProperty("role", "danger")
        # Fullscreen chrome: any widget listed here is hidden while the
        # project runs in real fullscreen (kept as attributes so the smoke
        # test and the fullscreen handler can reach them).
        self._chrome_widgets = [
            self.back_button,
            self.player_title,
            self.variables_button,
            self.lists_button,
            self.start_button,
            self.pause_button,
            self.stop_button,
            self.fullscreen_button,
            self._clone_count_label,
            self.clones_button,
        ]
        player_header.addWidget(self.start_button)
        player_header.addWidget(self.pause_button)
        player_header.addWidget(self.stop_button)
        player_box.addLayout(player_header)

        player_box.addWidget(self.player, 1)

        self._stack.addWidget(player_page)

        # Global bottom bar, visible on both pages ----------------------
        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        bottom.addWidget(self.progress)
        self.status_label = QLabel(i18n.tr("status_ready"))
        self.status_label.setObjectName("statusBar")
        bottom.addWidget(self.status_label, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(self._stack, 1)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        outer.addWidget(sep)
        outer.addLayout(bottom)

        # Fullscreen coordination: the chrome list must be complete before the
        # web player can request fullscreen, so connect after the whole UI build.
        self._chrome_widgets.extend([self.progress, self.status_label])
        self.player.fullscreen_requested.connect(self._on_fullscreen_requested)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        if busy:
            self.progress.show()
            if message:
                self.status_label.setText(message)
        else:
            self.progress.hide()

    # Settings -------------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(i18n.tr("settings_title"))
        form = QFormLayout(dialog)
        combo = QComboBox()
        for code, label in i18n.LANGUAGES.items():
            combo.addItem(label, code)
        combo.setCurrentIndex(list(i18n.LANGUAGES).index(i18n.current()))

        def _on_lang(idx):
            code = combo.itemData(idx)
            if code != i18n.current():
                i18n.set_language(code)
                settings.set("language", code)
                self._retranslate()
                if self._stack.currentIndex() == 1:
                    self.player.set_language(code)

        combo.currentIndexChanged.connect(_on_lang)
        form.addRow(i18n.tr("settings_language"), combo)
        close_btn = QPushButton(i18n.tr("close"))
        close_btn.clicked.connect(dialog.accept)
        form.addRow(close_btn)
        clear_cache_btn = QPushButton(i18n.tr("clear_cache"))
        clear_cache_btn.clicked.connect(lambda: self._confirm_clear_cache(dialog))
        form.addRow(clear_cache_btn)
        dialog.exec()

    def _confirm_clear_cache(self, dialog) -> None:
        if self._downloading:
            return
        answer = QMessageBox.question(
            dialog,
            i18n.tr("clear_cache_title"),
            i18n.tr("clear_cache_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = cache.clear_project_cache()
        for card in self._items.values():
            card.set_missing()
        self.status_label.setText(i18n.tr("cache_cleared", count=removed))

    def _retranslate(self) -> None:
        """Re-apply every static widget string in the current language."""
        self.refresh_button.setText(i18n.tr("refresh"))
        self.settings_button.setText(i18n.tr("menu_settings"))
        self.search_edit.setPlaceholderText(i18n.tr("search_placeholder"))
        self.back_button.setText(i18n.tr("back"))
        self.variables_button.setText(i18n.tr("variables"))
        self.lists_button.setText(i18n.tr("lists"))
        self.start_button.setToolTip(i18n.tr("iniciar"))
        self.pause_button.setToolTip(i18n.tr("reanudar" if self._paused else "pausar"))
        self.stop_button.setToolTip(i18n.tr("detener"))
        self.clones_button.setToolTip(i18n.tr("clones"))
        self._clone_count_label.setToolTip(i18n.tr("clones_active"))
        self.fullscreen_button.setToolTip(i18n.tr("fullscreen"))
        # Window title "Basic Engine Hub" stays untranslated.
        for card in self._items.values():
            card.retranslate()
        dialog = self._detail_dialog
        if dialog is not None:
            dialog.retranslate()
        dialog = self._variables_dialog
        if dialog is not None and dialog.isVisible():
            pid = self._current_pid
            card = self._items.get(pid) if pid is not None else None
            title = (
                (card.project.get("title") if card is not None else None)
                or i18n.tr("project_default_title", pid=pid)
            )
            kind_key = "var_title" if self._variables_dialog_kind == "variable" else "list_title"
            dialog.setWindowTitle(i18n.tr(kind_key, title=title))
            for index, key in enumerate(("col_save", "col_variable", "col_target", "col_value")):
                item = self._variables_table.horizontalHeaderItem(index)
                if item is not None:
                    item.setText(i18n.tr(key))
            self._variables_refresh_button.setText(i18n.tr("refresh"))
            self._variables_info_label.setText(i18n.tr("panel_info"))

    # Menu grid -----------------------------------------------------------

    def _clear_cards(self) -> None:
        if self._spacer_row is not None:
            self._grid.setRowStretch(self._spacer_row, 0)
            self._spacer_row = None
        for card in self._items.values():
            self._grid.removeWidget(card)
            card.deleteLater()
        self._items.clear()

    def _filter_cards(self, text: str) -> None:
        """Show only cards whose title/author/id match the search text."""
        needle = text.strip().lower()
        visible = 0
        for card in self._items.values():
            match = (
                not needle
                or needle in card.project.get("title", "").lower()
                or needle in card.project.get("username", "").lower()
                or needle in str(card.pid)
            )
            card.setVisible(match)
            if match:
                visible += 1
        if self._items and needle:
            self.status_label.setText(
                i18n.tr("filter_count", visible=visible, total=len(self._items))
            )
        elif self._items:
            self.status_label.setText(
                i18n.tr("projects_found", total=len(self._items))
            )

    # Listing --------------------------------------------------------------

    def refresh_listing(self) -> None:
        if self._downloading:
            return
        if self._listing is not None and self._listing.isRunning():
            return
        self._clear_cards()
        self._set_busy(True, i18n.tr("loading_projects"))
        self.refresh_button.setEnabled(False)
        self._listing = ListingWorker(SOURCE_USER, STUDIO_ID, self)
        self._listing.finished_ok.connect(self._on_listing_ok)
        self._listing.failed.connect(self._on_listing_failed)
        self._listing.start()

    def _on_listing_ok(self, projects: list[dict]) -> None:
        self._set_busy(False)
        self.refresh_button.setEnabled(not self._downloading)
        self._clear_cards()
        featured = [
            project
            for project in projects
            if int(project["id"]) == self.FEATURED_PROJECT_ID
        ]
        rest = [
            project
            for project in projects
            if int(project["id"]) != self.FEATURED_PROJECT_ID
        ]
        for index, project in enumerate(featured + rest):
            card = ProjectCard(
                project, featured=int(project["id"]) == self.FEATURED_PROJECT_ID
            )
            card.set_favorite(self._is_favorite(card.pid))
            # clicked emits the pid (int); the detail dialog needs the card dict.
            card.clicked.connect(
                lambda pid, p=project: self._open_project_detail(p)
            )
            row, col = divmod(index, max(1, self._column_count or 4))
            self._grid.addWidget(card, row, col)
            self._items[card.pid] = card
        self._spacer_row = self._grid.rowCount()
        self._grid.setRowStretch(self._spacer_row, 1)
        self.status_label.setText(i18n.tr("projects_found", total=len(projects)))
        self._thumbnails = ThumbnailWorker(projects, self)
        self._thumbnails.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._thumbnails.avatar_ready.connect(self._on_avatar_ready)
        self._thumbnails.done.connect(self._on_thumbnails_done)
        self._thumbnails.start()
        self._relayout_cards()

    @staticmethod
    def _is_favorite(project_id: int) -> bool:
        return any(
            str(value).isdigit() and int(value) == project_id
            for value in settings.get("favorites", [])
        )

    def _relayout_cards(self) -> None:
        if not self._items or not hasattr(self, "_scroll"):
            return
        spacing = self._grid.spacing()
        columns = max(1, min(4, (self._scroll.viewport().width() + spacing) // (260 + spacing)))
        if columns == self._column_count and self._spacer_row is not None:
            return
        self._column_count = columns
        for col in range(4):
            self._grid.setColumnStretch(col, int(col < columns))
        if self._spacer_row is not None:
            self._grid.setRowStretch(self._spacer_row, 0)
            self._spacer_row = None
        for index, card in enumerate(self._items.values()):
            self._grid.removeWidget(card)
            row, col = divmod(index, columns)
            self._grid.addWidget(card, row, col)
        self._spacer_row = self._grid.rowCount()
        self._grid.setRowStretch(self._spacer_row, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._relayout_cards)

    def _on_listing_failed(self, message: str) -> None:
        self._set_busy(False)
        self.refresh_button.setEnabled(not self._downloading)
        self.status_label.setText(i18n.tr("status_load_error"))
        QMessageBox.warning(self, i18n.tr("error_title"), message)

    # Thumbnails ------------------------------------------------------------

    def _on_thumbnail_ready(self, pid: int, path: str) -> None:
        card = self._items.get(pid)
        if card is not None:
            card.set_thumbnail(path)

    def _on_avatar_ready(self, creator_id: int, path: str) -> None:
        for card in self._items.values():
            if int(card.project.get("creator_id") or 0) == creator_id:
                card.set_avatar(path)

    def _on_thumbnails_done(self) -> None:
        self._thumbnails = None

    # Project detail dialog -------------------------------------------------

    def _open_project_detail(self, project: dict) -> None:
        """Open the modal detail dialog for a project card."""
        fav = int(project["id"]) in set(settings.get("favorites", []))
        thumb = None
        card = self._items.get(int(project["id"]))
        if card is not None:
            thumb = card.thumbnail_path
        dialog = ProjectDetailDialog(project, thumb, fav, self)
        dialog.play_requested.connect(self._open_project)
        dialog.favorite_toggled.connect(self._on_favorite_toggled)
        dialog.finished.connect(lambda _: self._close_detail_dialog(dialog))
        self._detail_dialog = dialog
        dialog.exec()

    def _close_detail_dialog(self, dialog) -> None:
        if self._detail_dialog is dialog:
            self._detail_dialog = None

    def _on_favorite_toggled(self, pid: int, fav: bool) -> None:
        """Persist a favorite change and mirror it on the card marker."""
        favorites = list(settings.get("favorites", []))
        if fav:
            if pid not in favorites:
                favorites.append(pid)
        else:
            favorites = [
                item
                for item in favorites
                if (not isinstance(item, int) or item != pid)
                and (not isinstance(item, str) or not item.isdigit() or int(item) != pid)
            ]
        settings.set("favorites", favorites)
        card = self._items.get(pid)
        if card is not None:
            card.set_favorite(fav)

    # Card click -> download -> load -----------------------------------------

    def _back_to_menu(self) -> None:
        self._clone_count_timer.stop()
        self._stack.setCurrentIndex(0)

    def _poll_clone_count(self) -> None:
        self.player.get_clone_count(self._on_clone_count)

    def _on_clone_count(self, raw) -> None:
        try:
            self._clone_count_label.setText(str(int(raw)))
        except (TypeError, ValueError):
            pass

    def _toggle_pause(self) -> None:
        """Pause/resume the running project by freezing the VM stepping loop."""
        if self._paused:
            self.player.resume_game()
            self.pause_button.setToolTip(i18n.tr("pausar"))
            self._paused = False
        else:
            self.player.pause_game()
            self.pause_button.setToolTip(i18n.tr("reanudar"))
            self._paused = True

    def _reset_pause(self) -> None:
        if self._paused:
            self._paused = False
            self.pause_button.setToolTip(i18n.tr("pausar"))

    def _on_fullscreen_requested(self, fs: bool) -> None:
        """Enter/leave real fullscreen together with the web player."""
        for w in self._chrome_widgets:
            w.setVisible(not fs)
        if fs:
            self.showFullScreen()
        else:
            self.showNormal()
            # QTBUG workaround: after the WebEngine fullscreen round-trip the
            # renderer viewport can stay at the fullscreen size; force a
            # resize event so Chromium relayouts to the restored window.
            QTimer.singleShot(0, self._kick_player_view)

    def _kick_player_view(self) -> None:
        w = self.player
        s = w.size()
        if s.isEmpty():
            return
        w.resize(s.width() + 1, s.height())
        w.resize(s.width(), s.height())

    def _start_project(self) -> None:
        self._reset_pause()
        self.player.green_flag()

    def _stop_project(self) -> None:
        self._reset_pause()
        self.player.stop_all()

    def _open_project(self, pid: int) -> None:
        card = self._items.get(pid)
        if card is None:
            return
        project = card.project
        title = project.get("title") or i18n.tr("project_default_title", pid=pid)
        if pid == self._current_pid:
            # Same project already in the player; keep the page, only refresh status.
            if self._downloading:
                self.status_label.setText(i18n.tr("loading"))
            else:
                self.status_label.setText(i18n.tr("cached_title", title=title))
            self._stack.setCurrentIndex(1)
            self._clone_count_timer.start()
            return
        if self._variables_dialog is not None:
            # A different project is loading: close the modeless variables panel.
            self._variables_dialog.close()
            self._variables_dialog = None
            self._variables_dialog_kind = None
        self._reset_pause()
        if self._downloading:
            return
        self._stack.setCurrentIndex(1)
        self._clone_count_timer.start()
        elided = self.player_title.fontMetrics().elidedText(
            title, Qt.TextElideMode.ElideRight, 360
        )
        self.player_title.setText(elided)
        self.player_title.setToolTip(title)
        old_pid = self._current_pid
        old_ids = list(self._saved_ids.get(old_pid, set()))
        if is_cached(pid):
            self.player.switch_project(old_pid, old_ids, pid, list(self._saved_ids.get(pid, set())))
            self._current_pid = pid
            self.status_label.setText(i18n.tr("cached_title", title=title))
            return
        self._pending_switch = (old_pid, old_ids)
        self._downloading = True
        self.refresh_button.setEnabled(False)
        self._set_busy(True, i18n.tr("downloading_pid", pid=pid))
        self._download = DownloadWorker(project, self)
        self._download.done.connect(self._on_download_done)
        self._download.failed.connect(self._on_download_failed)
        self._download.start()

    def _on_download_done(self, pid: int) -> None:
        self._downloading = False
        self.refresh_button.setEnabled(True)
        self._set_busy(False)
        card = self._items.get(pid)
        if card is not None:
            card.set_cached()
            title = card.project.get("title") or i18n.tr("project_default_title", pid=pid)
        else:
            title = i18n.tr("project_default_title", pid=pid)
        old_pid, old_ids = self._pending_switch or (None, [])
        self.player.switch_project(old_pid, old_ids, pid, self._saved_ids.get(pid, set()))
        self._current_pid = pid
        self.status_label.setText(i18n.tr("ready_title", title=title))

    def _on_download_failed(self, pid: int, message: str) -> None:
        self._downloading = False
        self.refresh_button.setEnabled(True)
        self._set_busy(False)
        self.status_label.setText(i18n.tr("download_failed"))
        QMessageBox.warning(self, i18n.tr("error_title"), message)

    # Variables panel -------------------------------------------------------

    def _open_variables_panel(self, kind: str) -> None:
        """Modeless dialog listing one kind (variable|list) with save checkboxes.

        The player keeps running while the panel is open; double-click a value
        to edit it locally.
        """
        if self._current_pid is None:
            QMessageBox.information(
                self, i18n.tr("variables"), i18n.tr("open_project_first")
            )
            return
        if self._variables_dialog is not None and self._variables_dialog.isVisible():
            if self._variables_dialog_kind == kind:
                self._variables_dialog.raise_()
                self._variables_dialog.activateWindow()
                return
            # Different kind: replace the current panel instead of stacking.
            self._variables_dialog.close()
            self._variables_dialog = None
            self._variables_dialog_kind = None
        pid = self._current_pid
        card = self._items.get(pid)
        title = (
            card.project.get("title") if card is not None else None
        ) or i18n.tr("project_default_title", pid=pid)
        dialog = QDialog(self)
        kind_key = "var_title" if kind == "variable" else "list_title"
        dialog.setWindowTitle(i18n.tr(kind_key, title=title))
        dialog.resize(560, 420)
        box = QVBoxLayout(dialog)
        info_label = QLabel(i18n.tr("panel_info"))
        self._variables_info_label = info_label
        info_label.setObjectName("panelInfo")
        info_label.setWordWrap(True)
        box.addWidget(info_label)
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(title_label)
        header.addStretch(1)
        refresh_button = QPushButton(i18n.tr("refresh"))
        self._variables_refresh_button = refresh_button
        header.addWidget(refresh_button)
        box.addLayout(header)
        table = QTableWidget(0, 4, dialog)
        self._variables_table = table
        table.setHorizontalHeaderLabels(
            [
                i18n.tr("col_save"),
                i18n.tr("col_variable"),
                i18n.tr("col_target"),
                i18n.tr("col_value"),
            ]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.cellDoubleClicked.connect(
            lambda row, column: self._edit_variable_cell(dialog, table, row, column)
        )
        box.addWidget(table, 1)
        self._variables_dialog = dialog
        self._variables_dialog_kind = kind

        def reload() -> None:
            self.player.list_variables(
                lambda rows: self._populate_variables_table(
                    dialog,
                    table,
                    pid,
                    [row for row in rows if row.get("kind") == kind],
                )
            )

        refresh_button.clicked.connect(reload)
        reload()
        dialog.show()

    def _populate_variables_table(self, dialog, table, pid: int, rows) -> None:
        """Build/refresh the variables table from JS rows [{id,name,target,value,kind}, ...]."""
        try:
            self._populate_variables_table_inner(dialog, table, pid, rows)
        except Exception as exc:  # noqa: BLE001 - never let a slot abort the app
            self.status_label.setText(i18n.tr("show_variables_failed", exc=exc))

    def _populate_variables_table_inner(self, dialog, table, pid: int, rows) -> None:
        if self._variables_dialog is not dialog or not dialog.isVisible():
            return
        table.setRowCount(0)
        saved = self._saved_ids.setdefault(pid, set())
        for variable in rows:
            row = table.rowCount()
            table.insertRow(row)
            checkbox = QCheckBox()
            checkbox.setChecked(variable["id"] in saved)
            checkbox.toggled.connect(
                lambda checked, vid=variable["id"]: self._on_variable_save_toggled(
                    pid, vid, checked
                )
            )
            cell = QWidget()
            cell_box = QHBoxLayout(cell)
            cell_box.setContentsMargins(0, 0, 0, 0)
            cell_box.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 0, cell)
            kind = variable.get("kind")
            name_text = variable.get("name") or ""
            if variable.get("isCloud"):
                name_text += " ☁"
            table.setItem(row, 1, QTableWidgetItem(name_text))
            table.setItem(row, 2, QTableWidgetItem(variable.get("target") or ""))

            value = variable.get("value")
            if kind == "list":
                value_text = json.dumps(value, ensure_ascii=False)
            else:
                value_text = str(value)
            item = QTableWidgetItem(value_text)
            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "id": variable["id"],
                    "kind": kind,
                    "name": variable.get("name") or "",
                    "pid": pid,
                },
            )
            table.setItem(row, 3, item)
    def _edit_variable_cell(self, dialog, table, row, column) -> None:
        """Prompt for a new value after a double-click on the Valor column (3)."""
        if column != 3:
            return
        try:
            item = table.item(row, column)
            if item is None:
                return
            meta = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(meta, dict):
                return
            vid = meta.get("id")
            kind = meta.get("kind")
            name = meta.get("name") or ""
            pid = meta.get("pid")
            if kind == "list":
                prompt = i18n.tr("edit_list_prompt", name=name)
            else:
                prompt = i18n.tr("edit_value_prompt", name=name)
            text, ok = QInputDialog.getText(
                dialog, i18n.tr("edit_value_title"), prompt, QLineEdit.EchoMode.Normal, item.text()
            )
            if not ok:
                return  # Cancel: leave the value untouched
            parsed = self._parse_edited_value(kind, text)
            self.player.set_variable_value(vid, parsed)
            self.player.list_variables(
                lambda rows, d=dialog, table=table: self._populate_variables_table(
                    d, table, pid, rows
                )
            )
            self.status_label.setText(i18n.tr("variable_updated", name=name))
        except Exception as exc:  # noqa: BLE001 - never let a slot abort the app
            self.status_label.setText(i18n.tr("variable_update_failed", exc=exc))

    @staticmethod
    def _scalarish(entry):
        """Keep numbers/strings/bools as-is; anything else becomes text."""
        if isinstance(entry, (str, int, float, bool)):
            return entry
        return str(entry)

    def _parse_edited_value(self, kind: str, text: str):
        """Parse user-edited text into a JS-friendly value.

        Scalars may only become bool/number/string: arrays/objects typed by
        the user stay as plain text and are never stored into a scalar
        variable. Lists become arrays of scalar elements.
        """
        t = (text or "").strip()
        if kind == "list":
            if not t:
                return []
            if t.startswith("["):
                try:
                    parsed = json.loads(t)
                    if isinstance(parsed, list):
                        return [self._scalarish(entry) for entry in parsed]
                except (TypeError, ValueError):
                    pass
            return [part.strip() for part in t.split(",")]
        low = t.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        try:
            parsed = json.loads(t)  # numbers and JSON string literals
        except (TypeError, ValueError):
            return t
        if isinstance(parsed, (str, bool, int, float)) and parsed is not None:
            return parsed
        return t  # arrays/objects/null typed into a scalar stay as plain text

    def _on_variable_save_toggled(self, pid: int, variable_id: str, checked: bool) -> None:
        ids = self._saved_ids.setdefault(pid, set())
        if checked:
            ids.add(variable_id)
        else:
            ids.discard(variable_id)

    # Misc ------------------------------------------------------------------

    def _on_player_failed(self, message: str) -> None:
        self.status_label.setText(i18n.tr("player_unavailable"))
        QMessageBox.warning(self, i18n.tr("error_title"), message)

    def shutdown(self) -> None:
        self.player.shutdown()
        for worker in (self._listing, self._download, self._thumbnails):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(1500)