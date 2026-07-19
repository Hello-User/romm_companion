"""Data models used by the UI."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QImage


@dataclass(frozen=True)
class LibraryItem:
    """UI-ready data supplied by a future RomM integration."""

    identifier: str
    title: str
    platform: str = ""
    release_year: str = ""
    genre: str = ""
    description: str = ""
    cover: QImage | None = None
