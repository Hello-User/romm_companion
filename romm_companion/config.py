"""Persistent connection configuration with OS-backed secret storage."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import ModuleType
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtCore import QSettings


_SERVER_URL_KEY = "connection/server_url"
_ALLOW_INSECURE_HTTP_KEY = "connection/allow_insecure_http"
_KEYRING_SERVICE = "RomM Companion"
_KEYRING_ACCOUNT = "active-romm-account"
_CLIENT_TOKEN_PATTERN = re.compile(r"rmm_[0-9a-fA-F]{64}\Z")


def is_valid_client_token(token: str) -> bool:
    return _CLIENT_TOKEN_PATTERN.fullmatch(token.strip()) is not None


class ConnectionStorageError(RuntimeError):
    """Raised when connection settings or credentials cannot be stored safely."""


@dataclass(frozen=True)
class ConnectionConfig:
    server_url: str
    allow_insecure_http: bool = False

    @classmethod
    def from_input(
        cls, server_url: str, *, allow_insecure_http: bool = False
    ) -> ConnectionConfig:
        normalized_url = server_url.strip()
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
        path = parsed.path.rstrip("/")
        normalized_url = urlunsplit(
            (parsed.scheme.lower(), parsed.netloc, path, "", "")
        )
        return cls(
            server_url=normalized_url,
            allow_insecure_http=allow_insecure_http,
        )


class SecretStore(Protocol):
    def get_token(self) -> str | None: ...

    def set_token(self, token: str) -> None: ...


class SettingsStore(Protocol):
    def value(self, key: str, default_value: object = None) -> object: ...

    def setValue(self, key: str, value: object) -> None: ...  # noqa: N802

    def sync(self) -> None: ...

    def status(self) -> QSettings.Status: ...


def _load_keyring() -> tuple[ModuleType, type[Exception]]:
    """Import keyring lazily so configuration works without a credential service."""
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as error:
        raise ConnectionStorageError("Credential storage is unavailable") from error
    return keyring, KeyringError


class KeyringTokenStore:
    """Store the active RomM Client API Token in the credential service."""

    def get_token(self) -> str | None:
        keyring, keyring_error = _load_keyring()
        try:
            token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        except keyring_error as error:
            raise ConnectionStorageError("Credential storage is unavailable") from error
        return token if token is not None and is_valid_client_token(token) else None

    def set_token(self, token: str) -> None:
        keyring, keyring_error = _load_keyring()
        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, token)
        except keyring_error as error:
            raise ConnectionStorageError("Credential storage is unavailable") from error


class ConnectionStore:
    """Coordinate non-secret settings and the separately stored client token."""

    def __init__(self, settings: SettingsStore, secrets: SecretStore) -> None:
        self._settings = settings
        self._secrets = secrets

    @classmethod
    def system_default(cls) -> ConnectionStore:
        return cls(QSettings("RomM", "RomM Companion"), KeyringTokenStore())

    def load_config(self) -> ConnectionConfig | None:
        server_url = str(self._settings.value(_SERVER_URL_KEY, "") or "")
        if not server_url:
            return None
        allow_insecure_http = self._settings.value(
            _ALLOW_INSECURE_HTTP_KEY, False
        ) in (True, "true", "True", 1, "1")
        try:
            return ConnectionConfig.from_input(
                server_url,
                allow_insecure_http=allow_insecure_http,
            )
        except ValueError as error:
            raise ConnectionStorageError("Stored connection settings are invalid") from error

    def get_token(self) -> str | None:
        return self._secrets.get_token()

    def save(self, config: ConnectionConfig, token: str) -> None:
        normalized_token = token.strip()
        if not is_valid_client_token(normalized_token):
            raise ValueError("Client API Token has an invalid format")

        self._secrets.set_token(normalized_token)
        self._settings.setValue(_SERVER_URL_KEY, config.server_url)
        self._settings.setValue(
            _ALLOW_INSECURE_HTTP_KEY, config.allow_insecure_http
        )
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise ConnectionStorageError("Connection settings could not be saved")
