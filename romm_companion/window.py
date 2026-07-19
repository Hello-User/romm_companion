"""Main window orchestration for the RomM Companion shell."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPoint, Qt
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
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import random

from .models import LibraryItem
from .config import ConnectionConfig, ConnectionStorageError, ConnectionStore
from .style import STYLE
from .widgets import LibraryGrid


class MainWindow(QMainWindow):
    def __init__(
        self,
        items: Iterable[LibraryItem] = (),
        connection_store: ConnectionStore | None = None,
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

        # mark = QLabel("◆")
        # mark.setObjectName("brandMark")
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
        form = QFormLayout(popup)
        form.setContentsMargins(16, 16, 16, 16)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.server_url_input = QLineEdit()
        self.server_url_input.setObjectName("serverUrlInput")
        form.addRow("Server URL", self.server_url_input)

        self.username_input = QLineEdit()
        self.username_input.setObjectName("usernameInput")
        form.addRow("Username", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setObjectName("passwordInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self.password_input)

        self.sign_in_button = QPushButton("Save")
        self.sign_in_button.setObjectName("primary")
        self.sign_in_button.setEnabled(False)
        self.sign_in_button.clicked.connect(self.save_connection)
        form.addRow(self.sign_in_button)

        for field in (
            self.server_url_input,
            self.username_input,
            self.password_input,
        ):
            field.textChanged.connect(self.update_save_enabled)

        QWidget.setTabOrder(self.server_url_input, self.username_input)
        QWidget.setTabOrder(self.username_input, self.password_input)
        QWidget.setTabOrder(self.password_input, self.sign_in_button)
        return popup

    def show_connection_popup(self) -> None:
        self.connection_popup.adjustSize()
        popup_width = self.connection_popup.width()
        position = self.source_status.mapToGlobal(
            QPoint(self.source_status.width() - popup_width, self.source_status.height())
        )
        self.connection_popup.move(position)
        self.connection_popup.show()
        self.server_url_input.setFocus(Qt.FocusReason.PopupFocusReason)

    def load_connection_config(self) -> None:
        try:
            config = self._connection_store.load_config()
        except ConnectionStorageError:
            self.statusBar().showMessage("Connection settings could not be loaded")
            return
        if config is not None:
            self.server_url_input.setText(config.server_url)
            self.username_input.setText(config.username)

    def update_save_enabled(self) -> None:
        try:
            ConnectionConfig.from_input(
                self.server_url_input.text(), self.username_input.text()
            )
        except ValueError:
            self.sign_in_button.setEnabled(False)
            return
        self.sign_in_button.setEnabled(bool(self.password_input.text()))

    def save_connection(self) -> None:
        try:
            config = ConnectionConfig.from_input(
                self.server_url_input.text(), self.username_input.text()
            )
            self._connection_store.save(config, self.password_input.text())
        except ValueError:
            self.update_save_enabled()
            return
        except ConnectionStorageError:
            self.statusBar().showMessage("Connection settings could not be saved")
            return

        self.server_url_input.setText(config.server_url)
        self.username_input.setText(config.username)
        self.password_input.clear()
        self.connection_popup.close()
        self.statusBar().showMessage("Connection settings saved")

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
