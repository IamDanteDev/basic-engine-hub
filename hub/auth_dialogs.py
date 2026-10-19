"""Sign-in and profile dialogs for the desktop app (Scratch Auth custom flow).

The browser completes the flow (S3): the dialog asks the service for the codes,
shows the public one to copy, opens the auth project with QDesktopServices and
polls verifyToken until the service confirms the username. Only the username is
ever persisted (S4) — the privateCode lives in this dialog and nowhere else.

hub/gui.py owns the header control and only wires these dialogs.
"""

import time
from datetime import datetime

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from hub import auth, cache, i18n, scratch_api

CHIP_AVATAR = 24
PROFILE_AVATAR = 96
POLL_INTERVAL_MS = 2000
# profile-comment is the only method the service needs a username for.
USERNAME_METHOD = "profile-comment"


def rounded(pixmap: QPixmap, radius: int) -> QPixmap:
    """Round a pixmap's corners, with transparent surroundings."""
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


def avatar_pixmap(path, size: int = PROFILE_AVATAR) -> QPixmap:
    """A cached avatar at ``size``, falling back to the shared placeholder.

    An empty path (nothing downloaded yet) and an unreadable file both land on
    Assets/Placeholders/profile.png, the same art the cards use.
    """
    source = str(path) if path else str(cache.PLACEHOLDER_AVATAR)
    pixmap = QPixmap(source)
    if pixmap.isNull() and source != str(cache.PLACEHOLDER_AVATAR):
        pixmap = QPixmap(str(cache.PLACEHOLDER_AVATAR))
    if pixmap.isNull():
        return pixmap
    scaled = pixmap.scaled(
        QSize(size, size),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    return rounded(scaled, size // 2)


def _joined_text(raw: str) -> str:
    """Format the API's ISO timestamp as a plain date; keep it raw if unknown."""
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return str(raw)


# Workers ------------------------------------------------------------------


class TokensWorker(QThread):
    """One getTokens call, off the GUI thread."""

    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, redirect: str, method: str, username: str, parent=None) -> None:
        super().__init__(parent)
        self._redirect = redirect
        self._method = method
        self._username = username

    def run(self) -> None:
        try:
            tokens = auth.request_tokens(self._redirect, self._method, self._username)
        except auth.AuthError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(tokens)


class VerifyWorker(QThread):
    """One verifyToken poll, off the GUI thread."""

    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, private_code: str, parent=None) -> None:
        super().__init__(parent)
        self._private_code = private_code

    def run(self) -> None:
        try:
            result = auth.verify_code(self._private_code)
        except auth.AuthError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)


class ProfileWorker(QThread):
    """Fetch a user's profile and cache their avatar (S6).

    The avatar download is best-effort: when it fails the dialog keeps the
    placeholder and the profile data still arrives.
    """

    finished_ok = Signal(dict, str)  # profile, cached avatar path ("" when none)
    failed = Signal(str)

    def __init__(self, username: str, parent=None) -> None:
        super().__init__(parent)
        self._username = username

    def run(self) -> None:
        try:
            profile = scratch_api.fetch_user_profile(self._username)
        except scratch_api.ScratchAPIError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(profile, self._cached_avatar(profile))

    @staticmethod
    def _cached_avatar(profile: dict) -> str:
        url = profile.get("avatar") or ""
        creator_id = profile.get("id") or 0
        if not url or not creator_id:
            return ""
        existing = cache.find_avatar_path(creator_id)
        if existing.is_file():
            return str(existing)
        destination = cache.avatar_path(creator_id)
        try:
            scratch_api.download_avatar(creator_id, url, destination)
        except scratch_api.ScratchAPIError:
            return ""
        return str(destination)


# Dialogs ------------------------------------------------------------------


