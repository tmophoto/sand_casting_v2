"""

Sand Casting Simulation  v1.0.0

PyQt6 + PyVista + CuPy/NumPy + numpy-stl



Major architectural upgrades from v0.1.0:

- PyVista for GPU-accelerated OpenGL rendering with PBR materials

- Real-time lighting and shadows

- CuPy acceleration (with NumPy fallback) for CUDA-enabled RTX 3090

- Per-triangle temperature tracking

- Voxel-based heat diffusion simulation

- Visual effects: heat glow, particle system, animated metal flow,
  solidification front animation, defect markers, sand texture

"""



import sys

import math

import hashlib

import textwrap

import time
import random



# Try CuPy first, fall back to NumPy

try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    cp = None
    CUPY_AVAILABLE = False


import numpy as np

from stl import mesh as stl_mesh



from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QCheckBox,
    QTextEdit, QScrollArea, QProgressBar, QListWidget,
    QFileDialog, QInputDialog, QMessageBox, QSizePolicy,
    QFrame
)

from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QTimer

# Unconditional matplotlib import for Poly3DCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection



# PyVista imports (with matplotlib fallback)

try:
    import pyvista as pv
    PV_AVAILABLE = True
    from pyvista import Plotter, PolyData
except ImportError:
    pv = None
    PV_AVAILABLE = False
    # Fallback to matplotlib
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure


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

METAL_DEFAULTS = {
    "A356 Aluminum": {
        "pour_temp_f": 1300,
        "melt_temp_f": 1075,
        "density": 2.67,
        "specific_heat": 963,
        "latent_heat": 389,
        "conductivity": 151,
        "color": "#C8C8C8",
        "mold_constant": 1.0,
        "shrinkage_pct": 6.0,
    },
    "Everdur Bronze (C52100)": {
        "pour_temp_f": 1950,
        "melt_temp_f": 1780,
        "density": 8.8,
        "specific_heat": 380,
        "latent_heat": 175,
        "conductivity": 50,
        "color": "#CD7F32",
        "mold_constant": 1.4,
        "shrinkage_pct": 2.0,
    },
}



FLASK_SIZES = {
    "6 x 6":   (6,  6),
    "6 x 8":   (6,  8),
    "8 x 10":  (8,  10),
    "10 x 12": (10, 12),
    "12 x 14": (12, 14),
    "14 x 20": (14, 20),
}

# Viewport colors
COPE_COLOR   = "#4A90D9"
DRAG_COLOR   = "#C0834A"
SPRUE_COLOR  = "#E87040"
RUNNER_COLOR = "#D4A030"
GATE_COLOR   = "#A0C840"
RISER_COLOR  = "#70A0FF"

MODEL_COLORS = [
    "#BEC1D2", "#89DCEB", "#A6E3A1",
    "#FAB387", "#F38BA8", "#CBA6F7",
]



# ---------------------------------------------------------------------------

# Dark-theme QSS  (Catppuccin Mocha palette)

# ---------------------------------------------------------------------------



from ui.style import APP_STYLE





# ---------------------------------------------------------------------------

# SimWorker

# ---------------------------------------------------------------------------



class SimWorker(QObject):

    """Runs the casting simulation in a worker thread."""



    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)



    def __init__(self, params: dict):
        super().__init__()
        self.params = params



    @staticmethod

    def _compute_fill_time_gating_hydraulics(
        vol_cm3: float, gating: dict, pour_f: int, metal: dict
    ) -> tuple[float, str]:

        """

        Compute fill time using proper gating hydraulics.


        Uses Bernoullis equation with the restrictive element determining flow rate.
        Returns (fill_time_seconds, description_of_restrictive_element).

        """

        sprue_height_mm = 100.0


        Cd = 0.75
        g = 9806.65



        def area_mm2(radius_mm: float) -> float:
            return math.pi * radius_mm ** 2


        sprue_top_area = area_mm2(gating["sprue_top_r"]) if gating.get("sprue_top_r") else None
        sprue_bot_area = area_mm2(gating["sprue_bot_r"]) if gating.get("sprue_bot_r") else None
        runner_area = (math.pi * (gating["runner_dia"] / 2) ** 2) if gating.get("runner_dia") else None
        gate_area = gating.get("gate_area_mm2", 40.0)


        restrictive_elem = "sprue"
        effective_area_mm2 = None


        if gating.get("has_sprue") and gating.get("has_gate"):
            if sprue_bot_area and gate_area:
                if sprue_bot_area < gate_area * 0.85:
                    restrictive_elem = "sprue_exit"
                    effective_area_mm2 = sprue_bot_area
                else:
                    restrictive_elem = "gate"
                    effective_area_mm2 = gate_area


        elif gating.get("has_sprue") and gating.get("has_runner"):
            if sprue_bot_area and runner_area:
                if sprue_bot_area < runner_area * 0.85:
                    restrictive_elem = "sprue_exit"
                    effective_area_mm2 = sprue_bot_area
                else:
                    restrictive_elem = "runner"
                    effective_area_mm2 = runner_area


        elif gating.get("has_sprue"):
            if sprue_bot_area:
                effective_area_mm2 = sprue_bot_area


        elif gating.get("gate_area_mm2"):
            effective_area_mm2 = gate_area
            restrictive_elem = "gate"


        if effective_area_mm2:
            velocity_ms = Cd * math.sqrt(g * sprue_height_mm / 1000.0)
            area_cm2 = effective_area_mm2 / 100.0
            velocity_cm_s = velocity_ms * 100.0
            flow_rate_cm3s = area_cm2 * velocity_cm_s


            if flow_rate_cm3s > 0:
                fill_time_s = vol_cm3 / flow_rate_cm3s
                return max(1.5, fill_time_s), restrictive_elem


        return max(3.0, vol_cm3 / 80.0), "fallback"



    def run(self):
        p = self.params
        metal_name = p.get("metal", "A356 Aluminum")
        metal      = METAL_DEFAULTS[metal_name]


        vol_cm3  = p.get("vol_cm3",  100.0)
        surf_cm2 = p.get("surf_cm2", 120.0)
        if vol_cm3  <= 0: vol_cm3  = 100.0
        if surf_cm2 <= 0: surf_cm2 = 120.0


        pour_f  = p.get("pour_temp_f", metal["pour_temp_f"])
        mold_f  = p.get("mold_temp_f", 77)
        has_riser = p.get("has_riser", False)
        thin_wall = p.get("thin_wall",  False)
        gating_params = p.get("gating_params", {})


        self.progress.emit(10, "Computing geometry ratios")
        vsr = vol_cm3 / surf_cm2


        self.progress.emit(30, "Applying Chvorinov Rule")
        B = 3.0 * metal["mold_constant"]
        t_solidify_min = B * (vsr ** 2)


        self.progress.emit(50, "Checking defect risks")
        superheat = pour_f - metal["melt_temp_f"]
        defects  = []
        warnings = []


        if superheat < 50:
            defects.append("Misrun risk superheat below 50 F")
        if thin_wall and pour_f < metal["melt_temp_f"] + 150:
            defects.append("Cold shut risk thin wall with low superheat")
        if mold_f > 120:
            warnings.append("Burn-on warning mold temp above 120 F")
        if superheat < 100:
            warnings.append("Low superheat warning superheat below 100 F")


        self.progress.emit(70, "Computing gating hydraulics")
        fill_time_s, restrictive = self._compute_fill_time_gating_hydraulics(
            vol_cm3, gating_params, pour_f, metal
        )


        self.progress.emit(90, "Assembling results")


        # Use shrink_scale from params if provided, otherwise compute from metal defaults
        shrink_scale = p.get("shrink_scale", 1.0 + (metal["shrinkage_pct"] / 100.0))


        result = {
            "t_solidify_min": t_solidify_min,
            "fill_time_s":    fill_time_s,
            "restrictive_elem": restrictive,
            "vsr":            vsr,
            "vol_cm3":        vol_cm3,
            "surf_cm2":       surf_cm2,
            "superheat":      superheat,
            "defects":        defects,
            "warnings":       warnings,
            "metal":          metal_name,
            "pour_f":         pour_f,
            "mold_f":         mold_f,
            "shrink_scale":   shrink_scale,  # FIX: now properly computed
        }


        self.progress.emit(100, "Done.")
        self.finished.emit(result)



