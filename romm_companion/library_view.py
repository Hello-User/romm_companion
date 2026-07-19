"""Library empty and populated presentation."""

from __future__ import annotations

import random
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .models import LibraryItem
from .widgets import LibraryGrid


class LibraryView(QWidget):
    """Own the display state for an arbitrary collection of library items."""

    def __init__(
        self,
        items: Iterable[LibraryItem] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: tuple[LibraryItem, ...] = ()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 18, 18)
        outer.setSpacing(13)

        self.empty_state = QFrame()
        self.empty_state.setObjectName("emptyState")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(28, 30, 28, 30)
        empty_layout.setSpacing(10)
        empty_layout.addStretch()

        self.empty_eyebrow = QLabel()
        self.empty_eyebrow.setObjectName("section")
        empty_layout.addWidget(
            self.empty_eyebrow,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        self.empty_title = QLabel()
        self.empty_title.setObjectName("emptyTitle")
        empty_layout.addWidget(
            self.empty_title,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        self.empty_subtitle = QLabel()
        self.empty_subtitle.setObjectName("emptySubtitle")
        empty_layout.addWidget(
            self.empty_subtitle,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        empty_layout.addStretch()
        outer.addWidget(self.empty_state, 1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid = LibraryGrid()
        self.scroll_area.setWidget(self.grid)
        outer.addWidget(self.scroll_area, 1)

        self.set_items(items)

    @property
    def items(self) -> tuple[LibraryItem, ...]:
        return self._items

    def set_items(self, items: Iterable[LibraryItem]) -> None:
        self._items = tuple(items)
        self.grid.set_items(self._items)
        self._update_state()

    def _update_state(self) -> None:
        has_items = bool(self._items)
        if not has_items:
            self.empty_eyebrow.setText("LIBRARY")
            self.empty_title.setText("No games")
            self.empty_subtitle.setText(self._choose_emote())
        self.empty_state.setVisible(not has_items)
        self.scroll_area.setVisible(has_items)

    @staticmethod
    def _choose_emote() -> str:
        return random.choice(
            (
                ":(",
                ">:(",
                ":'(",
                "D:",
                "D:<",
                ":-(",
                ":/",
                ":\\",
                ">:(",
                ">:O",
                "(ノಠ益ಠ)ノ",
            )
        )
