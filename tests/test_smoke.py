import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from romm_companion import LibraryItem, MainWindow
from romm_companion.widgets import LibraryCard


class MainWindowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_empty_state_can_be_replaced_with_many_items(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        self.assertTrue(window.library_empty_state.isVisible())
        self.assertFalse(window.library_scroll.isVisible())
        self.assertEqual(window.library_empty_title.text(), "No games")
        self.assertEqual(window.platform_summary.text(), "")
        self.assertIsNone(window.findChild(QWidget, "details"))

        items = [
            LibraryItem(identifier=str(index), title=f"Game {index}", platform="NES")
            for index in range(25)
        ]
        window.set_library_items(items)
        self.app.processEvents()

        self.assertFalse(window.library_empty_state.isVisible())
        self.assertTrue(window.library_scroll.isVisible())
        self.assertEqual(len(window.library_grid.findChildren(LibraryCard)), len(items))


if __name__ == "__main__":
    unittest.main()
