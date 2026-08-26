from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt


class CollapsiblePanel(QFrame):
    """Card-styled collapsible section with a clickable title bar."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameStyle(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        self._header = QFrame()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        title_bar = QHBoxLayout(self._header)
        title_bar.setContentsMargins(2, 2, 2, 2)
        title_bar.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "font-weight: 700; color: #CDD6F4; font-size: 13px; background: transparent;"
        )
        self.toggle_btn = QPushButton("\u25BE")
        self.toggle_btn.setObjectName("cardToggle")
        self.toggle_btn.setFixedWidth(22)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle)
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()
        title_bar.addWidget(self.toggle_btn)

        self.content_frame = QFrame()
        self.content_frame.setFrameStyle(QFrame.Shape.NoFrame)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(6)
        self.content_frame.setLayout(self.content_layout)
        self.content_frame.setVisible(False)

        layout.addWidget(self._header)
        layout.addWidget(self.content_frame)
        self._is_expanded = False

    def mousePressEvent(self, event):
        if self._header.geometry().contains(event.position().toPoint()):
            self.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def setTitle(self, title: str) -> None:
        self.title_label.setText(title)

    def toggle(self):
        self.setExpanded(not self._is_expanded)

    def setContentLayout(self, layout: QVBoxLayout):
        self.content_layout.addLayout(layout)

    def setExpanded(self, expanded: bool):
        self._is_expanded = expanded
        self.content_frame.setVisible(expanded)
        self.toggle_btn.setText("\u25BE" if expanded else "\u25B8")
