"""Connection popup presentation and form interaction."""

from __future__ import annotations

from urllib.parse import urlsplit

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import ConnectionConfig, is_valid_client_token
from ..widgets import FullRowCheckBox


class ConnectionPanel(QFrame):
    """Present disconnected and connected states without owning persistence."""

    connect_requested = Signal(object, str)
    disconnect_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setObjectName("connectionPopup")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.connection_form = self._build_connection_form()
        self.connected_view = self._build_connected_view()
        self.stack.addWidget(self.connection_form)
        self.stack.addWidget(self.connected_view)
        layout.addWidget(self.stack)

        QWidget.setTabOrder(self.server_url_input, self.client_token_input)
        QWidget.setTabOrder(
            self.client_token_input, self.allow_insecure_http_input
        )
        QWidget.setTabOrder(self.allow_insecure_http_input, self.connect_button)

    def _build_connection_form(self) -> QWidget:
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
        self.connect_button.clicked.connect(self._request_connection)
        form.addRow(self.connect_button)

        self.server_url_input.textChanged.connect(self._update_connect_enabled)
        self.client_token_input.textChanged.connect(self._update_connect_enabled)
        self.allow_insecure_http_input.toggled.connect(
            self._update_connect_enabled
        )
        return connection_form

    def _build_connected_view(self) -> QWidget:
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
        self.disconnect_button.clicked.connect(self.disconnect_requested)
        layout.addWidget(self.disconnect_button)
        return connected_view

    def load_config(self, config: ConnectionConfig) -> None:
        self.allow_insecure_http_input.setChecked(config.allow_insecure_http)
        self.server_url_input.setText(config.server_url)

    def show_for(self, anchor: QWidget) -> None:
        self.adjustSize()
        position = anchor.mapToGlobal(
            QPoint(anchor.width() - self.width(), anchor.height())
        )
        self.move(position)
        self.show()
        if self.stack.currentWidget() is self.connection_form:
            self.server_url_input.setFocus(Qt.FocusReason.PopupFocusReason)
        else:
            self.disconnect_button.setFocus(Qt.FocusReason.PopupFocusReason)

    def show_connecting(self) -> None:
        self.set_busy(True)
        self.close()

    def show_connected(self, config: ConnectionConfig) -> None:
        self.server_url_input.setText(config.server_url)
        self.client_token_input.clear()
        self.connected_server_label.setText(config.server_url)
        self.stack.setCurrentWidget(self.connected_view)

    def show_disconnected(self) -> None:
        self.connected_server_label.clear()
        self.stack.setCurrentWidget(self.connection_form)
        if self.isVisible():
            self.focus_form()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_connect_enabled()

    def focus_form(self) -> None:
        self.server_url_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _request_connection(self) -> None:
        if self._busy:
            return
        try:
            config = ConnectionConfig.from_input(self.server_url_input.text())
        except ValueError:
            self._update_connect_enabled()
            return
        if urlsplit(config.server_url).scheme == "http":
            config = ConnectionConfig.from_input(
                config.server_url,
                allow_insecure_http=self.allow_insecure_http_input.isChecked(),
            )
        self.connect_requested.emit(config, self.client_token_input.text().strip())

    def _update_connect_enabled(self) -> None:
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
            not self._busy and token_is_usable and transport_is_approved
        )
