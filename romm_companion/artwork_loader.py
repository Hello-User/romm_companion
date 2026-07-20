"""Qt-safe orchestration for progressive cover-art loading."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Iterable
from typing import Protocol

from PySide6.QtCore import QBuffer, QIODevice, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage, QImageReader

from .api import RommApiError, RommImageApi
from .api.roms import ArtworkRequest

_MAX_IMAGE_DIMENSION = 8_192
_MAX_IMAGE_PIXELS = 16_000_000
_SUPPORTED_FORMATS = {b"bmp", b"gif", b"jpeg", b"jpg", b"png", b"webp"}


class ManagedRommImageApi(RommImageApi, Protocol):
    def close(self) -> None: ...


ArtworkClientFactory = Callable[[], ManagedRommImageApi]


def _decode_image(content: bytes) -> QImage | None:
    buffer = QBuffer()
    buffer.setData(content)
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        return None
    reader = QImageReader(buffer)
    image_format = bytes(reader.format().data()).lower()
    size = reader.size()
    if (
        image_format not in _SUPPORTED_FORMATS
        or not size.isValid()
        or size.width() <= 0
        or size.height() <= 0
        or size.width() > _MAX_IMAGE_DIMENSION
        or size.height() > _MAX_IMAGE_DIMENSION
        or size.width() * size.height() > _MAX_IMAGE_PIXELS
    ):
        return None
    reader.setAutoTransform(True)
    image = reader.read()
    return None if image.isNull() else image


class _ArtworkWorker(QObject):
    artwork_available = Signal(str, object)
    finished = Signal()

    def __init__(self, client_factory: ArtworkClientFactory) -> None:
        super().__init__()
        self._client_factory = client_factory
        self._requests: deque[ArtworkRequest] = deque()
        self._condition = threading.Condition()
        self._submissions_finished = False
        self._cancelled = False

    def enqueue(self, requests: Iterable[ArtworkRequest]) -> None:
        additions = tuple(requests)
        if not additions:
            return
        with self._condition:
            if self._submissions_finished or self._cancelled:
                return
            self._requests.extend(additions)
            self._condition.notify()

    def finish_submissions(self) -> None:
        with self._condition:
            self._submissions_finished = True
            self._condition.notify()

    def cancel(self) -> None:
        with self._condition:
            self._cancelled = True
            self._requests.clear()
            self._condition.notify()

    @Slot()
    def run(self) -> None:
        client: ManagedRommImageApi | None = None
        try:
            first_request = self._take_request()
            if first_request is None:
                return
            client = self._client_factory()
            request: ArtworkRequest | None = first_request
            while request is not None:
                image = self._load_image(client, request.asset_path)
                if image is not None and not self._is_cancelled():
                    self.artwork_available.emit(request.identifier, image)
                request = self._take_request()
        except Exception:
            pass
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                self.finished.emit()

    @staticmethod
    def _load_image(client: ManagedRommImageApi, asset_path: str) -> QImage | None:
        try:
            content = client.get_image_bytes(asset_path)
        except (ValueError, RommApiError):
            return None
        except Exception:
            return None
        return _decode_image(content)

    def _take_request(self) -> ArtworkRequest | None:
        with self._condition:
            while (
                not self._requests
                and not self._submissions_finished
                and not self._cancelled
            ):
                self._condition.wait()
            if self._cancelled or not self._requests:
                return None
            return self._requests.popleft()

    def _is_cancelled(self) -> bool:
        with self._condition:
            return self._cancelled


class ArtworkLoader(QObject):
    """Own one progressive artwork queue and its worker thread lifecycle."""

    artwork_available = Signal(str, object)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _ArtworkWorker | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None

    def start(self, client_factory: ArtworkClientFactory) -> None:
        if self._thread is not None:
            raise RuntimeError("An artwork load is already active")

        thread = QThread(self)
        worker = _ArtworkWorker(client_factory)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.artwork_available.connect(self.artwork_available)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def enqueue(self, requests: Iterable[ArtworkRequest]) -> None:
        worker = self._worker
        if worker is None:
            raise RuntimeError("No artwork load is active")
        worker.enqueue(requests)

    def finish_submissions(self) -> None:
        worker = self._worker
        if worker is not None:
            worker.finish_submissions()

    def cancel(self) -> None:
        worker = self._worker
        if worker is not None:
            worker.cancel()

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.finished.emit()
