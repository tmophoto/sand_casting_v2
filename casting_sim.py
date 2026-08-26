"""Sand Casting Simulator — desktop entry point."""

import sys

from PyQt6.QtWidgets import QApplication
from ui.style import APP_STYLE
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
