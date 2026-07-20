import os
import threading
import unittest

# The offscreen Qt platform must be selected before importing PySide6.
# ruff: noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from romm_companion.api import RommResponseError
from romm_companion.api.roms import ArtworkRequest
from romm_companion.artwork_loader import ArtworkLoader


def make_png() -> bytes:
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkMagenta)
    content = QByteArray()
    buffer = QBuffer(content)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(
        buffer, "PNG"
    ):
        raise AssertionError("Could not create test image")
    return bytes(content)


class FakeImageClient:
    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        self.responses = responses
        self.requests: list[str] = []
        self.closed = False

    def get_image_bytes(self, asset_path: str, *, max_bytes: int = 0) -> bytes:
        del max_bytes
        self.requests.append(asset_path)
        response = self.responses[asset_path]
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        self.closed = True


def wait_for_loader(loader: ArtworkLoader) -> None:
    for _ in range(200):
        QApplication.processEvents()
        if not loader.is_running:
            QApplication.processEvents()
            return
        QTest.qWait(5)
    raise AssertionError("Artwork loader did not finish")


class ArtworkLoaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_loads_valid_images_and_skips_individual_failures(self):
        paths = {
            "good": "/assets/romm/resources/good.png",
            "invalid": "/assets/romm/resources/invalid.png",
            "failed": "/assets/romm/resources/failed.png",
        }
        client = FakeImageClient(
            {
                paths["good"]: make_png(),
                paths["invalid"]: b"not an image",
                paths["failed"]: RommResponseError("Unavailable"),
            }
        )
        loader = ArtworkLoader()
        self.addCleanup(loader.cancel)
        available: list[tuple[str, QImage]] = []
        loader.artwork_available.connect(
            lambda identifier, image: available.append((identifier, image))
        )

        loader.start(lambda: client)
        loader.enqueue(
            ArtworkRequest(identifier, path) for identifier, path in paths.items()
        )
        loader.finish_submissions()
        wait_for_loader(loader)

        self.assertEqual([identifier for identifier, _ in available], ["good"])
        self.assertFalse(available[0][1].isNull())
        self.assertEqual(client.requests, list(paths.values()))
        self.assertTrue(client.closed)

    def test_accepts_requests_progressively_until_submissions_finish(self):
        first_path = "/assets/romm/resources/first.png"
        second_path = "/assets/romm/resources/second.png"
        client = FakeImageClient({first_path: make_png(), second_path: make_png()})
        loader = ArtworkLoader()
        self.addCleanup(loader.cancel)
        identifiers: list[str] = []
        loader.artwork_available.connect(
            lambda identifier, image: identifiers.append(identifier)
        )

        loader.start(lambda: client)
        loader.enqueue([ArtworkRequest("first", first_path)])
        for _ in range(200):
            self.app.processEvents()
            if identifiers:
                break
            QTest.qWait(5)

        self.assertEqual(identifiers, ["first"])
        self.assertTrue(loader.is_running)

        loader.enqueue([ArtworkRequest("second", second_path)])
        loader.finish_submissions()
        wait_for_loader(loader)

        self.assertEqual(identifiers, ["first", "second"])
        self.assertTrue(client.closed)

    def test_cancel_discards_queued_and_in_flight_results(self):
        request_started = threading.Event()
        release = threading.Event()
        image_content = make_png()

        class BlockingClient(FakeImageClient):
            def get_image_bytes(self, asset_path: str, *, max_bytes: int = 0) -> bytes:
                del max_bytes
                self.requests.append(asset_path)
                request_started.set()
                release.wait(5)
                return image_content

        paths = (
            "/assets/romm/resources/first.png",
            "/assets/romm/resources/second.png",
        )
        client = BlockingClient({})
        loader = ArtworkLoader()
        self.addCleanup(release.set)
        available: list[str] = []
        loader.artwork_available.connect(
            lambda identifier, image: available.append(identifier)
        )

        loader.start(lambda: client)
        loader.enqueue(
            [ArtworkRequest("first", paths[0]), ArtworkRequest("second", paths[1])]
        )
        self.assertTrue(request_started.wait(5))
        loader.cancel()
        release.set()
        wait_for_loader(loader)

        self.assertEqual(available, [])
        self.assertEqual(client.requests, [paths[0]])
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
