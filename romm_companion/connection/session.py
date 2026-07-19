"""Connection persistence and state orchestration independent of widgets."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..config import (
    ConnectionConfig,
    ConnectionStorageError,
    ConnectionStore,
    is_valid_client_token,
)
from .check import ClientFactory, ConnectionCheck


@dataclass(frozen=True)
class _PendingConnection:
    config: ConnectionConfig
    token: str
    persist_on_success: bool


class ConnectionSession(QObject):
    """Coordinate saved credentials and the active verified connection state."""

    configuration_loaded = Signal(object)
    connecting = Signal()
    connected = Signal(object)
    disconnected = Signal()
    message_changed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        store: ConnectionStore,
        client_factory: ClientFactory,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._check = ConnectionCheck(client_factory, self)
        self._check.succeeded.connect(self._connection_succeeded)
        self._check.failed.connect(self._connection_failed)
        self._check.finished.connect(self._connection_finished)
        self._pending: _PendingConnection | None = None
        self._startup_connection: ConnectionConfig | None = None
        self._active_connection: ConnectionConfig | None = None

    @property
    def is_running(self) -> bool:
        return self._check.is_running

    @property
    def active_connection(self) -> ConnectionConfig | None:
        return self._active_connection

    def initialize(self) -> None:
        try:
            config = self._store.load_config()
        except ConnectionStorageError:
            self.message_changed.emit("Connection settings could not be loaded")
            return
        if config is None:
            return
        self.configuration_loaded.emit(config)
        self._startup_connection = config
        QTimer.singleShot(0, self._connect_on_startup)

    @Slot(object, str)
    def connect_requested(self, config: ConnectionConfig, token: str) -> None:
        if self.is_running:
            return
        self._startup_connection = None
        normalized_token = token.strip()
        if not normalized_token:
            try:
                normalized_token = self._store.get_token() or ""
            except ConnectionStorageError:
                self.message_changed.emit("Client API Token could not be loaded")
                return
        if not is_valid_client_token(normalized_token):
            self.message_changed.emit("Client API Token is required")
            return
        self._start(config, normalized_token, persist_on_success=True)

    @Slot()
    def disconnect_requested(self) -> None:
        if self.is_running:
            return
        self._active_connection = None
        self.disconnected.emit()
        self.message_changed.emit("Disconnected")

    def shutdown(self, milliseconds: int) -> bool:
        return self._check.wait(milliseconds)

    def _connect_on_startup(self) -> None:
        config = self._startup_connection
        self._startup_connection = None
        if config is None or self.is_running:
            return
        try:
            token = self._store.get_token()
        except ConnectionStorageError:
            self.message_changed.emit("Client API Token could not be loaded")
            return
        if token is None or not is_valid_client_token(token):
            return
        self._start(config, token, persist_on_success=False)

    def _start(
        self,
        config: ConnectionConfig,
        token: str,
        *,
        persist_on_success: bool,
    ) -> None:
        self._active_connection = None
        self._pending = _PendingConnection(config, token, persist_on_success)
        self.connecting.emit()
        self.message_changed.emit("Connecting")
        self._check.start(config, token)

    @Slot()
    def _connection_succeeded(self) -> None:
        pending = self._pending
        if pending is None:
            return
        if pending.persist_on_success:
            try:
                self._store.save(pending.config, pending.token)
            except ConnectionStorageError:
                self._active_connection = None
                self.disconnected.emit()
                self.message_changed.emit("Connection settings could not be saved")
                return
        self._active_connection = pending.config
        self.connected.emit(pending.config)
        self.message_changed.emit("Connected")

    @Slot(str)
    def _connection_failed(self, message: str) -> None:
        self._active_connection = None
        self.disconnected.emit()
        self.message_changed.emit(message)

    @Slot()
    def _connection_finished(self) -> None:
        self._pending = None
        self.finished.emit()