class SignInDialog(QDialog):
    """Request the codes, hand the user to the browser, poll until confirmed."""

    signed_in = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("auth_title"))
        self.setMinimumWidth(460)
        self._tokens: dict = {}
        self._expires_at = 0.0
        self._tokens_worker = None
        self._verify_worker = None

        self._poll = QTimer(self)
        self._poll.setInterval(POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._poll_once)

        box = QVBoxLayout(self)
        intro = QLabel(i18n.tr("auth_intro"))
        intro.setObjectName("authIntro")
        intro.setWordWrap(True)
        box.addWidget(intro)

        self._form = QFormLayout()
        self.method_combo = QComboBox()
        for key, method in (
            ("auth_method_cloud", "cloud"),
            ("auth_method_comment", "comment"),
            ("auth_method_profile", USERNAME_METHOD),
        ):
            self.method_combo.addItem(i18n.tr(key), method)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._form.addRow(i18n.tr("auth_method_label"), self.method_combo)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(i18n.tr("auth_username_placeholder"))
        self.username_edit.editingFinished.connect(self._on_username_committed)
        self._username_row = self._form.rowCount()
        self._form.addRow(i18n.tr("auth_username_label"), self.username_edit)

        code_row = QHBoxLayout()
        self.code_edit = QLineEdit()
        self.code_edit.setObjectName("authCode")
        self.code_edit.setReadOnly(True)
        code_row.addWidget(self.code_edit, 1)
        self.copy_button = QPushButton(i18n.tr("auth_copy"))
        self.copy_button.clicked.connect(self._copy_code)
        code_row.addWidget(self.copy_button)
        self._form.addRow(i18n.tr("auth_code_label"), code_row)
        box.addLayout(self._form)

        self.status_label = QLabel(i18n.tr("auth_requesting"))
        self.status_label.setObjectName("authStatus")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.open_button = QPushButton(i18n.tr("auth_open"))
        self.open_button.setProperty("role", "primary")
        self.open_button.clicked.connect(self._open_project)
        buttons.addWidget(self.open_button)
        self.verify_button = QPushButton(i18n.tr("auth_verify"))
        self.verify_button.clicked.connect(self._verify_now)
        buttons.addWidget(self.verify_button)
        buttons.addStretch(1)
        self.close_button = QPushButton(i18n.tr("close"))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        box.addLayout(buttons)

        self._sync_username_row()
        self._request_tokens()

    # Flow ----------------------------------------------------------------

    def _method(self) -> str:
        return str(self.method_combo.currentData() or auth.AUTH_METHOD_DEFAULT)

    def _request_tokens(self) -> None:
        """Ask the service for a fresh pair of codes for the chosen method."""
        if self._tokens_worker is not None and self._tokens_worker.isRunning():
            return
        self._poll.stop()
        self._tokens = {}
        self.code_edit.clear()
        self.open_button.setEnabled(False)
        if self._method() == USERNAME_METHOD and not self.username_edit.text().strip():
            self.status_label.setText(i18n.tr("auth_username_required"))
            return
        self.status_label.setText(i18n.tr("auth_requesting"))
        worker = TokensWorker(
            auth.AUTH_REDIRECT, self._method(), self.username_edit.text().strip(), self
        )
        worker.finished_ok.connect(self._on_tokens)
        worker.failed.connect(self._on_tokens_failed)
        self._tokens_worker = worker
        worker.start()

    def _on_tokens(self, tokens: dict) -> None:
        self._tokens = tokens
        self.code_edit.setText(str(tokens.get("publicCode") or ""))
        self.open_button.setEnabled(True)
        self._expires_at = time.monotonic() + auth.AUTH_CODE_TTL
        self.status_label.setText(self._waiting_text())
        self._poll.start()
        # The whole point is that the user acts in the project: take them there.
        self._open_project()

    def _on_tokens_failed(self, message: str) -> None:
        self.open_button.setEnabled(False)
        self.status_label.setText(i18n.tr("auth_failed", exc=message))

    def _verify_now(self) -> None:
        """Check on demand instead of waiting for the next tick."""
        if not self._tokens.get("privateCode") or time.monotonic() > self._expires_at:
            # Nothing is pending (or the code expired): ask for a fresh pair.
            self._request_tokens()
            return
        self.status_label.setText(i18n.tr("auth_checking"))
        self._poll_once()

    def _poll_once(self) -> None:
        if self._verify_worker is not None and self._verify_worker.isRunning():
            return
        private_code = self._tokens.get("privateCode")
        if not private_code:
            return
        if time.monotonic() > self._expires_at:
            self._poll.stop()
            self.status_label.setText(i18n.tr("auth_expired"))
            return
        worker = VerifyWorker(str(private_code), self)
        worker.finished_ok.connect(self._on_verified)
        worker.failed.connect(self._on_verify_failed)
        self._verify_worker = worker
        worker.start()

    def _on_verified(self, result: dict) -> None:
        if not result.get("valid"):
            self.status_label.setText(self._waiting_text())
            return
        if not auth.is_trusted_redirect(result.get("redirect"), auth.AUTH_REDIRECT):
            self._poll.stop()
            self.status_label.setText(i18n.tr("auth_callback_failed"))
            return
        session = auth.write_session(result.get("username") or "", self._method())
        self._poll.stop()
        if session is None:
            self.status_label.setText(i18n.tr("auth_callback_failed"))
            return
        self.status_label.setText(i18n.tr("auth_done", name=session["username"]))
        self.signed_in.emit(session["username"])
        self.accept()

    def _on_verify_failed(self, message: str) -> None:
        # A transport hiccup mid-poll is not fatal: the code is still pending,
        # so keep waiting instead of flashing an error every interval.
        self.status_label.setText(self._waiting_text())

    # UI ------------------------------------------------------------------

    def _waiting_text(self) -> str:
        method = self._method()
        if method == "comment":
            return i18n.tr("auth_waiting_comment")
        if method == USERNAME_METHOD:
            return i18n.tr("auth_waiting_profile")
        return i18n.tr("auth_waiting_project")

    def _on_method_changed(self, _index: int) -> None:
        self._sync_username_row()
        self._request_tokens()

    def _on_username_committed(self) -> None:
        # A code is bound to the username it was requested with: ask again.
        if self._method() == USERNAME_METHOD:
            self._request_tokens()

    def _sync_username_row(self) -> None:
        self._form.setRowVisible(self._username_row, self._method() == USERNAME_METHOD)

    def _copy_code(self) -> None:
        code = self.code_edit.text().strip()
        if not code:
            return
        self.code_edit.selectAll()
        self.code_edit.copy()
        self.status_label.setText(i18n.tr("auth_copied"))

    def _open_project(self) -> None:
        QDesktopServices.openUrl(QUrl(auth.AUTH_PROJECT_URL))

    def closeEvent(self, event) -> None:
        self._poll.stop()
        for worker in (self._tokens_worker, self._verify_worker):
            if worker is not None and worker.isRunning():
                worker.wait(1500)
        super().closeEvent(event)


