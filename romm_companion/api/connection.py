"""Connection verification built on the general RomM API client."""

from .client import ReadOnlyRommApi
from .errors import RommResponseError


def verify_connection(client: ReadOnlyRommApi) -> None:
    """Confirm authenticated read access using RomM's platforms endpoint."""
    payload = client.get_json("platforms")
    if not isinstance(payload, (list, dict)):
        raise RommResponseError("RomM returned an unexpected response")
