"""Persistent connection configuration with OS-backed secret storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtCore import QSettings


_SERVER_URL_KEY = "connection/server_url"
_USERNAME_KEY = "connection/username"
_KEYRING_SERVICE = "RomM Companion"
_KEYRING_ACCOUNT = "active-romm-account"


class ConnectionStorageError(RuntimeError):
    """Raised when connection settings or credentials cannot be stored safely."""


@dataclass(frozen=True)
class ConnectionConfig:
    server_url: str
    username: str

    @classmethod
    def from_input(cls, server_url: str, username: str) -> ConnectionConfig:
        normalized_url = server_url.strip()
        normalized_username = username.strip()
        if not normalized_url or any(character.isspace() for character in normalized_url):
            raise ValueError("Server URL is required")

        parsed = urlsplit(normalized_url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Server URL must be an absolute HTTP or HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Server URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Server URL must not contain a query or fragment")
        try:
            parsed.port
        except ValueError as error:
            raise ValueError("Server URL contains an invalid port") from error
        if not normalized_username:
            raise ValueError("Username is required")

        path = parsed.path.rstrip("/")
        normalized_url = urlunsplit(
            (parsed.scheme.lower(), parsed.netloc, path, "", "")
        )
        return cls(server_url=normalized_url, username=normalized_username)


class SecretStore(Protocol):
    def get_password(self) -> str | None: ...

    def set_password(self, password: str) -> None: ...


class SettingsStore(Protocol):
    def value(self, key: str, default_value: object = None) -> object: ...

    def setValue(self, key: str, value: object) -> None: ...  # noqa: N802

    def sync(self) -> None: ...

    def status(self) -> QSettings.Status: ...


class KeyringSecretStore:
    """Store the active RomM password in the platform credential service."""

    def get_password(self) -> str | None:
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as error:
            raise ConnectionStorageError("Credential storage is unavailable") from error

        try:
            return keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        except KeyringError as error:
            raise ConnectionStorageError("Credential storage is unavailable") from error

    def set_password(self, password: str) -> None:
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as error:
            raise ConnectionStorageError("Credential storage is unavailable") from error

        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, password)
        except KeyringError as error:
            raise ConnectionStorageError("Credential storage is unavailable") from error


class ConnectionStore:
    """Coordinate non-secret settings and the separately stored password."""

    def __init__(self, settings: SettingsStore, secrets: SecretStore) -> None:
        self._settings = settings
        self._secrets = secrets

    @classmethod
    def system_default(cls) -> ConnectionStore:
        return cls(QSettings("RomM", "RomM Companion"), KeyringSecretStore())

    def load_config(self) -> ConnectionConfig | None:
        server_url = str(self._settings.value(_SERVER_URL_KEY, "") or "")
        username = str(self._settings.value(_USERNAME_KEY, "") or "")
        if not server_url and not username:
            return None
        try:
            return ConnectionConfig.from_input(server_url, username)
        except ValueError as error:
            raise ConnectionStorageError("Stored connection settings are invalid") from error

    def get_password(self) -> str | None:
        return self._secrets.get_password()

    def save(self, config: ConnectionConfig, password: str) -> None:
        if not password:
            raise ValueError("Password is required")

        self._secrets.set_password(password)
        self._settings.setValue(_SERVER_URL_KEY, config.server_url)
        self._settings.setValue(_USERNAME_KEY, config.username)
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise ConnectionStorageError("Connection settings could not be saved")
