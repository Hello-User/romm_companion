"""Qt-safe orchestration for the blocking connection check."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..api import ReadOnlyRommApi, RommApiClient, RommApiError
from ..api.connection import verify_connection
from ..config import ConnectionConfig


class ManagedReadOnlyRommApi(ReadOnlyRommApi, Protocol):
    def close(self) -> None: ...


ClientFactory = Callable[[ConnectionConfig, str], ManagedReadOnlyRommApi]


class _ConnectionWorker(QObject):
    succeeded = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        client_factory: ClientFactory,
        config: ConnectionConfig,
        token: str,
    ) -> None:
        super().__init__()
        self._client_factory = client_factory
        self._config = config
        self._token = token

    @Slot()
    def run(self) -> None:
        client: ManagedReadOnlyRommApi | None = None
        try:
            client = self._client_factory(self._config, self._token)
            verify_connection(client)
        except (ValueError, RommApiError) as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Connection verification failed")
        else:
            self.succeeded.emit()
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                self.finished.emit()


class ConnectionCheck(QObject):
    """Own one background verification task and its thread lifecycle."""

    succeeded = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        client_factory: ClientFactory = RommApiClient,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_factory = client_factory
        self._thread: QThread | None = None
        self._worker: _ConnectionWorker | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, config: ConnectionConfig, token: str) -> None:
        if self._thread is not None:
            raise RuntimeError("A connection check is already active")

        thread = QThread(self)
        worker = _ConnectionWorker(self._client_factory, config, token)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self.succeeded)
        worker.failed.connect(self.failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.finished.emit()
