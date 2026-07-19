"""Credential-safe errors raised by the RomM API boundary."""


class RommApiError(RuntimeError):
    """A safe-to-display RomM API failure."""


class InsecureConnectionError(RommApiError):
    """Plain HTTP was requested without explicit approval."""


class RommAuthenticationError(RommApiError):
    """RomM rejected the Client API Token."""


class RommPermissionError(RommApiError):
    """The Client API Token lacks a required read scope."""


class RommTimeoutError(RommApiError):
    """The RomM request exceeded its deadline."""


class RommNetworkError(RommApiError):
    """RomM could not be reached securely."""


class RommResponseError(RommApiError):
    """RomM returned an unusable response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
