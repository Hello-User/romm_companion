"""Qt-safe orchestration for blocking library loading."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .api import RommApiError
from .api.roms import iter_library_pages
from .connection.check import ManagedReadOnlyRommApi

LibraryClientFactory = Callable[[], ManagedReadOnlyRommApi]


class _LibraryWorker(QObject):
    items_available = Signal(object)
    artwork_requests_available = Signal(object)
    succeeded = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(self, client_factory: LibraryClientFactory) -> None:
        super().__init__()
        self._client_factory = client_factory

    @Slot()
    def run(self) -> None:
        client: ManagedReadOnlyRommApi | None = None
        try:
            client = self._client_factory()
            for page in iter_library_pages(client):
                self.items_available.emit(page.items)
                if page.artwork_requests:
                    self.artwork_requests_available.emit(page.artwork_requests)
        except (ValueError, RommApiError) as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Library loading failed")
        else:
            self.succeeded.emit()
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                self.finished.emit()


class LibraryLoader(QObject):
    """Own one background library fetch and its thread lifecycle."""

    items_available = Signal(object)
    artwork_requests_available = Signal(object)
    succeeded = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _LibraryWorker | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None

    def start(self, client_factory: LibraryClientFactory) -> None:
        if self._thread is not None:
            raise RuntimeError("A library load is already active")

        thread = QThread(self)
        worker = _LibraryWorker(client_factory)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.items_available.connect(self.items_available)
        worker.artwork_requests_available.connect(self.artwork_requests_available)
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
