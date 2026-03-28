from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QCheckBox, QTextEdit, QScrollArea,
    QProgressBar, QFileDialog, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread
from ui.style import APP_STYLE
from ui.collapsible import CollapsiblePanel
from viewport.viewport import Viewport3D
from simulation.worker import SimWorker
from results.formatter import build_results_text
from constants import METAL_DEFAULTS, FLASK_SIZES


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



    def _build_ui(self):
        main_layout = QHBoxLayout()
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)


        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)


        left_panel = QVBoxLayout()
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_panel.setContentsMargins(10, 10, 10, 10)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(320)
        splitter.addWidget(left_scroll)


        stl_panel = CollapsiblePanel("STL File")
        # Create container widget for proper parent-child ownership
        stl_container = QWidget()
        stl_layout = QVBoxLayout()
        stl_container.setLayout(stl_layout)
        self.load_btn = QPushButton("Load STL...")
        self.stl_label = QLabel("No file loaded")
        self.stl_label.setWordWrap(True)
        stl_layout.addWidget(self.load_btn)
        stl_layout.addWidget(self.stl_label)
        # Add container widget (not layout) to panel
        stl_panel.content_layout.addWidget(stl_container)
        left_panel.addWidget(stl_panel)
        stl_panel.setExpanded(True)


        parting_panel = CollapsiblePanel("Parting Line")
        # Create container widget for proper parent-child ownership
        parting_container = QWidget()
        parting_layout = QVBoxLayout()
        parting_container.setLayout(parting_layout)
        self.parting_slider = QSlider(Qt.Orientation.Horizontal)
        self.parting_slider.setMinimum(5)
        self.parting_slider.setMaximum(95)
        self.parting_slider.setValue(50)
        label = QLabel("Position: 50%")
        parting_layout.addWidget(label)
        parting_layout.addWidget(self.parting_slider)
        # Add container widget (not layout) to panel
        parting_panel.content_layout.addWidget(parting_container)
        left_panel.addWidget(parting_panel)
        parting_panel.setExpanded(True)


        flask_panel = CollapsiblePanel("Flask Size")
        # Create container widget for proper parent-child ownership
        flask_container = QWidget()
        flask_layout = QVBoxLayout()
        flask_container.setLayout(flask_layout)
        self.flask_combo = QComboBox()
        self._flask_presets = dict(FLASK_SIZES)  # mutable copy; grows with custom presets
        for name in self._flask_presets:
            self.flask_combo.addItem(name)
        self.add_flask_btn = QPushButton("+ Custom")
        flask_layout.addWidget(self.flask_combo)
        flask_layout.addWidget(self.add_flask_btn)
        # Add container widget (not layout) to panel
        flask_panel.content_layout.addWidget(flask_container)
        left_panel.addWidget(flask_panel)
        flask_panel.setExpanded(True)


        gating_panel = CollapsiblePanel("Gating System")
        # Create container widget for proper parent-child ownership
        gating_container = QWidget()
        gating_layout = QVBoxLayout()
        gating_container.setLayout(gating_layout)
        self.gating_checkboxes = {}
        for comp in ["Tapered Sprue", "Runner (Horizontal)", "Fan Gate",
                     "Riser (Open)"]:
            cb = QCheckBox(comp)
            self.gating_checkboxes[comp] = cb
            gating_layout.addWidget(cb)
        # Add container widget (not layout) to panel
        gating_panel.content_layout.addWidget(gating_container)
        left_panel.addWidget(gating_panel)
        gating_panel.setExpanded(True)


        metal_panel = CollapsiblePanel("Metal & Temperature")
        # Create container widget for proper parent-child ownership
        metal_container = QWidget()
        metal_layout = QVBoxLayout()
        metal_container.setLayout(metal_layout)
        self.metal_combo = QComboBox()
        for metal in METAL_DEFAULTS:
            self.metal_combo.addItem(metal)
        self.pour_spin = QSlider(Qt.Orientation.Horizontal)
        self.pour_spin.setMinimum(1000)
        self.pour_spin.setMaximum(2500)
        self.pour_spin.setValue(METAL_DEFAULTS["A356 Aluminum"]["pour_temp_f"])
        self.mold_spin = QSlider(Qt.Orientation.Horizontal)
        self.mold_spin.setMinimum(32)
        self.mold_spin.setMaximum(300)
        self.mold_spin.setValue(100)
        self.thin_combo = QComboBox()
        self.thin_combo.addItems(["No", "Yes"])
        metal_layout.addWidget(QLabel("Metal:"))
        metal_layout.addWidget(self.metal_combo)
        metal_layout.addWidget(QLabel("Pour Temp: 1300 F (default for A356)"))
        metal_layout.addWidget(self.pour_spin)
        metal_layout.addWidget(QLabel("Mold Temp: 100 F"))
        metal_layout.addWidget(self.mold_spin)
        metal_layout.addWidget(QLabel("Thin Wall?"))
        metal_layout.addWidget(self.thin_combo)
        # Add container widget (not layout) to panel
        metal_panel.content_layout.addWidget(metal_container)
        left_panel.addWidget(metal_panel)
        metal_panel.setExpanded(True)


        placement_panel = CollapsiblePanel("Model Placement")
        # Create container widget for proper parent-child ownership
        placement_container = QWidget()
        placement_layout = QVBoxLayout()
        placement_container.setLayout(placement_layout)
        self.x_slider = QSlider(Qt.Orientation.Horizontal)
        self.x_slider.setMinimum(-500)
        self.x_slider.setMaximum(500)
        self.x_slider.setValue(0)
        self.y_slider = QSlider(Qt.Orientation.Horizontal)
        self.y_slider.setMinimum(-500)
        self.y_slider.setMaximum(500)
        self.y_slider.setValue(0)
        self.z_slider = QSlider(Qt.Orientation.Horizontal)
        self.z_slider.setMinimum(-200)
        self.z_slider.setMaximum(200)
        self.z_slider.setValue(0)
        self.rot_slider = QSlider(Qt.Orientation.Horizontal)
        self.rot_slider.setMinimum(0)
        self.rot_slider.setMaximum(360)
        self.rot_slider.setValue(0)
        placement_layout.addWidget(QLabel("X Offset: 0 mm"))
        placement_layout.addWidget(self.x_slider)
        placement_layout.addWidget(QLabel("Y Offset: 0 mm"))
        placement_layout.addWidget(self.y_slider)
        placement_layout.addWidget(QLabel("Z Offset: 0 mm"))
        placement_layout.addWidget(self.z_slider)
        placement_layout.addWidget(QLabel("Rotation: 0 deg"))
        placement_layout.addWidget(self.rot_slider)
        # Add container widget (not layout) to panel
        placement_panel.content_layout.addWidget(placement_container)
        left_panel.addWidget(placement_panel)
        placement_panel.setExpanded(True)


        gating_placement_panel = CollapsiblePanel("Gating Placement")
        # Create container widget for proper parent-child ownership
        gating_placement_container = QWidget()
        gating_placement_layout = QVBoxLayout()
        gating_placement_container.setLayout(gating_placement_layout)
        self.sprue_x_slider = QSlider(Qt.Orientation.Horizontal)
        self.sprue_x_slider.setMinimum(-200)
        self.sprue_x_slider.setMaximum(200)
        self.sprue_x_slider.setValue(0)
        self.sprue_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.sprue_y_slider.setMinimum(-200)
        self.sprue_y_slider.setMaximum(200)
        self.sprue_y_slider.setValue(0)
        self.riser_x_slider = QSlider(Qt.Orientation.Horizontal)
        self.riser_x_slider.setMinimum(-200)
        self.riser_x_slider.setMaximum(200)
        self.riser_x_slider.setValue(0)
        self.riser_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.riser_y_slider.setMinimum(-200)
        self.riser_y_slider.setMaximum(200)
        self.riser_y_slider.setValue(0)
        gating_placement_layout.addWidget(QLabel("Sprue X: 0 mm"))
        gating_placement_layout.addWidget(self.sprue_x_slider)
        gating_placement_layout.addWidget(QLabel("Sprue Y: 0 mm"))
        gating_placement_layout.addWidget(self.sprue_y_slider)
        gating_placement_layout.addWidget(QLabel("Riser X: 0 mm"))
        gating_placement_layout.addWidget(self.riser_x_slider)
        gating_placement_layout.addWidget(QLabel("Riser Y: 0 mm"))
        gating_placement_layout.addWidget(self.riser_y_slider)
        # Add container widget (not layout) to panel
        gating_placement_panel.content_layout.addWidget(gating_placement_container)
        left_panel.addWidget(gating_placement_panel)
        gating_placement_panel.setExpanded(True)


        shrink_panel = CollapsiblePanel("Shrinkage Compensation")
        # Create container widget for proper parent-child ownership
        shrink_container = QWidget()
        shrink_layout = QVBoxLayout()
        shrink_container.setLayout(shrink_layout)
        self.shrink_slider = QSlider(Qt.Orientation.Horizontal)
        self.shrink_slider.setMinimum(100)
        self.shrink_slider.setMaximum(110)
        self.shrink_slider.setValue(106)
        shrink_pct = METAL_DEFAULTS["A356 Aluminum"]["shrinkage_pct"]
        self.shrink_label = QLabel("Shrinkage: " + str(shrink_pct) + "% (A356 Aluminum)")
        shrink_layout.addWidget(self.shrink_label)
        shrink_layout.addWidget(self.shrink_slider)
        # Add container widget (not layout) to panel
        shrink_panel.content_layout.addWidget(shrink_container)
        left_panel.addWidget(shrink_panel)
        shrink_panel.setExpanded(True)


        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_panel.addWidget(self.progress_bar)


        center_panel = QVBoxLayout()
        center_widget = QWidget()
        center_widget.setLayout(center_panel)
        center_panel.setContentsMargins(10, 10, 10, 10)
        view_label = QLabel("3D Part Viewer")
        view_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        center_panel.addWidget(view_label)
        self.render_frame = self.viewport
        if hasattr(self.viewport, "render_frame"):
            center_panel.addWidget(self.viewport.render_frame)
        else:
            center_panel.addWidget(self.viewport)
        splitter.addWidget(center_widget)


        # Create top-right panel for view buttons (small, horizontal)
        view_btn_layout = QHBoxLayout()
        view_btn_layout.setSpacing(5)
        for view in ["Top", "Bottom", "Front", "Back", "Left", "Right", "Iso"]:
            btn = QPushButton(view)
            btn.clicked.connect(lambda _, v=view: self.viewport.set_view(v))
            btn.setStyleSheet("QPushButton { padding: 4px 8px; font-size: 9px; }")
            view_btn_layout.addWidget(btn)
        right_panel = QVBoxLayout()
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_panel.setContentsMargins(10, 10, 10, 10)
        # Add view buttons at the top of right panel
        right_panel.addLayout(view_btn_layout)
        result_label = QLabel("Simulation Results")
        result_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        right_panel.addWidget(result_label)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMinimumWidth(350)
        right_panel.addWidget(self.results_text)
        self.sim_btn = QPushButton("Simulate Pour")
        self.sim_btn.setStyleSheet("QPushButton { background-color: #89B4FA; color: black; padding: 10px; font-weight: bold; }")
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setStyleSheet("QPushButton { background-color: #F38BA8; color: black; padding: 10px; }")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.sim_btn)
        btn_layout.addWidget(self.reset_btn)
        right_panel.addLayout(btn_layout)
        splitter.addWidget(right_widget)




        # Store reference to main layout for potential updates
        self._main_layout = main_layout



    def _wire_signals(self):

        """Connect all UI signals to their handlers."""

        # STL Load button
        self.load_btn.clicked.connect(self._on_load_stl)


        # Parting slider
        self.parting_slider.valueChanged.connect(self._on_parting_changed)


        # Gating checkboxes
        for name, cb in self.gating_checkboxes.items():
            cb.stateChanged.connect(lambda state, n=name: self.viewport.set_gating(
                [k for k, v in self.gating_checkboxes.items() if v.isChecked()]
            ))


        # Metal combo box
        self.metal_combo.currentIndexChanged.connect(self._on_metal_changed)


        # Flask combo box
        self.flask_combo.currentTextChanged.connect(self._on_flask_changed)


        # Add custom flask button
        self.add_flask_btn.clicked.connect(self._on_add_flask_preset)


        # Simulation button
        self.sim_btn.clicked.connect(self._on_simulate)


        # Reset button
        self.reset_btn.clicked.connect(self._on_reset)


        # Model placement sliders - X, Y, Z, Rotation

        def update_transform():
            dx = self.x_slider.value()
            dy = self.y_slider.value()
            dz = self.z_slider.value()
            rot = self.rot_slider.value()
            self.viewport.set_transformation(dx, dy, dz, rot)


        self.x_slider.valueChanged.connect(lambda v: update_transform())
        self.y_slider.valueChanged.connect(lambda v: update_transform())
        self.z_slider.valueChanged.connect(lambda v: update_transform())
        self.rot_slider.valueChanged.connect(lambda v: update_transform())


        # Gating placement sliders - Sprue X, Y

        def update_gating():
            sprue_x = self.sprue_x_slider.value()
            sprue_y = self.sprue_y_slider.value()
            riser_x = self.riser_x_slider.value()
            riser_y = self.riser_y_slider.value()
            runner_y = 0
            self.viewport.set_gating_offset(sprue_x, sprue_y, runner_y, riser_x, riser_y)


        self.sprue_x_slider.valueChanged.connect(lambda v: update_gating())
        self.sprue_y_slider.valueChanged.connect(lambda v: update_gating())
        self.riser_x_slider.valueChanged.connect(lambda v: update_gating())
        self.riser_y_slider.valueChanged.connect(lambda v: update_gating())


        # Shrinkage slider

        def update_shrink_label(val):
            pct = METAL_DEFAULTS[self.metal_combo.currentText()]["shrinkage_pct"]
            scale = 1.0 + (val - 100) / 1000.0
            self.shrink_label.setText("Shrinkage: " + str(pct) + "% (" + self.metal_combo.currentText() + ")")


        self.shrink_slider.valueChanged.connect(update_shrink_label)


        # Viewport gating moved signal
        self.viewport.gating_moved.connect(self._on_gating_moved)


        # Initial flask setup
        self._on_flask_changed(self.flask_combo.currentText())






    def _on_gating_moved(self, data):
        """Sync sliders from 3D drag operations."""
        self.sprue_x_slider.blockSignals(True)
        self.sprue_y_slider.blockSignals(True)
        self.riser_x_slider.blockSignals(True)
        self.riser_y_slider.blockSignals(True)
        self.sprue_x_slider.setValue(int(data.get("sprue_x", 0)))
        self.sprue_y_slider.setValue(int(data.get("sprue_y", 0)))
        self.riser_x_slider.setValue(int(data.get("riser_x", 0)))
        self.riser_y_slider.setValue(int(data.get("riser_y", 0)))
        self.sprue_x_slider.blockSignals(False)
        self.sprue_y_slider.blockSignals(False)
        self.riser_x_slider.blockSignals(False)
        self.riser_y_slider.blockSignals(False)

    def _on_load_stl(self):
        """Handle STL file load button click."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load STL File", "", "STL Files (*.stl);;All Files (*)"
        )
        if filename:
            try:
                stats = self.viewport.load_stl(filename)
                self.stl_label.setText(f"Loaded: {filename}\nVolume: {round(stats['vol_cm3'], 2)} cm^3\nSurface: {round(stats['surf_cm2'], 2)} cm^2")
                self._geometry_stats = stats
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load STL:\n{str(e)}")

    def _on_parting_changed(self, val):
        """Handle parting line slider change."""
        frac = val / 100.0
        self.viewport.set_parting(frac)
        parent_widget = self.parting_slider.parent()
        if parent_widget:
            for i in range(parent_widget.layout().count()):
                widget = parent_widget.layout().itemAt(i).widget()
                if isinstance(widget, QLabel) and "Position:" in widget.text():
                    widget.setText("Position: " + str(val) + "%")
                    break

    def _on_metal_changed(self, index):
        """Handle metal combo box change."""
        metal_name = self.metal_combo.currentText()
        pour_temp = METAL_DEFAULTS[metal_name]["pour_temp_f"]
        shrink_pct = METAL_DEFAULTS[metal_name]["shrinkage_pct"]
        self.pour_spin.setValue(pour_temp)
        self.shrink_label.setText("Shrinkage: " + str(shrink_pct) + "% (" + metal_name + ")")

    def _on_flask_changed(self, text):
        """Handle flask size combo box change."""
        size = self._flask_presets.get(text, (8, 10))
        self.viewport.set_flask(size)

    def _on_add_flask_preset(self):
        """Add custom flask preset."""
        text, ok = QInputDialog.getText(
            self, "Add Custom Flask",
            "Enter name, width, height (e.g., '10x12, 10, 12'):"
        )
        if ok and text:
            try:
                parts = text.replace(" ", "").split(",")
                name = parts[0]
                width = float(parts[1])
                height = float(parts[2])
                self._flask_presets[name] = (width, height)
                self.flask_combo.addItem(name)
            except Exception as e:
                QMessageBox.warning(self, "Error", "Invalid format: " + str(e))

    def _on_simulate(self):
        """Run the casting simulation."""
        # Gather all parameters
        metal_name = self.metal_combo.currentText()
        metal_params = METAL_DEFAULTS[metal_name]
        params = {
            'metal': metal_name,
            'pour_temp_f': self.pour_spin.value(),
            'mold_temp_f': self.mold_spin.value(),
            'thin_wall': self.thin_combo.currentIndex() == 1,
            'shrinkage': metal_params['shrinkage_pct'],
            'gate_types': [name for name, cb in self.gating_checkboxes.items() if cb.isChecked()],
            'vol_cm3': self._geometry_stats.get('vol_cm3', 100.0),
            'surf_cm2': self._geometry_stats.get('surf_cm2', 120.0),
            'has_riser': 'Riser (Open)' in self.viewport.gating,
            'gating_params': self.viewport.get_gating_params(),
            'runner_y_offset': self.viewport.runner_y_offset,
            'shrink_scale': 1.0 + (self.shrink_slider.value() - 100) / 1000.0,
            'z_max': self._geometry_stats.get('z_max', 100.0),
        }
        # Run simulation in a thread
        self.progress_bar.setVisible(True)
        self.sim_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self._sim_thread = QThread()
        self._sim_worker = SimWorker(params)
        self._sim_worker.moveToThread(self._sim_thread)
        self._sim_worker.progress.connect(lambda pct, msg: self._on_sim_progress(pct, msg))
        self._sim_worker.finished.connect(lambda result: self._on_sim_done(result))
        self._sim_worker.finished.connect(self._sim_thread.quit)
        self._sim_worker.finished.connect(self._sim_worker.deleteLater)
        self._sim_thread.finished.connect(self._sim_thread.deleteLater)
        self._sim_thread.started.connect(self._sim_worker.run)
        self._sim_thread.start()

    def _on_sim_progress(self, pct, msg):
        """Update progress during simulation."""
        self.progress_bar.setFormat(f"{msg} {int(pct)}%")
        self.progress_bar.setValue(int(pct))

    def _on_sim_done(self, result):
        """Handle simulation completion."""
        self.progress_bar.setVisible(False)
        self.sim_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        if result:
            self._last_result = result
            self.results_text.setText(build_results_text(result))
            # Decorate defects for drawing
            defects = result.get("defects", [])
            decorated_defects = []
            for d in defects:
                if isinstance(d, tuple):
                    decorated_defects.append(d)
                elif "shrinkage" in d.lower():
                    decorated_defects.append(("shrinkage_risk", 0, 0, result.get("z_max", 100)))
                elif "cold" in d.lower():
                    decorated_defects.append(("cold_shut_risk", 0, 0, result.get("z_max", 100)))
                else:
                    decorated_defects.append(d)
            # Start animations with draw_defect_markers as final callback
            duration = max(2.0, result.get("fill_time_s", 3.0))
            self.viewport.start_fill_animation(
                duration_s=duration,
                on_done=lambda: self.viewport.draw_defect_markers(decorated_defects)
            )
        else:
            self.results_text.setText("Simulation failed or was cancelled.")

    def _on_reset(self):
        """Reset the application state."""
        self.viewport.reset_anim()
        # Reset sliders to defaults
        metal_name = self.metal_combo.currentText()
        self.pour_spin.setValue(METAL_DEFAULTS[metal_name]["pour_temp_f"])
        self.mold_spin.setValue(100)
        self.x_slider.setValue(0)
        self.y_slider.setValue(0)
        self.z_slider.setValue(0)
        self.rot_slider.setValue(0)
        self.sprue_x_slider.setValue(0)
        self.sprue_y_slider.setValue(0)
        self.riser_x_slider.setValue(0)
        self.riser_y_slider.setValue(0)
        # Reset checkboxes
        for cb in self.gating_checkboxes.values():
            cb.setChecked(False)
        # Clear results
        self.results_text.setText("")
        self.stl_label.setText("No file loaded")
        self._last_result = None
