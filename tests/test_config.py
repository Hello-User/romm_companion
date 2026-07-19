import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from romm_companion.config import ConnectionConfig, ConnectionStore


class MemorySecretStore:
    def __init__(self) -> None:
        self.password: str | None = None

    def get_password(self) -> str | None:
        return self.password

    def set_password(self, password: str) -> None:
        self.password = password


class ConnectionConfigTest(unittest.TestCase):
    def test_normalizes_valid_connection_values(self):
        config = ConnectionConfig.from_input(
            " HTTPS://romm.example.test/library/ ", " player "
        )

        self.assertEqual(config.server_url, "https://romm.example.test/library")
        self.assertEqual(config.username, "player")

    def test_rejects_unsafe_or_incomplete_values(self):
        invalid_values = (
            ("", "player"),
            ("romm.example.test", "player"),
            ("ftp://romm.example.test", "player"),
            ("https://player:secret@romm.example.test", "player"),
            ("https://romm.example.test?token=secret", "player"),
            ("https://romm.example.test", ""),
        )

        for server_url, username in invalid_values:
            with self.subTest(server_url=server_url, username=username):
                with self.assertRaises(ValueError):
                    ConnectionConfig.from_input(server_url, username)

    def test_password_is_not_written_to_qsettings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.ini"
            settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
            secrets = MemorySecretStore()
            store = ConnectionStore(settings, secrets)
            config = ConnectionConfig.from_input(
                "https://romm.example.test", "player"
            )

            store.save(config, "correct horse battery staple")

            self.assertEqual(store.load_config(), config)
            self.assertEqual(store.get_password(), "correct horse battery staple")
            self.assertNotIn("password", " ".join(settings.allKeys()).lower())
            self.assertNotIn("correct horse battery staple", settings_path.read_text())


if __name__ == "__main__":
    unittest.main()
