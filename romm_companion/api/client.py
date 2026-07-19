"""Reusable authenticated HTTP client for read-only RomM API operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from ..config import ConnectionConfig, is_valid_client_token
from .errors import (
    InsecureConnectionError,
    RommAuthenticationError,
    RommNetworkError,
    RommPermissionError,
    RommResponseError,
    RommTimeoutError,
)

type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
type QueryValue = str | int | float | bool | None

_DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_RESOURCE_PATH_PREFIX = "/assets/romm/resources/"


class ReadOnlyRommApi(Protocol):
    """The transport-independent boundary used by endpoint services."""

    def get_json(
        self,
        endpoint: str,
        *,
        params: Mapping[str, QueryValue | list[QueryValue]] | None = None,
    ) -> JsonValue: ...


class RommImageApi(Protocol):
    """The transport-independent boundary used by artwork services."""

    def get_image_bytes(
        self,
        asset_path: str,
        *,
        max_bytes: int = _DEFAULT_MAX_IMAGE_BYTES,
    ) -> bytes: ...


class RommApiClient:
    """Issue authenticated GET requests against a RomM instance.

    Domain-specific APIs should depend on ``get_json`` instead of knowing about
    HTTP headers, timeouts, redirects, URL layout, or credential-safe errors.
    """

    def __init__(
        self,
        config: ConnectionConfig,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        normalized_token = token.strip()
        if not is_valid_client_token(normalized_token):
            raise ValueError("Client API Token has an invalid format")

        scheme = urlsplit(config.server_url).scheme.lower()
        if scheme == "http" and not config.allow_insecure_http:
            raise InsecureConnectionError(
                "Allow insecure HTTP to connect to this server"
            )

        self._client = httpx.Client(
            base_url=f"{config.server_url}/api/",
            follow_redirects=False,
            timeout=timeout,
            transport=transport,
        )
        self._authorization = f"Bearer {normalized_token}"
        parsed_server = urlsplit(config.server_url)
        self._server_origin = urlunsplit(
            (parsed_server.scheme, parsed_server.netloc, "", "", "")
        )

    def get_json(
        self,
        endpoint: str,
        *,
        params: Mapping[str, QueryValue | list[QueryValue]] | None = None,
    ) -> JsonValue:
        """GET one relative API endpoint and decode its JSON response."""
        normalized_endpoint = self._validate_endpoint(endpoint)
        try:
            response = self._client.get(
                normalized_endpoint,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Authorization": self._authorization,
                },
            )
        except httpx.TimeoutException as error:
            raise RommTimeoutError("Connection timed out") from error
        except httpx.TransportError as error:
            raise RommNetworkError("Could not reach RomM") from error

        self._raise_for_status(response.status_code)
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" not in content_type:
            raise RommResponseError("RomM returned an unexpected response")
        try:
            payload: JsonValue = response.json()
        except ValueError as error:
            raise RommResponseError("RomM returned invalid JSON") from error
        return payload

    def get_image_bytes(
        self,
        asset_path: str,
        *,
        max_bytes: int = _DEFAULT_MAX_IMAGE_BYTES,
    ) -> bytes:
        """GET one same-origin RomM resource image with a strict size bound."""
        if max_bytes <= 0:
            raise ValueError("Image byte limit must be positive")
        resource_url = self._build_resource_url(asset_path)
        try:
            with self._client.stream(
                "GET",
                resource_url,
                headers={
                    "Accept": "image/*",
                    "Authorization": self._authorization,
                },
            ) as response:
                self._raise_for_status(response.status_code)
                content_type = response.headers.get("content-type", "")
                content_type = content_type.partition(";")[0].strip().lower()
                if not content_type.startswith("image/"):
                    raise RommResponseError("RomM returned an unexpected response")

                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except ValueError as error:
                        raise RommResponseError(
                            "RomM returned an invalid image size"
                        ) from error
                    if declared_length < 0 or declared_length > max_bytes:
                        raise RommResponseError("RomM returned an oversized image")

                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > max_bytes:
                        raise RommResponseError("RomM returned an oversized image")
                    content.extend(chunk)
        except httpx.TimeoutException as error:
            raise RommTimeoutError("Connection timed out") from error
        except httpx.TransportError as error:
            raise RommNetworkError("Could not reach RomM") from error
        return bytes(content)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RommApiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @staticmethod
    def _validate_endpoint(endpoint: str) -> str:
        normalized = endpoint.strip().lstrip("/")
        parsed = urlsplit(normalized)
        if (
            not normalized
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or any(part == ".." for part in parsed.path.split("/"))
        ):
            raise ValueError("API endpoint must be a relative path")
        return normalized

    def _build_resource_url(self, asset_path: str) -> str:
        normalized_path = asset_path.strip()
        parsed = urlsplit(normalized_path)
        decoded_path = unquote(parsed.path)
        if (
            not normalized_path
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or not parsed.path.startswith(_RESOURCE_PATH_PREFIX)
            or any(part in {".", ".."} for part in decoded_path.split("/"))
        ):
            raise ValueError("Image path must be a RomM resource path")
        resource_path = urlunsplit(("", "", parsed.path, parsed.query, ""))
        return f"{self._server_origin}{resource_path}"

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code == 401:
            raise RommAuthenticationError("Client API Token was rejected")
        if status_code == 403:
            raise RommPermissionError(
                "Client API Token lacks permission for this operation"
            )
        if status_code < 200 or status_code >= 300:
            raise RommResponseError(
                f"RomM returned HTTP {status_code}",
                status_code=status_code,
            )
