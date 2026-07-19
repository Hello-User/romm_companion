"""Paginated ROM listing built on the general RomM API client."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from ..models import LibraryItem
from .client import JsonValue, ReadOnlyRommApi
from .errors import RommResponseError

_PAGE_SIZE = 100


@dataclass(frozen=True)
class ArtworkRequest:
    """A same-server cover resource associated with one library item."""

    identifier: str
    asset_path: str


@dataclass(frozen=True)
class LibraryPage:
    """One mapped ROM page and its separately retained artwork requests."""

    items: tuple[LibraryItem, ...]
    artwork_requests: tuple[ArtworkRequest, ...]


def fetch_library_items(client: ReadOnlyRommApi) -> list[LibraryItem]:
    """Fetch every ROM page and map the records to UI-ready library items."""
    return [item for page in iter_library_item_pages(client) for item in page]


def iter_library_item_pages(
    client: ReadOnlyRommApi,
) -> Iterator[tuple[LibraryItem, ...]]:
    """Yield each mapped ROM page before requesting the next one."""
    for page in iter_library_pages(client):
        yield page.items


def iter_library_pages(client: ReadOnlyRommApi) -> Iterator[LibraryPage]:
    """Yield mapped item pages with their same-server cover references."""
    offset = 0
    while True:
        payload = client.get_json(
            "roms", params={"limit": _PAGE_SIZE, "offset": offset}
        )
        if not isinstance(payload, dict):
            raise RommResponseError("RomM returned an unexpected response")
        page = payload.get("items")
        if not isinstance(page, list):
            raise RommResponseError("RomM returned an unexpected response")
        mapped_page: list[LibraryItem] = []
        artwork_requests: list[ArtworkRequest] = []
        for entry in page:
            item = _map_rom(entry)
            if item is not None:
                mapped_page.append(item)
                if isinstance(entry, dict):
                    cover_path = _first_text(
                        entry,
                        ("path_cover_small", "path_cover_large"),
                    )
                    if cover_path:
                        artwork_requests.append(
                            ArtworkRequest(item.identifier, cover_path)
                        )
        if mapped_page:
            yield LibraryPage(tuple(mapped_page), tuple(artwork_requests))
        offset += len(page)
        total = payload.get("total")
        if not page or not isinstance(total, int) or offset >= total:
            return


def _map_rom(entry: JsonValue) -> LibraryItem | None:
    """Map one ROM record; records without an id and title are skipped."""
    if not isinstance(entry, dict):
        return None
    identifier = entry.get("id")
    if isinstance(identifier, bool) or not isinstance(identifier, int):
        return None
    title = _first_text(entry, ("name", "fs_name_no_tags", "fs_name"))
    if not title:
        return None
    metadatum = entry.get("metadatum")
    if not isinstance(metadatum, dict):
        metadatum = {}
    return LibraryItem(
        identifier=str(identifier),
        title=title,
        platform=_first_text(entry, ("platform_display_name",)),
        release_year=_release_year(metadatum.get("first_release_date")),
        genre=_genres(metadatum.get("genres")),
        description=_first_text(entry, ("summary",)),
    )


def _first_text(entry: dict[str, JsonValue], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _release_year(stamp: JsonValue | None) -> str:
    """Derive a display year from RomM's epoch-millisecond release date."""
    if isinstance(stamp, bool) or not isinstance(stamp, int | float):
        return ""
    try:
        year = datetime.fromtimestamp(stamp / 1000, tz=UTC).year
    except (OverflowError, OSError, ValueError):
        return ""
    return str(year) if 1950 <= year <= 2100 else ""


def _genres(genres: JsonValue | None) -> str:
    if not isinstance(genres, list):
        return ""
    return ", ".join(genre for genre in genres if isinstance(genre, str))
