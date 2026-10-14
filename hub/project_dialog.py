"""Project detail dialog: cover, play, stats, description, instructions, favorite, comments."""

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hub import i18n, scratch_api

_MAX_REPLIES = 5
_COVER_W = 240
_COVER_H = 160
_ACTIVE_DIALOG_WORKERS: set[QThread] = set()


def _release_dialog_worker(worker: QThread) -> None:
    _ACTIVE_DIALOG_WORKERS.discard(worker)
    worker.deleteLater()


class ProjectDetailWorker(QThread):
    """Fetch project metadata without blocking the dialog or main window."""

    detail_ready = Signal(object)

    def __init__(self, project_id: int) -> None:
        super().__init__()
        self._pid = int(project_id)

    def run(self) -> None:
        try:
            detail = scratch_api.fetch_project_detail(self._pid)
        except Exception:  # noqa: BLE001 - metadata is additive, not required
            detail = None
        self.detail_ready.emit(detail)


class CommentsWorker(QThread):
    """One-shot comments fetch; runs off the GUI thread, never raises."""

    comments_ready = Signal(list)
    failed = Signal(str)

    def __init__(self, project_id, parent=None) -> None:
        super().__init__(parent)
        self._pid = int(project_id)

    def run(self) -> None:
        try:
            comments = scratch_api.fetch_project_comments(self._pid)
            self.comments_ready.emit(comments)
        except Exception as exc:  # noqa: BLE001 - keep the dialog alive
            self.failed.emit(str(exc))


