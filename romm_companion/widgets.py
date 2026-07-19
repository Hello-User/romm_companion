"""Reusable widgets for displaying library items."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .models import LibraryItem


class FullRowCheckBox(QCheckBox):
    """A checkbox whose complete row, including its label, toggles it."""

    def hitButton(self, position: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(position)


def set_artwork(label: QLabel, item: LibraryItem | None) -> None:
    """Display supplied artwork or an explicit no-artwork state."""
    label.clear()
    if item is not None and item.cover is not None and not item.cover.isNull():
        label.setPixmap(QPixmap.fromImage(item.cover))
        return
    label.setText("NO ARTWORK")


class LibraryCard(QFrame):
    def __init__(self, item: LibraryItem) -> None:
        super().__init__()
        self.item = item
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(190)
        self.setFixedHeight(292)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 9, 9, 10)
        layout.setSpacing(8)

        cover = QLabel()
        cover.setObjectName("artwork")
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setScaledContents(True)
        cover.setFixedHeight(204)
        set_artwork(cover, item)
        layout.addWidget(cover)

        title = QLabel(item.title)
        title.setObjectName("gameTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        metadata = [value for value in (item.platform, item.release_year) if value]
        meta = QLabel("  •  ".join(metadata))
        meta.setObjectName("muted")
        layout.addWidget(meta)


class LibraryGrid(QWidget):
    """Scrollable, data-driven card grid with no fixed record limit."""

    def __init__(self) -> None:
        super().__init__()
        self._items: tuple[LibraryItem, ...] = ()
        self._columns = 0
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 6, 0)
        self._layout.setHorizontalSpacing(12)
        self._layout.setVerticalSpacing(12)

    def set_items(self, items: Iterable[LibraryItem]) -> None:
        self._items = tuple(items)
        self._rebuild()

    def append_items(self, items: Iterable[LibraryItem]) -> None:
        additions = tuple(items)
        if not additions:
            return
        start = len(self._items)
        self._items += additions
        columns = self._fitting_columns()
        if self._columns not in (0, columns):
            self._rebuild()
            return
        if self._columns == 0:
            for column in range(columns):
                self._layout.setColumnStretch(column, 1)
            self._columns = columns
        for index, item in enumerate(additions, start=start):
            self._layout.addWidget(
                LibraryCard(item),
                index // columns,
                index % columns,
            )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._items and self._fitting_columns() != self._columns:
            self._rebuild()

    def _fitting_columns(self) -> int:
        return max(1, self.width() // 220)

    def _rebuild(self) -> None:
        while (layout_item := self._layout.takeAt(0)) is not None:
            widget = layout_item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        columns = self._fitting_columns() if self._items else 0
        for index, item in enumerate(self._items):
            self._layout.addWidget(LibraryCard(item), index // columns, index % columns)
        for column in range(columns):
            self._layout.setColumnStretch(column, 1)
        for column in range(columns, self._columns):
            self._layout.setColumnStretch(column, 0)
        self._columns = columns
