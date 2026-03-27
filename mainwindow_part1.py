
# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sand Casting Simulator v1.0")
        self.resize(1400, 900)
        self.setStyleSheet(APP_STYLE)

        self._geometry_stats = {"vol_cm3": 100.0, "surf_cm2": 120.0}
        self._sim_thread = None
        self._sim_worker = None
        self._last_result = None

        self.viewport = Viewport3D()
        self._build_ui()
        self._wire_signals()
