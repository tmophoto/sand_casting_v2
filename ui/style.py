"""
Catppuccin Mocha dark-theme QSS for the Sand Casting Simulator.
Imported by casting_sim.py as:  from ui.style import APP_STYLE
"""

APP_STYLE = """
QWidget {
    background-color: #11111B;
    color: #CDD6F4;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
}

QPushButton {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 4px;
    padding: 5px 12px;
    color: #CDD6F4;
}

QPushButton:hover  { background-color: #313244; }

QPushButton:pressed { background-color: #45475A; }

QPushButton#sim_btn {
    background-color: #89B4FA;
    color: #11111B;
    font-weight: bold;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
}

QPushButton#sim_btn:hover  { background-color: #74C7EC; }

QPushButton#reset_btn {
    background-color: #F38BA8;
    color: #11111B;
    font-weight: bold;
    border: none;
    padding: 6px 14px;
    border-radius: 6px;
}

QPushButton#reset_btn:hover { background-color: #EBA0AC; }

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

QComboBox {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 4px;
    padding: 4px 8px;
    color: #CDD6F4;
}

QComboBox::drop-down { border: none; }

QComboBox QAbstractItemView {
    background-color: #181825;
    selection-background-color: #313244;
}

QTextEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 4px;
    color: #CDD6F4;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
}

QScrollBar:vertical {
    background: #1E1E2E;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #45475A;
    border-radius: 4px;
}

QProgressBar {
    border: 1px solid #313244;
    border-radius: 4px;
    background: #1E1E2E;
    text-align: center;
    color: #CDD6F4;
}

QProgressBar::chunk {
    background-color: #89B4FA;
    border-radius: 3px;
}

QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #45475A;
    border-radius: 3px;
    background: #1E1E2E;
}

QCheckBox::indicator:checked {
    background: #89B4FA;
    border-color: #89B4FA;
}

QSpinBox {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 4px;
    padding: 4px 8px;
    color: #CDD6F4;
}

QListWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 4px;
    color: #CDD6F4;
}

QListWidget::item:selected { background: #313244; }

QToolButton {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    border-radius: 4px;
    padding: 4px 10px;
    color: #CDD6F4;
}
"""
