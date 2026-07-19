"""Top-level composition for the RomM Companion window."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .api import RommApiClient
from .config import ConnectionConfig, ConnectionStore
from .connection import (
    ClientFactory,
    ConnectionPanel,
    ConnectionSession,
)
from .library_loader import LibraryClientFactory, LibraryLoader
from .library_view import LibraryView
from .models import LibraryItem
from .style import STYLE


class MainWindow(QMainWindow):
    """Compose application-level views and route their state signals."""

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

        store = connection_store or ConnectionStore.system_default()
        self.connection_panel = ConnectionPanel(self)
        self.connection_session = ConnectionSession(
            store,
            client_factory,
            self,
        )
        self.library_loader = LibraryLoader(self)
        self.library_view = LibraryView(items)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_top_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self.library_view)
        splitter.setSizes([220, 1210])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

        self._library_generation = 0
        self._active_library_generation: int | None = None
        self._pending_library_load: tuple[int, LibraryClientFactory] | None = None
        self._close_after_background_work = False
        self._closing = False
        self._connect_connection_signals()
        self._connect_library_signals()
        self.connection_session.initialize()

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)
        layout.addStretch()

        self.source_status = QPushButton("NOT CONNECTED")
        self.source_status.setObjectName("statusPill")
        self.source_status.clicked.connect(self.show_connection_popup)
        layout.addWidget(self.source_status)
        return bar

    def _build_sidebar(self) -> QWidget:
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
        self._update_platform_summary()
        return sidebar

    def _connect_connection_signals(self) -> None:
        self.connection_panel.connect_requested.connect(
            self.connection_session.connect_requested
        )
        self.connection_panel.disconnect_requested.connect(
            self.connection_session.disconnect_requested
        )
        self.connection_session.configuration_loaded.connect(
            self.connection_panel.load_config
        )
        self.connection_session.connecting.connect(self._show_connecting)
        self.connection_session.connected.connect(self._show_connected)
        self.connection_session.connected.connect(self._queue_library_load)
        self.connection_session.disconnected.connect(self._show_disconnected)
        self.connection_session.disconnected.connect(self._clear_library)
        self.connection_session.finished.connect(
            lambda: self.connection_panel.set_busy(False)
        )
        self.connection_session.finished.connect(self._finish_pending_close)
        self.connection_session.message_changed.connect(self.statusBar().showMessage)

    def _connect_library_signals(self) -> None:
        self.library_loader.items_available.connect(self._library_items_available)
        self.library_loader.succeeded.connect(self._library_loaded)
        self.library_loader.failed.connect(self._library_failed)
        self.library_loader.finished.connect(self._library_load_finished)
        self.library_loader.finished.connect(self._finish_pending_close)

    def show_connection_popup(self) -> None:
        self.connection_panel.show_for(self.source_status)

    def set_library_items(self, items: Iterable[LibraryItem]) -> None:
        self.library_view.set_items(items)
        self._update_platform_summary()

    def append_library_items(self, items: Iterable[LibraryItem]) -> None:
        self.library_view.append_items(items)
        self._update_platform_summary()

    def _update_platform_summary(self) -> None:
        platforms = sorted(
            {item.platform for item in self.library_view.items if item.platform}
        )
        self.platform_summary.setText("\n".join(platforms))

    def _show_connecting(self) -> None:
        self.connection_panel.show_connecting()
        self.source_status.setText("CONNECTING")

    def _show_connected(self, config: ConnectionConfig) -> None:
        self.connection_panel.show_connected(config)
        self.source_status.setText("CONNECTED")

    def _show_disconnected(self) -> None:
        self.connection_panel.show_disconnected()
        self.source_status.setText("NOT CONNECTED")

    def _queue_library_load(self, _config: ConnectionConfig) -> None:
        client_factory = self.connection_session.active_client_factory
        if client_factory is None or self._closing:
            return
        self._library_generation += 1
        self._pending_library_load = (self._library_generation, client_factory)
        QTimer.singleShot(0, self._start_pending_library_load)

    def _start_pending_library_load(self) -> None:
        pending = self._pending_library_load
        if pending is None or self._closing or self.library_loader.is_running:
            return
        generation, client_factory = pending
        self._pending_library_load = None
        if (
            generation != self._library_generation
            or self.connection_session.active_connection is None
        ):
            return
        self._active_library_generation = generation
        self.set_library_items(())
        self.statusBar().showMessage("Loading library")
        self.library_loader.start(client_factory)

    def _library_items_available(self, items: tuple[LibraryItem, ...]) -> None:
        if self._active_library_generation != self._library_generation:
            return
        self.append_library_items(items)

    def _library_loaded(self) -> None:
        if self._active_library_generation != self._library_generation:
            return
        self.statusBar().showMessage("Connected")

    def _library_failed(self, message: str) -> None:
        if self._active_library_generation == self._library_generation:
            self.statusBar().showMessage(message)

    def _library_load_finished(self) -> None:
        self._active_library_generation = None
        self._start_pending_library_load()

    def _clear_library(self) -> None:
        self._library_generation += 1
        self._pending_library_load = None
        self.set_library_items(())

    def _finish_pending_close(self) -> None:
        if (
            self._close_after_background_work
            and not self.connection_session.is_running
            and not self.library_loader.is_running
        ):
            self._close_after_background_work = False
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._closing = True
        self._pending_library_load = None
        checking_connection = self.connection_session.is_running
        loading_library = self.library_loader.is_running
        if checking_connection or loading_library:
            self._close_after_background_work = True
            if checking_connection and loading_library:
                message = "Closing after background work"
            elif checking_connection:
                message = "Closing after the connection check"
            else:
                message = "Closing after the library load"
            self.statusBar().showMessage(message)
            event.ignore()
            return
        super().closeEvent(event)