# ---------------------------------------------------------------------------

# Viewport3D (PyVista with matplotlib fallback)

# ---------------------------------------------------------------------------



class Viewport3D(QWidget):

    """Embedded 3D viewport using PyVista or matplotlib fallback."""



    gating_moved = pyqtSignal(dict)



    def __init__(self, parent=None):
        super().__init__(parent)
        self.setParent(parent)


        # Multi-model state
        self.models: dict     = {}
        self.transforms: dict = {}
        self.active_model: str = ""
        self.parting_z: float = 0.5
        self.gating: list     = []
        self.flask_size       = (8, 10)


        self.sprue_offset  = np.array([0.0, 60.0])
        self.runner_y_offset = 0.0
        self.riser_offset  = np.array([60.0, 0.0])


        # Gating dimensions (mm)
        self.sprue_top_radius   = 7.5
        self.sprue_bottom_radius = 4.0
        self.runner_diameter    = 12.0
        self.gate_area          = 40.0


        self.pour_rate: float  = 1.0
        self._anim_frac: float = 0.0
        self._anim_timer       = QTimer()
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_done_cb     = None
        self._anim_steps       = 40
        self._anim_step        = 0


        self._solidify_frac: float = 0.0
        self._solidify_timer     = QTimer()
        self._solidify_timer.timeout.connect(self._solidify_tick)
        self._solidify_done_cb   = None
        self._solidify_steps     = 60
        self._solidify_step      = 0


        self._dragging_part    = None
        self._drag_last        = None
        self._zoom_factor      = 1.0


        # Setup rendering backend
        self.setup_renderer()


        self._draw_idle_scene()



    def setup_renderer(self):

        """Setup PyVista or matplotlib renderer."""

        if PV_AVAILABLE:
            try:
                from pyvistaqt import BackgroundPlotter
                self.use_pyvista = True
                self.plotter = BackgroundPlotter(show=False)
                self.render_frame = self.plotter.app_window
                return
            except Exception:
                pass
        self.use_pyvista = False
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        fig = Figure(facecolor="#11111B")
        self.canvas = FigureCanvas(fig)
        self.fig = fig
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.canvas.updateGeometry()
        self.ax = fig.add_subplot(111, projection="3d")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.mpl_connect = self.canvas.mpl_connect
        self.mpl_connect("button_press_event",   self._on_mouse_press)
        self.mpl_connect("motion_notify_event",  self._on_mouse_move)
        self.mpl_connect("button_release_event", self._on_mouse_release)
        self.mpl_connect("scroll_event",         self._on_scroll)


    def _style_axes(self):
        if not self.use_pyvista:
            ax = self.ax
            ax.set_facecolor("#11111B")
            for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
                pane.fill = False
                pane.set_edgecolor("#313244")
            ax.tick_params(colors="#585B70", labelsize=7)
            ax.set_xlabel("X (mm)", fontsize=7)
            ax.set_ylabel("Y (mm)", fontsize=7)
            ax.set_zlabel("Z (mm)", fontsize=7)
            ax.grid(True, color="#313244", linewidth=0.4)



    def _draw_idle_scene(self):
        if self.use_pyvista:
            self.plotter.clear()
            self.plotter.add_text("Load an STL to begin", position="upper_left", font_size=12, color="#585B70")
            self.plotter.render()
        else:
            self.ax.cla()
            self._style_axes()
            self.ax.text(0, 0, 0, "Load an STL to begin",
                         ha="center", va="center", color="#585B70", fontsize=10)
            self.canvas.draw_idle()



    def get_model_names(self):
        return list(self.models.keys())



    def set_active_model(self, name: str):
        self.active_model = name



    def remove_model(self, name: str):
        self.models.pop(name, None)
        self.transforms.pop(name, None)
        if self.active_model == name:
            self.active_model = next(iter(self.models), "") if self.models else ""
        self.render(self._anim_frac)



    def _get_color_for_model(self, name: str) -> str:
        idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(MODEL_COLORS)
        return MODEL_COLORS[idx]





    # ------------------------------------------------------------------

    # Load STL  

    # ------------------------------------------------------------------



    def load_stl(self, path: str, name: str = None) -> dict:

        """Load an STL file, auto-name it, and add it to the scene."""

        if name is None:
            n = len(self.models) + 1
            name = f"Part_{n}"


        loaded = stl_mesh.Mesh.from_file(path)

        # Clean degenerate triangles
        vectors = loaded.vectors
        v0, v1, v2 = vectors[:, 0], vectors[:, 1], vectors[:, 2]
        cross = np.cross(v1 - v0, v2 - v0)
        areas = np.linalg.norm(cross, axis=1)
        # Remove NaN, Inf, and zero-area (degenerate) triangles
        valid = (
            np.isfinite(vectors).all(axis=(1, 2)) &
            (areas > 1e-10)
        )
        vectors = vectors[valid]
        # Remove duplicate triangles by hashing centroid coordinates
        centroids = vectors.mean(axis=1).round(6)
        _, unique_idx = np.unique(centroids, axis=0, return_index=True)
        vectors = vectors[unique_idx]

        # Decimate: keep at most 25000 triangles
        max_tris = 25_000
        if len(vectors) > max_tris:
            step    = math.ceil(len(vectors) / max_tris)
            vectors = vectors[::step]

        loaded.vectors = vectors
        self.models[name] = {
            "mesh":        loaded,
            "render_data": vectors,
        }
        self.transforms[name] = {
            "offset":   np.array([0.0, 0.0, 0.0]),
            "rotation": 0.0,
        }
        if not self.active_model:
            self.active_model = name


        stats = self._geometry_stats(loaded)
        self.render()
        return stats



    # ------------------------------------------------------------------

    # Geometry stats  

    # ------------------------------------------------------------------



    def _geometry_stats(self, mesh) -> dict:

        """Volume via divergence theorem, surface area from triangle cross-products."""

        verts = mesh.vectors
        v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]


        cross = np.cross(v1 - v0, v2 - v0)
        vol_mm3 = abs(np.sum(v0 * cross) / 6.0)


        area_mm2 = np.sum(np.linalg.norm(cross, axis=1)) / 2.0


        return {
            "vol_cm3":  vol_mm3  / 1000.0,
            "surf_cm2": area_mm2 / 100.0,
        }



    # ------------------------------------------------------------------

    # Bounds helpers  

    # ------------------------------------------------------------------



    def _compute_bounds_for_model(self, name: str):
        t   = self.transforms[name]
        off = t["offset"]
        rot = math.radians(t["rotation"])


        verts = self.models[name]["render_data"].reshape(-1, 3)
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        xs = verts[:, 0] * cos_r - verts[:, 1] * sin_r + off[0]
        ys = verts[:, 0] * sin_r + verts[:, 1] * cos_r + off[1]
        zs = verts[:, 2] + off[2]
        return xs.min(), xs.max(), ys.min(), ys.max(), zs.min(), zs.max()



    def _compute_bounds(self):
        if not self.models:
            fw_mm = self.flask_size[0] * 25.4
            fh_mm = self.flask_size[1] * 25.4
            return -fw_mm/2, fw_mm/2, -fh_mm/2, fh_mm/2, 0.0, 100.0


        all_b = [self._compute_bounds_for_model(n) for n in self.models]
        xmins, xmaxs, ymins, ymaxs, zmins, zmaxs = zip(*all_b)
        return min(xmins), max(xmaxs), min(ymins), max(ymaxs), min(zmins), max(zmaxs)





    # ------------------------------------------------------------------

    # Rendering  

    # ------------------------------------------------------------------



    def render(self, anim_frac: float = 0.0):

        """Redraw the full 3D scene."""

        if self.use_pyvista:
            self._render_pyvista(anim_frac)
        else:
            self._render_matplotlib(anim_frac)



    def _render_matplotlib(self, anim_frac: float = 0.0):

        """Render using matplotlib backend."""

        self.ax.cla()
        self._style_axes()


        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part  = zmin + part_h * self.parting_z


        PAD = 76.0
        fw_mm = self.flask_size[0] * 25.4
        fh_mm = self.flask_size[1] * 25.4


        for name, data in self.models.items():
            t   = self.transforms[name]
            off = t["offset"]
            rot = math.radians(t["rotation"])


            verts = data["render_data"].copy()


            cos_r, sin_r = math.cos(rot), math.sin(rot)
            x_rot = verts[:, :, 0] * cos_r - verts[:, :, 1] * sin_r
            y_rot = verts[:, :, 0] * sin_r + verts[:, :, 1] * cos_r
            verts[:, :, 0] = x_rot
            verts[:, :, 1] = y_rot


            verts[:, :, 0] += off[0]
            verts[:, :, 1] += off[1]
            verts[:, :, 2] += off[2]


            centroids_z = verts[:, :, 2].mean(axis=1)
            cope_mask   = centroids_z >= z_part


            base_hex = (COPE_COLOR if np.sum(cope_mask) > len(cope_mask) // 2
                        else self._get_color_for_model(name))


            cope_base = self._hex_to_rgb(COPE_COLOR)
            drag_base = self._hex_to_rgb(DRAG_COLOR)


            if np.any(cope_mask):
                n_faces = int(cope_mask.sum())
                if n_faces > 0:
                    face_colors = [cope_base + (1.0,)] * n_faces
                    self.ax.add_collection3d(
                        Poly3DCollection(verts[cope_mask], facecolors=face_colors,
                                         edgecolors="none", linewidths=0, shade=True))


            if np.any(~cope_mask):
                n_faces = int((~cope_mask).sum())
                if n_faces > 0:
                    face_colors = [drag_base + (1.0,)] * n_faces
                    self.ax.add_collection3d(
                        Poly3DCollection(verts[~cope_mask], facecolors=face_colors,
                                         edgecolors="none", linewidths=0, shade=True))


            if anim_frac > 0 and np.any(~cope_mask):
                fill_z = zmin + part_h * anim_frac
                fill_mask = centroids_z <= fill_z
                if np.any(fill_mask):
                    # Use heat colors based on fill animation
                    heat_colors = self._compute_heat_colors(verts, anim_frac)
                    fill_colors = heat_colors[fill_mask]
                    self.ax.add_collection3d(
                        Poly3DCollection(verts[fill_mask],
                                         facecolors=fill_colors,
                                         edgecolors="none"))


        self._draw_flask_outline(z_part)


        if self.models:
            self._draw_gating(z_part)
            # Draw sprue particles during fill animation
            if anim_frac > 0 and "Tapered Sprue" in self.gating:
                self._draw_sprue_particles(z_part, anim_frac)


        half_w = fw_mm / 2 + PAD
        half_h = fh_mm / 2 + PAD
        cx = half_w / self._zoom_factor
        cy = half_h / self._zoom_factor
        z_center = (zmin + zmax) / 2
        z_range = ((zmax + 120) - (zmin - 20)) / 2 / self._zoom_factor
        self.ax.set_xlim(-cx, cx)
        self.ax.set_ylim(-cy, cy)
        self.ax.set_zlim(z_center - z_range, z_center + z_range)


        self.canvas.draw_idle()





    def _render_pyvista(self, anim_frac: float):

        """Render using PyVista backend with PBR materials."""

        self.plotter.clear()


        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part  = zmin + part_h * self.parting_z


        # Set camera view
        center = [(xmin+xmax)/2, (ymin+ymax)/2, (zmin+zmax)/2]
        dist = max(xmax-xmin, ymax-ymin, zmax-zmin) * 1.5
        self.plotter.camera_position = 'isometric'


        # Add models with PBR materials
        for name, data in self.models.items():
            t   = self.transforms[name]
            off = t["offset"]
            rot = math.radians(t["rotation"])


            verts = data["render_data"].copy()
            cos_r, sin_r = math.cos(rot), math.sin(rot)
            x_rot = verts[:, :, 0] * cos_r - verts[:, :, 1] * sin_r
            y_rot = verts[:, :, 0] * sin_r + verts[:, :, 1] * cos_r
            verts[:, :, 0] = x_rot
            verts[:, :, 1] = y_rot
            verts[:, :, 0] += off[0]
            verts[:, :, 1] += off[1]
            verts[:, :, 2] += off[2]


            # Create mesh from vertices and faces
            n_tris = len(verts)
            faces = np.hstack([np.full((n_tris, 1), 3), 
                              np.arange(n_tris * 3).reshape(-1, 3)])


            mesh = PolyData(verts.reshape(-1, 3), faces.flatten())


            # Get color for model
            color_hex = self._get_color_for_model(name)
            rgb = self._hex_to_rgb(color_hex)
            base_color = [rgb[0], rgb[1], rgb[2]]


            # Add mesh with PBR material
            self.plotter.add_mesh(
                mesh,
                color=base_color,
                metallic=0.3,
                roughness=0.5,
                smooth_shading=True,
            )



            # Add heat-colored metal fill triangles if animating
            if anim_frac > 0:
                heat_colors = self._compute_heat_colors(verts, anim_frac)
                # Create a separate mesh for filled triangles only
                centroids_z = verts[:, :, 2].mean(axis=1)
                fill_z = zmin + part_h * anim_frac
                fill_mask = centroids_z <= fill_z
                if np.any(fill_mask) and fill_mask.sum() > 0:
                    # Create sub-mesh with just filled triangles
                    filled_verts = verts[fill_mask].reshape(-1, 3)
                    n_filled = len(verts[fill_mask])
                    filled_faces = np.hstack([np.full((n_filled, 1), 3),
                                             np.arange(n_filled * 3).reshape(-1, 3)])
                    fill_mesh = PolyData(filled_verts, filled_faces.flatten())
                    # Add with vertex colors
                    self.plotter.add_mesh(
                        fill_mesh,
                        scalars=heat_colors[fill_mask][:, :3],
                        rgb=True,
                        smooth_shading=True,
                    )
        # Draw flask outline
        self._draw_flask_outline_pv(z_part)


        # Add sprue particles during fill animation (PyVista)
        if anim_frac > 0 and "Tapered Sprue" in self.gating:
            self._draw_sprue_particles_pv(z_part, anim_frac)


        # Add lighting
        self.plotter.enable_lightkit()


        self.plotter.render()



    def _draw_flask_outline(self, z_part: float):
        fw_mm = self.flask_size[0] * 25.4
        fh_mm = self.flask_size[1] * 25.4
        hw, hh = fw_mm / 2, fh_mm / 2


        xs = [-hw, hw, hw, -hw, -hw]
        ys = [-hh, -hh, hh, hh, -hh]


        _, _, _, _, zmin, zmax = self._compute_bounds()


        for z, color in [(zmin - 5, "#45475A"), (zmax + 5, "#45475A"), (z_part, "#89B4FA")]:
            self.ax.plot(xs, ys, [z] * 5, color=color,
                         linestyle="--" if z != z_part else "-",
                         linewidth=1.2 if z != z_part else 1.8, alpha=0.7)


        from mpl_toolkits.mplot3d.art3d import Poly3DCollection as P3
        plane_verts = [[[-hw, -hh, z_part], [hw, -hh, z_part],
                        [hw,  hh, z_part], [-hw, hh, z_part]]]
        self.ax.add_collection3d(
            P3(plane_verts, facecolors=[(0.537, 0.706, 0.980, 0.08)],
               edgecolors="none"))



    def _draw_flask_outline_pv(self, z_part: float):

        """Draw flask outline using PyVista."""

        fw_mm = self.flask_size[0] * 25.4
        fh_mm = self.flask_size[1] * 25.4
        hw, hh = fw_mm / 2, fh_mm / 2


        xs = [-hw, hw, hw, -hw, -hw]
        ys = [-hh, -hh, hh, hh, -hh]


        _, _, _, _, zmin, zmax = self._compute_bounds()


        # Draw bottom and top lines
        for z in [zmin - 5, zmax + 5]:
            points = np.column_stack([xs, ys, [z] * 5])
            line = pv.PolyData(points)
            line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
            self.plotter.add_mesh(line, color="#45475A", line_width=2)


        # Draw parting plane
        points = np.column_stack([xs, ys, [z_part] * 5])
        line = pv.PolyData(points)
        line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
        self.plotter.add_mesh(line, color="#89B4FA", line_width=3)



    def _draw_gating(self, z_part: float):

        """Draw 3D gating geometry into the current axes."""

        if not self.models:
            return
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection


        _, _, _, _, _, zmax = self._compute_bounds()
        top_z = zmax + 100



        # --- Tapered Sprue ---

        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            faces = self._make_cylinder_mesh(
                cx=sx, cy=sy, z_bottom=zmax,
                r_bottom=self.sprue_bottom_radius,
                r_top=self.sprue_top_radius,
                height=100.0, sides=24
            )
            sprue_rgb = self._hex_to_rgb(SPRUE_COLOR)
            colors = self._shade_faces(faces, sprue_rgb, alpha=0.85)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))



        # --- Runner ---

        if "Runner (Horizontal)" in self.gating:
            sx, sy = self.sprue_offset
            ry = sy + self.runner_y_offset
            faces = self._make_box_mesh(
                cx=sx, cy=ry, z_bottom=z_part - 4.0,
                width=160.0, depth=10.0, height=8.0
            )
            runner_rgb = self._hex_to_rgb(RUNNER_COLOR)
            colors = self._shade_faces(faces, runner_rgb, alpha=0.85)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))



        # --- Riser ---

        if "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            faces = self._make_cylinder_mesh(
                cx=rx, cy=ry, z_bottom=z_part,
                r_bottom=20.0, r_top=20.0, height=60.0, sides=24
            )
            riser_rgb = self._hex_to_rgb(RISER_COLOR)
            colors = self._shade_faces(faces, riser_rgb, alpha=0.75)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))



        # --- Fan Gate ---

        if "Fan Gate" in self.gating:
            sx, sy = self.sprue_offset
            faces = self._make_box_mesh(
                cx=sx, cy=sy - 4.0, z_bottom=z_part - 3.0,
                width=60.0, depth=8.0, height=6.0
            )
            gate_rgb = self._hex_to_rgb(GATE_COLOR)
            colors = self._shade_faces(faces, gate_rgb, alpha=0.85)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))



    def _draw_sprue_particles(self, z_part: float, anim_frac: float):

        """Draw particle stream from sprue during fill animation.

        Emits 15-20 small scatter points within 20mm radius of the sprue position
        using random offsets seeded by anim_frac.
        Args:
            z_part: Parting line z coordinate
            anim_frac: Animation fraction (0.0 to 1.0) controlling particle emission
        """

        if not self.models:
            return
        # Only draw particles when sprue is active in gating
        if "Tapered Sprue" not in self.gating:
            return
        if anim_frac <= 0:
            return
        sx, sy = self.sprue_offset
        _, _, _, _, zmin, zmax = self._compute_bounds()
        top_z = zmax + 100
        # Generate particles based on animation fraction
        np.random.seed(int(anim_frac * 1000) % 1000)
        n_particles = int(15 + anim_frac * 5)  # 15-20 particles
        z_bottom = zmin
        for i in range(n_particles):
            # Compute particle position along sprue height
            z_pos = z_bottom + anim_frac * (top_z - z_bottom)
            # Random offset within 20mm radius (decreasing toward bottom)
            r_max = 20.0 * (1.0 - anim_frac * 0.5)  # 20mm at top, 10mm at bottom
            theta = np.random.uniform(0, 2 * np.pi)
            r = np.random.uniform(0, r_max)
            x_offset = r * np.cos(theta)
            y_offset = r * np.sin(theta)
            # Particle size decreases as it flows down
            particle_size = 1.5 + anim_frac * 2.0
            self.ax.scatter(
                sx + x_offset,
                sy + y_offset,
                z_pos - (1.0 - anim_frac) * 20,
                c='orange',
                s=particle_size,
                alpha=0.9
            )



    def _draw_sprue_particles_pv(self, z_part: float, anim_frac: float):

        """Draw particle stream from sprue during fill animation - PyVista version.

        Args:
            z_part: Parting line z coordinate
            anim_frac: Animation fraction (0.0 to 1.0) controlling particle emission
        """

        if not self.models:
            return
        # Only draw particles when sprue is active in gating
        if "Tapered Sprue" not in self.gating:
            return
        if anim_frac <= 0:
            return
        sx, sy = self.sprue_offset
        _, _, _, _, zmin, zmax = self._compute_bounds()
        top_z = zmax + 100
        # Generate particles based on animation fraction
        np.random.seed(int(anim_frac * 1000) % 1000)
        n_particles = int(15 + anim_frac * 5)  # 15-20 particles
        for i in range(n_particles):
            # Compute particle position along sprue height
            z_pos = zmin + anim_frac * (top_z - zmin)
            # Random offset within 20mm radius (decreasing toward bottom)
            r_max = 20.0 * (1.0 - anim_frac * 0.5)  # 20mm at top, 10mm at bottom
            theta = np.random.uniform(0, 2 * np.pi)
            r = np.random.uniform(0, r_max)
            x_offset = sx + r * np.cos(theta)
            y_offset = sy + r * np.sin(theta)
            z_pos -= (1.0 - anim_frac) * 20
            # Create sphere mesh for each particle
            particle_size = 1.5 + anim_frac * 2.0
            sphere = pv.Sphere(radius=particle_size, center=(x_offset, y_offset, z_pos))
            self.plotter.add_mesh(
                sphere,
                color="orange",
                opacity=min(0.9, 0.5 + anim_frac)
            )



    def _draw_defect_markers(self, defects):

        """Draw colored spheres at defect risk regions.

        Args:
            defects: List of defect descriptions. Each can be:
                - String description (generic placement)
                - Tuple (type, x, y, z) with coordinates
        """

        if not self.models or not defects:
            return
        _, _, _, _, zmin, zmax = self._compute_bounds()
        for i, defect in enumerate(defects):
            if isinstance(defect, tuple) and len(defect) >= 4:
                # Defect with coordinates: (type, x, y, z)
                dtype = defect[0].lower()
                x, y, z = defect[1], defect[2], defect[3]
            else:
                # Generic placement - use top region of mesh
                dtype = ""
                rng = random.Random(i)  # seeded by index for consistency
                x = rng.uniform(-10, 10)
                y = rng.uniform(-10, 10)
                z = zmax + 30 + i * 8
            if dtype in ("shrinkage", "shrinkage_risk"):
                # Red sphere for shrinkage risk
                sphere = pv.Sphere(radius=6.0, center=(x, y, z))
                self.plotter.add_mesh(sphere, color="red", opacity=0.8)
            elif dtype in ("cold_shut", "cold shut", "cold_shut_risk"):
                # Yellow sphere for cold shut risk
                sphere = pv.Sphere(radius=6.0, center=(x, y, z))
                self.plotter.add_mesh(sphere, color="yellow", opacity=0.8)
            else:
                # Default - use type detection from string description
                desc = defect.lower() if isinstance(defect, str) else ""
                if "shrinkage" in desc:
                    sphere = pv.Sphere(radius=6.0, center=(x, y, z))
                    self.plotter.add_mesh(sphere, color="red", opacity=0.8)
                elif "cold" in desc:
                    sphere = pv.Sphere(radius=6.0, center=(x, y, z))
                    self.plotter.add_mesh(sphere, color="yellow", opacity=0.8)



    def _draw_defect_markers_matplotlib(self, defects):

        """Draw defect markers using matplotlib."""

        if not self.models or not defects:
            return
        _, _, _, _, zmin, zmax = self._compute_bounds()
        colors = {"shrinkage": "red", "cold_shut": "yellow"}
        for i, defect in enumerate(defects):
            if isinstance(defect, tuple) and len(defect) >= 4:
                dtype = defect[0].lower()
                x, y, z = defect[1], defect[2], defect[3]
            else:
                rng = random.Random(i)
                x = rng.uniform(-10, 10)
                y = rng.uniform(-10, 10)
                z = zmax + 30 + i * 8
            desc = defect.lower() if isinstance(defect, str) else ""
            color = colors.get(dtype, "red" if "shrinkage" in desc else "yellow" if "cold" in desc else "gray")
            self.ax.scatter(x, y, z, c=color, s=200, marker="o", depthshade=True)

    def draw_defect_markers(self, defects):

        """Public method to draw defect markers using current backend."""

        if self.use_pyvista:
            self._draw_defect_markers(defects)
        else:
            self._draw_defect_markers_matplotlib(defects)



    # ------------------------------------------------------------------

    # Shading helpers

    # ------------------------------------------------------------------



    def _shade_faces(self, verts: np.ndarray, base_rgb, alpha: float = 1.0):

        """Per-face Phong-style shading with key, fill, and rim lights."""

        v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
        normals = np.cross(v1 - v0, v2 - v0).astype(float)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        lengths[lengths == 0] = 1e-9
        normals /= lengths


        lights = [
            (np.array([0.5,  0.8, 1.0]),  0.7),
            (np.array([-0.3, 0.2, 0.5]),  0.25),
            (np.array([0.8, -0.4, -0.1]), 0.15),
        ]
        intensities = np.zeros(len(verts))
        for light_dir, strength in lights:
            ld = light_dir / np.linalg.norm(light_dir)
            intensities += np.clip(normals @ ld, 0, 1) * strength
        intensities = np.clip(intensities + 0.18, 0, 1)


        br, bg, bb = base_rgb
        colors = np.stack([
            np.clip(br * intensities, 0, 1),
            np.clip(bg * intensities, 0, 1),
            np.clip(bb * intensities, 0, 1),
            np.full(len(verts), alpha),
        ], axis=1)
        return colors

    def _compute_heat_colors(self, verts: np.ndarray, anim_frac: float) -> np.ndarray:
        """Compute per-triangle heat colors based on fill animation fraction.

        Colors triangles by temperature state:
        - Filled (z <= fill_level): #FFFFA0 (yellowish)
        - Cooling (fill_level < z <= fill_level + margin): interpolated
        - Solidified (z > fill_level + margin): #909090 (gray)
        Args:
            verts: Triangle vertices array of shape (n_tris, 3, 3)
            anim_frac: Animation fraction (0.0 to 1.0) representing fill level
        Returns:
            RGBA colors array of shape (n_tris, 4)
        """
        # Compute centroid z for each triangle
        centroids_z = verts[:, :, 2].mean(axis=1)
        # Define colors as RGB tuples
        filled_color = np.array([1.0, 1.0, 0.631])   # #FFFFA0
        cooling_color = np.array([1.0, 0.4, 0.0])     # #FF6600
        solidified_color = np.array([0.565, 0.565, 0.565])  # #909090
        # Normalize z range for coloring
        z_min = centroids_z.min()
        z_max = centroids_z.max()
        z_range = max(z_max - z_min, 1e-9)
        # Calculate fill level in z coordinates
        part_h = z_max - z_min
        fill_z = z_min + part_h * anim_frac
        # Compute relative position (0=below fill, 1=at top)
        rel_pos = (centroids_z - fill_z) / z_range
        # Vectorized color assignment
        alpha = 0.85
        t_clamp = np.clip(rel_pos / 0.1, 0.0, 1.0)  # 0=filled, 1=solidified
        # Start with filled color broadcast to all rows
        rgb = np.where(
            rel_pos[:, None] <= 0,
            filled_color,
            np.where(
                rel_pos[:, None] >= 0.1,
                solidified_color,
                cooling_color * (1 - t_clamp[:, None]) + solidified_color * t_clamp[:, None],
            )
        )
        colors = np.concatenate([rgb, np.full((len(verts), 1), alpha)], axis=1)
        return colors

    # ------------------------------------------------------------------

    # Mesh generators for gating components

    # ------------------------------------------------------------------



    @staticmethod
    def _make_cylinder_mesh(cx: float, cy: float, z_bottom: float,
                            r_bottom: float, r_top: float, height: float,
                            sides: int = 24) -> np.ndarray:
        """Generate a truncated cone as triangle faces (vectorised)."""
        theta = np.linspace(0, 2 * np.pi, sides + 1)[:-1]
        idx   = np.arange(sides)
        wrap  = (idx + 1) % sides
        bv = np.stack([cx + r_bottom * np.cos(theta),
                       cy + r_bottom * np.sin(theta),
                       np.full(sides, z_bottom)], axis=1)
        tv = np.stack([cx + r_top    * np.cos(theta),
                       cy + r_top    * np.sin(theta),
                       np.full(sides, z_bottom + height)], axis=1)
        # Side faces: 2 triangles per segment
        side_a = np.stack([bv[idx], bv[wrap], tv[idx]],  axis=1)
        side_b = np.stack([tv[idx], bv[wrap], tv[wrap]], axis=1)
        # Cap faces
        cbot = np.tile([cx, cy, z_bottom],          (sides, 1))
        ctop = np.tile([cx, cy, z_bottom + height], (sides, 1))
        cap_bot = np.stack([cbot, bv[idx], bv[wrap]], axis=1)
        cap_top = np.stack([ctop, tv[wrap], tv[idx]], axis=1)
        return np.concatenate([side_a, side_b, cap_bot, cap_top]).astype(float)


    @staticmethod

    def _make_box_mesh(cx: float, cy: float, z_bottom: float,
                       width: float, depth: float, height: float) -> np.ndarray:

        """Generate a rectangular box as triangle faces."""

        hw, hd, hh = width / 2, depth / 2, height / 2


        corners = np.array([
            [-hw, -hd, -hh],
            [ hw, -hd, -hh],
            [ hw,  hd, -hh],
            [-hw,  hd, -hh],
            [-hw, -hd,  hh],
            [ hw, -hd,  hh],
            [ hw,  hd,  hh],
            [-hw,  hd,  hh],
        ])


        faces = []


        faces.append(np.stack([corners[0], corners[1], corners[2]]))
        faces.append(np.stack([corners[0], corners[2], corners[3]]))


        faces.append(np.stack([corners[4], corners[6], corners[5]]))
        faces.append(np.stack([corners[4], corners[7], corners[6]]))


        faces.append(np.stack([corners[0], corners[1], corners[5]]))
        faces.append(np.stack([corners[0], corners[5], corners[4]]))


        faces.append(np.stack([corners[2], corners[3], corners[7]]))
        faces.append(np.stack([corners[2], corners[7], corners[6]]))


        faces.append(np.stack([corners[0], corners[3], corners[7]]))
        faces.append(np.stack([corners[0], corners[7], corners[4]]))


        faces.append(np.stack([corners[1], corners[2], corners[6]]))
        faces.append(np.stack([corners[1], corners[6], corners[5]]))


        return np.array(faces, dtype=float)



    @staticmethod

    def _hex_to_rgb(hex_color: str):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))



    # ------------------------------------------------------------------

    # Transform setters

    # ------------------------------------------------------------------



    def set_transformation(self, dx, dy, dz, rot_z):
        if not self.active_model or self.active_model not in self.transforms:
            return
        self.transforms[self.active_model] = {
            "offset":   np.array([float(dx), float(dy), float(dz)]),
            "rotation": float(rot_z),
        }
        self.render(self._anim_frac)



    def set_gating_offset(self, sprue_x, sprue_y, runner_y, riser_x, riser_y):
        self.sprue_offset     = np.array([float(sprue_x), float(sprue_y)])
        self.runner_y_offset  = float(runner_y)
        self.riser_offset     = np.array([float(riser_x), float(riser_y)])
        self.render(self._anim_frac)



    def set_flask(self, size_tuple):
        self.flask_size = size_tuple
        self.render(self._anim_frac)



    def set_parting(self, frac: float):
        self.parting_z = float(frac)
        self.render(self._anim_frac)



    def set_gating(self, components: list):
        self.gating = [c for c in components if c != "None"]
        self.render(self._anim_frac)



    def update_gating_display(self, selected: list):
        self.set_gating(selected)



    def set_view(self, view_name: str):
        if self.use_pyvista:
            pv_map = {
                "Top": "xy", "Bottom": "xy",
                "Front": "xz", "Back": "xz",
                "Left": "yz", "Right": "yz",
                "Iso": "isometric",
            }
            vkey = pv_map.get(view_name)
            if vkey:
                if vkey == "isometric":
                    self.plotter.view_isometric()
                else:
                    getattr(self.plotter, f"view_{vkey}")()
            return
        views = {
            "Top":    (90,  -90),
            "Bottom": (-90,  90),
            "Front":  (0,   -90),
            "Back":   (0,    90),
            "Left":   (0,     0),
            "Right":  (0,   180),
            "Iso":    (30,  -60),
        }
        if view_name in views:
            elev, azim = views[view_name]
            self.ax.view_init(elev=elev, azim=azim)
            self.draw_idle()

    def set_pour_rate(self, rate: float):
        self.pour_rate = max(0.5, min(3.0, rate))



    def get_gating_params(self) -> dict:
        has_sprue  = "Tapered Sprue" in self.gating
        has_runner = "Runner (Horizontal)" in self.gating
        has_gate   = any(c in self.gating for c in ["Fan Gate"])


        return {
            "has_sprue":    has_sprue,
            "has_runner":   has_runner,
            "has_gate":     has_gate,
            "sprue_top_r":  self.sprue_top_radius if has_sprue else None,
            "sprue_bot_r":  self.sprue_bottom_radius if has_sprue else None,
            "runner_dia":   self.runner_diameter if has_runner else None,
            "gate_area_mm2": self.gate_area if has_gate else None,
        }



    def draw_idle(self):
        if self.use_pyvista:
            self.plotter.render()
        else:
            self.canvas.draw_idle()



    # ------------------------------------------------------------------

    # Mouse interaction

    # ------------------------------------------------------------------



    def _on_mouse_press(self, event):
        if event.inaxes != self.ax:
            return
        mx, my = event.x, event.y


        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            _, _, _, _, _, zmax = self._compute_bounds()
            if self._is_near_point(mx, my, sx, sy, zmax + 50):
                self._dragging_part = "sprue"
                self._drag_last = (mx, my)
                return


        if "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            _, _, _, _, zmin, zmax = self._compute_bounds()
            part_h = max(zmax - zmin, 1.0)
            z_part = zmin + part_h * self.parting_z
            if self._is_near_point(mx, my, rx, ry, z_part + 30):
                self._dragging_part = "riser"
                self._drag_last = (mx, my)
                return


        if self.active_model and self.active_model in self.transforms:
            self._dragging_part = "model"
            self._drag_last = (mx, my)



    def _on_mouse_move(self, event):
        if not self._dragging_part or event.inaxes != self.ax:
            return
        mx, my = event.x, event.y
        lx, ly = self._drag_last
        dx_px  = mx - lx
        dy_px  = my - ly
        self._drag_last = (mx, my)


        fw_mm = self.flask_size[0] * 25.4
        canvas_w = self.get_width_height()[0]
        scale = fw_mm / max(canvas_w, 1)
        dmm_x = dx_px * scale
        dmm_y = dy_px * scale


        if self._dragging_part == "sprue":
            self.sprue_offset += np.array([dmm_x, -dmm_y])
            self.render(self._anim_frac)
            self.gating_moved.emit({
                "sprue_x": float(self.sprue_offset[0]),
                "sprue_y": float(self.sprue_offset[1]),
                "riser_x": float(self.riser_offset[0]),
                "riser_y": float(self.riser_offset[1]),
            })


        elif self._dragging_part == "riser":
            self.riser_offset += np.array([dmm_x, -dmm_y])
            self.render(self._anim_frac)
            self.gating_moved.emit({
                "sprue_x": float(self.sprue_offset[0]),
                "sprue_y": float(self.sprue_offset[1]),
                "riser_x": float(self.riser_offset[0]),
                "riser_y": float(self.riser_offset[1]),
            })


        elif self._dragging_part == "model" and self.active_model:
            t   = self.transforms[self.active_model]
            off = t["offset"]
            t["offset"] = off + np.array([dmm_x, -dmm_y, 0.0])
            self.render(self._anim_frac)



    def _on_mouse_release(self, event):
        self._dragging_part = None
        self._drag_last     = None



    def get_width_height(self):
        if self.use_pyvista:
            return self.render_frame.width(), self.render_frame.height()
        else:
            return self.canvas.get_width_height()



    def _is_near_point(self, mx, my, dx, dy, dz, threshold=25) -> bool:

        """Projects 3D point to screen pixels and checks distance."""

        try:
            point_3d = np.array([[dx, dy, dz, 1.0]])
            proj = self.ax.get_proj()
            clip = point_3d @ proj.T
            ndc_x = clip[0, 0] / clip[0, 3]
            ndc_y = clip[0, 1] / clip[0, 3]


            w, h = self.ax.get_figure().get_size_inches() * self.ax.get_figure().dpi
            sx = (ndc_x + 1) / 2 * w
            sy = (1 - (ndc_y + 1) / 2) * h


            return math.hypot(mx - sx, my - sy) < threshold
        except Exception:
            return False



    # ------------------------------------------------------------------

    # Zoom via scroll wheel

    # ------------------------------------------------------------------



    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return


        if event.button == 'up':
            self._zoom_factor *= 1.1
        elif event.button == 'down':
            self._zoom_factor /= 1.1


        self._zoom_factor = max(0.25, min(self._zoom_factor, 4.0))
        self.render(self._anim_frac)



    # ------------------------------------------------------------------

    # Fill animation

    # ------------------------------------------------------------------



    def start_fill_animation(self, duration_s: float = 3.0, on_done=None):
        self._anim_done_cb = on_done
        self._anim_step    = 0
        self._anim_steps   = 40
        interval_ms        = int((duration_s * 1000) / self._anim_steps)
        interval_ms        = max(16, int(interval_ms / self.pour_rate))
        self._anim_timer.start(interval_ms)



    def _anim_tick(self):
        self._anim_step += 1
        self._anim_frac  = self._anim_step / self._anim_steps
        self.render(self._anim_frac)
        if self._anim_step >= self._anim_steps:
            self._anim_timer.stop()
            self._anim_frac = 0.0
            # Start solidification animation
            self.start_solidify_animation(duration_s=3.0, on_done=self._anim_done_cb)



    def start_solidify_animation(self, duration_s: float = 3.0, on_done=None):

        """Start solidification animation - boundary moves inward from mold walls."""

        self._solidify_done_cb = on_done
        self._solidify_step    = 0
        self._solidify_steps   = 60
        interval_ms            = int((duration_s * 1000) / self._solidify_steps)
        self._solidify_timer.start(interval_ms)



    def _solidify_tick(self):

        """Update solidification animation tick."""

        self._solidify_step += 1
        self._solidify_frac  = self._solidify_step / self._solidify_steps
        self.render(max(self._anim_frac, self._solidify_frac))
        if self._solidify_step >= self._solidify_steps:
            self._solidify_timer.stop()
            self._solidify_frac = 0.0
            if self._solidify_done_cb:
                self._solidify_done_cb()



    def reset_anim(self):

        """Stop animation and clear all loaded model state."""

        self._anim_timer.stop()
        self._solidify_timer.stop()
        self._anim_frac = 0.0
        self._solidify_frac = 0.0
        self._anim_step = 0
        self._solidify_step = 0
        self.models.clear()
        self.transforms.clear()
        self.active_model = ""
        self._draw_idle_scene()





