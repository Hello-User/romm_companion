"""Command-line entry point for the RomM Companion shell."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("RomM")
    app.setApplicationName("RomM Companion")
    window = MainWindow()
    window.show()
    return app.exec()
