import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
from PySide6.QtTest import QTest

from romm_companion import ConnectionStore, LibraryItem, MainWindow
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

    def get_token(self) -> str | None:
        return self.token

    def set_token(self, token: str) -> None:
        self.token = token


def make_connection_store() -> tuple[ConnectionStore, MemorySettings, MemorySecretStore]:
    settings = MemorySettings()
    secrets = MemorySecretStore()
    return ConnectionStore(settings, secrets), settings, secrets


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

    def test_not_connected_opens_client_token_popup(self):
        store, settings, secrets = make_connection_store()
        window = MainWindow(connection_store=store)
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
        self.assertFalse(window.save_connection_button.isEnabled())

        window.connection_popup.setWindowFlags(Qt.WindowType.Window)
        window.connection_popup.show()
        window.server_url_input.setFocus()
        self.app.processEvents()

        QTest.keyClick(window.server_url_input, Qt.Key.Key_Tab)
        self.assertTrue(window.client_token_input.hasFocus())

        token = "rmm_" + ("a" * 64)
        window.server_url_input.setText("https://romm.example.test/")
        window.client_token_input.setText(token)
        self.assertTrue(window.save_connection_button.isEnabled())

        window.save_connection_button.click()

        self.assertEqual(
            store.load_config().server_url, "https://romm.example.test"
        )
        self.assertEqual(secrets.token, token)
        self.assertNotIn("token", " ".join(settings.values).lower())
        self.assertEqual(window.client_token_input.text(), "")
        self.assertEqual(window.source_status.text(), "NOT CONNECTED")
        self.assertEqual(window.statusBar().currentMessage(), "Connection settings saved")


if __name__ == "__main__":
    unittest.main()