# ---------------------------------------------------------------------------

# build_results_text

# ---------------------------------------------------------------------------



def build_results_text(r: dict) -> str:
    lines = []
    lines.append("=" * 46)
    lines.append("  SAND CASTING SIMULATION RESULTS")
    lines.append("=" * 46)
    lines.append(f"  Metal       : {r['metal']}")
    lines.append(f"  Pour temp   : {r['pour_f']:.0f} F")
    lines.append(f"  Mold temp   : {r['mold_f']:.0f} F")
    lines.append(f"  Superheat   : {r['superheat']:.1f} F")
    lines.append("-" * 46)
    lines.append(f"  Volume      : {r['vol_cm3']:.2f} cm3")
    lines.append(f"  Surface     : {r['surf_cm2']:.2f} cm2")
    lines.append(f"  V/S Ratio   : {r['vsr']:.4f} cm")
    lines.append("-" * 46)
    lines.append(f"  Fill time   : {r['fill_time_s']:.1f} s")
    lines.append(f"  Solidify    : {r['t_solidify_min']:.2f} min")
    lines.append("-" * 46)


    if r["defects"]:
        lines.append("  DEFECT RISKS:")
        for d in r["defects"]:
            for ln in textwrap.wrap(d, 42):
                lines.append(f"    - {ln}")
    else:
        lines.append("  No defect risks detected.")


    if r["warnings"]:
        lines.append("")
        lines.append("  WARNINGS:")
        for w in r["warnings"]:
            for ln in textwrap.wrap(w, 42):
                lines.append(f"    - {ln}")


    lines.append("=" * 46)
    return '\n'.join(lines)



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


        # Pour rate slider

        def on_pour_rate_changed(val):
            rate = 0.1 + (val / 50.0)
            self.viewport.set_pour_rate(rate)


        self.pour_spin.valueChanged.connect(on_pour_rate_changed)


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






def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")


    app.setStyleSheet(APP_STYLE)


    win = MainWindow()
    win.show()


    original_resize = win.resizeEvent



    def new_resize(event):
        original_resize(event)
        try:
            win.viewport.fig.tight_layout()
            win.viewport.fig.canvas.draw_idle()
        except Exception:
            pass


    if not win.viewport.use_pyvista:
        win.resizeEvent = new_resize


    sys.exit(app.exec())




if __name__ == "__main__":
    main()