from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QCheckBox, QScrollArea,
    QProgressBar, QFileDialog, QInputDialog, QMessageBox, QSpinBox,
    QListWidget, QListWidgetItem, QTextBrowser, QFrame,
)
from PyQt6.QtCore import Qt, QThread, QUrl
from PyQt6.QtGui import QKeySequence, QDragEnterEvent, QDropEvent, QShortcut
import numpy as np
from ui.style import APP_STYLE
from ui.collapsible import CollapsiblePanel
from ui.demo_part import build_demo_mesh, DEMO_PART_NAME
from viewport.viewport import Viewport3D
from simulation.worker import SimWorker
from results.formatter import build_results_text, empty_results_html
from constants import (
    METAL_DEFAULTS, FLASK_SIZES, shrink_scale_from_slider, DEFAULT_FLASK_HEIGHT_IN,
    MOLD_TYPES, GATING_RATIOS, DEFAULT_SHELL_MM, SHELL_MM_MIN,
    SHELL_MM_MAX, CERAMIC_SHELL, SHOP_RECIPES,
)
from simulation.mesh_tools import scale_geometry, local_thickness, THIN_WALL_MM
from simulation.foundry import (
    apply_gating_ratio, flask_fit, recommended_pour_band, draft_analysis,
    undercut_hints, is_shell_mold, recommended_shell_preheat_f,
)
from simulation.shop import (
    size_rigging, recipe as shop_recipe, write_pattern_stl, compare_setups,
    pattern_ticket,
)
from simulation.session import (
    save_session, load_session, recent_projects, remember_project, default_session,
)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Casting Simulator")
        self.resize(1480, 920)
        self.setStyleSheet(APP_STYLE)
        self.setAcceptDrops(True)

        self._geometry_stats = {"vol_cm3": 100.0, "surf_cm2": 120.0}
        self._sim_thread = None
        self._sim_worker = None
        self._last_result = None
        self._stl_path = None
        self._is_demo = False
        self._undo_stack: list[dict] = []
        self._session_path = None
        self._baseline_result = None

        self.viewport = Viewport3D()
        self._sand_molds = [n for n in MOLD_TYPES if n != CERAMIC_SHELL]
        self._build_ui()
        self._wire_signals()
        self._refresh_recents()
        self._refresh_status()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        shell = QWidget()
        self.setCentralWidget(shell)
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)

        outer.addWidget(self._build_top_bar())
        outer.addWidget(self._build_step_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        left_widget = QWidget()
        left_panel = QVBoxLayout(left_widget)
        left_panel.setContentsMargins(0, 0, 8, 0)
        left_panel.setSpacing(8)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(312)
        splitter.addWidget(left_scroll)

        self._build_part_panel(left_panel)
        self._build_process_panel(left_panel)
        self._build_gating_panel(left_panel)
        self._build_metal_panel(left_panel)
        self._build_flask_panel(left_panel)
        self._build_parting_panel(left_panel)
        self._build_placement_panel(left_panel)
        self._build_shrink_panel(left_panel)
        self._build_inspect_panel(left_panel)
        left_panel.addStretch()

        center = QWidget()
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        if hasattr(self.viewport, "render_frame"):
            center_l.addWidget(self.viewport.render_frame)
        else:
            center_l.addWidget(self.viewport)
        splitter.addWidget(center)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 0, 0, 0)
        right_l.setSpacing(8)
        views = QHBoxLayout()
        views.setSpacing(4)
        for view in ["Top", "Bottom", "Front", "Back", "Left", "Right", "Iso"]:
            btn = QPushButton(view)
            btn.setObjectName("viewBtn")
            btn.clicked.connect(lambda _, v=view: self.viewport.set_view(v))
            views.addWidget(btn)
        right_l.addLayout(views)
        res_cap = QLabel("RESULTS")
        res_cap.setObjectName("caption")
        right_l.addWidget(res_cap)
        cmp = QHBoxLayout()
        self.keep_a_btn = QPushButton("Keep as A")
        self.keep_a_btn.setObjectName("ghostBtn")
        self.keep_a_btn.setToolTip("Store this pour, then simulate a second setup to compare.")
        self.clear_a_btn = QPushButton("Clear A")
        self.clear_a_btn.setObjectName("ghostBtn")
        cmp.addWidget(self.keep_a_btn)
        cmp.addWidget(self.clear_a_btn)
        right_l.addLayout(cmp)
        self.compare_label = QLabel("")
        self.compare_label.setObjectName("hint")
        self.compare_label.setWordWrap(True)
        right_l.addWidget(self.compare_label)
        self.results_text = QTextBrowser()
        self.results_text.setOpenExternalLinks(False)
        self.results_text.setOpenLinks(False)
        self.results_text.setMinimumWidth(340)
        self.results_text.setHtml(empty_results_html())
        right_l.addWidget(self.results_text)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        self._status = QLabel("Drop a part to start")
        self._status.setObjectName("statusChip")
        outer.addWidget(self._status)
        self._main_layout = outer

    def _build_top_bar(self) -> QFrame:
        chrome = QFrame()
        chrome.setObjectName("chromeBar")
        bar = QHBoxLayout(chrome)
        bar.setContentsMargins(10, 8, 10, 8)
        bar.setSpacing(8)

        mark = QLabel("Casting")
        mark.setObjectName("wordmark")
        sub = QLabel("Simulator")
        sub.setObjectName("wordmarkSub")
        bar.addWidget(mark)
        bar.addWidget(sub)

        self.demo_btn = QPushButton("Try demo")
        self.demo_btn.setObjectName("demoBtn")
        self.demo_btn.setToolTip("Load the Motor Mount Bracket with gating already placed.")
        self.load_btn = QPushButton("Open part…")
        self.load_btn.setObjectName("ghostBtn")
        self.sim_btn = QPushButton("Simulate pour")
        self.sim_btn.setObjectName("primaryBtn")
        self.sim_btn.setEnabled(False)
        self.sim_btn.setToolTip("Load a part first.")
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("dangerBtn")
        self.save_btn = QPushButton("Save job")
        self.save_btn.setObjectName("ghostBtn")
        self.open_btn = QPushButton("Open job")
        self.open_btn.setObjectName("ghostBtn")
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("ghostBtn")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)

        bar.addSpacing(8)
        bar.addWidget(self.demo_btn)
        bar.addWidget(self.load_btn)
        bar.addSpacing(12)
        bar.addWidget(self.sim_btn)
        bar.addWidget(self.reset_btn)
        bar.addStretch()
        bar.addWidget(self.progress_bar)
        bar.addWidget(self.save_btn)
        bar.addWidget(self.open_btn)
        bar.addWidget(self.export_btn)
        return chrome

    def _build_step_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("stepBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 0, 6, 0)
        for text in (
            "1  Open a part",
            "2  Pick sand or shell",
            "3  Place gating",
            "4  Simulate",
        ):
            lab = QLabel(text)
            lab.setObjectName("step")
            row.addWidget(lab)
        row.addStretch()
        return bar

    def _caption(self, text: str) -> QLabel:
        lab = QLabel(text.upper())
        lab.setObjectName("caption")
        return lab

    def _build_part_panel(self, parent):
        panel = CollapsiblePanel("Part")
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stl_label = QLabel("Drop an STL or OBJ on the window — or open a part.")
        self.stl_label.setWordWrap(True)
        self.stl_label.setObjectName("hint")
        lay.addWidget(self.stl_label)
        lay.addWidget(self._caption("Import units"))
        self.units_combo = QComboBox()
        self.units_combo.addItem("Millimetres", 1.0)
        self.units_combo.addItem("Inches", 25.4)
        self.units_combo.setToolTip("Scale the file so the simulator works in millimetres.")
        lay.addWidget(self.units_combo)
        lay.addWidget(self._caption("Recent"))
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(96)
        lay.addWidget(self.recent_list)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(True)
        self._part_panel = panel

    def _build_process_panel(self, parent):
        panel = CollapsiblePanel("Process")
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Same part, two shop methods. Pick one — flask vs fired shell.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.sand_btn = QPushButton("Sand mold")
        self.sand_btn.setObjectName("processBtn")
        self.sand_btn.setCheckable(True)
        self.sand_btn.setChecked(True)
        self.sand_btn.setToolTip("Green, dry, or resin sand in a flask.")
        self.shell_btn = QPushButton("Ceramic shell")
        self.shell_btn.setObjectName("processBtn")
        self.shell_btn.setCheckable(True)
        self.shell_btn.setToolTip("Investment / lost-wax. Preheat the fired shell.")
        row.addWidget(self.sand_btn)
        row.addWidget(self.shell_btn)
        lay.addLayout(row)
        lay.addWidget(self._caption("Shop recipe"))
        self.recipe_combo = QComboBox()
        self.recipe_combo.addItem("Custom…")
        for name in SHOP_RECIPES:
            self.recipe_combo.addItem(name)
        self.recipe_combo.setToolTip(
            "Named process templates — metal, mould, and temps in one click."
        )
        lay.addWidget(self.recipe_combo)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(True)

    def _build_gating_panel(self, parent):
        panel = CollapsiblePanel("Gating")
        box = QWidget()
        lay = QVBoxLayout(box)
        self.gating_hint = QLabel("Click a face to drop a sprue, gate, or riser.")
        self.gating_hint.setWordWrap(True)
        self.gating_hint.setStyleSheet("color: #A6ADC8;")
        lay.addWidget(self.gating_hint)
        place = QHBoxLayout()
        self.pick_sprue_btn = QPushButton("Sprue")
        self.pick_gate_btn = QPushButton("Gate")
        self.pick_riser_btn = QPushButton("Riser")
        self.pick_chill_btn = QPushButton("Chill")
        for b, tip in (
            (self.pick_sprue_btn, "Click the part to drop the sprue."),
            (self.pick_gate_btn, "Click a face to drop the fan gate."),
            (self.pick_riser_btn, "Click the hot spot to drop an open riser."),
            (self.pick_chill_btn, "Click a thick section to plant a chill."),
        ):
            b.setObjectName("ghostBtn")
            b.setToolTip(tip)
            place.addWidget(b)
        lay.addLayout(place)
        self.wizard_btn = QPushButton("Size sprue, runner, gate, riser")
        self.wizard_btn.setObjectName("primaryBtn")
        self.wizard_btn.setToolTip(
            "Rigging wizard — sizes the whole tree for this metal and part."
        )
        lay.addWidget(self.wizard_btn)

        self.gating_checkboxes = {}
        for comp in ["Tapered Sprue", "Runner (Horizontal)", "Fan Gate", "Riser (Open)"]:
            cb = QCheckBox(comp)
            self.gating_checkboxes[comp] = cb
            lay.addWidget(cb)
        self.sleeve_cb = QCheckBox("Insulating sleeve on riser")
        self.sleeve_cb.setToolTip("Slows freeze around the riser (exothermic / sleeve).")
        lay.addWidget(self.sleeve_cb)

        lay.addWidget(QLabel("Ratio preset"))
        self.ratio_combo = QComboBox()
        for name in GATING_RATIOS:
            self.ratio_combo.addItem(name)
        self.apply_ratio_btn = QPushButton("Apply ratio")
        self.snap_btn = QPushButton("Snap to part")
        row = QHBoxLayout()
        row.addWidget(self.apply_ratio_btn)
        row.addWidget(self.snap_btn)
        lay.addWidget(self.ratio_combo)
        lay.addLayout(row)

        self.sprue_dim_box, self.sprue_top_slider, self.sprue_top_label = None, None, None
        self._gating_dim_widgets: dict[str, QWidget] = {}

        sprue_w = QWidget()
        sl = QVBoxLayout(sprue_w)
        sl.setContentsMargins(0, 0, 0, 0)
        self.sprue_top_slider, self.sprue_top_label = self._mm_slider(
            sl, "Sprue top r", 4, 30, 8, "Radius at the pouring basin (mm).",
        )
        self.sprue_bot_slider, self.sprue_bot_label = self._mm_slider(
            sl, "Sprue exit r", 2, 20, 4, "Radius at the runner — usually the choke.",
        )
        self.sprue_h_slider, self.sprue_h_label = self._mm_slider(
            sl, "Sprue height", 40, 250, 100, "Basin length above the cope.",
        )
        self.sprue_x_slider, self.sprue_x_label = self._mm_slider(sl, "Sprue X", -200, 200, 0)
        self.sprue_y_slider, self.sprue_y_label = self._mm_slider(sl, "Sprue Y", -200, 200, 0)
        lay.addWidget(sprue_w)
        self._gating_dim_widgets["Tapered Sprue"] = sprue_w

        run_w = QWidget()
        rl = QVBoxLayout(run_w)
        rl.setContentsMargins(0, 0, 0, 0)
        self.runner_w_slider, self.runner_w_label = self._mm_slider(
            rl, "Runner width", 4, 50, 10, "Cross-section width (mm).",
        )
        self.runner_h_slider, self.runner_h_label = self._mm_slider(
            rl, "Runner height", 4, 30, 8, "Cross-section height (mm).",
        )
        lay.addWidget(run_w)
        self._gating_dim_widgets["Runner (Horizontal)"] = run_w

        gate_w = QWidget()
        gl = QVBoxLayout(gate_w)
        gl.setContentsMargins(0, 0, 0, 0)
        self.gate_area_slider, self.gate_area_label = self._mm_slider(
            gl, "Gate area", 10, 400, 40, "Fan-gate hydraulic area (mm²).",
        )
        lay.addWidget(gate_w)
        self._gating_dim_widgets["Fan Gate"] = gate_w

        riser_w = QWidget()
        risl = QVBoxLayout(riser_w)
        risl.setContentsMargins(0, 0, 0, 0)
        self.riser_r_slider, self.riser_r_label = self._mm_slider(
            risl, "Riser radius", 8, 40, 20, "Open-riser radius (mm).",
        )
        self.riser_h_slider, self.riser_h_label = self._mm_slider(
            risl, "Riser height", 24, 120, 60, "Open-riser height (mm).",
        )
        self.riser_x_slider, self.riser_x_label = self._mm_slider(risl, "Riser X", -200, 200, 0)
        self.riser_y_slider, self.riser_y_label = self._mm_slider(risl, "Riser Y", -200, 200, 0)
        lay.addWidget(riser_w)
        self._gating_dim_widgets["Riser (Open)"] = riser_w

        for w in self._gating_dim_widgets.values():
            w.setVisible(False)

        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(True)

    def _build_metal_panel(self, parent):
        panel = CollapsiblePanel("Metal")
        box = QWidget()
        lay = QVBoxLayout(box)
        self.metal_combo = QComboBox()
        for metal in METAL_DEFAULTS:
            self.metal_combo.addItem(metal)
        lay.addWidget(self._caption("Alloy"))
        lay.addWidget(self.metal_combo)
        self.sand_type_label = self._caption("Sand type")
        lay.addWidget(self.sand_type_label)
        self.mold_combo = QComboBox()
        for name in self._sand_molds:
            self.mold_combo.addItem(name)
        lay.addWidget(self.mold_combo)
        self.mold_hint = QLabel("")
        self.mold_hint.setWordWrap(True)
        self.mold_hint.setObjectName("hint")
        lay.addWidget(self.mold_hint)

        self.pour_spin = QSpinBox()
        self.pour_spin.setRange(800, 3200)
        self.pour_spin.setSuffix(" °F")
        self.pour_spin.setValue(METAL_DEFAULTS["A356 Aluminum"]["pour_temp_f"])
        self.pour_temp_label = QLabel("Pour temp")
        self.pour_temp_label.setObjectName("caption")
        self.pour_band_label = QLabel("")
        self.pour_band_label.setObjectName("hint")
        lay.addWidget(self.pour_temp_label)
        lay.addWidget(self.pour_spin)
        lay.addWidget(self.pour_band_label)

        self.mold_spin = QSpinBox()
        self.mold_spin.setRange(32, 300)
        self.mold_spin.setSuffix(" °F")
        self.mold_spin.setValue(100)
        self.mold_temp_label = QLabel("Mold temp")
        self.mold_temp_label.setObjectName("caption")
        lay.addWidget(self.mold_temp_label)
        lay.addWidget(self.mold_spin)
        self.preheat_band_label = QLabel("")
        self.preheat_band_label.setObjectName("hint")
        self.preheat_band_label.setVisible(False)
        lay.addWidget(self.preheat_band_label)

        self.thin_combo = QComboBox()
        self.thin_combo.addItems(["Auto", "No", "Yes"])
        self.thin_combo.setToolTip(
            f"Auto flags walls thinner than {THIN_WALL_MM:.0f} mm."
        )
        lay.addWidget(self._caption("Thin wall"))
        lay.addWidget(self.thin_combo)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(True)
        self._update_pour_band()

    def _build_flask_panel(self, parent):
        panel = CollapsiblePanel("Flask")
        self.flask_panel = panel
        box = QWidget()
        lay = QVBoxLayout(box)

        self._flask_sand_box = QWidget()
        sand = QVBoxLayout(self._flask_sand_box)
        sand.setContentsMargins(0, 0, 0, 0)
        self.flask_combo = QComboBox()
        self._flask_presets = dict(FLASK_SIZES)
        for name in self._flask_presets:
            self.flask_combo.addItem(name)
        self.add_flask_btn = QPushButton("+ Custom")
        self.auto_flask_btn = QPushButton("Auto-fit")
        row = QHBoxLayout()
        row.addWidget(self.flask_combo)
        row.addWidget(self.add_flask_btn)
        sand.addLayout(row)
        sand.addWidget(self.auto_flask_btn)
        self.flask_h_slider = QSlider(Qt.Orientation.Horizontal)
        self.flask_h_slider.setMinimum(3)
        self.flask_h_slider.setMaximum(18)
        self.flask_h_slider.setValue(int(DEFAULT_FLASK_HEIGHT_IN))
        self.flask_h_label = QLabel(f"Stack height: {int(DEFAULT_FLASK_HEIGHT_IN)} in")
        sand.addWidget(self.flask_h_label)
        sand.addWidget(self.flask_h_slider)
        self.flask_fit_label = QLabel("")
        self.flask_fit_label.setWordWrap(True)
        sand.addWidget(self.flask_fit_label)
        lay.addWidget(self._flask_sand_box)

        self._flask_shell_box = QWidget()
        shell = QVBoxLayout(self._flask_shell_box)
        shell.setContentsMargins(0, 0, 0, 0)
        self.shell_hint = QLabel(
            "Lost-wax / investment: dip ceramic slurry, dewax, fire, pour into the hot shell. No sand flask."
        )
        self.shell_hint.setWordWrap(True)
        self.shell_hint.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        shell.addWidget(self.shell_hint)
        self.shell_mm_slider = QSlider(Qt.Orientation.Horizontal)
        self.shell_mm_slider.setMinimum(SHELL_MM_MIN)
        self.shell_mm_slider.setMaximum(SHELL_MM_MAX)
        self.shell_mm_slider.setValue(int(DEFAULT_SHELL_MM))
        self.shell_mm_label = QLabel(f"Fired shell: {int(DEFAULT_SHELL_MM)} mm")
        shell.addWidget(self.shell_mm_label)
        shell.addWidget(self.shell_mm_slider)
        self._flask_shell_box.setVisible(False)
        lay.addWidget(self._flask_shell_box)

        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(False)

    def _build_parting_panel(self, parent):
        panel = CollapsiblePanel("Parting line")
        box = QWidget()
        lay = QVBoxLayout(box)
        self.parting_slider = QSlider(Qt.Orientation.Horizontal)
        self.parting_slider.setMinimum(5)
        self.parting_slider.setMaximum(95)
        self.parting_slider.setValue(50)
        self.parting_label = QLabel("Position: 50%")
        self.pick_parting_btn = QPushButton("Pick in 3D")
        self.pick_parting_btn.setToolTip("Click in the viewport to set the cope/drag split height.")
        self.parting_hint = QLabel("")
        self.parting_hint.setWordWrap(True)
        self.parting_hint.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        lay.addWidget(self.parting_label)
        lay.addWidget(self.parting_slider)
        lay.addWidget(self.pick_parting_btn)
        lay.addWidget(self.parting_hint)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(False)

    def _build_placement_panel(self, parent):
        panel = CollapsiblePanel("Model placement")
        box = QWidget()
        lay = QVBoxLayout(box)
        self.x_slider = QSlider(Qt.Orientation.Horizontal)
        self.x_slider.setRange(-500, 500)
        self.y_slider = QSlider(Qt.Orientation.Horizontal)
        self.y_slider.setRange(-500, 500)
        self.z_slider = QSlider(Qt.Orientation.Horizontal)
        self.z_slider.setRange(-200, 200)
        self.rot_slider = QSlider(Qt.Orientation.Horizontal)
        self.rot_slider.setRange(0, 360)
        self.x_label = QLabel("X Offset: 0 mm")
        self.y_label = QLabel("Y Offset: 0 mm")
        self.z_label = QLabel("Z Offset: 0 mm")
        self.rot_label = QLabel("Rotation: 0 deg")
        for lab, sl in (
            (self.x_label, self.x_slider), (self.y_label, self.y_slider),
            (self.z_label, self.z_slider), (self.rot_label, self.rot_slider),
        ):
            lay.addWidget(lab)
            lay.addWidget(sl)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(False)

    def _build_shrink_panel(self, parent):
        panel = CollapsiblePanel("Shrinkage")
        box = QWidget()
        lay = QVBoxLayout(box)
        self.shrink_slider = QSlider(Qt.Orientation.Horizontal)
        self.shrink_slider.setMinimum(100)
        self.shrink_slider.setMaximum(110)
        self.shrink_slider.setValue(106)
        shrink_pct = METAL_DEFAULTS["A356 Aluminum"]["shrinkage_pct"]
        scale_val = shrink_scale_from_slider(106)
        self.shrink_label = QLabel(f"Shrinkage: {shrink_pct}%  ·  scale ×{scale_val:.3f}")
        self.as_cast_cb = QCheckBox("Show as-cast (no pattern scale)")
        self.export_pattern_btn = QPushButton("Export pattern STL…")
        self.export_pattern_btn.setObjectName("ghostBtn")
        self.export_pattern_btn.setToolTip("Write the mesh at the shrink scale — print this for lost-PLA.")
        lay.addWidget(self.shrink_label)
        lay.addWidget(self.shrink_slider)
        lay.addWidget(self.as_cast_cb)
        lay.addWidget(self.export_pattern_btn)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(False)

    def _build_inspect_panel(self, parent):
        panel = CollapsiblePanel("Foundry checks")
        box = QWidget()
        lay = QVBoxLayout(box)
        self.draft_cb = QCheckBox("Draft overlay (red = lock)")
        self.undercut_cb = QCheckBox("Undercut / core-print overlay")
        self.hotspot_cb = QCheckBox("Hot-spot overlay (last to freeze)")
        lay.addWidget(self._caption("Result layer"))
        self.overlay_combo = QComboBox()
        self.overlay_combo.addItem("None", "")
        self.overlay_combo.addItem("Hot-spot (thickness)", "hotspot")
        self.overlay_combo.addItem("Last-to-freeze", "freeze")
        self.overlay_combo.addItem("Fill order", "fill")
        self.overlay_combo.addItem("Porosity", "porosity")
        self.overlay_combo.addItem("Niyama proxy", "niyama")
        self.clip_cb = QCheckBox("Cut plane")
        self.clip_axis_combo = QComboBox()
        self.clip_axis_combo.addItems(["X", "Y", "Z"])
        self.clip_axis_combo.setCurrentIndex(2)
        self.clip_slider = QSlider(Qt.Orientation.Horizontal)
        self.clip_slider.setRange(0, 100)
        self.clip_slider.setValue(50)
        self.clip_label = QLabel("Cut: 50%")
        self.inspect_label = QLabel("")
        self.inspect_label.setWordWrap(True)
        lay.addWidget(self.draft_cb)
        lay.addWidget(self.undercut_cb)
        lay.addWidget(self.hotspot_cb)
        lay.addWidget(self.overlay_combo)
        lay.addWidget(self.clip_cb)
        clip_row = QHBoxLayout()
        clip_row.addWidget(self.clip_axis_combo)
        clip_row.addWidget(self.clip_slider)
        lay.addLayout(clip_row)
        lay.addWidget(self.clip_label)
        lay.addWidget(self.inspect_label)
        panel.content_layout.addWidget(box)
        parent.addWidget(panel)
        panel.setExpanded(True)

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

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _wire_signals(self):
        self.load_btn.clicked.connect(self._on_load_stl)
        self.demo_btn.clicked.connect(self._on_load_demo)
        self.sim_btn.clicked.connect(self._on_simulate)
        self.reset_btn.clicked.connect(self._on_reset)
        self.export_btn.clicked.connect(self._on_export)
        self.save_btn.clicked.connect(self._on_save_session)
        self.open_btn.clicked.connect(self._on_open_session)
        self.recent_list.itemClicked.connect(self._on_recent_clicked)

        self.parting_slider.valueChanged.connect(self._on_parting_changed)
        self.pick_parting_btn.clicked.connect(self._on_pick_parting)

        for name, cb in self.gating_checkboxes.items():
            cb.stateChanged.connect(lambda _s, n=name: self._on_gating_toggled())

        self.metal_combo.currentIndexChanged.connect(self._on_metal_changed)
        self.mold_combo.currentTextChanged.connect(self._on_mold_changed)
        self.sand_btn.clicked.connect(lambda: self._set_process("sand"))
        self.shell_btn.clicked.connect(lambda: self._set_process("shell"))
        self.pour_spin.valueChanged.connect(self._on_pour_changed)
        self.mold_spin.valueChanged.connect(self._on_mold_temp_changed)
        self.shell_mm_slider.valueChanged.connect(self._on_shell_mm_changed)

        self.flask_combo.currentTextChanged.connect(self._on_flask_changed)
        self.flask_h_slider.valueChanged.connect(self._on_flask_height_changed)
        self.add_flask_btn.clicked.connect(self._on_add_flask_preset)
        self.auto_flask_btn.clicked.connect(self._on_auto_flask)

        self.x_slider.valueChanged.connect(lambda _: self._apply_transform())
        self.y_slider.valueChanged.connect(lambda _: self._apply_transform())
        self.z_slider.valueChanged.connect(lambda _: self._apply_transform())
        self.rot_slider.valueChanged.connect(lambda _: self._apply_transform())

        self.sprue_x_slider.valueChanged.connect(lambda _: self._apply_gating_offset())
        self.sprue_y_slider.valueChanged.connect(lambda _: self._apply_gating_offset())
        self.riser_x_slider.valueChanged.connect(lambda _: self._apply_gating_offset())
        self.riser_y_slider.valueChanged.connect(lambda _: self._apply_gating_offset())

        self.shrink_slider.valueChanged.connect(self._on_shrink)
        self.as_cast_cb.toggled.connect(self.viewport.set_show_as_cast)
        self.viewport.set_shrink_scale(shrink_scale_from_slider(self.shrink_slider.value()))

        for sl in (
            self.sprue_top_slider, self.sprue_bot_slider, self.sprue_h_slider,
            self.runner_w_slider, self.runner_h_slider, self.gate_area_slider,
            self.riser_r_slider, self.riser_h_slider,
        ):
            sl.valueChanged.connect(lambda _v: self._on_gating_dims())
        self._on_gating_dims()

        self.apply_ratio_btn.clicked.connect(self._on_apply_ratio)
        self.snap_btn.clicked.connect(self._on_snap)
        self.wizard_btn.clicked.connect(self._on_wizard)
        self.pick_sprue_btn.clicked.connect(lambda: self._start_place("sprue"))
        self.pick_gate_btn.clicked.connect(lambda: self._start_place("gate"))
        self.pick_riser_btn.clicked.connect(lambda: self._start_place("riser"))
        self.pick_chill_btn.clicked.connect(lambda: self._start_place("chill"))
        self.recipe_combo.currentTextChanged.connect(self._on_recipe)
        self.export_pattern_btn.clicked.connect(self._on_export_pattern)
        self.keep_a_btn.clicked.connect(self._on_keep_a)
        self.clear_a_btn.clicked.connect(self._on_clear_a)
        self.hotspot_cb.toggled.connect(self._on_inspect)
        self.overlay_combo.currentIndexChanged.connect(self._on_overlay_combo)
        self.clip_cb.toggled.connect(self._on_clip_changed)
        self.clip_axis_combo.currentIndexChanged.connect(self._on_clip_changed)
        self.clip_slider.valueChanged.connect(self._on_clip_changed)

        self.viewport.gating_moved.connect(self._on_gating_moved)
        self.viewport.model_moved.connect(self._on_model_moved)
        self.viewport.gating_selected.connect(self._on_gating_selected)
        self.viewport.parting_picked.connect(self._on_parting_picked)
        self.viewport.gating_list_changed.connect(self._on_gating_list)
        self.viewport.drag_began.connect(self._push_undo)
        self.results_text.anchorClicked.connect(self._on_result_anchor)

        self.draft_cb.toggled.connect(self._on_inspect)
        self.undercut_cb.toggled.connect(self._on_inspect)

        self._undo_sc = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._undo_sc.activated.connect(self._on_undo)
        self._save_sc = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_sc.activated.connect(self._on_save_session)
        self._open_sc = QShortcut(QKeySequence.StandardKey.Open, self)
        self._open_sc.activated.connect(self._on_open_session)

        self._on_flask_changed(self.flask_combo.currentText())
        self._update_pour_band()
        self._sync_process_ui(set_preheat=False)

    def _apply_transform(self):
        dx, dy, dz, rot = (
            self.x_slider.value(), self.y_slider.value(),
            self.z_slider.value(), self.rot_slider.value(),
        )
        self.x_label.setText(f"X Offset: {dx} mm")
        self.y_label.setText(f"Y Offset: {dy} mm")
        self.z_label.setText(f"Z Offset: {dz} mm")
        self.rot_label.setText(f"Rotation: {rot} deg")
        self.viewport.set_transformation(dx, dy, dz, rot)

    def _apply_gating_offset(self):
        sx, sy = self.sprue_x_slider.value(), self.sprue_y_slider.value()
        rx, ry = self.riser_x_slider.value(), self.riser_y_slider.value()
        self.sprue_x_label.setText(f"Sprue X: {sx}")
        self.sprue_y_label.setText(f"Sprue Y: {sy}")
        self.riser_x_label.setText(f"Riser X: {rx}")
        self.riser_y_label.setText(f"Riser Y: {ry}")
        self.viewport.set_gating_offset(sx, sy, 0, rx, ry)

    def _on_gating_dims(self) -> None:
        self.viewport.set_gating_dimensions(
            sprue_top_r=self.sprue_top_slider.value(),
            sprue_bot_r=self.sprue_bot_slider.value(),
            sprue_height=self.sprue_h_slider.value(),
            runner_width=self.runner_w_slider.value(),
            runner_height=self.runner_h_slider.value(),
            gate_area=self.gate_area_slider.value(),
            riser_r=self.riser_r_slider.value(),
            riser_h=self.riser_h_slider.value(),
        )

    def _on_gating_toggled(self) -> None:
        names = [k for k, v in self.gating_checkboxes.items() if v.isChecked()]
        self.viewport.set_gating(names)

    def _on_gating_selected(self, name: str) -> None:
        for key, w in self._gating_dim_widgets.items():
            w.setVisible(key == name)
        self.viewport.set_selected_gating(name)
        if name:
            self.gating_checkboxes[name].setChecked(True)
            self.gating_hint.setText(f"Editing {name}. Drag in 3D to place.")

    def _on_gating_moved(self, data: dict) -> None:
        for sl in (self.sprue_x_slider, self.sprue_y_slider, self.riser_x_slider, self.riser_y_slider):
            sl.blockSignals(True)
        self.sprue_x_slider.setValue(int(data.get("sprue_x", 0)))
        self.sprue_y_slider.setValue(int(data.get("sprue_y", 0)))
        self.riser_x_slider.setValue(int(data.get("riser_x", 0)))
        self.riser_y_slider.setValue(int(data.get("riser_y", 0)))
        self.sprue_x_label.setText(f"Sprue X: {self.sprue_x_slider.value()}")
        self.sprue_y_label.setText(f"Sprue Y: {self.sprue_y_slider.value()}")
        self.riser_x_label.setText(f"Riser X: {self.riser_x_slider.value()}")
        self.riser_y_label.setText(f"Riser Y: {self.riser_y_slider.value()}")
        for sl in (self.sprue_x_slider, self.sprue_y_slider, self.riser_x_slider, self.riser_y_slider):
            sl.blockSignals(False)

    def _on_model_moved(self, data: dict) -> None:
        self.x_slider.blockSignals(True)
        self.y_slider.blockSignals(True)
        self.x_slider.setValue(int(round(data.get("x", 0))))
        self.y_slider.setValue(int(round(data.get("y", 0))))
        self.x_label.setText(f"X Offset: {self.x_slider.value()} mm")
        self.y_label.setText(f"Y Offset: {self.y_slider.value()} mm")
        self.x_slider.blockSignals(False)
        self.y_slider.blockSignals(False)

    def _on_apply_ratio(self) -> None:
        self._push_undo()
        ratio = GATING_RATIOS[self.ratio_combo.currentText()]
        sized = apply_gating_ratio(
            self.sprue_bot_slider.value(), ratio,
            runner_height_mm=self.runner_h_slider.value(),
        )
        self.runner_w_slider.setValue(int(round(sized["runner_width_mm"])))
        self.gate_area_slider.setValue(int(round(max(10, min(400, sized["gate_area_mm2"])))))
        for name in ("Tapered Sprue", "Runner (Horizontal)", "Fan Gate"):
            self.gating_checkboxes[name].setChecked(True)
        self._on_gating_dims()

    def _on_snap(self) -> None:
        self._push_undo()
        if not self.viewport.models:
            QMessageBox.information(self, "Snap", "Load a part first.")
            return
        self.viewport.snap_gating_to_part()

    def _start_place(self, kind: str) -> None:
        if not self.viewport.models:
            QMessageBox.information(self, "Place gating", "Load a part first.")
            return
        self.viewport.pick_mode = kind
        labels = {
            "sprue": "Click a face to drop the sprue…",
            "gate": "Click a face to drop the fan gate…",
            "riser": "Click the hot spot to drop the riser…",
            "chill": "Click a thick section to plant a chill…",
        }
        self.gating_hint.setText(labels.get(kind, "Click the viewport…"))

    def _on_gating_list(self, names: list) -> None:
        for name, cb in self.gating_checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(name in names)
            cb.blockSignals(False)
        self.viewport.set_gating(list(names))

    def _on_wizard(self) -> None:
        if not self.viewport.models:
            QMessageBox.information(self, "Rigging wizard", "Load a part first.")
            return
        self._push_undo()
        metal = self.metal_combo.currentText()
        scale = shrink_scale_from_slider(self.shrink_slider.value())
        vol, surf, _z = scale_geometry(
            self._geometry_stats.get("vol_cm3", 100.0),
            self._geometry_stats.get("surf_cm2", 120.0),
            self._geometry_stats.get("z_max", 100.0),
            scale,
        )
        sized = size_rigging(vol, surf, metal, sprue_h_mm=self.sprue_h_slider.value())
        self.ratio_combo.setCurrentText(sized["ratio_label"])
        self.sprue_bot_slider.setValue(int(round(sized["sprue_bot_r_mm"])))
        self.sprue_top_slider.setValue(int(round(sized["sprue_top_r_mm"])))
        self.sprue_h_slider.setValue(int(round(sized["sprue_h_mm"])))
        self.runner_w_slider.setValue(int(round(sized["runner_width_mm"])))
        self.runner_h_slider.setValue(int(round(sized["runner_height_mm"])))
        self.gate_area_slider.setValue(int(round(sized["gate_area_mm2"])))
        self.riser_r_slider.setValue(int(round(sized["riser_r_mm"])))
        self.riser_h_slider.setValue(int(round(sized["riser_h_mm"])))
        for name in ("Tapered Sprue", "Runner (Horizontal)", "Fan Gate", "Riser (Open)"):
            self.gating_checkboxes[name].setChecked(True)
        self._on_gating_dims()
        self.gating_hint.setText(
            f"Sized {sized['ratio_label']} · sprue Ø {2 * sized['sprue_bot_r_mm']:.0f} mm · "
            f"riser Ø {2 * sized['riser_r_mm']:.0f} mm · target fill {sized['target_fill_s']:.0f} s"
        )
        if not self.viewport.gating or "Tapered Sprue" not in self.viewport.gating:
            self.viewport.snap_gating_to_part()

    def _on_recipe(self, name: str) -> None:
        if not name or name.startswith("Custom"):
            return
        rec = shop_recipe(name)
        if not rec:
            return
        self._push_undo()
        if rec.get("metal"):
            self.metal_combo.setCurrentText(rec["metal"])
        self._set_process("shell" if rec.get("process") == "shell" else "sand")
        if rec.get("mold_type") and rec.get("process") != "shell":
            idx = self.mold_combo.findText(rec["mold_type"])
            if idx >= 0:
                self.mold_combo.setCurrentIndex(idx)
        if rec.get("pour_temp_f") is not None:
            self.pour_spin.setValue(int(rec["pour_temp_f"]))
        if rec.get("mold_temp_f") is not None:
            self.mold_spin.setValue(int(rec["mold_temp_f"]))
        if rec.get("shell_mm") is not None:
            self.shell_mm_slider.setValue(int(rec["shell_mm"]))
        if rec.get("gating_ratio"):
            self.ratio_combo.setCurrentText(rec["gating_ratio"])
        if rec.get("thin_wall"):
            self.thin_combo.setCurrentText(rec["thin_wall"])
        self._refresh_status()

    def _on_export_pattern(self) -> None:
        mesh = self.viewport.world_meshes()
        if mesh is None:
            QMessageBox.information(self, "Pattern STL", "Load a part first.")
            return
        scale = shrink_scale_from_slider(self.shrink_slider.value())
        path, _ = QFileDialog.getSaveFileName(
            self, "Export pattern STL",
            f"pattern_x{scale:.3f}.stl",
            "STL (*.stl)",
        )
        if not path:
            return
        try:
            write_pattern_stl(mesh, path, scale)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        ticket = pattern_ticket(self.metal_combo.currentText(), self.shrink_slider.value())
        QMessageBox.information(self, "Pattern STL", f"Saved:\n{path}\n\n{ticket['hint']}")

    def _on_keep_a(self) -> None:
        if not self._last_result:
            QMessageBox.information(self, "Compare", "Run a simulation first.")
            return
        self._baseline_result = dict(self._last_result)
        self._baseline_result.pop("voxel_faces", None)
        label = self._last_result.get("setup_label", "A")
        self.compare_label.setText(f"A stored: {label}. Change setup and simulate for B.")

    def _on_clear_a(self) -> None:
        self._baseline_result = None
        self.compare_label.setText("")

    def _on_overlay_combo(self) -> None:
        mode = self.overlay_combo.currentData() or ""
        if mode:
            self.draft_cb.blockSignals(True)
            self.undercut_cb.blockSignals(True)
            self.hotspot_cb.blockSignals(True)
            self.draft_cb.setChecked(False)
            self.undercut_cb.setChecked(False)
            self.hotspot_cb.setChecked(mode == "hotspot")
            self.draft_cb.blockSignals(False)
            self.undercut_cb.blockSignals(False)
            self.hotspot_cb.blockSignals(False)
            self.viewport.set_overlay_mode(str(mode))
            self.inspect_label.setText({
                "hotspot": "Thick sections (red) freeze last — that is the hot spot.",
                "freeze": "Last-to-freeze from the voxel thermal pass.",
                "fill": "Gravity-flood fill order from the gate.",
                "porosity": "Isolated liquid — shrinkage cavities.",
                "niyama": "Low Niyama (dark) → shrinkage risk.",
            }.get(str(mode), ""))
        else:
            self._on_inspect()

    def _on_clip_changed(self, *_args) -> None:
        self.clip_label.setText(f"Cut: {self.clip_slider.value()}%")
        self.viewport.set_clip(
            self.clip_cb.isChecked(),
            axis=self.clip_axis_combo.currentIndex(),
            frac=self.clip_slider.value() / 100.0,
        )

    def _on_pick_parting(self) -> None:
        self.viewport.pick_mode = "parting"
        self.parting_label.setText("Click the viewport to set parting height…")

    def _on_parting_picked(self, frac: float) -> None:
        self.parting_slider.setValue(int(round(frac * 100)))

    def _on_parting_changed(self, val: int) -> None:
        self.viewport.set_parting(val / 100.0)
        self.parting_label.setText(f"Position: {val}%")

    def _on_pour_changed(self, val: int) -> None:
        self.pour_temp_label.setText(f"Pour temp: {val} °F")

    def _update_pour_band(self) -> None:
        metal = METAL_DEFAULTS[self.metal_combo.currentText()]
        lo, hi = recommended_pour_band(metal)
        self.pour_band_label.setText(f"Recommended {lo}–{hi} °F")

    def _on_metal_changed(self, index: int) -> None:
        metal_name = self.metal_combo.currentText()
        metal = METAL_DEFAULTS[metal_name]
        self.pour_spin.setValue(metal["pour_temp_f"])
        shrink_slider = min(self.shrink_slider.maximum(), 100 + int(round(metal["shrinkage_pct"])))
        self.shrink_slider.setValue(shrink_slider)
        self.viewport.set_active_metal(metal_name)
        self._update_pour_band()
        self._on_shrink(self.shrink_slider.value())
        if self._is_shell():
            self.mold_spin.setValue(recommended_shell_preheat_f(metal_name))
        self._sync_process_ui(set_preheat=False)
        self._refresh_status()

    def _is_shell(self) -> bool:
        return bool(self.shell_btn.isChecked())

    def _set_process(self, kind: str) -> None:
        sand = kind != "shell"
        self.sand_btn.blockSignals(True)
        self.shell_btn.blockSignals(True)
        self.sand_btn.setChecked(sand)
        self.shell_btn.setChecked(not sand)
        self.sand_btn.blockSignals(False)
        self.shell_btn.blockSignals(False)
        self._sync_process_ui(set_preheat=True)
        self._refresh_status()

    def _on_mold_changed(self, _text: str = "") -> None:
        self._sync_process_ui(set_preheat=False)
        self._refresh_status()

    def _on_mold_temp_changed(self, val: int) -> None:
        if self._is_shell():
            self.mold_temp_label.setText(f"Shell preheat: {val} °F")
        else:
            self.mold_temp_label.setText(f"Mold temp: {val} °F")

    def _on_shell_mm_changed(self, val: int) -> None:
        self.shell_mm_label.setText(f"Fired shell: {val} mm")
        self.viewport.set_mold_process("shell", shell_mm=val)

    def _sync_process_ui(self, set_preheat: bool = False) -> None:
        shell = self._is_shell()
        metal_name = self.metal_combo.currentText()
        rec = recommended_shell_preheat_f(metal_name)
        self._flask_sand_box.setVisible(not shell)
        self._flask_shell_box.setVisible(shell)
        self.mold_combo.setVisible(not shell)
        self.sand_type_label.setVisible(not shell)
        self.flask_panel.setTitle("Ceramic shell" if shell else "Flask")
        self.preheat_band_label.setVisible(shell)
        if shell:
            self.mold_hint.setText(
                "Ceramic shell (investment / lost-wax). Preheat the fired shell; skip the sand flask."
            )
            self.preheat_band_label.setText(f"Typical preheat ~{rec} °F for {metal_name}.")
            self.mold_spin.setRange(200, 2200)
            if set_preheat:
                self.mold_spin.setValue(rec)
            self.mold_temp_label.setText(f"Shell preheat: {self.mold_spin.value()} °F")
            self.parting_hint.setText(
                "Investment has no cope/drag split — this plane is only the sprue/gate height."
            )
            self.pick_parting_btn.setToolTip("Click in the viewport to set sprue/gate height.")
            self.undercut_cb.setText("Undercut overlay (lost-wax: wax melts out)")
            self.draft_cb.setText("Draft overlay (wax die — optional)")
            self.viewport.set_mold_process("shell", shell_mm=self.shell_mm_slider.value())
            self.flask_panel.setExpanded(True)
        else:
            self.mold_hint.setText("")
            self.mold_spin.setRange(32, 400)
            if set_preheat:
                self.mold_spin.setValue(100)
            self.mold_temp_label.setText(f"Mold temp: {self.mold_spin.value()} °F")
            self.parting_hint.setText("")
            self.pick_parting_btn.setToolTip("Click in the viewport to set the cope/drag split height.")
            self.undercut_cb.setText("Undercut / core-print overlay")
            self.draft_cb.setText("Draft overlay (red = lock)")
            self.viewport.set_mold_process("sand")
            self._refresh_flask_fit()

    def _on_shrink(self, val: int) -> None:
        pct = METAL_DEFAULTS[self.metal_combo.currentText()]["shrinkage_pct"]
        scale = shrink_scale_from_slider(val)
        self.shrink_label.setText(f"Shrinkage: {pct}%  ·  scale ×{scale:.3f}")
        self.viewport.set_shrink_scale(scale)

    def _on_flask_changed(self, text: str) -> None:
        size = self._flask_presets.get(text, (8, 10))
        self.viewport.set_flask(size, height_in=self.flask_h_slider.value())
        self._refresh_flask_fit()

    def _on_flask_height_changed(self, val: int) -> None:
        self.flask_h_label.setText(f"Stack height: {val} in")
        size = self._flask_presets.get(self.flask_combo.currentText(), (8, 10))
        self.viewport.set_flask(size, height_in=val)

    def _current_flask_fit(self) -> dict:
        xmin, xmax, ymin, ymax, zmin, zmax = self.viewport._compute_bounds()
        size = self._flask_presets.get(self.flask_combo.currentText(), (8, 10))
        return flask_fit(xmin, xmax, ymin, ymax, float(size[0]), float(size[1]),
                         presets=self._flask_presets)

    def _refresh_flask_fit(self) -> None:
        info = self._current_flask_fit()
        if not self.viewport.models:
            self.flask_fit_label.setText("")
            return
        if info["fits"]:
            self.flask_fit_label.setText(
                f"Clears the part ({info['need_w_in']:.1f} × {info['need_d_in']:.1f} in needed)."
            )
        else:
            sug = info["suggested"] or "a custom flask"
            self.flask_fit_label.setText(
                f"Too small — need {info['need_w_in']:.1f} × {info['need_d_in']:.1f} in. Try {sug}."
            )

    def _on_auto_flask(self) -> None:
        info = self._current_flask_fit()
        if info["suggested"]:
            self.flask_combo.setCurrentText(info["suggested"])
        else:
            QMessageBox.information(self, "Flask", "No preset is large enough — add a custom flask.")

    def _on_add_flask_preset(self):
        text, ok = QInputDialog.getText(
            self, "Add Custom Flask",
            "name, width_in, depth_in[, height_in]\ne.g. 10x12x8, 10, 12, 8",
        )
        if ok and text:
            try:
                parts = [p for p in text.replace(" ", "").split(",") if p]
                name, width, height = parts[0], float(parts[1]), float(parts[2])
                preset = (width, height)
                if len(parts) >= 4:
                    self.flask_h_slider.setValue(int(round(float(parts[3]))))
                    preset = (width, height, float(parts[3]))
                self._flask_presets[name] = preset
                self.flask_combo.addItem(name)
                self.flask_combo.setCurrentText(name)
            except Exception as e:
                QMessageBox.warning(self, "Error", "Invalid format: " + str(e))

    def _on_inspect(self) -> None:
        if self.hotspot_cb.isChecked():
            self.draft_cb.blockSignals(True)
            self.undercut_cb.blockSignals(True)
            self.draft_cb.setChecked(False)
            self.undercut_cb.setChecked(False)
            self.draft_cb.blockSignals(False)
            self.undercut_cb.blockSignals(False)
            self.overlay_combo.blockSignals(True)
            idx = self.overlay_combo.findData("hotspot")
            if idx >= 0:
                self.overlay_combo.setCurrentIndex(idx)
            self.overlay_combo.blockSignals(False)
            self.viewport.set_overlay_mode("hotspot")
            self.inspect_label.setText(
                "Thick sections (red) freeze last — 80% of what people use Niyama for."
            )
            return
        if self.draft_cb.isChecked():
            self.undercut_cb.blockSignals(True)
            self.hotspot_cb.blockSignals(True)
            self.undercut_cb.setChecked(False)
            self.hotspot_cb.setChecked(False)
            self.undercut_cb.blockSignals(False)
            self.hotspot_cb.blockSignals(False)
            self.viewport.set_overlay_mode("draft")
            mesh = self.viewport.world_meshes()
            if mesh is not None:
                min_deg = 0.5 if self._is_shell() else 1.5
                d = draft_analysis(mesh, min_deg=min_deg)
                kind = "wax-die draft" if self._is_shell() else "sand draft"
                self.inspect_label.setText(
                    f"{d['lock_count']} faces below {min_deg:.1f}° {kind} "
                    f"({100 * d['lock_frac']:.0f}% of the surface)."
                )
            return
        if self.undercut_cb.isChecked():
            self.hotspot_cb.blockSignals(True)
            self.hotspot_cb.setChecked(False)
            self.hotspot_cb.blockSignals(False)
            self.viewport.set_overlay_mode("undercut")
            mesh = self.viewport.world_meshes()
            if mesh is not None:
                xmin, xmax, ymin, ymax, zmin, zmax = self.viewport._compute_bounds()
                z_part = zmin + max(zmax - zmin, 1.0) * self.viewport.parting_z
                u = undercut_hints(mesh, z_part)
                if self._is_shell():
                    self.inspect_label.setText(
                        f"{u['count']} faces would undercut a two-part sand mold "
                        f"({100 * u['frac']:.0f}%). Lost-wax: wax melts out — cores only if hollow."
                    )
                else:
                    self.inspect_label.setText(
                        f"{u['count']} faces look like undercuts / core prints "
                        f"({100 * u['frac']:.0f}% of the surface)."
                    )
            return
        self.overlay_combo.blockSignals(True)
        self.overlay_combo.setCurrentIndex(0)
        self.overlay_combo.blockSignals(False)
        self.viewport.set_overlay_mode("")
        self.inspect_label.setText("")

    # ------------------------------------------------------------------
    # File / session
    # ------------------------------------------------------------------

    def _set_stl_label(self, title: str, stats: dict) -> None:
        extra = ""
        warn = stats.get("mesh_warnings") or []
        if warn:
            extra += "\n⚠ " + " ".join(warn)
        if stats.get("thin_wall_auto"):
            extra += f"\nThin wall: min {stats.get('min_wall_mm', 0):.1f} mm"
        self.stl_label.setText(
            f"{title}\nVolume: {stats['vol_cm3']:.2f} cm³   Surface: {stats['surf_cm2']:.2f} cm²"
            f"{extra}"
        )

    def _on_load_stl(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open part", "",
            "Mesh files (*.stl *.obj);;STL (*.stl);;OBJ (*.obj);;All files (*)",
        )
        if filename:
            self._load_stl_path(filename)

    def _import_scale(self) -> float:
        data = self.units_combo.currentData()
        try:
            return float(data)
        except (TypeError, ValueError):
            return 1.0

    def _enable_simulate(self, on: bool) -> None:
        self.sim_btn.setEnabled(on)
        self.sim_btn.setToolTip("" if on else "Load a part first.")

    def _load_stl_path(self, filename: str) -> None:
        try:
            stats = self.viewport.load_stl(filename, scale=self._import_scale())
            self._geometry_stats = stats
            self._stl_path = filename
            self._is_demo = False
            self._set_stl_label(f"{Path(filename).name}", stats)
            remember_project(filename)
            self._refresh_recents()
            self._refresh_flask_fit()
            self._enable_simulate(True)
            self._refresh_status()
            if stats.get("mesh_warnings"):
                QMessageBox.warning(
                    self, "Mesh quality",
                    "This mesh may not be a closed solid:\n\n" + "\n".join(stats["mesh_warnings"]),
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open part:\n{str(e)}")

    def _on_load_demo(self) -> None:
        self._on_reset()
        self.viewport.clear_scene()
        triangles, normals, stats = build_demo_mesh()
        self.viewport.models[DEMO_PART_NAME] = {
            "render_data": triangles,
            "normals": normals,
            "mesh": None,
            "thickness": local_thickness(triangles),
        }
        self.viewport.transforms[DEMO_PART_NAME] = {
            "offset": np.array([0.0, 0.0, 0.0]),
            "rotation": 0.0,
        }
        self.viewport.active_model = DEMO_PART_NAME
        self._geometry_stats = stats
        thick = self.viewport.models[DEMO_PART_NAME]["thickness"]
        min_w = float(np.min(thick)) if len(thick) else 999.0
        self._geometry_stats["min_wall_mm"] = min_w
        self._geometry_stats["thin_wall_auto"] = min_w < THIN_WALL_MM
        self._stl_path = None
        self._is_demo = True
        self.flask_combo.setCurrentText("10 x 12")
        self.metal_combo.setCurrentText("A356 Aluminum")
        self.pour_spin.setValue(1160)
        self.thin_combo.setCurrentText("Yes")
        self.parting_slider.setValue(39)
        for name in ["Tapered Sprue", "Runner (Horizontal)", "Fan Gate", "Riser (Open)"]:
            self.gating_checkboxes[name].setChecked(True)
        self.sprue_x_slider.setValue(100)
        self.sprue_y_slider.setValue(100)
        self.riser_x_slider.setValue(-80)
        self.riser_y_slider.setValue(70)
        self._set_stl_label("Demo: Motor Mount Bracket", stats)
        self.stl_label.setText(self.stl_label.text() + "\nHeight: 102 mm — 7 primitives")
        self.viewport.render()
        self.viewport.fit_view()
        self._refresh_flask_fit()
        self._enable_simulate(True)
        self._refresh_status()

    def _collect_session(self) -> dict:
        data = default_session()
        data.update({
            "stl_path": self._stl_path,
            "demo": self._is_demo,
            "metal": self.metal_combo.currentText(),
            "pour_temp_f": self.pour_spin.value(),
            "mold_temp_f": self.mold_spin.value(),
            "mold_type": CERAMIC_SHELL if self._is_shell() else self.mold_combo.currentText(),
            "shell_mm": self.shell_mm_slider.value(),
            "thin_wall": self.thin_combo.currentText(),
            "parting_pct": self.parting_slider.value(),
            "flask": self.flask_combo.currentText(),
            "flask_height_in": self.flask_h_slider.value(),
            "gating": [k for k, v in self.gating_checkboxes.items() if v.isChecked()],
            "sprue_top_r": self.sprue_top_slider.value(),
            "sprue_bot_r": self.sprue_bot_slider.value(),
            "sprue_height": self.sprue_h_slider.value(),
            "runner_width": self.runner_w_slider.value(),
            "runner_height": self.runner_h_slider.value(),
            "gate_area": self.gate_area_slider.value(),
            "sprue_x": self.sprue_x_slider.value(),
            "sprue_y": self.sprue_y_slider.value(),
            "riser_x": self.riser_x_slider.value(),
            "riser_y": self.riser_y_slider.value(),
            "model_x": self.x_slider.value(),
            "model_y": self.y_slider.value(),
            "model_z": self.z_slider.value(),
            "model_rot": self.rot_slider.value(),
            "shrink_slider": self.shrink_slider.value(),
            "gating_ratio": self.ratio_combo.currentText(),
        })
        return data

    def _apply_session(self, data: dict, load_mesh: bool = True) -> None:
        if load_mesh:
            if data.get("demo"):
                self._on_load_demo()
            elif data.get("stl_path") and Path(data["stl_path"]).exists():
                self._load_stl_path(data["stl_path"])
        if data.get("metal"):
            self.metal_combo.blockSignals(True)
            self.metal_combo.setCurrentText(data["metal"])
            self.metal_combo.blockSignals(False)
            self.viewport.set_active_metal(data["metal"])
            self._update_pour_band()
        self.mold_combo.blockSignals(True)
        mold = data.get("mold_type") or "Green sand"
        if is_shell_mold(mold):
            self.sand_btn.setChecked(False)
            self.shell_btn.setChecked(True)
        else:
            self.sand_btn.setChecked(True)
            self.shell_btn.setChecked(False)
            if mold in self._sand_molds:
                self.mold_combo.setCurrentText(mold)
        self.mold_combo.blockSignals(False)
        self.shell_mm_slider.blockSignals(True)
        self.shell_mm_slider.setValue(int(data.get("shell_mm", DEFAULT_SHELL_MM)))
        self.shell_mm_slider.blockSignals(False)
        self._sync_process_ui(set_preheat=False)
        self.pour_spin.setValue(int(data.get("pour_temp_f", 1300)))
        self.mold_spin.setValue(int(data.get("mold_temp_f", 100)))
        self._on_mold_temp_changed(self.mold_spin.value())
        if data.get("thin_wall"):
            self.thin_combo.setCurrentText(data["thin_wall"])
        self.parting_slider.setValue(int(data.get("parting_pct", 50)))
        if data.get("flask"):
            self.flask_combo.setCurrentText(data["flask"])
        self.flask_h_slider.setValue(int(data.get("flask_height_in", 6)))
        for name, cb in self.gating_checkboxes.items():
            cb.setChecked(name in (data.get("gating") or []))
        self.sprue_top_slider.setValue(int(data.get("sprue_top_r", 8)))
        self.sprue_bot_slider.setValue(int(data.get("sprue_bot_r", 4)))
        self.sprue_h_slider.setValue(int(data.get("sprue_height", 100)))
        self.runner_w_slider.setValue(int(data.get("runner_width", 10)))
        self.runner_h_slider.setValue(int(data.get("runner_height", 8)))
        self.gate_area_slider.setValue(int(data.get("gate_area", 40)))
        self.sprue_x_slider.setValue(int(data.get("sprue_x", 0)))
        self.sprue_y_slider.setValue(int(data.get("sprue_y", 0)))
        self.riser_x_slider.setValue(int(data.get("riser_x", 0)))
        self.riser_y_slider.setValue(int(data.get("riser_y", 0)))
        self.x_slider.setValue(int(data.get("model_x", 0)))
        self.y_slider.setValue(int(data.get("model_y", 0)))
        self.z_slider.setValue(int(data.get("model_z", 0)))
        self.rot_slider.setValue(int(data.get("model_rot", 0)))
        self.shrink_slider.setValue(int(data.get("shrink_slider", 106)))
        if data.get("gating_ratio"):
            self.ratio_combo.setCurrentText(data["gating_ratio"])
        self._enable_simulate(bool(self.viewport.models or data.get("demo")))
        self._refresh_status()

    def _on_save_session(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save casting session", "job.cast.json", "Casting session (*.cast.json *.json)",
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".cast.json"
        save_session(path, self._collect_session())
        remember_project(path)
        self._refresh_recents()
        QMessageBox.information(self, "Saved", path)

    def _on_open_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open casting session", "", "Casting session (*.cast.json *.json);;All (*)",
        )
        if path:
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        p = Path(path)
        if p.suffix.lower() in {".stl", ".obj"}:
            self._load_stl_path(path)
            return
        try:
            data = load_session(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self._apply_session(data)
        remember_project(path)
        self._refresh_recents()

    def _refresh_recents(self) -> None:
        self.recent_list.clear()
        for path in recent_projects():
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.recent_list.addItem(item)

    def _on_recent_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._open_path(path)

    def _push_undo(self) -> None:
        self._undo_stack.append(self._collect_session())
        self._undo_stack = self._undo_stack[-40:]

    def _on_undo(self) -> None:
        if not self._undo_stack:
            return
        data = self._undo_stack.pop()
        self._apply_session(data, load_mesh=False)

    # ------------------------------------------------------------------
    # Simulate
    # ------------------------------------------------------------------

    def _thin_wall_flag(self) -> bool:
        mode = self.thin_combo.currentText()
        if mode == "Yes":
            return True
        if mode == "No":
            return False
        if "thin_wall_auto" not in self._geometry_stats and self.viewport.models:
            chunks = [data["render_data"] for data in self.viewport.models.values()]
            thick = local_thickness(np.concatenate(chunks, axis=0))
            min_w = float(np.min(thick)) if len(thick) else 999.0
            self._geometry_stats["min_wall_mm"] = min_w
            self._geometry_stats["thin_wall_auto"] = min_w < THIN_WALL_MM
        return bool(self._geometry_stats.get("thin_wall_auto"))

    def _on_simulate(self) -> None:
        metal_name = self.metal_combo.currentText()
        metal_params = METAL_DEFAULTS[metal_name]
        scale = shrink_scale_from_slider(self.shrink_slider.value())
        vol, surf, z_max = scale_geometry(
            self._geometry_stats.get("vol_cm3", 100.0),
            self._geometry_stats.get("surf_cm2", 120.0),
            self._geometry_stats.get("z_max", 100.0),
            scale,
        )
        params = {
            "metal": metal_name,
            "pour_temp_f": self.pour_spin.value(),
            "mold_temp_f": self.mold_spin.value(),
            "mold_type": CERAMIC_SHELL if self._is_shell() else self.mold_combo.currentText(),
            "shell_mm": self.shell_mm_slider.value(),
            "thin_wall": self._thin_wall_flag(),
            "shrinkage": metal_params["shrinkage_pct"],
            "gate_types": [n for n, cb in self.gating_checkboxes.items() if cb.isChecked()],
            "vol_cm3": vol,
            "surf_cm2": surf,
            "has_riser": "Riser (Open)" in self.viewport.gating,
            "gating_params": self.viewport.get_gating_params(),
            "runner_y_offset": self.viewport.runner_y_offset,
            "shrink_scale": scale,
            "z_max": z_max,
            "flask_fit": {} if self._is_shell() else self._current_flask_fit(),
        }
        mesh = self.viewport.world_meshes()
        if mesh is not None:
            params["mesh_vectors"] = mesh
        gp = params["gating_params"]
        xmin, xmax, ymin, ymax, zmin, zmax = self.viewport._compute_bounds()
        z_part = zmin + max(zmax - zmin, 1.0) * self.viewport.parting_z
        params["gate_xyz"] = self.viewport._gate_xyz()
        params["sprue_xyz"] = np.array(
            [float(self.viewport.sprue_offset[0]), float(self.viewport.sprue_offset[1]), z_part]
        )
        params["riser_xyz"] = np.array(
            [float(self.viewport.riser_offset[0]), float(self.viewport.riser_offset[1]), z_part]
        ) if gp.get("has_riser") else None
        params["chills_xyz"] = list(self.viewport.chills)
        params["sleeve"] = self.sleeve_cb.isChecked()
        params["setup_label"] = (
            f"{'shell' if self._is_shell() else self.mold_combo.currentText()} · {metal_name}"
        )
        self.progress_bar.setVisible(True)
        self.sim_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self._sim_thread = QThread()
        self._sim_worker = SimWorker(params)
        self._sim_worker.moveToThread(self._sim_thread)
        self._sim_worker.progress.connect(self._on_sim_progress)
        self._sim_worker.finished.connect(self._on_sim_done)
        self._sim_worker.finished.connect(self._sim_thread.quit)
        self._sim_worker.finished.connect(self._sim_worker.deleteLater)
        self._sim_thread.finished.connect(self._sim_thread.deleteLater)
        self._sim_thread.started.connect(self._sim_worker.run)
        self._sim_thread.start()

    def _on_sim_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setFormat(f"{msg} {int(pct)}%")
        self.progress_bar.setValue(int(pct))

    def _on_sim_done(self, result: dict) -> None:
        self.progress_bar.setVisible(False)
        self._enable_simulate(bool(self.viewport.models))
        self.reset_btn.setEnabled(True)
        if not result:
            self.results_text.setHtml(
                "<p style='color:#F38BA8;'>Simulation failed or was cancelled.</p>"
            )
            return
        self._last_result = result
        faces = result.get("voxel_faces") or {}
        self.viewport.set_sim_fields(faces)
        if self._baseline_result is not None:
            result["compare"] = compare_setups(self._baseline_result, result)
        self.results_text.setHtml(build_results_text(result))
        self.viewport.set_restrictive(result.get("restrictive_elem") or "")
        defects = result.get("defects", [])
        warnings = result.get("warnings", [])
        sites = self.viewport.defect_sites()
        decorated = []

        def _site(kind: str):
            xyz = sites.get(kind) or (0.0, 0.0, result.get("z_max", 100))
            return (kind, float(xyz[0]), float(xyz[1]), float(xyz[2]))

        for d in defects:
            if isinstance(d, tuple):
                decorated.append(d)
            elif "shrinkage" in d.lower() or "porosity" in d.lower():
                decorated.append(_site("shrinkage_risk"))
            elif "cold" in d.lower():
                decorated.append(_site("cold_shut_risk"))
            elif "misrun" in d.lower():
                decorated.append(_site("misrun_risk"))
        for w in warnings:
            if "porosity" in w.lower() or "shrinkage" in w.lower() or "riser" in w.lower():
                decorated.append(_site("shrinkage_risk"))
        duration = max(2.0, min(8.0, result.get("fill_time_s", 3.0)))
        vsr = result.get("vsr", 1.0)
        self.viewport.start_fill_animation(
            duration_s=duration,
            fill_s=result.get("fill_time_s", duration),
            solidify_min=result.get("t_solidify_min", 3.0),
            on_done=lambda: self.viewport.draw_defect_markers(decorated, vsr),
        )

    def _on_result_anchor(self, url: QUrl) -> None:
        kind = url.toString()
        if kind.startswith("defect:"):
            kind = kind.split(":", 1)[1]
        sites = self.viewport.defect_sites()
        xyz = sites.get(kind)
        if xyz:
            self.viewport.look_at(*xyz)
            return
        gp = self.viewport.get_gating_params()
        xmin, xmax, ymin, ymax, zmin, zmax = self.viewport._compute_bounds()
        z_part = zmin + max(zmax - zmin, 1.0) * self.viewport.parting_z
        from simulation.foundry import choke_location
        loc = choke_location(
            self.viewport.restrictive_elem or "sprue_exit",
            (float(self.viewport.sprue_offset[0]), float(self.viewport.sprue_offset[1])),
            (float(self.viewport.riser_offset[0]), float(self.viewport.riser_offset[1])),
            z_part, zmax,
        )
        if loc:
            self.viewport.look_at(*loc)

    def _on_reset(self) -> None:
        self.viewport.reset_anim()
        metal = METAL_DEFAULTS[self.metal_combo.currentText()]
        self.pour_spin.setValue(metal["pour_temp_f"])
        if self._is_shell():
            self.mold_spin.setValue(recommended_shell_preheat_f(self.metal_combo.currentText()))
        else:
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
        self.shrink_slider.setValue(min(110, 100 + int(round(metal["shrinkage_pct"]))))
        for cb in self.gating_checkboxes.values():
            cb.setChecked(False)
        self.results_text.setHtml(empty_results_html())
        self._last_result = None
        self.viewport.set_restrictive("")
        self.viewport.set_sim_fields({})
        self.viewport.chills = []
        self.as_cast_cb.setChecked(False)
        self.draft_cb.setChecked(False)
        self.undercut_cb.setChecked(False)
        self.hotspot_cb.setChecked(False)
        self.clip_cb.setChecked(False)
        self.sleeve_cb.setChecked(False)
        self.overlay_combo.setCurrentIndex(0)

    def _on_export(self) -> None:
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
            else:
                if not lower.endswith(".html"):
                    path += ".html"
                Path(path).write_text(html, encoding="utf-8")
                try:
                    self.viewport.screenshot(path.rsplit(".", 1)[0] + ".png")
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        QMessageBox.information(self, "Export", f"Saved:\n{path}")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._open_path(path)
                break

    def _refresh_status(self) -> None:
        if self._is_demo:
            part = "Demo bracket"
        elif self._stl_path:
            part = Path(self._stl_path).name
        elif self.viewport.models:
            part = self.viewport.active_model or "Part"
        else:
            part = "No part"
        metal = self.metal_combo.currentText()
        proc = "Ceramic shell" if self._is_shell() else self.mold_combo.currentText()
        self._status.setText(f"{part}    ·    {metal}    ·    {proc}")

    def closeEvent(self, event) -> None:
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
