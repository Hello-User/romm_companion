import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
from PySide6.QtTest import QTest

from romm_companion import ConnectionStore, LibraryItem, MainWindow
from romm_companion.api import RommAuthenticationError
from romm_companion.widgets import LibraryCard


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


def make_connection_store() -> tuple[ConnectionStore, MemorySettings, MemorySecretStore]:
    settings = MemorySettings()
    secrets = MemorySecretStore()
    return ConnectionStore(settings, secrets), settings, secrets


class FakeRommApiClient:
    def __init__(self, payload: object = None, error: Exception | None = None) -> None:
        self.payload = [] if payload is None else payload
        self.error = error
        self.closed = False

    def get_json(self, endpoint: str, *, params=None):
        if self.error is not None:
            raise self.error
        return self.payload

    def close(self) -> None:
        self.closed = True


def wait_for_connection(window: MainWindow) -> None:
    for _ in range(200):
        QApplication.processEvents()
        if (
            not window._connection_check.is_running
            and window.source_status.text() != "CONNECTING"
        ):
            QApplication.processEvents()
            return
        QTest.qWait(5)
    raise AssertionError("Connection check did not finish")


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

        self.assertTrue(window.library_empty_state.isVisible())
        self.assertFalse(window.library_scroll.isVisible())
        self.assertEqual(window.library_empty_title.text(), "No games")
        self.assertEqual(window.platform_summary.text(), "")
        self.assertIsNone(window.findChild(QWidget, "details"))

        items = [
            LibraryItem(identifier=str(index), title=f"Game {index}", platform="NES")
            for index in range(25)
        ]
        window.set_library_items(items)
        self.app.processEvents()

        self.assertFalse(window.library_empty_state.isVisible())
        self.assertTrue(window.library_scroll.isVisible())
        self.assertEqual(len(window.library_grid.findChildren(LibraryCard)), len(items))

    def test_not_connected_opens_client_token_popup_and_connects(self):
        store, settings, secrets = make_connection_store()
        clients: list[FakeRommApiClient] = []
        connection_values = []

        def client_factory(config, token):
            connection_values.append((config, token))
            client = FakeRommApiClient()
            clients.append(client)
            return client

        window = MainWindow(
            connection_store=store,
            client_factory=client_factory,
        )
        self.addCleanup(window.close)
        self.addCleanup(window.connection_popup.close)
        window.show()

        window.source_status.click()
        self.app.processEvents()

        self.assertTrue(window.connection_popup.windowFlags() & Qt.WindowType.Popup)
        self.assertEqual(window.server_url_input.text(), "")
        self.assertEqual(window.client_token_input.text(), "")
        self.assertEqual(window.client_token_input.maxLength(), 68)
        self.assertEqual(
            window.client_token_input.echoMode(), QLineEdit.EchoMode.Password
        )
        self.assertFalse(window.connect_button.isEnabled())

        window.connection_popup.close()
        self.app.processEvents()
        window.connection_popup.setWindowFlags(Qt.WindowType.Window)
        window.connection_popup.show()
        window.server_url_input.setFocus()
        self.app.processEvents()

        QTest.keyClick(window.server_url_input, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertTrue(window.client_token_input.hasFocus())

        token = "rmm_" + ("a" * 64)
        window.server_url_input.setText("https://romm.example.test/")
        window.client_token_input.setText(token)
        self.assertTrue(window.connect_button.isEnabled())

        window.connect_button.click()
        wait_for_connection(window)

        self.assertEqual(
            store.load_config().server_url, "https://romm.example.test"
        )
        self.assertEqual(connection_values[0], (store.load_config(), token))
        self.assertTrue(clients[0].closed)
        self.assertEqual(secrets.token, token)
        self.assertNotIn("token", " ".join(settings.values).lower())
        self.assertEqual(window.client_token_input.text(), "")
        self.assertEqual(window.source_status.text(), "CONNECTED")
        self.assertEqual(window.statusBar().currentMessage(), "Connected")
        self.assertIs(
            window.connection_stack.currentWidget(), window.connected_view
        )
        self.assertEqual(window.connection_status_label.text(), "CONNECTED")
        self.assertEqual(
            window.connected_server_label.text(), "https://romm.example.test"
        )

        window.connection_popup.show()
        self.app.processEvents()
        self.assertTrue(window.disconnect_button.isVisible())
        window.disconnect_button.click()

        self.assertEqual(window.source_status.text(), "NOT CONNECTED")
        self.assertEqual(window.statusBar().currentMessage(), "Disconnected")
        self.assertIs(
            window.connection_stack.currentWidget(), window.connection_form
        )
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

        window.server_url_input.setText("https://new.example.test")
        window.client_token_input.setText("rmm_" + ("a" * 64))
        window.connect_button.click()
        wait_for_connection(window)

        self.assertEqual(
            store.load_config().server_url, "https://old.example.test"
        )
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
        wait_for_connection(window)

        self.assertEqual(len(connection_values), 1)
        self.assertEqual(connection_values[0], (store.load_config(), token))
        self.assertEqual(window.source_status.text(), "CONNECTED")
        self.assertEqual(secrets.set_calls, 0)
        self.assertIs(
            window.connection_stack.currentWidget(), window.connected_view
        )

    def test_plain_http_requires_checkbox_approval(self):
        store, _, _ = make_connection_store()
        window = MainWindow(connection_store=store)
        self.addCleanup(window.close)
        self.addCleanup(window.connection_popup.close)
        window.show()
        window.connection_popup.setWindowFlags(Qt.WindowType.Window)
        window.connection_popup.show()
        self.app.processEvents()

        self.assertTrue(window.allow_insecure_http_input.isEnabled())
        label_position = QPoint(
            window.allow_insecure_http_input.width() - 8,
            window.allow_insecure_http_input.height() // 2,
        )
        QTest.mouseClick(
            window.allow_insecure_http_input,
            Qt.MouseButton.LeftButton,
            pos=label_position,
        )
        self.assertTrue(window.allow_insecure_http_input.isChecked())

        window.server_url_input.setText("http://romm.example.test")
        window.client_token_input.setText("rmm_" + ("a" * 64))

        self.assertTrue(window.connect_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