class ProjectDetailDialog(QDialog):
    """Modal details for one project: header, stats, texts and comments."""

    play_requested = Signal(int)
    favorite_toggled = Signal(int, bool)

    def __init__(
        self,
        project: dict,
        thumbnail_path: str | None,
        is_favorite: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project = dict(project)
        self._pid = int(project["id"])
        self._thumbnail_path = thumbnail_path
        self._favorite = bool(is_favorite)
        self._detail: dict | None = None
        self._stats = {"views": 0, "loves": 0, "favorites": 0, "remixes": 0}
        self._cover_placeholder = False
        # loading | empty | failed | populated (drives retranslate placeholders).
        self._comments_state = "loading"

        self.setWindowTitle(i18n.tr("project_detail_title"))
        self.setModal(True)
        self.resize(720, 620)
        self.setMinimumSize(640, 520)

        self._build_ui()

        self._detail_worker = ProjectDetailWorker(self._pid)
        _ACTIVE_DIALOG_WORKERS.add(self._detail_worker)
        self._detail_worker.detail_ready.connect(self._apply_detail)
        self._detail_worker.finished.connect(
            lambda worker=self._detail_worker: _release_dialog_worker(worker)
        )
        self._detail_worker.start()

        self._comments_worker = CommentsWorker(self._pid)
        _ACTIVE_DIALOG_WORKERS.add(self._comments_worker)
        self._comments_worker.comments_ready.connect(self._on_comments_ready)
        self._comments_worker.failed.connect(self._on_comments_failed)
        self._comments_worker.finished.connect(
            lambda worker=self._comments_worker: _release_dialog_worker(worker)
        )
        QTimer.singleShot(0, self._comments_worker.start)

    # UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(_COVER_W, _COVER_H)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._thumbnail_path:
            pixmap = QPixmap(self._thumbnail_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    _COVER_W,
                    _COVER_H,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.cover_label.setPixmap(scaled)
                self.cover_label.setObjectName("detailCover")
            else:
                self._show_no_cover()
        else:
            self._show_no_cover()
        top.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(6)

        title_text = self._project.get("title") or i18n.tr(
            "project_default_title", pid=self._pid
        )
        self.title_label = QLabel(title_text)
        self.title_label.setObjectName("detailTitle")
        self.title_label.setWordWrap(True)
        right.addWidget(self.title_label)

        username = self._project.get("username") or ""
        self.author_label = QLabel(f"@{username}")
        self.author_label.setObjectName("detailAuthor")
        right.addWidget(self.author_label)

        self.stats_label = QLabel()
        self.stats_label.setObjectName("detailStats")
        self._refresh_stats()
        right.addWidget(self.stats_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.play_button = QPushButton(i18n.tr("play"))
        self.play_button.setObjectName("detailPlay")
        self.play_button.clicked.connect(self._on_play_clicked)
        buttons.addWidget(self.play_button)
        self.favorite_button = QPushButton()
        self.favorite_button.setObjectName("detailFavorite")
        self.favorite_button.clicked.connect(self._on_favorite_clicked)
        self._set_favorite_text()
        buttons.addWidget(self.favorite_button)
        self.open_button = QPushButton(i18n.tr("open_in_scratch"))
        self.open_button.setObjectName("detailOpen")
        self.open_button.clicked.connect(self._on_open_clicked)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        right.addLayout(buttons)
        right.addStretch(1)

        top.addLayout(right, 1)
        box.addLayout(top)

        # Description / instructions (scrollable body) ------------------
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 4, 0)
        detail_layout.setSpacing(4)

        self._description_header = QLabel(i18n.tr("section_description"))
        self._description_header.setObjectName("detailSection")
        detail_layout.addWidget(self._description_header)
        self.description_label = QLabel(i18n.tr("no_description"))
        self.description_label.setObjectName("detailText")
        self.description_label.setWordWrap(True)
        detail_layout.addWidget(self.description_label)

        self._instructions_header = QLabel(i18n.tr("section_instructions"))
        self._instructions_header.setObjectName("detailSection")
        self._instructions_header.setVisible(False)
        detail_layout.addWidget(self._instructions_header)
        self.instructions_label = QLabel()
        self.instructions_label.setObjectName("detailText")
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setVisible(False)
        detail_layout.addWidget(self.instructions_label)
        detail_layout.addStretch(1)

        self._detail_scroll.setWidget(detail_container)
        box.addWidget(self._detail_scroll, 1)

        # Comments -------------------------------------------------------
        self._comments_header = QLabel(i18n.tr("section_comments"))
        self._comments_header.setObjectName("detailSection")
        box.addWidget(self._comments_header)

        self._comments_scroll = QScrollArea()
        self._comments_scroll.setWidgetResizable(True)
        self._comments_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._comments_container = QWidget()
        self._comments_layout = QVBoxLayout(self._comments_container)
        self._comments_layout.setContentsMargins(0, 0, 4, 0)
        self._comments_layout.setSpacing(6)
        self._comments_placeholder = QLabel(i18n.tr("comments_loading"))
        self._comments_placeholder.setObjectName("commentsPlaceholder")
        self._comments_placeholder.setWordWrap(True)
        self._comments_layout.addWidget(self._comments_placeholder)
        self._comments_layout.addStretch(1)  # keep content top-aligned
        self._comments_scroll.setWidget(self._comments_container)
        box.addWidget(self._comments_scroll, 1)

    # Data ---------------------------------------------------------------

    def _apply_detail(self, detail: dict | None) -> None:
        self._detail = detail or None
        stats = self._detail.get("stats") if self._detail else None
        if isinstance(stats, dict):
            self._stats = {
                "views": self._as_int(stats.get("views")),
                "loves": self._as_int(stats.get("loves")),
                "favorites": self._as_int(stats.get("favorites")),
                "remixes": self._as_int(stats.get("remixes")),
            }
        self._refresh_stats()
        description = (self._detail.get("description") if self._detail else None) or ""
        self.description_label.setText(description or i18n.tr("no_description"))
        instructions = (self._detail.get("instructions") if self._detail else None) or ""
        if instructions:
            self.instructions_label.setText(instructions)
            self._instructions_header.setVisible(True)
            self.instructions_label.setVisible(True)
        else:
            self._instructions_header.setVisible(False)
            self.instructions_label.setVisible(False)

    def _refresh_stats(self) -> None:
        s = self._stats
        self.stats_label.setText(
            i18n.tr("stats_loves", n=s["loves"])
            + "  "
            + i18n.tr("stats_favorites", n=s["favorites"])
            + "  "
            + i18n.tr("stats_views", n=s["views"])
            + "  "
            + i18n.tr("stats_remixes", n=s["remixes"])
        )

    @staticmethod
    def _as_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    # Actions ------------------------------------------------------------

    def _on_play_clicked(self) -> None:
        self.play_requested.emit(self._pid)
        # Modal dialog: close it so the player page is reachable underneath.
        self.accept()

    def _on_open_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl(f"https://scratch.mit.edu/projects/{self._pid}/"))

    def _on_favorite_clicked(self) -> None:
        self._favorite = not self._favorite
        self._set_favorite_text()
        self.favorite_toggled.emit(self._pid, self._favorite)

    def _set_favorite_text(self) -> None:
        key = "favorite_remove" if self._favorite else "favorite_add"
        self.favorite_button.setText(i18n.tr(key))

    # Comments -----------------------------------------------------------

    def _on_comments_ready(self, comments: list) -> None:
        self._comments_placeholder.hide()
        if not comments:
            self._comments_state = "empty"
            self._comments_placeholder.setText(i18n.tr("no_comments"))
            self._comments_placeholder.show()
            return
        self._comments_state = "populated"
        for comment in comments:
            card = self._build_comment_card(comment)
            # Insert before the trailing stretch so cards stay top-aligned.
            self._comments_layout.insertWidget(self._comments_layout.count() - 1, card)

    def _on_comments_failed(self, message: str) -> None:
        self._comments_state = "failed"
        self._comments_placeholder.setText(i18n.tr("comments_unavailable"))

    def _build_comment_card(self, comment: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("commentCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(8, 6, 8, 6)
        box.setSpacing(2)

        user = QLabel(comment.get("user") or "")
        user.setObjectName("commentUser")
        box.addWidget(user)

        content = QLabel(comment.get("content") or "")
        content.setObjectName("commentContent")
        content.setWordWrap(True)
        box.addWidget(content)

        timestamp = QLabel(comment.get("timestamp") or "")
        timestamp.setObjectName("commentTime")
        box.addWidget(timestamp)

        for reply in list(comment.get("replies") or [])[:_MAX_REPLIES]:
            reply_label = QLabel(
                f"↳ {reply.get('user') or ''}: {reply.get('content') or ''}"
            )
            reply_label.setObjectName("commentReply")
            reply_label.setWordWrap(True)
            box.addWidget(reply_label)

        return card

    # Translation --------------------------------------------------------

    def retranslate(self) -> None:
        """Refresh every tr() text on the dialog; content texts stay untouched."""
        self.setWindowTitle(i18n.tr("project_detail_title"))
        self.play_button.setText(i18n.tr("play"))
        self.open_button.setText(i18n.tr("open_in_scratch"))
        self._set_favorite_text()
        self._description_header.setText(i18n.tr("section_description"))
        self._instructions_header.setText(i18n.tr("section_instructions"))
        self._comments_header.setText(i18n.tr("section_comments"))
        self._refresh_stats()
        if self._cover_placeholder:
            self.cover_label.setText(i18n.tr("no_cover"))
        description = (self._detail.get("description") if self._detail else None) or ""
        if not description:
            self.description_label.setText(i18n.tr("no_description"))
        if self._comments_state == "loading":
            self._comments_placeholder.setText(i18n.tr("comments_loading"))
        elif self._comments_state == "empty":
            self._comments_placeholder.setText(i18n.tr("no_comments"))
        elif self._comments_state == "failed":
            self._comments_placeholder.setText(i18n.tr("comments_unavailable"))

    # Internals ----------------------------------------------------------

    def _show_no_cover(self) -> None:
        self._cover_placeholder = True
        self.cover_label.setObjectName("detailCoverEmpty")
        self.cover_label.setText(i18n.tr("no_cover"))
        self.cover_label.style().unpolish(self.cover_label)
        self.cover_label.style().polish(self.cover_label)