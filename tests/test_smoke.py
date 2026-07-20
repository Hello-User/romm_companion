import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QSettings, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from romm_companion import ConnectionStore, LibraryItem, MainWindow, set_artwork
from romm_companion.api import RommAuthenticationError
from romm_companion.widgets import LibraryCard, LibraryGrid


class MemorySettings:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def value(self, key: str, default_value: object = None) -> object:
        return self.values.get(key, default_value)

    def setValue(self, key: str, value: object) -> None:  # noqa: N802
        self.values[key] = value

    def sync(self) -> None:
        pass

    def status(self) -> QSettings.Status:
        return QSettings.Status.NoError


class MemorySecretStore:
    def __init__(self) -> None:
        self.token: str | None = None
        self.set_calls = 0

    def get_token(self) -> str | None:
        return self.token

    def set_token(self, token: str) -> None:
        self.set_calls += 1
        self.token = token


def make_connection_store() -> tuple[
    ConnectionStore, MemorySettings, MemorySecretStore
]:
    settings = MemorySettings()
    secrets = MemorySecretStore()
    return ConnectionStore(settings, secrets), settings, secrets


class FakeRommApiClient:
    def __init__(
        self,
        payload: object = None,
        error: Exception | None = None,
        images: dict[str, bytes | Exception] | None = None,
    ) -> None:
        self.payload = payload
        self.error = error
        self.images = images or {}
        self.closed = False

    def get_json(self, endpoint: str, *, params=None):
        if self.error is not None:
            raise self.error
        if self.payload is not None:
            return self.payload
        if endpoint == "roms":
            return {"items": [], "total": 0}
        return []

    def get_image_bytes(self, asset_path: str, *, max_bytes: int = 0) -> bytes:
        del max_bytes
        response = self.images[asset_path]
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        self.closed = True


def wait_for_background_work(window: MainWindow) -> None:
    for _ in range(200):
        QApplication.processEvents()
        if (
            not window.connection_session.is_running
            and not window.library_loader.is_running
            and not window.artwork_loader.is_running
            and window.source_status.text() != "CONNECTING"
        ):
            QApplication.processEvents()
            QTest.qWait(1)
            QApplication.processEvents()
            if (
                not window.connection_session.is_running
                and not window.library_loader.is_running
                and not window.artwork_loader.is_running
            ):
                return
        QTest.qWait(5)
    raise AssertionError("Background work did not finish")


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


class MainWindowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_empty_state_can_be_replaced_with_many_items(self):
        store, _, _ = make_connection_store()
        window = MainWindow(connection_store=store)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        library = window.library_view

        self.assertTrue(library.empty_state.isVisible())
        self.assertFalse(library.scroll_area.isVisible())
        self.assertEqual(library.empty_title.text(), "No games")
        self.assertIsNotNone(window.findChild(QWidget, "sidebar"))
        self.assertEqual(window.platform_summary.text(), "")
        self.assertIsNone(window.findChild(QWidget, "details"))

        items = [
            LibraryItem(
                identifier=str(index),
                title=f"Game {index}",
                platform="NES" if index % 2 == 0 else "SNES",
            )
            for index in range(25)
        ]
        window.set_library_items(items)
        self.app.processEvents()

        self.assertFalse(library.empty_state.isVisible())
        self.assertTrue(library.scroll_area.isVisible())
        self.assertEqual(len(library.grid.findChildren(LibraryCard)), len(items))
        self.assertEqual(window.platform_summary.text(), "NES\nSNES")

    def test_artwork_shows_supplied_images_and_explicit_absence(self):
        label = QLabel()
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkMagenta)

        set_artwork(label, LibraryItem(identifier="1", title="Game", cover=image))
        self.assertFalse(label.pixmap().isNull())
        self.assertEqual(label.text(), "")

        set_artwork(label, LibraryItem(identifier="2", title="Game"))
        self.assertEqual(label.text(), "NO ARTWORK")

    def test_library_card_artwork_preserves_the_source_aspect_ratio(self):
        image = QImage(400, 200, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkMagenta)
        card = LibraryCard(LibraryItem(identifier="1", title="Landscape", cover=image))
        self.addCleanup(card.close)
        card.resize(220, card.height())
        card.show()
        self.app.processEvents()

        pixmap = card.artwork.pixmap()
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), pixmap.height() * 2)
        self.assertLessEqual(pixmap.width(), card.artwork.contentsRect().width())
        self.assertLessEqual(pixmap.height(), card.artwork.contentsRect().height())

    def test_library_card_uses_a_two_by_three_artwork_viewport(self):
        card = LibraryCard(LibraryItem(identifier="1", title="Game"))
        self.addCleanup(card.close)
        card.resize(220, card.height())
        card.show()
        self.app.processEvents()

        self.assertAlmostEqual(
            card.artwork.width() / card.artwork.height(),
            2 / 3,
            places=2,
        )

    def test_grid_appends_cards_and_rebuilds_only_for_column_changes(self):
        grid = LibraryGrid()
        self.addCleanup(grid.close)
        grid.show()
        grid.resize(700, 600)
        self.app.processEvents()

        items = [
            LibraryItem(identifier=str(index), title=f"Game {index}")
            for index in range(6)
        ]
        grid.set_items(items)
        self.app.processEvents()
        original_cards = grid.findChildren(LibraryCard)
        self.assertEqual(len(original_cards), len(items))

        additions = [
            LibraryItem(identifier="6", title="Game 6"),
            LibraryItem(identifier="7", title="Game 7"),
        ]
        grid.append_items(additions)
        self.app.processEvents()
        appended_cards = grid.findChildren(LibraryCard)
        self.assertEqual(len(appended_cards), len(items) + len(additions))
        self.assertTrue(all(card in appended_cards for card in original_cards))

        grid.resize(710, 600)
        self.app.processEvents()
        self.assertEqual(grid.findChildren(LibraryCard), appended_cards)

        grid.resize(460, 600)
        self.app.processEvents()
        rebuilt_cards = grid.findChildren(LibraryCard)
        self.assertEqual(len(rebuilt_cards), len(items) + len(additions))
        self.assertNotEqual(rebuilt_cards, appended_cards)

    def test_grid_updates_artwork_in_place_and_retains_it_after_rebuild(self):
        grid = LibraryGrid()
        self.addCleanup(grid.close)
        grid.show()
        grid.resize(700, 600)
        grid.set_items([LibraryItem(identifier="1", title="Game")])
        self.app.processEvents()
        original_card = grid.findChildren(LibraryCard)[0]
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkMagenta)

        grid.update_item(LibraryItem(identifier="1", title="Game", cover=image))
        self.app.processEvents()

        self.assertIn(original_card, grid.findChildren(LibraryCard))
        self.assertFalse(original_card.artwork.pixmap().isNull())

        grid.resize(210, 600)
        self.app.processEvents()
        rebuilt_card = grid.findChildren(LibraryCard)[0]

        self.assertIsNot(rebuilt_card, original_card)
        self.assertFalse(rebuilt_card.artwork.pixmap().isNull())

    def test_not_connected_opens_client_token_popup_and_connects(self):
        store, settings, secrets = make_connection_store()
        clients: list[FakeRommApiClient] = []
        connection_values = []
        library_payload = {
            "items": [
                {
                    "id": 7,
                    "name": "Chrono Trigger",
                    "platform_display_name": "SNES",
                }
            ],
            "total": 1,
        }

        def client_factory(config, token):
            connection_values.append((config, token))
            client = FakeRommApiClient(
                payload=library_payload if clients else None,
            )
            clients.append(client)
            return client

        window = MainWindow(
            connection_store=store,
            client_factory=client_factory,
        )
        self.addCleanup(window.close)
        panel = window.connection_panel
        self.addCleanup(panel.close)
        window.show()

        window.source_status.click()
        self.app.processEvents()

        self.assertTrue(panel.windowFlags() & Qt.WindowType.Popup)
        self.assertEqual(panel.server_url_input.text(), "")
        self.assertEqual(panel.client_token_input.text(), "")
        self.assertEqual(panel.client_token_input.maxLength(), 68)
        self.assertEqual(
            panel.client_token_input.echoMode(), QLineEdit.EchoMode.Password
        )
        self.assertFalse(panel.connect_button.isEnabled())

        panel.close()
        self.app.processEvents()
        panel.setWindowFlags(Qt.WindowType.Window)
        panel.show()
        panel.server_url_input.setFocus()
        self.app.processEvents()

        QTest.keyClick(panel.server_url_input, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertTrue(panel.client_token_input.hasFocus())

        token = "rmm_" + ("a" * 64)
        panel.server_url_input.setText("https://romm.example.test/")
        panel.client_token_input.setText(token)
        self.assertTrue(panel.connect_button.isEnabled())

        panel.connect_button.click()
        wait_for_background_work(window)

        self.assertEqual(store.load_config().server_url, "https://romm.example.test")
        self.assertEqual(connection_values[0], (store.load_config(), token))
        self.assertTrue(clients[0].closed)
        self.assertEqual(secrets.token, token)
        self.assertNotIn("token", " ".join(settings.values).lower())
        self.assertEqual(panel.client_token_input.text(), "")
        self.assertEqual(window.source_status.text(), "CONNECTED")
        self.assertEqual(
            window.connection_session.active_connection,
            store.load_config(),
        )
        factory = window.connection_session.active_client_factory
        self.assertIsNotNone(factory)
        authenticated_client = factory()
        self.addCleanup(authenticated_client.close)
        self.assertEqual(connection_values[-1], (store.load_config(), token))
        self.assertEqual(window.statusBar().currentMessage(), "Connected")
        self.assertEqual(
            [item.title for item in window.library_view.items],
            ["Chrono Trigger"],
        )
        self.assertTrue(clients[1].closed)
        self.assertIs(panel.stack.currentWidget(), panel.connected_view)
        self.assertEqual(panel.connection_status_label.text(), "CONNECTED")
        self.assertEqual(
            panel.connected_server_label.text(), "https://romm.example.test"
        )

        panel.show()
        self.app.processEvents()
        self.assertTrue(panel.disconnect_button.isVisible())
        panel.disconnect_button.click()

        self.assertEqual(window.source_status.text(), "NOT CONNECTED")
        self.assertIsNone(window.connection_session.active_connection)
        self.assertIsNone(window.connection_session.active_client_factory)
        self.assertEqual(window.statusBar().currentMessage(), "Disconnected")
        self.assertEqual(window.library_view.items, ())
        self.assertEqual(window.platform_summary.text(), "")
        self.assertIs(panel.stack.currentWidget(), panel.connection_form)
        self.assertEqual(store.load_config().server_url, "https://romm.example.test")
        self.assertEqual(secrets.token, token)

    def test_connection_failure_does_not_replace_stored_values(self):
        store, settings, secrets = make_connection_store()
        settings.values["connection/server_url"] = "https://old.example.test"
        secrets.token = "rmm_" + ("b" * 64)
        client = FakeRommApiClient(
            error=RommAuthenticationError("Client API Token was rejected")
        )
        window = MainWindow(
            connection_store=store,
            client_factory=lambda config, token: client,
        )
        self.addCleanup(window.close)
        panel = window.connection_panel

        panel.server_url_input.setText("https://new.example.test")
        panel.client_token_input.setText("rmm_" + ("a" * 64))
        panel.connect_button.click()
        wait_for_background_work(window)

        self.assertEqual(store.load_config().server_url, "https://old.example.test")
        self.assertEqual(secrets.token, "rmm_" + ("b" * 64))
        self.assertEqual(window.source_status.text(), "NOT CONNECTED")
        self.assertEqual(
            window.statusBar().currentMessage(), "Client API Token was rejected"
        )

    def test_saved_connection_is_verified_on_startup(self):
        store, settings, secrets = make_connection_store()
        token = "rmm_" + ("a" * 64)
        settings.values["connection/server_url"] = "https://romm.example.test"
        secrets.token = token
        connection_values = []

        def client_factory(config, client_token):
            connection_values.append((config, client_token))
            return FakeRommApiClient()

        window = MainWindow(
            connection_store=store,
            client_factory=client_factory,
        )
        self.addCleanup(window.close)
        window.show()
        wait_for_background_work(window)

        self.assertEqual(len(connection_values), 2)
        self.assertEqual(connection_values[0], (store.load_config(), token))
        self.assertEqual(window.source_status.text(), "CONNECTED")
        self.assertEqual(secrets.set_calls, 0)
        self.assertIsNotNone(window.connection_session.active_client_factory)
        self.assertIs(
            window.connection_panel.stack.currentWidget(),
            window.connection_panel.connected_view,
        )

    def test_close_during_check_is_deferred_until_it_finishes(self):
        release = threading.Event()

        class BlockingClient(FakeRommApiClient):
            def get_json(self, endpoint, *, params=None):
                release.wait(5)
                return super().get_json(endpoint, params=params)

        store, _, _ = make_connection_store()
        window = MainWindow(
            connection_store=store,
            client_factory=lambda config, token: BlockingClient(),
        )
        self.addCleanup(window.close)
        window.show()
        panel = window.connection_panel

        panel.server_url_input.setText("https://romm.example.test")
        panel.client_token_input.setText("rmm_" + ("a" * 64))
        panel.connect_button.click()
        for _ in range(200):
            if window.connection_session.is_running:
                break
            QTest.qWait(5)
        self.assertTrue(window.connection_session.is_running)

        window.close()
        self.app.processEvents()

        self.assertTrue(window.isVisible())
        self.assertEqual(
            window.statusBar().currentMessage(),
            "Closing after the connection check",
        )

        release.set()
        wait_for_background_work(window)
        self.app.processEvents()

        self.assertFalse(window.isVisible())

    def test_plain_http_requires_checkbox_approval(self):
        store, _, _ = make_connection_store()
        window = MainWindow(connection_store=store)
        self.addCleanup(window.close)
        panel = window.connection_panel
        self.addCleanup(panel.close)
        window.show()
        panel.setWindowFlags(Qt.WindowType.Window)
        panel.show()
        self.app.processEvents()

        self.assertTrue(panel.allow_insecure_http_input.isEnabled())
        label_position = QPoint(
            panel.allow_insecure_http_input.width() - 8,
            panel.allow_insecure_http_input.height() // 2,
        )
        QTest.mouseClick(
            panel.allow_insecure_http_input,
            Qt.MouseButton.LeftButton,
            pos=label_position,
        )
        self.assertTrue(panel.allow_insecure_http_input.isChecked())

        panel.server_url_input.setText("http://romm.example.test")
        panel.client_token_input.setText("rmm_" + ("a" * 64))

        self.assertTrue(panel.connect_button.isEnabled())

    def test_library_pages_appear_while_later_pages_are_loading(self):
        release = threading.Event()
        second_page_started = threading.Event()

        class BlockingLibraryClient(FakeRommApiClient):
            def get_json(self, endpoint, *, params=None):
                if endpoint == "roms":
                    offset = (params or {}).get("offset", 0)
                    if offset == 0:
                        return {
                            "items": [{"id": 9, "name": "EarthBound"}],
                            "total": 2,
                        }
                    second_page_started.set()
                    release.wait(5)
                    return {
                        "items": [{"id": 10, "name": "Mother 3"}],
                        "total": 2,
                    }
                return super().get_json(endpoint, params=params)

        store, _, _ = make_connection_store()
        clients: list[FakeRommApiClient] = []

        def client_factory(config, token):
            del config, token
            client = BlockingLibraryClient() if clients else FakeRommApiClient()
            clients.append(client)
            return client

        window = MainWindow(connection_store=store, client_factory=client_factory)
        self.addCleanup(window.close)
        self.addCleanup(release.set)
        window.show()
        panel = window.connection_panel
        panel.server_url_input.setText("https://romm.example.test")
        panel.client_token_input.setText("rmm_" + ("a" * 64))
        panel.connect_button.click()

        for _ in range(200):
            self.app.processEvents()
            if second_page_started.is_set() and window.library_view.items:
                break
            QTest.qWait(5)
        self.assertTrue(second_page_started.is_set())
        self.assertTrue(window.library_loader.is_running)
        self.assertEqual(window.statusBar().currentMessage(), "Loading library")
        self.assertEqual(
            [item.title for item in window.library_view.items],
            ["EarthBound"],
        )
        first_card = window.library_view.grid.findChildren(LibraryCard)[0]

        release.set()
        wait_for_background_work(window)

        self.assertEqual(
            [item.title for item in window.library_view.items],
            ["EarthBound", "Mother 3"],
        )
        self.assertIn(
            first_card,
            window.library_view.grid.findChildren(LibraryCard),
        )
        self.assertEqual(window.statusBar().currentMessage(), "Connected")
        self.assertTrue(clients[1].closed)

    def test_cover_artwork_updates_the_existing_card_progressively(self):
        release = threading.Event()
        image_request_started = threading.Event()
        cover_path = "/assets/romm/resources/roms/3/9/cover/small.png"

        class BlockingArtworkClient(FakeRommApiClient):
            def get_image_bytes(self, asset_path: str, *, max_bytes: int = 0) -> bytes:
                del max_bytes
                self.asserted_path = asset_path
                image_request_started.set()
                release.wait(5)
                return make_png()

        store, _, _ = make_connection_store()
        clients: list[FakeRommApiClient] = []

        def client_factory(config, token):
            del config, token
            if not clients:
                client = FakeRommApiClient()
            elif len(clients) == 1:
                client = FakeRommApiClient(
                    payload={
                        "items": [
                            {
                                "id": 9,
                                "name": "EarthBound",
                                "path_cover_small": cover_path,
                            }
                        ],
                        "total": 1,
                    }
                )
            else:
                client = BlockingArtworkClient()
            clients.append(client)
            return client

        window = MainWindow(connection_store=store, client_factory=client_factory)
        self.addCleanup(window.close)
        self.addCleanup(release.set)
        panel = window.connection_panel
        panel.server_url_input.setText("https://romm.example.test")
        panel.client_token_input.setText("rmm_" + ("a" * 64))
        panel.connect_button.click()

        for _ in range(200):
            self.app.processEvents()
            if image_request_started.is_set() and window.library_view.items:
                break
            QTest.qWait(5)

        self.assertTrue(image_request_started.is_set())
        original_card = window.library_view.grid.findChildren(LibraryCard)[0]
        self.assertEqual(original_card.artwork.text(), "NO ARTWORK")

        release.set()
        wait_for_background_work(window)

        current_card = window.library_view.grid.findChildren(LibraryCard)[0]
        self.assertIs(current_card, original_card)
        self.assertFalse(current_card.artwork.pixmap().isNull())
        self.assertIsNotNone(window.library_view.items[0].cover)
        self.assertEqual(window.statusBar().currentMessage(), "Connected")
        self.assertEqual(clients[2].asserted_path, cover_path)
        self.assertTrue(clients[2].closed)

    def test_later_library_failure_keeps_available_items(self):
        store, _, _ = make_connection_store()
        clients: list[FakeRommApiClient] = []

        class PartialFailureClient(FakeRommApiClient):
            def get_json(self, endpoint, *, params=None):
                if endpoint == "roms" and (params or {}).get("offset", 0) == 0:
                    return {
                        "items": [{"id": 11, "name": "Mother"}],
                        "total": 2,
                    }
                raise RommAuthenticationError("Library denied")

        def client_factory(config, token):
            del config, token
            client = PartialFailureClient() if clients else FakeRommApiClient()
            clients.append(client)
            return client

        window = MainWindow(connection_store=store, client_factory=client_factory)
        self.addCleanup(window.close)
        panel = window.connection_panel
        panel.server_url_input.setText("https://romm.example.test")
        panel.client_token_input.setText("rmm_" + ("a" * 64))
        panel.connect_button.click()

        wait_for_background_work(window)

        self.assertEqual(window.statusBar().currentMessage(), "Library denied")
        self.assertEqual(
            [item.title for item in window.library_view.items],
            ["Mother"],
        )
        self.assertTrue(clients[1].closed)


if __name__ == "__main__":
    unittest.main()
