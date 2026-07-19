import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from romm_companion.config import ConnectionConfig, ConnectionStore


class MemorySecretStore:
    def __init__(self) -> None:
        self.token: str | None = None

    def get_token(self) -> str | None:
        return self.token

    def set_token(self, token: str) -> None:
        self.token = token


class ConnectionConfigTest(unittest.TestCase):
    def test_normalizes_valid_connection_values(self):
        config = ConnectionConfig.from_input(" HTTPS://romm.example.test/library/ ")

        self.assertEqual(config.server_url, "https://romm.example.test/library")

    def test_rejects_unsafe_or_incomplete_values(self):
        invalid_values = (
            "",
            "romm.example.test",
            "ftp://romm.example.test",
            "https://player:secret@romm.example.test",
            "https://romm.example.test?token=secret",
        )

        for server_url in invalid_values:
            with self.subTest(server_url=server_url):
                with self.assertRaises(ValueError):
                    ConnectionConfig.from_input(server_url)

    def test_client_token_is_not_written_to_qsettings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.ini"
            settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
            secrets = MemorySecretStore()
            store = ConnectionStore(settings, secrets)
            config = ConnectionConfig.from_input("https://romm.example.test")
            token = "rmm_" + ("a" * 64)

            store.save(config, token)

            self.assertEqual(store.load_config(), config)
            self.assertEqual(store.get_token(), token)
            self.assertNotIn("token", " ".join(settings.allKeys()).lower())
            self.assertNotIn(token, settings_path.read_text())

    def test_persists_explicit_insecure_http_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.Format.IniFormat,
            )
            store = ConnectionStore(settings, MemorySecretStore())
            config = ConnectionConfig.from_input(
                "http://romm.example.test",
                allow_insecure_http=True,
            )

            store.save(config, "rmm_" + ("a" * 64))

            self.assertEqual(store.load_config(), config)

    def test_rejects_non_client_token_secrets(self):
        settings = QSettings()
        store = ConnectionStore(settings, MemorySecretStore())
        config = ConnectionConfig.from_input("https://romm.example.test")

        with self.assertRaises(ValueError):
            store.save(config, "account password")


if __name__ == "__main__":
    unittest.main()
