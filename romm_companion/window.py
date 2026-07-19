"""Main window orchestration for the RomM Companion shell."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .api import RommApiClient
from .config import (
    ConnectionConfig,
    ConnectionStorageError,
    ConnectionStore,
    is_valid_client_token,
)
from .connection import ClientFactory, ConnectionCheck
from .models import LibraryItem
from .style import STYLE
from .widgets import FullRowCheckBox, LibraryGrid


@dataclass(frozen=True)
class _PendingConnection:
    config: ConnectionConfig
    token: str
    persist_on_success: bool


class MainWindow(QMainWindow):
    def __init__(
        self,
        items: Iterable[LibraryItem] = (),
        connection_store: ConnectionStore | None = None,
        client_factory: ClientFactory = RommApiClient,
    ) -> None:
        super().__init__()
        self.setWindowTitle("RomM Companion")
        self.resize(1440, 900)
        self.setMinimumSize(1050, 700)
        self.setStyleSheet(STYLE)
        self._items: tuple[LibraryItem, ...] = ()
        self._connection_store = (
            connection_store
            if connection_store is not None
            else ConnectionStore.system_default()
        )
        self._pending_connection: _PendingConnection | None = None
        self._startup_connection: ConnectionConfig | None = None
        self._active_connection: ConnectionConfig | None = None
        self._connection_check = ConnectionCheck(client_factory, self)
        self._connection_check.succeeded.connect(self.connection_succeeded)
        self._connection_check.failed.connect(self.connection_failed)
        self._connection_check.finished.connect(self.connection_finished)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.build_top_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.build_sidebar())
        splitter.addWidget(self.build_library())
        splitter.setSizes([220, 1210])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        self.setStatusBar(status)
        self.load_connection_config()
        self.set_library_items(items)

    def build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)
        mark = QLabel("◆")
        mark.setObjectName("brandMark")
        # layout.addWidget(mark)
        layout.addStretch()

        self.connection_popup = self.build_connection_popup()
        self.source_status = QPushButton("NOT CONNECTED")
        self.source_status.setObjectName("statusPill")
        self.source_status.clicked.connect(self.show_connection_popup)
        layout.addWidget(self.source_status)
        return bar

    def build_connection_popup(self) -> QFrame:
        popup = QFrame(self)
        popup.setWindowFlags(Qt.WindowType.Popup)
        popup.setObjectName("connectionPopup")
        popup.setMinimumWidth(320)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.connection_stack = QStackedWidget()
        self.connection_form = self.build_connection_form()
        self.connected_view = self.build_connected_view()
        self.connection_stack.addWidget(self.connection_form)
        self.connection_stack.addWidget(self.connected_view)
        layout.addWidget(self.connection_stack)
        QWidget.setTabOrder(self.server_url_input, self.client_token_input)
        QWidget.setTabOrder(
            self.client_token_input, self.allow_insecure_http_input
        )
        QWidget.setTabOrder(self.allow_insecure_http_input, self.connect_button)
        return popup

    def build_connection_form(self) -> QWidget:
        connection_form = QWidget()
        form = QFormLayout(connection_form)
        form.setContentsMargins(16, 16, 16, 16)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.server_url_input = QLineEdit()
        self.server_url_input.setObjectName("serverUrlInput")
        form.addRow("Server URL", self.server_url_input)

        self.client_token_input = QLineEdit()
        self.client_token_input.setObjectName("clientTokenInput")
        self.client_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_token_input.setMaxLength(68)
        form.addRow("Client API Token", self.client_token_input)

        self.allow_insecure_http_input = FullRowCheckBox("Allow insecure HTTP")
        self.allow_insecure_http_input.setObjectName("insecureHttpInput")
        form.addRow(self.allow_insecure_http_input)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("primary")
        self.connect_button.setEnabled(False)
        self.connect_button.clicked.connect(self.connect_to_server)
        form.addRow(self.connect_button)

        self.server_url_input.textChanged.connect(self.update_connect_enabled)
        self.client_token_input.textChanged.connect(self.update_connect_enabled)
        self.allow_insecure_http_input.toggled.connect(
            self.update_connect_enabled
        )

        return connection_form

    def build_connected_view(self) -> QWidget:
        connected_view = QWidget()
        layout = QVBoxLayout(connected_view)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.connection_status_label = QLabel("CONNECTED")
        self.connection_status_label.setObjectName("connectionState")
        layout.addWidget(self.connection_status_label)

        self.connected_server_label = QLabel()
        self.connected_server_label.setObjectName("connectedServer")
        self.connected_server_label.setWordWrap(True)
        layout.addWidget(self.connected_server_label)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect_from_server)
        layout.addWidget(self.disconnect_button)
        return connected_view

    def show_connection_popup(self) -> None:
        self.connection_popup.adjustSize()
        popup_width = self.connection_popup.width()
        position = self.source_status.mapToGlobal(
            QPoint(self.source_status.width() - popup_width, self.source_status.height())
        )
        self.connection_popup.move(position)
        self.connection_popup.show()
        if self._active_connection is None:
            self.server_url_input.setFocus(Qt.FocusReason.PopupFocusReason)
        else:
            self.disconnect_button.setFocus(Qt.FocusReason.PopupFocusReason)

    def load_connection_config(self) -> None:
        try:
            config = self._connection_store.load_config()
        except ConnectionStorageError:
            self.statusBar().showMessage("Connection settings could not be loaded")
            return
        if config is not None:
            self.allow_insecure_http_input.setChecked(config.allow_insecure_http)
            self.server_url_input.setText(config.server_url)
            self._startup_connection = config
            QTimer.singleShot(0, self.connect_on_startup)

    def connect_on_startup(self) -> None:
        config = self._startup_connection
        self._startup_connection = None
        if config is None or self._connection_check.is_running:
            return
        try:
            token = self._connection_store.get_token()
        except ConnectionStorageError:
            self.statusBar().showMessage("Client API Token could not be loaded")
            return
        if token is None or not is_valid_client_token(token):
            return
        self.start_connection(config, token, persist_on_success=False)

    def update_connect_enabled(self) -> None:
        try:
            config = ConnectionConfig.from_input(self.server_url_input.text())
        except ValueError:
            self.connect_button.setEnabled(False)
            return

        is_http = urlsplit(config.server_url).scheme == "http"
        token = self.client_token_input.text()
        token_is_usable = not token.strip() or is_valid_client_token(token)
        transport_is_approved = (
            not is_http or self.allow_insecure_http_input.isChecked()
        )
        self.connect_button.setEnabled(
            not self._connection_check.is_running
            and token_is_usable
            and transport_is_approved
        )

    def connect_to_server(self) -> None:
        if self._connection_check.is_running:
            return
        self._startup_connection = None
        try:
            config = ConnectionConfig.from_input(self.server_url_input.text())
        except ValueError:
            self.update_connect_enabled()
            return
        if urlsplit(config.server_url).scheme == "http":
            config = ConnectionConfig.from_input(
                config.server_url,
                allow_insecure_http=self.allow_insecure_http_input.isChecked(),
            )

        token = self.client_token_input.text().strip()
        if not token:
            try:
                token = self._connection_store.get_token() or ""
            except ConnectionStorageError:
                self.statusBar().showMessage("Client API Token could not be loaded")
                return
        if not is_valid_client_token(token):
            self.statusBar().showMessage("Client API Token is required")
            return

        self.start_connection(config, token, persist_on_success=True)

    def start_connection(
        self,
        config: ConnectionConfig,
        token: str,
        *,
        persist_on_success: bool,
    ) -> None:
        self._pending_connection = _PendingConnection(
            config=config,
            token=token,
            persist_on_success=persist_on_success,
        )
        self.source_status.setText("CONNECTING")
        self.connect_button.setEnabled(False)
        self.connection_popup.close()
        self.statusBar().showMessage("Connecting")
        self._connection_check.start(config, token)

    def connection_succeeded(self) -> None:
        pending = self._pending_connection
        if pending is None:
            return
        if pending.persist_on_success:
            try:
                self._connection_store.save(pending.config, pending.token)
            except ConnectionStorageError:
                self.statusBar().showMessage("Connection settings could not be saved")
                self.show_disconnected_state()
                return

        self.server_url_input.setText(pending.config.server_url)
        self.client_token_input.clear()
        self.show_connected_state(pending.config)
        self.statusBar().showMessage("Connected")

    def connection_failed(self, message: str) -> None:
        self.show_disconnected_state()
        self.statusBar().showMessage(message)

    def connection_finished(self) -> None:
        self._pending_connection = None
        self.update_connect_enabled()

    def show_connected_state(self, config: ConnectionConfig) -> None:
        self._active_connection = config
        self.connected_server_label.setText(config.server_url)
        self.connection_stack.setCurrentWidget(self.connected_view)
        self.source_status.setText("CONNECTED")

    def show_disconnected_state(self) -> None:
        self._active_connection = None
        self.connected_server_label.clear()
        self.connection_stack.setCurrentWidget(self.connection_form)
        self.source_status.setText("NOT CONNECTED")

    def disconnect_from_server(self) -> None:
        self.show_disconnected_state()
        self.statusBar().showMessage("Disconnected")
        self.server_url_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if (
            self._connection_check.is_running
            and not self._connection_check.wait(11_000)
        ):
            self.statusBar().showMessage("Connection check is still finishing")
            event.ignore()
            return
        super().closeEvent(event)

    def build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(205)
        sidebar.setMaximumWidth(250)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 18, 10, 12)
        layout.setSpacing(8)

        section = QLabel("LIBRARY")
        section.setObjectName("section")
        layout.addWidget(section)

        current = QFrame()
        current.setObjectName("navItem")
        current_layout = QHBoxLayout(current)
        current_layout.setContentsMargins(11, 9, 11, 9)
        current_layout.addWidget(QLabel("▦"))
        current_layout.addWidget(QLabel("All games"))
        current_layout.addStretch()
        layout.addWidget(current)

        platforms = QLabel("PLATFORMS")
        platforms.setObjectName("section")
        layout.addWidget(platforms)

        self.platform_summary = QLabel()
        self.platform_summary.setObjectName("muted")
        self.platform_summary.setWordWrap(True)
        layout.addWidget(self.platform_summary)
        layout.addStretch()
        return sidebar

    def build_library(self) -> QWidget:
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(22, 18, 18, 18)
        outer.setSpacing(13)

        self.library_empty_state = QFrame()
        self.library_empty_state.setObjectName("emptyState")
        empty_layout = QVBoxLayout(self.library_empty_state)
        empty_layout.setContentsMargins(28, 30, 28, 30)
        empty_layout.setSpacing(10)
        empty_layout.addStretch()
        empty_eyebrow = QLabel()
        empty_eyebrow.setObjectName("section")
        self.library_empty_eyebrow = empty_eyebrow
        empty_layout.addWidget(empty_eyebrow, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_title = QLabel()
        empty_subtitle = QLabel()
        empty_title.setObjectName("emptyTitle")
        empty_subtitle.setObjectName("emptySubtitle")
        self.library_empty_title = empty_title
        self.library_empty_subtitle = empty_subtitle
        empty_layout.addWidget(empty_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(empty_subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        outer.addWidget(self.library_empty_state, 1)
        self.library_scroll = QScrollArea()
        self.library_scroll.setWidgetResizable(True)
        self.library_grid = LibraryGrid()
        self.library_scroll.setWidget(self.library_grid)
        outer.addWidget(self.library_scroll, 1)
        return content

    def set_library_items(self, items: Iterable[LibraryItem]) -> None:
        """Replace the current library with any iterable of real data records."""
        self._items = tuple(items)
        self.library_grid.set_items(self._items)
        platforms = sorted({item.platform for item in self._items if item.platform})
        if platforms:
            self.platform_summary.setText("\n".join(platforms))
        else:
            self.platform_summary.clear()
        self._update_library_state()

    def _update_library_state(self) -> None:
        has_items = bool(self._items)
        if not has_items:
            self.library_empty_eyebrow.setText("LIBRARY")
            self.library_empty_title.setText("No games")
            self.library_empty_subtitle.setText(self._choose_emote())

        self.library_empty_state.setVisible(not has_items)
        self.library_scroll.setVisible(has_items)
        if self.statusBar() is not None:
            if has_items:
                self.statusBar().showMessage(f"{len(self._items):,} library items loaded")
            else:
                self.statusBar().clearMessage()
    
    def _choose_emote(self) -> str:
        emote_list = (":(", ">:(", ":'(", "D:", "D:<", ":-(", ":/", ":\\", ">:(", ">:O", "(ノಠ益ಠ)ノ",)
        return random.choice(emote_list)
