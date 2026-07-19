"""Top-level composition for the RomM Companion window."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
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

        self._connect_connection_signals()
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
            self.connection_session.disconnect
        )
        self.connection_session.configuration_loaded.connect(
            self.connection_panel.load_config
        )
        self.connection_session.connecting.connect(self._show_connecting)
        self.connection_session.connected.connect(self._show_connected)
        self.connection_session.disconnected.connect(self._show_disconnected)
        self.connection_session.finished.connect(
            lambda: self.connection_panel.set_busy(False)
        )
        self.connection_session.message_changed.connect(
            self.statusBar().showMessage
        )

    def show_connection_popup(self) -> None:
        self.connection_panel.show_for(self.source_status)

    def set_library_items(self, items: Iterable[LibraryItem]) -> None:
        self.library_view.set_items(items)
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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if (
            self.connection_session.is_running
            and not self.connection_session.shutdown(11_000)
        ):
            self.statusBar().showMessage("Connection check is still finishing")
            event.ignore()
            return
        super().closeEvent(event)
