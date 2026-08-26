from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QCheckBox, QTextEdit, QScrollArea,
    QProgressBar, QFileDialog, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread
import numpy as np
from ui.style import APP_STYLE
from ui.collapsible import CollapsiblePanel
from ui.demo_part import build_demo_mesh, DEMO_PART_NAME
from viewport.viewport import Viewport3D
from simulation.worker import SimWorker
from results.formatter import build_results_text
from constants import METAL_DEFAULTS, FLASK_SIZES, shrink_scale_from_slider, DEFAULT_FLASK_HEIGHT_IN
from simulation.mesh_tools import scale_geometry, local_thickness, THIN_WALL_MM


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
        self.demo_btn = QPushButton("▶ Try Demo")
        self.demo_btn.setToolTip(
            "Load a pre-built Motor Mount Bracket with all settings pre-configured.\n"
            "Press Simulate Pour to see fill animation and defect analysis."
        )
        self.demo_btn.setStyleSheet(
            "QPushButton { background-color: #A6E3A1; color: black; font-weight: bold; padding: 6px; }"
        )
        self.stl_label = QLabel("No file loaded")
        self.stl_label.setWordWrap(True)
        stl_layout.addWidget(self.load_btn)
        stl_layout.addWidget(self.demo_btn)
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
        self.parting_slider.setToolTip(
            "Where the mold splits into cope (top) and drag (bottom),\n"
            "expressed as % of part height."
        )
        self.parting_label = QLabel("Position: 50%")
        parting_layout.addWidget(self.parting_label)
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
        self.flask_h_slider = QSlider(Qt.Orientation.Horizontal)
        self.flask_h_slider.setMinimum(3)
        self.flask_h_slider.setMaximum(18)
        self.flask_h_slider.setValue(int(DEFAULT_FLASK_HEIGHT_IN))
        self.flask_h_slider.setToolTip("Cope + drag stack height in inches.")
        self.flask_h_label = QLabel(f"Flask height: {int(DEFAULT_FLASK_HEIGHT_IN)} in")
        flask_layout.addWidget(self.flask_h_label)
        flask_layout.addWidget(self.flask_h_slider)
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

        gating_layout.addWidget(QLabel("Dimensions (mm)"))
        self.sprue_top_slider, self.sprue_top_label = self._mm_slider(
            gating_layout, "Sprue top r", 4, 20, 8,
            "Tapered sprue radius at the pouring basin (mm).",
        )
        self.sprue_bot_slider, self.sprue_bot_label = self._mm_slider(
            gating_layout, "Sprue exit r", 2, 12, 4,
            "Tapered sprue radius at the runner (mm). This is usually the choke.",
        )
        self.sprue_h_slider, self.sprue_h_label = self._mm_slider(
            gating_layout, "Sprue height", 40, 250, 100,
            "Visible sprue length. Hydraulic head also includes cope height.",
        )
        self.runner_w_slider, self.runner_w_label = self._mm_slider(
            gating_layout, "Runner width", 4, 24, 10,
            "Horizontal runner cross-section width (mm).",
        )
        self.runner_h_slider, self.runner_h_label = self._mm_slider(
            gating_layout, "Runner height", 4, 20, 8,
            "Horizontal runner cross-section height (mm).",
        )
        self.gate_area_slider, self.gate_area_label = self._mm_slider(
            gating_layout, "Gate area", 10, 200, 40,
            "Fan-gate hydraulic area (mm²).",
        )
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
        # Covers A356 (1300 °F) through 316 stainless (2900 °F)
        self.pour_spin.setMinimum(800)
        self.pour_spin.setMaximum(3200)
        self.pour_spin.setValue(METAL_DEFAULTS["A356 Aluminum"]["pour_temp_f"])
        self.mold_spin = QSlider(Qt.Orientation.Horizontal)
        self.mold_spin.setMinimum(32)
        self.mold_spin.setMaximum(300)
        self.mold_spin.setValue(100)
        self.thin_combo = QComboBox()
        self.thin_combo.addItems(["Auto", "No", "Yes"])
        self.thin_combo.setToolTip(
            f"Auto: flag thin walls when the mesh has sections thinner than {THIN_WALL_MM:.0f} mm.\n"
            "Yes/No override the detector. Thin walls tighten the cold-shut superheat check."
        )
        metal_layout.addWidget(QLabel("Metal:"))
        metal_layout.addWidget(self.metal_combo)
        self.pour_temp_label = QLabel(f"Pour Temp: {METAL_DEFAULTS['A356 Aluminum']['pour_temp_f']} °F")
        metal_layout.addWidget(self.pour_temp_label)
        metal_layout.addWidget(self.pour_spin)
        self.mold_temp_label = QLabel("Mold Temp: 100 °F")
        metal_layout.addWidget(self.mold_temp_label)
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
        self.x_label = QLabel("X Offset: 0 mm")
        self.y_label = QLabel("Y Offset: 0 mm")
        self.z_label = QLabel("Z Offset: 0 mm")
        self.rot_label = QLabel("Rotation: 0 deg")
        placement_layout.addWidget(self.x_label)
        placement_layout.addWidget(self.x_slider)
        placement_layout.addWidget(self.y_label)
        placement_layout.addWidget(self.y_slider)
        placement_layout.addWidget(self.z_label)
        placement_layout.addWidget(self.z_slider)
        placement_layout.addWidget(self.rot_label)
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
        self.sprue_x_slider.setToolTip("Sprue X position relative to part centre (mm)")
        self.sprue_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.sprue_y_slider.setMinimum(-200)
        self.sprue_y_slider.setMaximum(200)
        self.sprue_y_slider.setValue(0)
        self.sprue_y_slider.setToolTip("Sprue Y position relative to part centre (mm)")
        self.riser_x_slider = QSlider(Qt.Orientation.Horizontal)
        self.riser_x_slider.setMinimum(-200)
        self.riser_x_slider.setMaximum(200)
        self.riser_x_slider.setValue(0)
        self.riser_x_slider.setToolTip("Riser X position relative to part centre (mm)")
        self.riser_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.riser_y_slider.setMinimum(-200)
        self.riser_y_slider.setMaximum(200)
        self.riser_y_slider.setValue(0)
        self.riser_y_slider.setToolTip("Riser Y position relative to part centre (mm)")
        self.sprue_x_label = QLabel("Sprue X: 0 mm")
        self.sprue_y_label = QLabel("Sprue Y: 0 mm")
        self.riser_x_label = QLabel("Riser X: 0 mm")
        self.riser_y_label = QLabel("Riser Y: 0 mm")
        gating_placement_layout.addWidget(self.sprue_x_label)
        gating_placement_layout.addWidget(self.sprue_x_slider)
        gating_placement_layout.addWidget(self.sprue_y_label)
        gating_placement_layout.addWidget(self.sprue_y_slider)
        gating_placement_layout.addWidget(self.riser_x_label)
        gating_placement_layout.addWidget(self.riser_x_slider)
        gating_placement_layout.addWidget(self.riser_y_label)
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
        self.shrink_slider.setToolTip(
            "Scale the pattern slightly larger to compensate for metal shrinkage.\n"
            "The slider adds 0–10 % to part dimensions."
        )
        shrink_pct = METAL_DEFAULTS["A356 Aluminum"]["shrinkage_pct"]
        scale_val = shrink_scale_from_slider(self.shrink_slider.value())
        self.shrink_label = QLabel(f"Shrinkage: {shrink_pct}%  ·  scale ×{scale_val:.3f}")
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
        self.results_text.setAcceptRichText(True)
        self.results_text.setMinimumWidth(350)
        right_panel.addWidget(self.results_text)
        self.sim_btn = QPushButton("Simulate Pour")
        self.sim_btn.setObjectName("sim_btn")
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("reset_btn")
        self.export_btn = QPushButton("Export…")
        self.export_btn.setToolTip("Save results as HTML or PDF, plus a viewport screenshot.")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.sim_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addWidget(self.export_btn)
        right_panel.addLayout(btn_layout)
        splitter.addWidget(right_widget)




        # Store reference to main layout for potential updates
        self._main_layout = main_layout

    def _mm_slider(self, layout, title, vmin, vmax, value, tooltip=""):
        lab = QLabel(f"{title}: {value}")
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setMinimum(vmin)
        sl.setMaximum(vmax)
        sl.setValue(value)
        if tooltip:
            sl.setToolTip(tooltip)
        sl.valueChanged.connect(lambda v, l=lab, t=title: l.setText(f"{t}: {v}"))
        layout.addWidget(lab)
        layout.addWidget(sl)
        return sl, lab

    def _on_gating_dims(self) -> None:
        self.viewport.set_gating_dimensions(
            sprue_top_r=self.sprue_top_slider.value(),
            sprue_bot_r=self.sprue_bot_slider.value(),
            sprue_height=self.sprue_h_slider.value(),
            runner_width=self.runner_w_slider.value(),
            runner_height=self.runner_h_slider.value(),
            gate_area=self.gate_area_slider.value(),
        )



    def _wire_signals(self):

        """Connect all UI signals to their handlers."""

        # STL Load button
        self.load_btn.clicked.connect(self._on_load_stl)

        # Demo button
        self.demo_btn.clicked.connect(self._on_load_demo)


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
        self.flask_h_slider.valueChanged.connect(self._on_flask_height_changed)
        self.add_flask_btn.clicked.connect(self._on_add_flask_preset)


        # Simulation button
        self.sim_btn.clicked.connect(self._on_simulate)


        # Reset button
        self.reset_btn.clicked.connect(self._on_reset)
        self.export_btn.clicked.connect(self._on_export)


        # Model placement sliders - X, Y, Z, Rotation

        def update_transform():
            dx = self.x_slider.value()
            dy = self.y_slider.value()
            dz = self.z_slider.value()
            rot = self.rot_slider.value()
            self.x_label.setText(f"X Offset: {dx} mm")
            self.y_label.setText(f"Y Offset: {dy} mm")
            self.z_label.setText(f"Z Offset: {dz} mm")
            self.rot_label.setText(f"Rotation: {rot} deg")
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
            self.sprue_x_label.setText(f"Sprue X: {sprue_x} mm")
            self.sprue_y_label.setText(f"Sprue Y: {sprue_y} mm")
            self.riser_x_label.setText(f"Riser X: {riser_x} mm")
            self.riser_y_label.setText(f"Riser Y: {riser_y} mm")
            self.viewport.set_gating_offset(sprue_x, sprue_y, runner_y, riser_x, riser_y)


        self.sprue_x_slider.valueChanged.connect(lambda v: update_gating())
        self.sprue_y_slider.valueChanged.connect(lambda v: update_gating())
        self.riser_x_slider.valueChanged.connect(lambda v: update_gating())
        self.riser_y_slider.valueChanged.connect(lambda v: update_gating())


        # Pour temp / mold temp live labels
        self.pour_spin.valueChanged.connect(
            lambda v: self.pour_temp_label.setText(f"Pour Temp: {v} °F")
        )
        self.mold_spin.valueChanged.connect(
            lambda v: self.mold_temp_label.setText(f"Mold Temp: {v} °F")
        )

        # Shrinkage slider
        def update_shrink_label(val):
            pct = METAL_DEFAULTS[self.metal_combo.currentText()]["shrinkage_pct"]
            scale = shrink_scale_from_slider(val)
            self.shrink_label.setText(f"Shrinkage: {pct}%  ·  scale ×{scale:.3f}")
            self.viewport.set_shrink_scale(scale)

        self.shrink_slider.valueChanged.connect(update_shrink_label)
        self.viewport.set_shrink_scale(shrink_scale_from_slider(self.shrink_slider.value()))

        for sl in (
            self.sprue_top_slider, self.sprue_bot_slider, self.sprue_h_slider,
            self.runner_w_slider, self.runner_h_slider, self.gate_area_slider,
        ):
            sl.valueChanged.connect(lambda _v: self._on_gating_dims())
        self._on_gating_dims()


        # Viewport gating moved signal
        self.viewport.gating_moved.connect(self._on_gating_moved)
        self.viewport.model_moved.connect(self._on_model_moved)


        # Initial flask setup
        self._on_flask_changed(self.flask_combo.currentText())






    def _on_gating_moved(self, data: dict) -> None:
        """Sync sliders from 3D drag operations."""
        self.sprue_x_slider.blockSignals(True)
        self.sprue_y_slider.blockSignals(True)
        self.riser_x_slider.blockSignals(True)
        self.riser_y_slider.blockSignals(True)
        self.sprue_x_slider.setValue(int(data.get("sprue_x", 0)))
        self.sprue_y_slider.setValue(int(data.get("sprue_y", 0)))
        self.riser_x_slider.setValue(int(data.get("riser_x", 0)))
        self.riser_y_slider.setValue(int(data.get("riser_y", 0)))
        self.sprue_x_label.setText(f"Sprue X: {self.sprue_x_slider.value()} mm")
        self.sprue_y_label.setText(f"Sprue Y: {self.sprue_y_slider.value()} mm")
        self.riser_x_label.setText(f"Riser X: {self.riser_x_slider.value()} mm")
        self.riser_y_label.setText(f"Riser Y: {self.riser_y_slider.value()} mm")
        self.sprue_x_slider.blockSignals(False)
        self.sprue_y_slider.blockSignals(False)
        self.riser_x_slider.blockSignals(False)
        self.riser_y_slider.blockSignals(False)

    def _on_model_moved(self, data: dict) -> None:
        """Keep X/Y placement sliders in sync with 3D model drags."""
        self.x_slider.blockSignals(True)
        self.y_slider.blockSignals(True)
        self.x_slider.setValue(int(round(data.get("x", 0))))
        self.y_slider.setValue(int(round(data.get("y", 0))))
        self.x_label.setText(f"X Offset: {self.x_slider.value()} mm")
        self.y_label.setText(f"Y Offset: {self.y_slider.value()} mm")
        self.x_slider.blockSignals(False)
        self.y_slider.blockSignals(False)

    def _on_load_stl(self) -> None:
        """Handle STL file load button click."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load STL File", "", "STL Files (*.stl);;All Files (*)"
        )
        if filename:
            try:
                stats = self.viewport.load_stl(filename)
                warn = stats.get("mesh_warnings") or []
                extra = ""
                if warn:
                    extra += "\n⚠ " + " ".join(warn)
                if stats.get("thin_wall_auto"):
                    extra += f"\nThin wall auto-detect: min section {stats.get('min_wall_mm', 0):.1f} mm"
                self.stl_label.setText(
                    f"Loaded: {filename}\n"
                    f"Volume: {stats['vol_cm3']:.2f} cm\u00b3\n"
                    f"Surface: {stats['surf_cm2']:.2f} cm\u00b2"
                    f"{extra}"
                )
                self._geometry_stats = stats
                if warn:
                    QMessageBox.warning(
                        self, "Mesh quality",
                        "This STL may not be a closed solid:\n\n" + "\n".join(warn)
                    )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load STL:\n{str(e)}")

    def _on_load_demo(self) -> None:
        """Load the built-in Motor Mount Bracket demo with pre-configured settings."""
        # 1. Reset controls, then clear any previously loaded parts
        self._on_reset()
        self.viewport.clear_scene()

        # 2. Build the procedural mesh
        triangles, normals, stats = build_demo_mesh()

        # 3. Inject into viewport — bypasses load_stl / file dialog entirely
        self.viewport.models[DEMO_PART_NAME] = {
            "render_data": triangles,
            "normals":     normals,
            "mesh":        None,
            "thickness":   local_thickness(triangles),
        }
        self.viewport.transforms[DEMO_PART_NAME] = {
            "offset":   np.array([0.0, 0.0, 0.0]),
            "rotation": 0.0,
        }
        self.viewport.active_model = DEMO_PART_NAME

        # 4. Store geometry stats for the simulation worker
        self._geometry_stats = stats
        thick = self.viewport.models[DEMO_PART_NAME]["thickness"]
        min_w = float(np.min(thick)) if len(thick) else 999.0
        self._geometry_stats["min_wall_mm"] = min_w
        self._geometry_stats["thin_wall_auto"] = min_w < THIN_WALL_MM

        # 5. Flask: 10 x 12 inches
        self.flask_combo.setCurrentText("10 x 12")

        # 6. Metal: A356 Aluminum (fires _on_metal_changed → sets pour temp)
        self.metal_combo.setCurrentText("A356 Aluminum")

        # 7. Pour temp: 1160 F  (superheat = 85 F → triggers cold-shut + low-superheat)
        self.pour_spin.setValue(1160)

        # 8. Mold temp: default 100 F (already set by reset)

        # 9. Thin wall: Yes — needed for cold-shut defect detection
        self.thin_combo.setCurrentText("Yes")

        # 10. Parting line at 39% — bisects central body just above base plate
        self.parting_slider.setValue(39)

        # 11. Gating: full set
        for name in ["Tapered Sprue", "Runner (Horizontal)", "Fan Gate", "Riser (Open)"]:
            self.gating_checkboxes[name].setChecked(True)

        # 12. Sprue at (+100, +100) — right-front corner; riser at (-80, +70)
        self.sprue_x_slider.setValue(100)
        self.sprue_y_slider.setValue(100)
        self.riser_x_slider.setValue(-80)
        self.riser_y_slider.setValue(70)

        # 13. Update the STL label
        self.stl_label.setText(
            "Demo: Motor Mount Bracket\n"
            f"Volume: {stats['vol_cm3']:.2f} cm\u00b3 | Surface: {stats['surf_cm2']:.2f} cm\u00b2\n"
            "Height: 102 mm  \u2014  7 primitives"
        )

        # 14. Final render with all new state
        self.viewport.render()

    def _on_parting_changed(self, val: int) -> None:
        """Handle parting line slider change."""
        frac = val / 100.0
        self.viewport.set_parting(frac)
        self.parting_label.setText(f"Position: {val}%")

    def _on_metal_changed(self, index: int) -> None:
        """Handle metal combo box change."""
        metal_name = self.metal_combo.currentText()
        metal = METAL_DEFAULTS[metal_name]
        pour_temp = metal["pour_temp_f"]
        shrink_pct = metal["shrinkage_pct"]
        self.pour_spin.setValue(pour_temp)
        self.pour_temp_label.setText(f"Pour Temp: {pour_temp} °F")
        shrink_slider = min(self.shrink_slider.maximum(), 100 + int(round(shrink_pct)))
        self.shrink_slider.setValue(shrink_slider)
        scale_val = shrink_scale_from_slider(self.shrink_slider.value())
        self.shrink_label.setText(f"Shrinkage: {shrink_pct}%  ·  scale ×{scale_val:.3f}")
        self.viewport.set_active_metal(metal_name)
        self.viewport.set_shrink_scale(scale_val)

    def _on_flask_changed(self, text: str) -> None:
        """Handle flask size combo box change."""
        size = self._flask_presets.get(text, (8, 10))
        self.viewport.set_flask(size, height_in=self.flask_h_slider.value())

    def _on_flask_height_changed(self, val: int) -> None:
        self.flask_h_label.setText(f"Flask height: {val} in")
        size = self._flask_presets.get(self.flask_combo.currentText(), (8, 10))
        self.viewport.set_flask(size, height_in=val)

    def _on_add_flask_preset(self):
        """Add custom flask preset."""
        text, ok = QInputDialog.getText(
            self, "Add Custom Flask",
            "Enter name, width, depth in inches (optional height):\n"
            "e.g. '10x12x8, 10, 12, 8'"
        )
        if ok and text:
            try:
                parts = [p for p in text.replace(" ", "").split(",") if p]
                name = parts[0]
                width = float(parts[1])
                height = float(parts[2])
                preset = (width, height)
                if len(parts) >= 4:
                    self.flask_h_slider.setValue(int(round(float(parts[3]))))
                    preset = (width, height, float(parts[3]))
                self._flask_presets[name] = preset
                self.flask_combo.addItem(name)
                self.flask_combo.setCurrentText(name)
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    "Invalid format (name, width_in, depth_in[, height_in]): " + str(e)
                )

    def _on_simulate(self) -> None:
        """Run the casting simulation."""
        # Gather all parameters
        metal_name = self.metal_combo.currentText()
        metal_params = METAL_DEFAULTS[metal_name]
        scale = shrink_scale_from_slider(self.shrink_slider.value())
        vol, surf, z_max = scale_geometry(
            self._geometry_stats.get("vol_cm3", 100.0),
            self._geometry_stats.get("surf_cm2", 120.0),
            self._geometry_stats.get("z_max", 100.0),
            scale,
        )
        thin_mode = self.thin_combo.currentText()
        if thin_mode == "Yes":
            thin_wall = True
        elif thin_mode == "No":
            thin_wall = False
        else:
            if "thin_wall_auto" not in self._geometry_stats and self.viewport.models:
                chunks = [data["render_data"] for data in self.viewport.models.values()]
                thick = local_thickness(np.concatenate(chunks, axis=0))
                min_w = float(np.min(thick)) if len(thick) else 999.0
                self._geometry_stats["min_wall_mm"] = min_w
                self._geometry_stats["thin_wall_auto"] = min_w < THIN_WALL_MM
            thin_wall = bool(self._geometry_stats.get("thin_wall_auto"))
        params = {
            'metal': metal_name,
            'pour_temp_f': self.pour_spin.value(),
            'mold_temp_f': self.mold_spin.value(),
            'thin_wall': thin_wall,
            'shrinkage': metal_params['shrinkage_pct'],
            'gate_types': [name for name, cb in self.gating_checkboxes.items() if cb.isChecked()],
            'vol_cm3': vol,
            'surf_cm2': surf,
            'has_riser': 'Riser (Open)' in self.viewport.gating,
            'gating_params': self.viewport.get_gating_params(),
            'runner_y_offset': self.viewport.runner_y_offset,
            'shrink_scale': scale,
            'z_max': z_max,
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

    def _on_sim_progress(self, pct: int, msg: str) -> None:
        """Update progress during simulation."""
        self.progress_bar.setFormat(f"{msg} {int(pct)}%")
        self.progress_bar.setValue(int(pct))

    def _on_sim_done(self, result: dict) -> None:
        """Handle simulation completion."""
        self.progress_bar.setVisible(False)
        self.sim_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        if result:
            self._last_result = result
            self.results_text.setHtml(build_results_text(result))
            # Decorate defects for drawing
            defects = result.get("defects", [])
            warnings = result.get("warnings", [])
            sites = self.viewport.defect_sites()
            decorated_defects = []

            def _site(kind: str):
                xyz = sites.get(kind) or (0.0, 0.0, result.get("z_max", 100))
                return (kind, float(xyz[0]), float(xyz[1]), float(xyz[2]))

            for d in defects:
                if isinstance(d, tuple):
                    decorated_defects.append(d)
                elif "shrinkage" in d.lower() or "porosity" in d.lower():
                    decorated_defects.append(_site("shrinkage_risk"))
                elif "cold" in d.lower():
                    decorated_defects.append(_site("cold_shut_risk"))
                elif "misrun" in d.lower():
                    decorated_defects.append(_site("misrun_risk"))
                else:
                    decorated_defects.append(d)
            for w in warnings:
                if "porosity" in w.lower() or "shrinkage" in w.lower():
                    decorated_defects.append(_site("shrinkage_risk"))
            # Start animations with draw_defect_markers as final callback
            duration = max(2.0, result.get("fill_time_s", 3.0))
            vsr = result.get("vsr", 1.0)
            self.viewport.start_fill_animation(
                duration_s=duration,
                on_done=lambda: self.viewport.draw_defect_markers(decorated_defects, vsr)
            )
        else:
            self.results_text.setHtml(
                "<p style='color:#F38BA8;font-family:Consolas,monospace;font-size:11px;'>"
                "Simulation failed or was cancelled.</p>"
            )

    def _on_reset(self) -> None:
        """Reset controls and animations without unloading the current part."""
        self.viewport.reset_anim()
        metal_name = self.metal_combo.currentText()
        metal = METAL_DEFAULTS[metal_name]
        self.pour_spin.setValue(metal["pour_temp_f"])
        self.mold_spin.setValue(100)
        self.thin_combo.setCurrentIndex(0)
        self.parting_slider.setValue(50)
        self.x_slider.setValue(0)
        self.y_slider.setValue(0)
        self.z_slider.setValue(0)
        self.rot_slider.setValue(0)
        self.sprue_x_slider.setValue(0)
        self.sprue_y_slider.setValue(0)
        self.riser_x_slider.setValue(0)
        self.riser_y_slider.setValue(0)
        shrink_slider = min(self.shrink_slider.maximum(), 100 + int(round(metal["shrinkage_pct"])))
        self.shrink_slider.setValue(shrink_slider)
        for cb in self.gating_checkboxes.values():
            cb.setChecked(False)
        self.results_text.setText("")
        self._last_result = None

    def _on_export(self) -> None:
        """Save results HTML/PDF and a viewport screenshot."""
        if not self._last_result:
            QMessageBox.information(self, "Export", "Run a simulation first.")
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "Export results", "casting_results.html",
            "HTML (*.html);;PDF (*.pdf);;PNG screenshot (*.png)",
        )
        if not path:
            return
        html = build_results_text(self._last_result)
        lower = path.lower()
        try:
            if lower.endswith(".png") or "PNG" in selected:
                if not lower.endswith(".png"):
                    path += ".png"
                self.viewport.screenshot(path)
            elif lower.endswith(".pdf") or "PDF" in selected:
                if not lower.endswith(".pdf"):
                    path += ".pdf"
                from PyQt6.QtGui import QTextDocument
                from PyQt6.QtPrintSupport import QPrinter
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(path)
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print(printer)
                try:
                    self.viewport.screenshot(path[:-4] + ".png")
                except Exception:
                    pass
            else:
                if not lower.endswith(".html"):
                    path += ".html"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                try:
                    self.viewport.screenshot(path.rsplit(".", 1)[0] + ".png")
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        QMessageBox.information(self, "Export", f"Saved:\n{path}")

    def closeEvent(self, event) -> None:
        """Stop a running simulation thread before the window closes."""
        if self._sim_thread is not None:
            try:
                if self._sim_thread.isRunning():
                    self._sim_thread.quit()
                    self._sim_thread.wait(2000)
            except RuntimeError:
                pass
        self.viewport.reset_anim()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not getattr(self.viewport, "use_pyvista", False):
            try:
                self.viewport.fig.tight_layout()
                self.viewport.fig.canvas.draw_idle()
            except Exception:
                pass
