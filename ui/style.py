"""
Casting Simulator — shop-tool dark theme (Catppuccin Mocha).
"""

APP_STYLE = """
QMainWindow, QWidget {
    background-color: #11111B;
    color: #CDD6F4;
    font-family: "Segoe UI", "Inter", "SF Pro Text", sans-serif;
    font-size: 13px;
}

QWidget#chromeBar {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 12px;
}

QLabel#wordmark {
    color: #CDD6F4;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.2px;
    padding: 0 4px 0 8px;
}

QLabel#wordmarkSub {
    color: #6C7086;
    font-size: 11px;
    padding-right: 12px;
}

QLabel#caption {
    color: #7F849C;
    font-size: 10px;
    font-weight: 600;
    padding: 6px 0 2px 1px;
}

QLabel#hint {
    color: #6C7086;
    font-size: 11px;
}

QLabel#statusChip {
    color: #A6ADC8;
    font-size: 11px;
    padding: 2px 0;
}

QFrame#stepBar {
    background: transparent;
}

QLabel#step {
    color: #6C7086;
    font-size: 11px;
    padding: 2px 10px 6px 4px;
}

QPushButton {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 8px;
    padding: 7px 14px;
    color: #CDD6F4;
}

QPushButton:hover  { background-color: #313244; border-color: #585B70; }
QPushButton:pressed { background-color: #45475A; }
QPushButton:disabled { color: #585B70; border-color: #313244; }

QPushButton#ghostBtn {
    background: transparent;
    border: 1px solid #313244;
    color: #A6ADC8;
}

QPushButton#primaryBtn {
    background-color: #89B4FA;
    color: #11111B;
    font-weight: 700;
    border: none;
    padding: 8px 18px;
}

QPushButton#primaryBtn:hover  { background-color: #B4BEFE; }
QPushButton#primaryBtn:disabled { background-color: #313244; color: #6C7086; }

QPushButton#demoBtn {
    background-color: #A6E3A1;
    color: #11111B;
    font-weight: 700;
    border: none;
}

QPushButton#demoBtn:hover { background-color: #94E2D5; }

QPushButton#dangerBtn {
    background: transparent;
    color: #F38BA8;
    border: 1px solid #45475A;
}

QPushButton#dangerBtn:hover { background-color: #3a1e28; border-color: #F38BA8; }

QPushButton#processBtn {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 10px;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
}

QPushButton#processBtn:checked {
    background-color: #1e2a40;
    border: 1px solid #89B4FA;
    color: #CDD6F4;
}

QPushButton#viewBtn {
    padding: 4px 8px;
    font-size: 11px;
    border-radius: 6px;
    min-width: 42px;
}

QFrame#card {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 12px;
}

QFrame#card QLabel {
    background: transparent;
}

QPushButton#cardToggle {
    border: none;
    background: transparent;
    color: #7F849C;
    font-size: 11px;
    padding: 2px 6px;
}

QPushButton#cardToggle:hover { color: #CDD6F4; background: rgba(137, 180, 250, 0.08); }

QSlider::groove:horizontal {
    height: 4px;
    background: #313244;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #89B4FA;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::sub-page:horizontal { background: #89B4FA; border-radius: 2px; }

QComboBox, QSpinBox {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 8px;
    padding: 6px 10px;
    color: #CDD6F4;
    min-height: 18px;
}

QComboBox:hover, QSpinBox:hover { border-color: #89B4FA; }
QComboBox::drop-down { border: none; width: 22px; }

QComboBox QAbstractItemView {
    background-color: #181825;
    selection-background-color: #313244;
    border: 1px solid #45475A;
    padding: 4px;
}

QTextEdit, QTextBrowser {
    background-color: #11111B;
    border: 1px solid #313244;
    border-radius: 10px;
    color: #CDD6F4;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
    padding: 4px;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}

QScrollBar::handle:vertical {
    background: #45475A;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QProgressBar {
    border: none;
    border-radius: 6px;
    background: #1E1E2E;
    text-align: center;
    color: #A6ADC8;
    height: 16px;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #89B4FA;
    border-radius: 6px;
}

QCheckBox { spacing: 8px; color: #CDD6F4; }

QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid #45475A;
    border-radius: 4px;
    background: #1E1E2E;
}

QCheckBox::indicator:checked {
    background: #89B4FA;
    border-color: #89B4FA;
}

QListWidget {
    background-color: #1E1E2E;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #CDD6F4;
    padding: 4px;
}

QListWidget::item { padding: 5px 8px; border-radius: 6px; }
QListWidget::item:selected { background: #313244; }
QListWidget::item:hover { background: #262637; }

QScrollArea { border: none; background: transparent; }
QSplitter::handle { background: #313244; width: 1px; }

QStatusBar {
    background: #181825;
    color: #A6ADC8;
    border-top: 1px solid #313244;
    font-size: 11px;
}
"""
