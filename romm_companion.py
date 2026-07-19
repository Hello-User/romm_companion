"""Compatibility launcher for the packaged RomM Companion shell."""

from romm_companion import (
    STYLE,
    LibraryCard,
    LibraryGrid,
    LibraryItem,
    MainWindow,
    set_artwork,
)
from romm_companion.app import main

__all__ = [
    "STYLE",
    "LibraryCard",
    "LibraryGrid",
    "LibraryItem",
    "MainWindow",
    "main",
    "set_artwork",
]


if __name__ == "__main__":
    raise SystemExit(main())