class ProfileDialog(QDialog):
    """The signed-in user's own Scratch profile, from the users endpoint (S6)."""

    signed_out = Signal()

    def __init__(self, username: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("profile_title"))
        self.setMinimumWidth(440)
        self._username = username
        self._worker = None

        box = QVBoxLayout(self)

        head = QHBoxLayout()
        self.avatar_label = QLabel()
        self.avatar_label.setObjectName("profileAvatar")
        self.avatar_label.setFixedSize(PROFILE_AVATAR, PROFILE_AVATAR)
        self.avatar_label.setPixmap(avatar_pixmap("", PROFILE_AVATAR))
        head.addWidget(self.avatar_label)
        identity = QVBoxLayout()
        self.name_label = QLabel(f"@{username}")
        self.name_label.setObjectName("profileName")
        identity.addWidget(self.name_label)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("profileMeta")
        self.meta_label.setWordWrap(True)
        identity.addWidget(self.meta_label)
        identity.addStretch(1)
        head.addLayout(identity, 1)
        box.addLayout(head)

        self.bio_title = QLabel(i18n.tr("profile_bio"))
        self.bio_title.setObjectName("profileSection")
        self.bio_label = QLabel()
        self.bio_label.setObjectName("profileBio")
        self.bio_label.setWordWrap(True)
        self.bio_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.addWidget(self.bio_title)
        box.addWidget(self.bio_label)

        self.status_title = QLabel(i18n.tr("profile_status"))
        self.status_title.setObjectName("profileSection")
        self.status_label = QLabel()
        self.status_label.setObjectName("profileStatus")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_title)
        box.addWidget(self.status_label)

        self.message_label = QLabel(i18n.tr("profile_loading"))
        self.message_label.setObjectName("profileMessage")
        self.message_label.setWordWrap(True)
        box.addWidget(self.message_label)
        box.addStretch(1)

        buttons = QHBoxLayout()
        self.open_button = QPushButton(i18n.tr("profile_open"))
        self.open_button.setProperty("role", "primary")
        self.open_button.clicked.connect(self._open_profile)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        self.signout_button = QPushButton(i18n.tr("sign_out"))
        self.signout_button.setProperty("role", "danger")
        self.signout_button.clicked.connect(self._sign_out)
        buttons.addWidget(self.signout_button)
        self.close_button = QPushButton(i18n.tr("close"))
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        box.addLayout(buttons)

        self._hide_profile_texts()
        self._worker = ProfileWorker(username, self)
        self._worker.finished_ok.connect(self._on_profile)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    # Data -----------------------------------------------------------------

    def _on_profile(self, profile: dict, avatar_path: str) -> None:
        self.message_label.hide()
        self.avatar_label.setPixmap(avatar_pixmap(avatar_path, PROFILE_AVATAR))
        meta = []
        joined = _joined_text(profile.get("joined") or "")
        if joined:
            meta.append(i18n.tr("profile_joined", date=joined))
        country = profile.get("country") or ""
        if country:
            meta.append(i18n.tr("profile_country", country=country))
        self.meta_label.setText(" • ".join(meta))
        self._set_section(self.bio_title, self.bio_label, profile.get("bio") or "")
        self._set_section(self.status_title, self.status_label, profile.get("status") or "")

    def _on_failed(self, message: str) -> None:
        self.meta_label.clear()
        self._hide_profile_texts()
        self.message_label.setText(i18n.tr("profile_error", exc=message))
        self.message_label.show()

    def _hide_profile_texts(self) -> None:
        for widget in (self.bio_title, self.bio_label, self.status_title, self.status_label):
            widget.hide()

    @staticmethod
    def _set_section(title, value_label, text: str) -> None:
        """Show a section only when the profile actually carries that text."""
        if text.strip():
            value_label.setText(text)
            title.show()
            value_label.show()
        else:
            title.hide()
            value_label.hide()

    # Actions --------------------------------------------------------------

    def _open_profile(self) -> None:
        QDesktopServices.openUrl(QUrl(f"https://scratch.mit.edu/users/{self._username}/"))

    def _sign_out(self) -> None:
        auth.clear_session()
        self.signed_out.emit()
        self.accept()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(1500)
        super().closeEvent(event)
