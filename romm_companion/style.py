"""Application stylesheet."""

STYLE = """
QWidget {
    background: #0D1117;
    color: #FEFDFE;
    font-family: "IBM Plex Sans", "Noto Sans", sans-serif;
    font-size: 13px;
}
QLabel { background: transparent; }
QMainWindow { background: #0D1117; }
QFrame#topBar {
    background: #161B22;
    border-bottom: 1px solid #1C2330;
}
QFrame#sidebar {
    background: #161B22;
    border-right: 1px solid #1C2330;
}
QFrame#card {
    background: #161B22;
    border: 1px solid #1C2330;
    border-radius: 10px;
}
QFrame#card:hover { border: 1px solid #8B74E8; background: #1C2330; }
QFrame#emptyState {
    background: #161B22;
    border: 1px solid #1C2330;
    border-radius: 14px;
}
QFrame#navItem {
    background: #1C2330;
    border: 1px solid #6043C8;
    border-radius: 8px;
}
QLabel#artwork {
    background: #1C2330;
    border: 1px dashed #5D5D5D;
    border-radius: 8px;
    color: #9E8CD6;
}
QLabel#muted { color: #9E8CD6; }
QLabel#section {
    color: #8B74E8;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#gameTitle { font-size: 14px; font-weight: 600; }
QLabel#emptyTitle { font-size: 22px; font-weight: 700; }
QLabel#brandMark { color: #8B74E8; }
QPushButton#statusPill {
    color: #EBE7FA;
    background: #1C2330;
    border: 1px solid #7A6BB4;
    border-radius: 12px;
    padding: 5px 10px;
    font-size: 10px;
    font-weight: 700;
}
QPushButton#statusPill:hover { background: #6043C8; }
QFrame#connectionPopup {
    background: #161B22;
    border: 1px solid #6043C8;
}
QLineEdit {
    background: #0D1117;
    border: 1px solid #5D5D5D;
    border-radius: 6px;
    padding: 7px 9px;
}
QLineEdit:focus { border-color: #8B74E8; }
QLabel#artworkNote { color: #9E8CD6; font-size: 11px; font-weight: 700; }
QPushButton {
    background: #1C2330;
    border: 1px solid #6043C8;
    border-radius: 7px;
    padding: 8px 13px;
}
QPushButton:hover { background: #6043C8; }
QPushButton#primary {
    background: #8B74E8;
    border-color: #A18FFF;
    font-weight: 700;
}
QPushButton#primary:hover { background: #A18FFF; }
QPushButton:disabled {
    color: #5D5D5D;
    background: #161B22;
    border-color: #1C2330;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #7A6BB4; min-height: 30px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #0D1117; width: 3px; }
QStatusBar { background: #161B22; color: #9E8CD6; border-top: 1px solid #1C2330; }

QLabel#emptySubtitle {
    color: #9E8CD6;
    font-size: 14px;
}
"""
