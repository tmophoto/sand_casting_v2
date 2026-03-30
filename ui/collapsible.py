from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class CollapsiblePanel(QFrame):
    """A collapsible panel with a title bar and content area."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Title bar
        title_bar = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #89B4FA;")
        self.toggle_btn = QPushButton("\u25BC")  # Down arrow
        self.toggle_btn.setFixedWidth(20)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                color: #89B4FA;
                font-size: 10px;
                padding: 2px;
            }
            QPushButton:hover { background: rgba(137, 180, 250, 0.1); }
        """)
        self.toggle_btn.clicked.connect(self.toggle)
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()
        title_bar.addWidget(self.toggle_btn)
        # Content area
        self.content_frame = QFrame()
        self.content_frame.setFrameStyle(QFrame.Shape.NoFrame)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_frame.setLayout(self.content_layout)
        self.content_frame.setVisible(False)  # Start collapsed
        layout.addLayout(title_bar)
        layout.addWidget(self.content_frame)
        self._is_expanded = False

    def toggle(self):
        """Toggle the expanded state."""
        self._is_expanded = not self._is_expanded
        self.content_frame.setVisible(self._is_expanded)
        self.toggle_btn.setText("\u25BC" if self._is_expanded else "\u25B6")  # Down or right arrow

    def setContentLayout(self, layout: QVBoxLayout):
        """Set the content layout directly without clearing first."""
        # Just add the layout to content_frame's layout
        # The widgets in this layout will be parented correctly by Qt
        self.content_layout.addLayout(layout)

    def setExpanded(self, expanded: bool):
        """Set expanded state explicitly."""
        self._is_expanded = expanded
        self.content_frame.setVisible(expanded)
        self.toggle_btn.setText("\u25BC" if expanded else "\u25B6")
