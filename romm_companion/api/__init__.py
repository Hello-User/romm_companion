"""Public boundary for authenticated, read-only RomM API access."""

from .client import JsonValue, ReadOnlyRommApi, RommApiClient
from .errors import (
    InsecureConnectionError,
    RommApiError,
    RommAuthenticationError,
    RommNetworkError,
    RommPermissionError,
    RommResponseError,
    RommTimeoutError,
)

__all__ = [
    "InsecureConnectionError",
    "JsonValue",
    "ReadOnlyRommApi",
    "RommApiClient",
    "RommApiError",
    "RommAuthenticationError",
    "RommNetworkError",
    "RommPermissionError",
    "RommResponseError",
    "RommTimeoutError",
]
