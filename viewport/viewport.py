import math
import hashlib
import random
import time
import numpy as np
import matplotlib.cm as _cm
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
try:
    import pyvista as pv
    PV_AVAILABLE = True
    from pyvista import PolyData
except ImportError:
    pv = None
    PV_AVAILABLE = False
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
from constants import (COPE_COLOR, DRAG_COLOR, SPRUE_COLOR, RUNNER_COLOR,
                       GATE_COLOR, RISER_COLOR, MODEL_COLORS, METAL_PBR,
                       DEFAULT_FLASK_HEIGHT_IN, SHELL_COLOR, DEFAULT_SHELL_MM,
                       CHILL_COLOR, FILTER_COLOR, BASIN_COLOR, GATE2_COLOR,
                       PRINTED_SAND_COLOR, DEFAULT_PRINTED_MM, FEEDING_STOP_FRAC)
from simulation.mesh_tools import (
    inspect_mesh, invert_winding, qem_decimate, local_thickness,
    find_defect_sites, THIN_WALL_MM, load_mesh_vectors,
    transform_triangles, rescale_world_point as _rescale_world_point,
)
from simulation.foundry import (
    snap_xy_to_silhouette, choke_location, draft_analysis, undercut_hints,
    DRAFT_MIN_DEG,
)

# Optional GPU array backend (falls back to NumPy transparently)
try:
    import cupy as cp
    _CUPY_AVAILABLE = True
except ImportError:
    cp = None
    _CUPY_AVAILABLE = False
xp = cp if _CUPY_AVAILABLE else np

# Pre-built 256-entry plasma LUT for GPU-friendly heat color lookup
_PLASMA_LUT: np.ndarray = _cm.plasma(np.linspace(0, 1, 256))[:, :3].astype(np.float32)

# Normalised light directions and strengths for Phong shading (vectorised)
_LIGHT_DIRS = np.array([
    [0.5,  0.8,  1.0],
    [-0.3, 0.2,  0.5],
    [0.8, -0.4, -0.1],
], dtype=np.float64)
_LIGHT_DIRS /= np.linalg.norm(_LIGHT_DIRS, axis=1, keepdims=True)
_LIGHT_STRENGTHS = np.array([0.7, 0.25, 0.15], dtype=np.float64)


class Viewport3D(QWidget):

    """Embedded 3D viewport using PyVista or matplotlib fallback."""



    gating_moved = pyqtSignal(dict)
    model_moved = pyqtSignal(dict)
    gating_selected = pyqtSignal(str)
    parting_picked = pyqtSignal(float)
    gating_list_changed = pyqtSignal(list)
    drag_began = pyqtSignal()



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
        self.flask_height_in  = float(DEFAULT_FLASK_HEIGHT_IN)
        self.mold_kind        = "sand"
        self.shell_mm         = float(DEFAULT_SHELL_MM)
        self.printed_mm       = float(DEFAULT_PRINTED_MM)


        self.sprue_offset  = np.array([0.0, 60.0])
        self.runner_y_offset = 0.0
        self.riser_offset  = np.array([60.0, 0.0])


        # Gating dimensions (mm) — hydraulics must match the rendered mesh
        self.sprue_top_radius    = 7.5
        self.sprue_bottom_radius = 4.0
        self.sprue_height        = 100.0
        self.runner_length       = 160.0
        self.runner_width        = 10.0   # cross-section depth
        self.runner_height       = 8.0    # cross-section height
        self.runner_diameter     = 12.0   # legacy circular approx; unused when width/height set
        self.gate_area           = 40.0
        self.riser_radius        = 20.0
        self.riser_height        = 60.0
        self.riser_blind         = False
        self.neck_radius         = 8.0
        self.neck_height         = 12.0
        self.gate2_offset        = np.array([0.0, -60.0])
        self.filter_area         = 400.0
        self.basin_radius        = 18.0
        self.basin_height        = 22.0
        self.chills: list        = []
        self.shrink_scale        = 1.0
        self.show_as_cast        = False
        self.selected_gating     = ""
        self.pick_mode           = ""          # "", "parting", "sprue", "gate", "riser", "chill", "filter", "gate2"
        self.overlay_mode        = ""          # + "xray"
        self.restrictive_elem    = ""
        self.clip_enabled        = False
        self.clip_axis           = 0           # 0=X 1=Y 2=Z
        self.clip_frac           = 0.5
        self._sim_fields: dict   = {}
        self._clock_fill_s       = 0.0
        self._clock_solidify_min = 0.0
        self._solid_frac_label   = False


        self.pour_rate: float  = 1.0
        self._anim_frac: float = 0.0
        self._anim_timer       = QTimer()
        self._anim_timer.setSingleShot(True)   # restarts after render, prevents queue buildup
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_done_cb     = None
        self._anim_steps       = 120
        self._anim_step        = 0


        self._solidify_frac: float = 0.0
        self._solidify_timer     = QTimer()
        self._solidify_timer.setSingleShot(True)   # restarts after render, prevents queue buildup
        self._solidify_timer.timeout.connect(self._solidify_tick)
        self._solidify_done_cb   = None
        self._solidify_steps     = 120
        self._solidify_step      = 0


        self._dragging_part    = None
        self._drag_last        = None
        self._zoom_factor      = 1.0

        # Active metal name — drives PBR material selection in PyVista renderer
        self.active_metal: str = "A356 Aluminum"

        # Gating geometry cache — rebuilt only when params change (both backends)
        self._gating_geo_cache: dict  = {}
        self._gating_cache_key: tuple = ()

        # Animation interval stored for single-shot timer restarts
        self._anim_interval_ms:     int = 25
        self._solidify_interval_ms: int = 25

        # PyVista incremental actor management
        self._pv_actors:          dict  = {}   # name -> {model, fill}
        self._pv_flask_actors:    list  = []
        self._pv_flask_key:       tuple = ()
        self._pv_gating_actors:   list  = []
        self._pv_gating_key:      tuple = ()
        self._pv_particle_actors: list  = []

        # Matplotlib persistent model collections (Phase 4b)
        self._mpl_model_collections: dict = {}   # name -> {cope, drag}

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
                # --- Visual quality settings (set once at startup) ---
                try:
                    self.plotter.enable_ssao(radius=0.5, bias=0.025, kernel_size=32)
                except Exception:
                    pass
                try:
                    self.plotter.enable_shadows()
                except Exception:
                    pass
                # 3-point lighting rig: key / fill / rim
                self.plotter.remove_all_lights()
                self.plotter.add_light(pv.Light(position=(200, 200, 300),
                                                focal_point=(0, 0, 0),
                                                intensity=0.75))
                self.plotter.add_light(pv.Light(position=(-150, 100, 100),
                                                focal_point=(0, 0, 0),
                                                intensity=0.30))
                self.plotter.add_light(pv.Light(position=(0, -200, 250),
                                                focal_point=(0, 0, 0),
                                                intensity=0.15))
                self._bind_pyvista_drag()
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
        self._style_axes()   # style once at setup, not on every frame
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
        hint = "Drop an STL or OBJ here\nor try the demo"
        if self.use_pyvista:
            self.plotter.clear()
            self._pv_actors.clear()
            self._pv_flask_actors.clear()
            self._pv_flask_key = ()
            self._pv_gating_actors.clear()
            self._pv_gating_key = ()
            z_part = 50.0
            if self.mold_kind == "shell":
                self._draw_shell_outline_pv(z_part)
            elif self.mold_kind == "printed":
                self._draw_printed_outline_pv(z_part)
            else:
                fw_mm = self.flask_size[0] * 25.4
                fh_mm = self.flask_size[1] * 25.4
                hw, hh = fw_mm / 2, fh_mm / 2
                xs = [-hw, hw, hw, -hw, -hw]
                ys = [-hh, -hh, hh, hh, -hh]
                for z, col, lw in [(0.0, "#45475A", 2), (self.flask_height_in * 25.4, "#45475A", 2),
                                   (z_part, "#89B4FA", 3)]:
                    pts = np.column_stack([xs, ys, [z] * 5])
                    line = pv.PolyData(pts)
                    line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
                    self.plotter.add_mesh(line, color=col, line_width=lw)
            self.plotter.add_text(hint, position="upper_left", font_size=12, color="#A6ADC8")
            self.plotter.render()
        else:
            self.ax.cla()
            self._style_axes()
            if self.mold_kind == "shell":
                self._draw_shell_outline_mpl(z_part := 40.0)
                xmin, xmax, ymin, ymax, zmin, zmax = self._shell_aabb()
                self.ax.text(0, 0, (zmin + zmax) * 0.55, hint,
                             ha="center", va="center", color="#A6ADC8", fontsize=11)
                self.ax.set_xlim(xmin - 20, xmax + 20)
                self.ax.set_ylim(ymin - 20, ymax + 20)
            elif self.mold_kind == "printed":
                self._draw_printed_outline_mpl(z_part := 40.0)
                xmin, xmax, ymin, ymax, zmin, zmax = self._printed_aabb()
                self.ax.text(0, 0, (zmin + zmax) * 0.55, hint,
                             ha="center", va="center", color="#A6ADC8", fontsize=11)
                self.ax.set_xlim(xmin - 20, xmax + 20)
                self.ax.set_ylim(ymin - 20, ymax + 20)
                self.ax.set_zlim(zmin - 20, zmax + 20)
            else:
                fw_mm = self.flask_size[0] * 25.4
                fh_mm = self.flask_size[1] * 25.4
                hw, hh = fw_mm / 2, fh_mm / 2
                xs = [-hw, hw, hw, -hw, -hw]
                ys = [-hh, -hh, hh, hh, -hh]
                z_top = self.flask_height_in * 25.4
                for z, color in [(0.0, "#45475A"), (z_top, "#45475A"), (z_top * 0.5, "#89B4FA")]:
                    self.ax.plot(xs, ys, [z] * 5, color=color, linestyle="--", linewidth=1.2, alpha=0.7)
                self.ax.text(0, 0, z_top * 0.55, hint,
                             ha="center", va="center", color="#A6ADC8", fontsize=11)
                self.ax.set_xlim(-hw - 40, hw + 40)
                self.ax.set_ylim(-hh - 40, hh + 40)
                self.ax.set_zlim(-20, z_top + 40)
            self.canvas.draw_idle()



    def get_model_names(self) -> list[str]:
        return list(self.models.keys())



    def set_active_model(self, name: str):
        self.active_model = name



    def remove_model(self, name: str) -> None:
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



    def load_stl(self, path: str, name: str = None, scale: float = 1.0) -> dict:
        """Load an STL or OBJ, clean it, and add it to the scene.

        ``scale`` converts file units into millimetres (1.0 = already mm, 25.4 = inches).
        """
        if name is None:
            n = len(self.models) + 1
            name = f"Part_{n}"

        vectors = load_mesh_vectors(path)
        if abs(float(scale) - 1.0) > 1e-12:
            vectors = np.asarray(vectors, dtype=np.float64) * float(scale)

        v0, v1, v2 = vectors[:, 0], vectors[:, 1], vectors[:, 2]
        cross = np.cross(v1 - v0, v2 - v0)
        areas = np.linalg.norm(cross, axis=1)
        valid = (
            np.isfinite(vectors).all(axis=(1, 2)) &
            (areas > 1e-10)
        )
        vectors = vectors[valid]
        centroids = vectors.mean(axis=1).round(6)
        _, unique_idx = np.unique(centroids, axis=0, return_index=True)
        vectors = vectors[unique_idx]

        quality = inspect_mesh(vectors)
        if quality["inverted"]:
            vectors = invert_winding(vectors)

        vectors = qem_decimate(vectors, max_tris=25_000)
        thickness = local_thickness(vectors)

        class _Mesh:
            pass
        loaded = _Mesh()
        loaded.vectors = vectors

        _v0, _v1, _v2 = vectors[:, 0], vectors[:, 1], vectors[:, 2]
        _cross = np.cross(_v1 - _v0, _v2 - _v0).astype(np.float64)
        _lens = np.linalg.norm(_cross, axis=1, keepdims=True)
        _lens[_lens == 0] = 1e-9
        _cross /= _lens

        self.models[name] = {
            "mesh":        loaded,
            "render_data": vectors,
            "normals":     _cross,
            "thickness":   thickness,
        }
        self.transforms[name] = {
            "offset":   np.array([0.0, 0.0, 0.0]),
            "rotation": 0.0,
        }
        if not self.active_model:
            self.active_model = name

        stats = self._geometry_stats(loaded)
        self.render()
        self.fit_view()
        return stats



    # ------------------------------------------------------------------

    # Geometry stats  

    # ------------------------------------------------------------------



    def _geometry_stats(self, mesh) -> dict:

        """Volume via divergence theorem, surface area from triangle cross-products.

        Uses GPU arrays (CuPy) when available, falls back to NumPy automatically.
        """

        verts = xp.asarray(mesh.vectors)
        if verts.shape[0] == 0:
            return {
                "vol_cm3": 0.0, "surf_cm2": 0.0, "z_min": 0.0, "z_max": 0.0,
                "watertight": False, "inverted": False,
                "mesh_warnings": ["Mesh has no triangles."],
                "min_wall_mm": 0.0, "thin_wall_auto": False,
            }

        v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]

        cross   = xp.cross(v1 - v0, v2 - v0)
        vol_mm3 = float(abs(xp.sum(v0 * cross) / 6.0))

        area_mm2 = float(xp.sum(xp.linalg.norm(cross, axis=1)) / 2.0)

        quality = inspect_mesh(np.asarray(mesh.vectors, dtype=np.float64))
        thick = local_thickness(np.asarray(mesh.vectors, dtype=np.float64))
        min_wall = float(np.min(thick)) if len(thick) else 0.0

        return {
            "vol_cm3":  vol_mm3  / 1000.0,
            "surf_cm2": area_mm2 / 100.0,
            "z_min":    float(xp.min(verts[:, :, 2])),
            "z_max":    float(xp.max(verts[:, :, 2])),
            "watertight": quality["watertight"],
            "inverted":   quality["inverted"],
            "mesh_warnings": quality["warnings"],
            "min_wall_mm": min_wall,
            "thin_wall_auto": min_wall < THIN_WALL_MM,
        }



    # ------------------------------------------------------------------

    # Bounds helpers  

    # ------------------------------------------------------------------



    def _compute_bounds_for_model(self, name: str, scale: float | None = None):
        t   = self.transforms[name]
        off = t["offset"]
        rot = math.radians(t["rotation"])


        verts = self.models[name]["render_data"].reshape(-1, 3)
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        s = float(self._display_scale() if scale is None else scale)
        xs = (verts[:, 0] * cos_r - verts[:, 1] * sin_r) * s + off[0]
        ys = (verts[:, 0] * sin_r + verts[:, 1] * cos_r) * s + off[1]
        zs = verts[:, 2] * s + off[2]
        return xs.min(), xs.max(), ys.min(), ys.max(), zs.min(), zs.max()



    def _compute_bounds(self, scale: float | None = None):
        if not self.models:
            fw_mm = self.flask_size[0] * 25.4
            fh_mm = self.flask_size[1] * 25.4
            return -fw_mm/2, fw_mm/2, -fh_mm/2, fh_mm/2, 0.0, 100.0


        all_b = [self._compute_bounds_for_model(n, scale=scale) for n in self.models]
        xmins, xmaxs, ymins, ymaxs, zmins, zmaxs = zip(*all_b)
        return min(xmins), max(xmaxs), min(ymins), max(ymaxs), min(zmins), max(zmaxs)

    def _effective_runner_length(self, scale: float | None = None) -> float:
        """Runner bar spans the part XY silhouette plus a short over-run."""
        xmin, xmax, ymin, ymax, _, _ = self._compute_bounds(scale)
        span = max(xmax - xmin, ymax - ymin, 1.0)
        return float(max(40.0, span + 24.0))





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

        """Render using matplotlib backend.

        Persistent model Poly3DCollections are kept alive across frames and
        updated in-place; only overlay artists (flask outline, gating, particles,
        fill animation) are cleared and re-added each frame, avoiding ax.cla().
        """

        # Clear overlay artists (flask, gating, fill overlay, particles)
        # keeping persistent model collections intact
        self._clear_mpl_overlays()

        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part  = zmin + part_h * self.parting_z

        PAD   = 76.0
        fw_mm = self.flask_size[0] * 25.4
        fh_mm = self.flask_size[1] * 25.4

        cope_base = self._hex_to_rgb(COPE_COLOR)
        drag_base = self._hex_to_rgb(DRAG_COLOR)

        # Remove persistent collections for models that have been deleted
        for name in list(self._mpl_model_collections):
            if name not in self.models:
                for coll in self._mpl_model_collections[name].values():
                    if coll is not None:
                        try:
                            coll.remove()
                        except Exception:
                            pass
                del self._mpl_model_collections[name]

        for name, data in self.models.items():
            verts       = self._apply_transform(data["render_data"], self.transforms[name])
            centroids_z = verts[:, :, 2].mean(axis=1)
            cope_mask   = centroids_z >= z_part
            cope_verts  = verts[cope_mask]
            drag_verts  = verts[~cope_mask]
            if self.clip_enabled:
                if len(cope_verts):
                    cope_verts = cope_verts[self._clip_mask(cope_verts)]
                if len(drag_verts):
                    drag_verts = drag_verts[self._clip_mask(drag_verts)]

            cope_alpha = 0.12 if self.overlay_mode == "xray" else 1.0
            drag_alpha = 0.12 if self.overlay_mode == "xray" else 1.0
            cope_rgba = np.array(cope_base + (cope_alpha,), dtype=float)
            drag_rgba = np.array(drag_base + (drag_alpha,), dtype=float)
            cope_colors = np.broadcast_to(cope_rgba, (len(cope_verts), 4)).copy() if len(cope_verts) else np.zeros((0, 4))
            drag_colors = np.broadcast_to(drag_rgba, (len(drag_verts), 4)).copy() if len(drag_verts) else np.zeros((0, 4))

            if name not in self._mpl_model_collections:
                # First render of this model: create collections
                cope_coll = drag_coll = None
                if len(cope_verts):
                    cope_coll = Poly3DCollection(
                        cope_verts, facecolors=cope_colors,
                        edgecolors="none", linewidths=0, shade=False,
                    )
                    self.ax.add_collection3d(cope_coll)
                if len(drag_verts):
                    drag_coll = Poly3DCollection(
                        drag_verts, facecolors=drag_colors,
                        edgecolors="none", linewidths=0, shade=False,
                    )
                    self.ax.add_collection3d(drag_coll)
                self._mpl_model_collections[name] = {"cope": cope_coll, "drag": drag_coll}
            else:
                # Update existing collections in-place (avoids add_collection3d overhead)
                colls = self._mpl_model_collections[name]
                if colls["cope"] is not None and len(cope_verts):
                    colls["cope"].set_verts(cope_verts)
                    colls["cope"].set_facecolor(cope_colors)
                if colls["drag"] is not None and len(drag_verts):
                    colls["drag"].set_verts(drag_verts)
                    colls["drag"].set_facecolor(drag_colors)

            # Fill / solidification overlay
            if self.overlay_mode in ("draft", "undercut"):
                self._add_mpl_inspect_overlay(name, verts)
            elif self.overlay_mode:
                self._add_mpl_result_overlay(name, verts)
            elif self._solidify_frac > 0:
                self._add_mpl_solidify_overlay(name, verts)
            elif anim_frac > 0:
                fill_mask = self._fill_mask(verts, anim_frac) & self._clip_mask(verts)
                if np.any(fill_mask):
                    heat_colors = self._compute_heat_colors(verts, anim_frac)
                    self.ax.add_collection3d(
                        Poly3DCollection(verts[fill_mask],
                                         facecolors=heat_colors[fill_mask],
                                         edgecolors="none"))

        self._draw_flask_outline(z_part)
        if self.clip_enabled:
            self._draw_clip_plane_mpl()
        if self.overlay_mode == "xray":
            self._draw_xray_points_mpl()

        if self.models:
            self._draw_gating(z_part)
            self._draw_choke_marker(z_part, zmax)
            if anim_frac > 0 and "Tapered Sprue" in self.gating:
                self._draw_sprue_particles(z_part, anim_frac)
        self._draw_clock_mpl()

        half_w = fw_mm / 2 + PAD
        half_h = fh_mm / 2 + PAD
        if self.mold_kind in ("shell", "printed"):
            sx0, sx1, sy0, sy1, _, _ = self._shell_aabb()
            half_w = max(abs(sx0), abs(sx1)) + PAD * 0.5
            half_h = max(abs(sy0), abs(sy1)) + PAD * 0.5
        cx = half_w / self._zoom_factor
        cy = half_h / self._zoom_factor
        z_center = (zmin + zmax) / 2
        z_range  = ((zmax + 120) - (zmin - 20)) / 2 / self._zoom_factor
        self.ax.set_xlim(-cx, cx)
        self.ax.set_ylim(-cy, cy)
        self.ax.set_zlim(z_center - z_range, z_center + z_range)

        self.canvas.draw_idle()





    def _render_pyvista(self, anim_frac: float):

        """Render using PyVista backend with PBR materials."""

        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part  = zmin + part_h * self.parting_z

        # ----------------------------------------------------------------
        # 1. Sync model actors — create for new models, remove for deleted
        # ----------------------------------------------------------------
        for name, data in self.models.items():
            if name not in self._pv_actors:
                raw = data["render_data"]
                n   = len(raw)
                faces = np.hstack([np.full((n, 1), 3),
                                   np.arange(n * 3).reshape(-1, 3)])
                mesh  = PolyData(raw.reshape(-1, 3), faces.flatten())
                pbr   = METAL_PBR.get(self.active_metal, {
                    "color": list(self._hex_to_rgb(self._get_color_for_model(name))),
                    "metallic": 0.70, "roughness": 0.30,
                })
                actor = self.plotter.add_mesh(mesh, smooth_shading=True, **pbr)
                self._pv_actors[name] = {"model": actor, "fill": None}

        for name in list(self._pv_actors):
            if name not in self.models:
                self.plotter.remove_actor(self._pv_actors[name]["model"])
                if self._pv_actors[name]["fill"]:
                    self.plotter.remove_actor(self._pv_actors[name]["fill"])
                del self._pv_actors[name]

        # ----------------------------------------------------------------
        # 2. Update transform matrices (no vertex copy — GPU-side transform)
        # ----------------------------------------------------------------
        for name in self.models:
            if name in self._pv_actors:
                self._pv_actors[name]["model"].user_matrix = (
                    self._build_user_matrix(self.transforms[name])
                )
                try:
                    self._pv_actors[name]["model"].SetVisibility(self.overlay_mode != "xray")
                except Exception:
                    pass

        # ----------------------------------------------------------------
        # 3. Fill animation overlay — remove old, add new
        # ----------------------------------------------------------------
        for info in self._pv_actors.values():
            if info["fill"]:
                self.plotter.remove_actor(info["fill"])
                info["fill"] = None

        if anim_frac > 0 or self._solidify_frac > 0 or self.overlay_mode:
            for name, data in self.models.items():
                verts = self._apply_transform(data["render_data"], self.transforms[name])
                keep = self._clip_mask(verts)
                if self.overlay_mode in ("draft", "undercut"):
                    self._add_pv_inspect_overlay(name, verts)
                    continue
                if self.overlay_mode:
                    self._add_pv_result_overlay(name, verts)
                    continue
                if self._solidify_frac > 0:
                    self._add_pv_solidify_overlay(name, verts)
                    continue
                heat_colors = self._compute_heat_colors(verts, anim_frac)
                fill_mask   = self._fill_mask(verts, anim_frac) & keep
                if fill_mask.sum() > 0:
                    fv     = verts[fill_mask]
                    n_f    = len(fv)
                    ff     = np.hstack([np.full((n_f, 1), 3),
                                        np.arange(n_f * 3).reshape(-1, 3)])
                    fmesh  = PolyData(fv.reshape(-1, 3), ff.flatten())
                    factor = self.plotter.add_mesh(
                        fmesh,
                        scalars=heat_colors[fill_mask][:, :3],
                        rgb=True,
                        smooth_shading=True,
                    )
                    self._pv_actors[name]["fill"] = factor

        # ----------------------------------------------------------------
        # 4. Flask / ceramic-shell outline — cached, rebuild on bounds/size
        # ----------------------------------------------------------------
        flask_key = (
            round(zmin, 1), round(zmax, 1), self.flask_size,
            round(self.flask_height_in, 2), round(z_part, 1),
            self.mold_kind, round(self.shell_mm, 1), round(self.printed_mm, 1),
        )
        if flask_key != self._pv_flask_key:
            for a in self._pv_flask_actors:
                self.plotter.remove_actor(a)
            self._pv_flask_actors.clear()
            self._pv_flask_key = flask_key
            if self.mold_kind == "shell":
                self._draw_shell_outline_pv(z_part)
            elif self.mold_kind == "printed":
                self._draw_printed_outline_pv(z_part)
            else:
                fw_mm = self.flask_size[0] * 25.4
                fh_mm = self.flask_size[1] * 25.4
                hw, hh = fw_mm / 2, fh_mm / 2
                xs = [-hw, hw, hw, -hw, -hw]
                ys = [-hh, -hh, hh, hh, -hh]
                z_bot, z_top = self._flask_z_extents(zmin, zmax)
                for z, col, lw in [(z_bot, "#45475A", 2),
                                    (z_top, "#45475A", 2),
                                    (z_part,   "#89B4FA", 3)]:
                    pts  = np.column_stack([xs, ys, [z] * 5])
                    line = pv.PolyData(pts)
                    line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
                    self._pv_flask_actors.append(
                        self.plotter.add_mesh(line, color=col, line_width=lw)
                    )

        # ----------------------------------------------------------------
        # 5. Gating actors — cached by config key, rebuild on change
        # ----------------------------------------------------------------
        gating_key = self._gating_state_key(z_part, zmax)
        if gating_key != self._pv_gating_key:
            for a in self._pv_gating_actors:
                self.plotter.remove_actor(a)
            self._pv_gating_actors.clear()
            self._pv_gating_key = gating_key
            self._build_pv_gating_actors(z_part, zmax)

        # ----------------------------------------------------------------
        # 6. Particle overlay — rebuild each frame (dynamic by design)
        # ----------------------------------------------------------------
        for a in self._pv_particle_actors:
            self.plotter.remove_actor(a)
        self._pv_particle_actors.clear()
        if anim_frac > 0 and "Tapered Sprue" in self.gating:
            self._draw_sprue_particles_pv(z_part, anim_frac)
        self._draw_choke_marker_pv(z_part, zmax)
        self._draw_clock_pv()
        self._draw_clip_plane_pv()
        if self.overlay_mode == "xray":
            self._draw_xray_points_pv()

        self.plotter.render()



    def _draw_flask_outline(self, z_part: float):
        if self.mold_kind == "shell":
            self._draw_shell_outline_mpl(z_part)
            return
        if self.mold_kind == "printed":
            self._draw_printed_outline_mpl(z_part)
            return
        fw_mm = self.flask_size[0] * 25.4
        fh_mm = self.flask_size[1] * 25.4
        hw, hh = fw_mm / 2, fh_mm / 2


        xs = [-hw, hw, hw, -hw, -hw]
        ys = [-hh, -hh, hh, hh, -hh]

        _, _, _, _, zmin, zmax = self._compute_bounds()
        z_bot, z_top = self._flask_z_extents(zmin, zmax)

        for z, color in [(z_bot, "#45475A"), (z_top, "#45475A"), (z_part, "#89B4FA")]:
            self.ax.plot(xs, ys, [z] * 5, color=color,
                         linestyle="--" if z != z_part else "-",
                         linewidth=1.2 if z != z_part else 1.8, alpha=0.7)


        from mpl_toolkits.mplot3d.art3d import Poly3DCollection as P3
        plane_verts = [[[-hw, -hh, z_part], [hw, -hh, z_part],
                        [hw,  hh, z_part], [-hw, hh, z_part]]]
        self.ax.add_collection3d(
            P3(plane_verts, facecolors=[(0.537, 0.706, 0.980, 0.08)],
               edgecolors="none"))

    def _draw_shell_outline_mpl(self, z_part: float):
        xmin, xmax, ymin, ymax, zmin, zmax = self._shell_aabb()
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection as P3
        rgb = self._hex_to_rgb(SHELL_COLOR)
        faces = self._box_faces(xmin, xmax, ymin, ymax, zmin, zmax)
        self.ax.add_collection3d(
            P3(faces, facecolors=[rgb + (0.12,)] * 6, edgecolors=SHELL_COLOR,
               linewidths=0.8, alpha=0.12)
        )
        corners, edges = self._box_edges(xmin, xmax, ymin, ymax, zmin, zmax)
        for a, b in edges:
            p0, p1 = corners[a], corners[b]
            self.ax.plot([p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
                         color=SHELL_COLOR, linewidth=1.1, alpha=0.85)
        self.ax.plot(
            [xmin, xmax, xmax, xmin, xmin],
            [ymin, ymin, ymax, ymax, ymin],
            [z_part] * 5,
            color="#89B4FA", linewidth=1.6, alpha=0.7,
        )

    def _draw_printed_outline_mpl(self, z_part: float):
        xmin, xmax, ymin, ymax, zmin, zmax = self._printed_aabb()
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection as P3
        rgb = self._hex_to_rgb(PRINTED_SAND_COLOR)
        faces = self._box_faces(xmin, xmax, ymin, ymax, zmin, zmax)
        self.ax.add_collection3d(
            P3(faces, facecolors=[rgb + (0.10,)] * 6, edgecolors=PRINTED_SAND_COLOR,
               linewidths=0.8, alpha=0.10)
        )
        corners, edges = self._box_edges(xmin, xmax, ymin, ymax, zmin, zmax)
        for a, b in edges:
            p0, p1 = corners[a], corners[b]
            self.ax.plot([p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
                         color=PRINTED_SAND_COLOR, linewidth=1.1, alpha=0.9)

    def _draw_printed_outline_pv(self, z_part: float):
        xmin, xmax, ymin, ymax, zmin, zmax = self._printed_aabb()
        box = pv.Box(bounds=(xmin, xmax, ymin, ymax, zmin, zmax))
        self._pv_flask_actors.append(
            self.plotter.add_mesh(
                box, color=PRINTED_SAND_COLOR, opacity=0.10, show_edges=True,
                edge_color=PRINTED_SAND_COLOR, line_width=1,
            )
        )



    def _draw_flask_outline_pv(self, z_part: float):

        """Draw flask outline using PyVista."""
        if self.mold_kind == "shell":
            self._draw_shell_outline_pv(z_part)
            return
        if self.mold_kind == "printed":
            self._draw_printed_outline_pv(z_part)
            return

        fw_mm = self.flask_size[0] * 25.4
        fh_mm = self.flask_size[1] * 25.4
        hw, hh = fw_mm / 2, fh_mm / 2


        xs = [-hw, hw, hw, -hw, -hw]
        ys = [-hh, -hh, hh, hh, -hh]


        _, _, _, _, zmin, zmax = self._compute_bounds()
        z_bot, z_top = self._flask_z_extents(zmin, zmax)

        # Draw bottom and top lines
        for z in [z_bot, z_top]:
            points = np.column_stack([xs, ys, [z] * 5])
            line = pv.PolyData(points)
            line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
            self.plotter.add_mesh(line, color="#45475A", line_width=2)


        # Draw parting plane
        points = np.column_stack([xs, ys, [z_part] * 5])
        line = pv.PolyData(points)
        line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
        self.plotter.add_mesh(line, color="#89B4FA", line_width=3)

    def _draw_shell_outline_pv(self, z_part: float):
        xmin, xmax, ymin, ymax, zmin, zmax = self._shell_aabb()
        box = pv.Box(bounds=(xmin, xmax, ymin, ymax, zmin, zmax))
        self._pv_flask_actors.append(
            self.plotter.add_mesh(
                box, color=SHELL_COLOR, opacity=0.12, show_edges=True,
                edge_color=SHELL_COLOR, line_width=1,
            )
        )
        xs = [xmin, xmax, xmax, xmin, xmin]
        ys = [ymin, ymin, ymax, ymax, ymin]
        pts = np.column_stack([xs, ys, [z_part] * 5])
        line = pv.PolyData(pts)
        line.lines = np.array([len(xs), 0, 1, 2, 3, 4, 0])
        self._pv_flask_actors.append(
            self.plotter.add_mesh(line, color="#89B4FA", line_width=2)
        )



    # ------------------------------------------------------------------
    # New helper methods
    # ------------------------------------------------------------------

    def set_active_metal(self, name: str) -> None:
        """Update the active metal; forces PyVista model actors to recreate
        with the new per-metal PBR material on next render."""
        if self.active_metal == name:
            return
        self.active_metal = name
        if self.use_pyvista and self._pv_actors:
            for info in self._pv_actors.values():
                self.plotter.remove_actor(info["model"])
                if info["fill"]:
                    self.plotter.remove_actor(info["fill"])
            self._pv_actors.clear()
            self.render(self._anim_frac)

    def _build_user_matrix(self, t: dict) -> np.ndarray:
        """4×4 homogeneous transform (scale + Z-rotation + XYZ offset)."""
        off = t["offset"]
        rot = math.radians(t["rotation"])
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        s = float(self._display_scale())
        mat = np.eye(4, dtype=np.float64)
        mat[0, 0], mat[0, 1] =  s * cos_r, -s * sin_r
        mat[1, 0], mat[1, 1] =  s * sin_r,  s * cos_r
        mat[2, 2] = s
        mat[0, 3], mat[1, 3], mat[2, 3] = float(off[0]), float(off[1]), float(off[2])
        return mat

    def _apply_transform(
        self, render_data: np.ndarray, t: dict, scale: float | None = None,
    ) -> np.ndarray:
        """World-space triangles. ``scale=None`` uses the display (as-cast vs shrink) factor."""
        s = float(self._display_scale() if scale is None else scale)
        return transform_triangles(
            render_data,
            offset=t["offset"],
            rotation_deg=t["rotation"],
            scale=s,
        )

    def _clear_mpl_overlays(self) -> None:
        """Remove all matplotlib artists except persistent model collections."""
        persistent = {
            id(c)
            for colls in self._mpl_model_collections.values()
            for c in colls.values()
            if c is not None
        }
        for artist in list(self.ax.collections):
            if id(artist) not in persistent:
                artist.remove()
        for line in list(self.ax.lines):
            line.remove()
        for text in list(self.ax.texts):
            text.remove()

    def _build_pv_gating_actors(self, z_part: float, zmax: float) -> None:
        """Create PyVista mesh actors for all active gating components and
        append them to self._pv_gating_actors."""
        _gating_colors = {
            "Tapered Sprue":       ("#FF6600", 0.80),
            "Runner (Horizontal)": ("#B87333", 0.80),
            "Fan Gate":            ("#FFBF00", 0.80),
            "Riser (Open)":        ("#C0C0C0", 0.70),
        }
        if self.selected_gating in _gating_colors:
            c, _ = _gating_colors[self.selected_gating]
            _gating_colors[self.selected_gating] = ("#FFFFFF", 1.0) if False else (c, 1.0)
        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
            faces = self._make_cylinder_mesh(
                cx=sx, cy=sy, z_bottom=z_bot,
                r_bottom=self.sprue_bottom_radius,
                r_top=self.sprue_top_radius,
                height=sprue_h, sides=24,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Tapered Sprue"])

        if "Runner (Horizontal)" in self.gating:
            sx, sy = self.sprue_offset
            ry = sy + self.runner_y_offset
            faces = self._make_box_mesh(
                cx=sx, cy=ry, z_bottom=z_part - self.runner_height / 2.0,
                width=self._effective_runner_length(), depth=self.runner_width, height=self.runner_height,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Runner (Horizontal)"])

        if "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            faces = self._make_cylinder_mesh(
                cx=rx, cy=ry, z_bottom=z_part,
                r_bottom=self.riser_radius, r_top=self.riser_radius,
                height=self.riser_height, sides=24,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Riser (Open)"])

        if "Fan Gate" in self.gating:
            sx, sy = self.sprue_offset
            gw, gd, gh = self._gate_box()
            faces = self._make_box_mesh(
                cx=sx, cy=sy - gd / 2.0, z_bottom=z_part - gh / 2.0,
                width=gw, depth=gd, height=gh,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Fan Gate"])

        if "Second Gate" in self.gating:
            gx, gy = self.gate2_offset
            gw, gd, gh = self._gate_box()
            faces = self._make_box_mesh(
                cx=gx, cy=gy, z_bottom=z_part - gh / 2.0,
                width=gw, depth=gd, height=gh,
            )
            self._add_pv_gating_mesh(faces, GATE2_COLOR, 0.85)

        if "Foam Filter" in self.gating:
            sx, sy = self.sprue_offset
            side = max(12.0, math.sqrt(max(self.filter_area, 100.0)))
            faces = self._make_box_mesh(
                cx=sx, cy=sy + 18.0, z_bottom=z_part - 6.0,
                width=side, depth=8.0, height=12.0,
            )
            self._add_pv_gating_mesh(faces, FILTER_COLOR, 0.9)

        if "Pour Basin" in self.gating and "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
            faces = self._make_cylinder_mesh(
                cx=sx, cy=sy, z_bottom=z_bot + sprue_h,
                r_bottom=self.basin_radius, r_top=self.basin_radius * 1.15,
                height=self.basin_height, sides=20,
            )
            self._add_pv_gating_mesh(faces, BASIN_COLOR, 0.75)

        if "Riser (Open)" in self.gating and self.neck_height > 0:
            rx, ry = self.riser_offset
            faces = self._make_cylinder_mesh(
                cx=rx, cy=ry, z_bottom=z_part - self.neck_height,
                r_bottom=self.neck_radius, r_top=self.neck_radius,
                height=self.neck_height, sides=16,
            )
            self._add_pv_gating_mesh(faces, RISER_COLOR, 0.9)
            if self.riser_blind:
                cap = self._make_cylinder_mesh(
                    cx=rx, cy=ry, z_bottom=z_part + self.riser_height - 3.0,
                    r_bottom=self.riser_radius + 1.0, r_top=self.riser_radius + 1.0,
                    height=4.0, sides=16,
                )
                self._add_pv_gating_mesh(cap, RISER_COLOR, 0.95)

        self._add_pv_chills(z_part)

    def _add_pv_gating_mesh(self, faces: np.ndarray, color: str,
                             opacity: float) -> None:
        """Convert a triangle-face array to PolyData and add to the plotter."""
        n = len(faces)
        pv_faces = np.hstack([np.full((n, 1), 3), np.arange(n * 3).reshape(-1, 3)])
        mesh  = PolyData(faces.reshape(-1, 3), pv_faces.flatten())
        actor = self.plotter.add_mesh(mesh, color=color, opacity=opacity,
                                      smooth_shading=True)
        self._pv_gating_actors.append(actor)

    def _draw_gating(self, z_part: float):

        """Draw 3D gating geometry into the current axes, using a geometry cache.

        Mesh generation and shading are skipped when the gating configuration and
        positional parameters have not changed since the last draw (e.g. during
        fill animation where gating is static).
        """

        if not self.models:
            return
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        _, _, _, _, _, zmax = self._compute_bounds()

        # Build a lightweight key from every param that affects gating geometry.
        cache_key = self._gating_state_key(z_part, zmax)
        if cache_key != self._gating_cache_key:
            self._gating_geo_cache.clear()
            self._gating_cache_key = cache_key

        def _get(key, builder):
            """Return cached (faces, colors) or compute and cache."""
            if key not in self._gating_geo_cache:
                self._gating_geo_cache[key] = builder()
            return self._gating_geo_cache[key]

        # --- Tapered Sprue ---
        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            def _build_sprue():
                z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
                faces = self._make_cylinder_mesh(
                    cx=sx, cy=sy, z_bottom=z_bot,
                    r_bottom=self.sprue_bottom_radius,
                    r_top=self.sprue_top_radius,
                    height=sprue_h, sides=24,
                )
                colors = self._shade_faces(faces, self._hex_to_rgb(SPRUE_COLOR), alpha=0.85)
                return faces, colors
            faces, colors = _get("sprue", _build_sprue)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        # --- Runner ---
        if "Runner (Horizontal)" in self.gating:
            sx, sy = self.sprue_offset
            ry = sy + self.runner_y_offset
            def _build_runner():
                faces = self._make_box_mesh(
                    cx=sx, cy=ry, z_bottom=z_part - self.runner_height / 2.0,
                    width=self._effective_runner_length(), depth=self.runner_width, height=self.runner_height,
                )
                colors = self._shade_faces(faces, self._hex_to_rgb(RUNNER_COLOR), alpha=0.85)
                return faces, colors
            faces, colors = _get("runner", _build_runner)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        # --- Riser ---
        if "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            def _build_riser():
                faces = self._make_cylinder_mesh(
                    cx=rx, cy=ry, z_bottom=z_part,
                    r_bottom=self.riser_radius, r_top=self.riser_radius,
                    height=self.riser_height, sides=24,
                )
                colors = self._shade_faces(faces, self._hex_to_rgb(RISER_COLOR), alpha=0.75)
                return faces, colors
            faces, colors = _get("riser", _build_riser)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        # --- Fan Gate ---
        if "Fan Gate" in self.gating:
            sx, sy = self.sprue_offset
            def _build_gate():
                gw, gd, gh = self._gate_box()
                faces = self._make_box_mesh(
                    cx=sx, cy=sy - gd / 2.0, z_bottom=z_part - gh / 2.0,
                    width=gw, depth=gd, height=gh,
                )
                colors = self._shade_faces(faces, self._hex_to_rgb(GATE_COLOR), alpha=0.85)
                return faces, colors
            faces, colors = _get("gate", _build_gate)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        if "Second Gate" in self.gating:
            gx, gy = self.gate2_offset
            gw, gd, gh = self._gate_box()
            faces = self._make_box_mesh(
                cx=gx, cy=gy, z_bottom=z_part - gh / 2.0,
                width=gw, depth=gd, height=gh,
            )
            colors = self._shade_faces(faces, self._hex_to_rgb(GATE2_COLOR), alpha=0.85)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        if "Foam Filter" in self.gating:
            sx, sy = self.sprue_offset
            side = max(12.0, math.sqrt(max(self.filter_area, 100.0)))
            faces = self._make_box_mesh(
                cx=sx, cy=sy + 18.0, z_bottom=z_part - 6.0,
                width=side, depth=8.0, height=12.0,
            )
            colors = self._shade_faces(faces, self._hex_to_rgb(FILTER_COLOR), alpha=0.9)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        if "Pour Basin" in self.gating and "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            _, _, _, _, _, zmax = self._compute_bounds()
            z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
            faces = self._make_cylinder_mesh(
                cx=sx, cy=sy, z_bottom=z_bot + sprue_h,
                r_bottom=self.basin_radius, r_top=self.basin_radius * 1.15,
                height=self.basin_height, sides=20,
            )
            colors = self._shade_faces(faces, self._hex_to_rgb(BASIN_COLOR), alpha=0.75)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        if "Riser (Open)" in self.gating and self.neck_height > 0:
            rx, ry = self.riser_offset
            faces = self._make_cylinder_mesh(
                cx=rx, cy=ry, z_bottom=z_part - self.neck_height,
                r_bottom=self.neck_radius, r_top=self.neck_radius,
                height=self.neck_height, sides=16,
            )
            colors = self._shade_faces(faces, self._hex_to_rgb(RISER_COLOR), alpha=0.9)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))
        if "Riser (Open)" in self.gating and self.riser_blind:
            rx, ry = self.riser_offset
            cap = self._make_cylinder_mesh(
                cx=rx, cy=ry, z_bottom=z_part + self.riser_height - 3.0,
                r_bottom=self.riser_radius + 1.0, r_top=self.riser_radius + 1.0,
                height=4.0, sides=16,
            )
            colors = self._shade_faces(cap, self._hex_to_rgb(RISER_COLOR), alpha=0.95)
            self.ax.add_collection3d(Poly3DCollection(
                cap, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))

        self._draw_chills_mpl(z_part)



    def _draw_sprue_particles(self, z_part: float, anim_frac: float):

        """Draw particle stream from sprue during fill animation (single batch scatter).

        Args:
            z_part: Parting line z coordinate
            anim_frac: Animation fraction (0.0 to 1.0) controlling particle emission
        """

        if not self.models or "Tapered Sprue" not in self.gating or anim_frac <= 0:
            return
        sx, sy = self.sprue_offset
        _, _, _, _, zmin, zmax = self._compute_bounds()
        z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
        top_z = z_bot + sprue_h

        np.random.seed(int(anim_frac * 1000) % 1000)
        n_particles = int(15 + anim_frac * 5)
        r_max = 20.0 * (1.0 - anim_frac * 0.5)
        theta = np.random.uniform(0, 2 * np.pi, n_particles)
        r     = np.random.uniform(0, r_max,     n_particles)
        xs = sx + r * np.cos(theta)
        ys = sy + r * np.sin(theta)
        z_pos = zmin + anim_frac * (top_z - zmin) - (1.0 - anim_frac) * 20
        zs = np.full(n_particles, z_pos)
        particle_size = 1.5 + anim_frac * 2.0
        self.ax.scatter(xs, ys, zs, c="orange", s=particle_size, alpha=0.9)



    def _draw_sprue_particles_pv(self, z_part: float, anim_frac: float):

        """Draw particle stream from sprue during fill animation - PyVista version.

        Uses a single PolyData point cloud instead of one sphere mesh per particle.

        Args:
            z_part: Parting line z coordinate
            anim_frac: Animation fraction (0.0 to 1.0) controlling particle emission
        """

        if not self.models or "Tapered Sprue" not in self.gating or anim_frac <= 0:
            return
        sx, sy = self.sprue_offset
        _, _, _, _, zmin, zmax = self._compute_bounds()
        z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
        top_z = z_bot + sprue_h

        np.random.seed(int(anim_frac * 1000) % 1000)
        n_particles = int(15 + anim_frac * 5)
        r_max = 20.0 * (1.0 - anim_frac * 0.5)
        theta = np.random.uniform(0, 2 * np.pi, n_particles)
        r     = np.random.uniform(0, r_max,     n_particles)
        xs = sx + r * np.cos(theta)
        ys = sy + r * np.sin(theta)
        z_pos = zmin + anim_frac * (top_z - zmin) - (1.0 - anim_frac) * 20
        zs = np.full(n_particles, z_pos)

        points = np.column_stack([xs, ys, zs])
        cloud  = pv.PolyData(points)
        particle_size = 1.5 + anim_frac * 2.0
        actor = self.plotter.add_mesh(
            cloud,
            color="orange",
            point_size=particle_size * 4,
            render_points_as_spheres=True,
            opacity=min(0.9, 0.5 + anim_frac),
        )
        self._pv_particle_actors.append(actor)



    def _draw_defect_markers(self, defects, vsr: float = 1.0):

        """Draw colored spheres at defect risk regions.

        Args:
            defects: List of defect descriptions. Each can be:
                - String description (generic placement)
                - Tuple (type, x, y, z) with coordinates
            vsr: Volume-to-surface ratio (cm) used to scale marker radius.
        """

        if not self.models or not defects:
            return
        marker_r = max(4.0, min(vsr * 8.0, 20.0))
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
                sphere = pv.Sphere(radius=marker_r, center=(x, y, z))
                self.plotter.add_mesh(sphere, color="red", opacity=0.8)
            elif dtype in ("cold_shut", "cold shut", "cold_shut_risk"):
                sphere = pv.Sphere(radius=marker_r, center=(x, y, z))
                self.plotter.add_mesh(sphere, color="yellow", opacity=0.8)
            elif dtype in ("misrun", "misrun_risk"):
                sphere = pv.Sphere(radius=marker_r, center=(x, y, z))
                self.plotter.add_mesh(sphere, color="orange", opacity=0.8)
            else:
                desc = defect.lower() if isinstance(defect, str) else ""
                if "shrinkage" in desc or "porosity" in desc:
                    sphere = pv.Sphere(radius=marker_r, center=(x, y, z))
                    self.plotter.add_mesh(sphere, color="red", opacity=0.8)
                elif "cold" in desc:
                    sphere = pv.Sphere(radius=marker_r, center=(x, y, z))
                    self.plotter.add_mesh(sphere, color="yellow", opacity=0.8)
                elif "misrun" in desc:
                    sphere = pv.Sphere(radius=marker_r, center=(x, y, z))
                    self.plotter.add_mesh(sphere, color="orange", opacity=0.8)



    def _draw_defect_markers_matplotlib(self, defects, vsr: float = 1.0):

        """Draw defect markers using matplotlib."""

        if not self.models or not defects:
            return
        marker_s = max(80, min(int(vsr * 160), 400))
        _, _, _, _, zmin, zmax = self._compute_bounds()
        colors = {"shrinkage": "red", "shrinkage_risk": "red",
                  "cold_shut": "yellow", "cold_shut_risk": "yellow",
                  "misrun": "orange", "misrun_risk": "orange"}
        for i, defect in enumerate(defects):
            dtype = ""
            if isinstance(defect, tuple) and len(defect) >= 4:
                dtype = defect[0].lower()
                x, y, z = defect[1], defect[2], defect[3]
            else:
                rng = random.Random(i)
                x = rng.uniform(-10, 10)
                y = rng.uniform(-10, 10)
                z = zmax + 30 + i * 8
            desc = defect.lower() if isinstance(defect, str) else ""
            if dtype in colors:
                color = colors[dtype]
            elif "shrinkage" in desc or "porosity" in desc:
                color = "red"
            elif "cold" in desc:
                color = "yellow"
            elif "misrun" in desc:
                color = "orange"
            else:
                color = "gray"
            self.ax.scatter(x, y, z, c=color, s=marker_s, marker="o", depthshade=True)

    def draw_defect_markers(self, defects: list, vsr: float = 1.0) -> None:

        """Public method to draw defect markers using current backend."""

        if self.use_pyvista:
            self._draw_defect_markers(defects, vsr)
        else:
            self._draw_defect_markers_matplotlib(defects, vsr)



    # ------------------------------------------------------------------

    # Shading helpers

    # ------------------------------------------------------------------



    def _shade_faces(self, verts: np.ndarray, base_rgb, alpha: float = 1.0):

        """Per-face Phong-style shading — 3-light rig, fully vectorised, GPU-ready."""

        v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
        normals = xp.asarray(np.cross(v1 - v0, v2 - v0).astype(np.float64))
        lengths = xp.linalg.norm(normals, axis=1, keepdims=True)
        lengths[lengths == 0] = 1e-9
        normals /= lengths

        # Vectorised 3-light dot products: (n, 3) @ (3, 3).T → (n, 3)
        dots = xp.clip(normals @ xp.asarray(_LIGHT_DIRS.T), 0.0, 1.0)
        intensities = xp.clip(dots @ xp.asarray(_LIGHT_STRENGTHS) + 0.18, 0.0, 1.0)

        br, bg, bb = base_rgb
        colors = np.column_stack([
            np.clip(float(br) * np.asarray(intensities), 0, 1),
            np.clip(float(bg) * np.asarray(intensities), 0, 1),
            np.clip(float(bb) * np.asarray(intensities), 0, 1),
            np.full(len(verts), alpha),
        ])
        return colors

    def _compute_heat_colors(self, verts: np.ndarray, anim_frac: float) -> np.ndarray:
        """Compute per-triangle heat colours using the plasma LUT (GPU-ready).

        Molten metal (below fill level) → plasma bright yellow/orange.
        Cooling zone (just above fill) → plasma red/orange fading to steel grey.
        Solidified (well above fill) → steel grey.

        Args:
            verts: Triangle vertices array of shape (n_tris, 3, 3)
            anim_frac: Animation fraction (0.0–1.0) representing fill level
        Returns:
            RGBA colour array of shape (n_tris, 4)
        """
        centroids_z = verts[:, :, 2].mean(axis=1)
        z_min = float(centroids_z.min())
        z_max = float(centroids_z.max())
        z_range = max(z_max - z_min, 1e-9)
        fill_z  = z_min + (z_max - z_min) * anim_frac
        rel_pos = (centroids_z - fill_z) / z_range   # <0 hot, >0 cooling/cold

        # Plasma LUT lookup: hot=0.95 (yellow), cooling edge=0.30 (deep red)
        _COOL_RANGE = 0.35   # wider band → softer thermal gradient, no hard waterline
        t = np.clip(rel_pos / _COOL_RANGE, 0.0, 1.0) ** 0.5  # sqrt easing — gradual fade
        lut_idx = np.clip(((0.95 - 0.30) * (1.0 - t) + 0.30) * 255,
                          0, 255).astype(np.int32)
        rgb = _PLASMA_LUT[lut_idx].astype(np.float64)   # (n, 3) from LUT

        # Replace fully solidified triangles with steel grey
        solidified_grey = np.array([0.62, 0.62, 0.65])
        solid_mask = rel_pos > _COOL_RANGE
        rgb[solid_mask] = solidified_grey

        alpha = np.where(rel_pos <= 0, 0.92, 0.78)
        return np.column_stack([rgb, alpha])

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

        hw, hd = width / 2, depth / 2


        corners = np.array([
            [cx - hw, cy - hd, z_bottom],
            [cx + hw, cy - hd, z_bottom],
            [cx + hw, cy + hd, z_bottom],
            [cx - hw, cy + hd, z_bottom],
            [cx - hw, cy - hd, z_bottom + height],
            [cx + hw, cy - hd, z_bottom + height],
            [cx + hw, cy + hd, z_bottom + height],
            [cx - hw, cy + hd, z_bottom + height],
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

    def _metal_rgb(self) -> tuple:
        pbr = METAL_PBR.get(self.active_metal, {})
        return self._hex_to_rgb(pbr.get("color", "#C8C8C8"))

    def _flask_z_extents(self, zmin: float, zmax: float) -> tuple[float, float]:
        """Drag floor and cope lid from the flask height (inches) and part AABB."""
        z_bot = zmin - 10.0
        z_top = max(zmax + 10.0, z_bot + float(self.flask_height_in) * 25.4)
        return z_bot, z_top

    def _shell_aabb(self) -> tuple[float, float, float, float, float, float]:
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        if not self.models:
            xmin, xmax, ymin, ymax, zmin, zmax = -40.0, 40.0, -40.0, 40.0, 0.0, 80.0
        t = float(self.printed_mm if self.mold_kind == "printed" else self.shell_mm)
        return xmin - t, xmax + t, ymin - t, ymax + t, zmin - t, zmax + t

    def _printed_aabb(self):
        return self._shell_aabb()

    def _box_edges(self, xmin, xmax, ymin, ymax, zmin, zmax):
        corners = [
            (xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
            (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax),
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        return corners, edges

    def _box_faces(self, xmin, xmax, ymin, ymax, zmin, zmax):
        return [
            [[xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymax, zmin], [xmin, ymax, zmin]],
            [[xmin, ymin, zmax], [xmax, ymin, zmax], [xmax, ymax, zmax], [xmin, ymax, zmax]],
            [[xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymin, zmax], [xmin, ymin, zmax]],
            [[xmin, ymax, zmin], [xmax, ymax, zmin], [xmax, ymax, zmax], [xmin, ymax, zmax]],
            [[xmin, ymin, zmin], [xmin, ymax, zmin], [xmin, ymax, zmax], [xmin, ymin, zmax]],
            [[xmax, ymin, zmin], [xmax, ymax, zmin], [xmax, ymax, zmax], [xmax, ymin, zmax]],
        ]

    def _sprue_z_and_height(self, z_part: float, zmax: float) -> tuple[float, float]:
        """Sprue sits on the parting plane and rises through the cope to the basin."""
        cope = max(0.0, float(zmax) - float(z_part))
        return float(z_part), float(self.sprue_height) + cope

    def _display_scale(self) -> float:
        return 1.0 if self.show_as_cast else float(self.shrink_scale)

    def _gate_xyz(self, scale: float | None = None) -> np.ndarray:
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds(scale)
        z_part = zmin + max(zmax - zmin, 1.0) * self.parting_z
        sx, sy = float(self.sprue_offset[0]), float(self.sprue_offset[1])
        if "Fan Gate" in self.gating:
            return np.array([sx, sy - 4.0, z_part], dtype=np.float64)
        return np.array([sx, sy, z_part], dtype=np.float64)

    def rescale_world_point(self, xyz, scale: float) -> np.ndarray:
        """Re-express a display-space click at ``scale`` (cavity / pattern)."""
        t = self.transforms.get(self.active_model)
        if t is None and self.transforms:
            t = next(iter(self.transforms.values()))
        off = (t or {}).get("offset") or (0.0, 0.0, 0.0)
        return _rescale_world_point(
            xyz, offset=off, from_scale=self._display_scale(), to_scale=scale,
        )

    def _fill_mask(self, verts: np.ndarray, anim_frac: float) -> np.ndarray:
        """Fill from the gate outward (voxel flood order, else distance)."""
        field = self._face_sim_field(verts, "fill")
        if field is not None and len(field) == len(verts):
            mx = max(float(np.max(field)), 1.0)
            return field / mx <= max(float(anim_frac), 0.0)
        centroids = verts.mean(axis=1)
        d = np.linalg.norm(centroids - self._gate_xyz(), axis=1)
        dmax = max(float(d.max()), 1e-6)
        return d / dmax <= max(float(anim_frac), 0.0)

    def _gate_box(self) -> tuple[float, float, float]:
        """Fan-gate width × depth × height from hydraulic area."""
        area = max(float(self.gate_area), 10.0)
        height = 6.0
        width = float(min(80.0, max(20.0, math.sqrt(area * 4.0))))
        depth = float(min(16.0, max(4.0, area / max(width, 1.0))))
        return width, depth, height

    def _clip_mask(self, verts: np.ndarray) -> np.ndarray:
        if verts is None or len(verts) == 0:
            return np.zeros(0, dtype=bool)
        if not self.clip_enabled:
            return np.ones(len(verts), dtype=bool)
        axis = int(self.clip_axis) % 3
        cents = verts.mean(axis=1)
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        lo = (xmin, ymin, zmin)[axis]
        hi = (xmax, ymax, zmax)[axis]
        plane = lo + float(self.clip_frac) * max(hi - lo, 1.0)
        return cents[:, axis] <= plane + 1e-6

    def _clip_plane_geom(self) -> tuple[np.ndarray, np.ndarray] | None:
        if not self.clip_enabled or not self.models:
            return None
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        axis = int(self.clip_axis) % 3
        lo = (xmin, ymin, zmin)[axis]
        hi = (xmax, ymax, zmax)[axis]
        p = lo + float(self.clip_frac) * max(hi - lo, 1.0)
        pad = 4.0
        if axis == 0:
            pts = np.array([
                [p, ymin - pad, zmin - pad], [p, ymax + pad, zmin - pad],
                [p, ymax + pad, zmax + pad], [p, ymin - pad, zmax + pad],
            ], dtype=float)
        elif axis == 1:
            pts = np.array([
                [xmin - pad, p, zmin - pad], [xmax + pad, p, zmin - pad],
                [xmax + pad, p, zmax + pad], [xmin - pad, p, zmax + pad],
            ], dtype=float)
        else:
            pts = np.array([
                [xmin - pad, ymin - pad, p], [xmax + pad, ymin - pad, p],
                [xmax + pad, ymax + pad, p], [xmin - pad, ymax + pad, p],
            ], dtype=float)
        faces = np.array([[pts[0], pts[1], pts[2]], [pts[0], pts[2], pts[3]]])
        return pts, faces

    def _draw_clip_plane_mpl(self) -> None:
        geom = self._clip_plane_geom()
        if geom is None:
            return
        _, faces = geom
        self.ax.add_collection3d(Poly3DCollection(
            faces, facecolors=[(0.53, 0.70, 0.98, 0.18)] * 2,
            edgecolors="#89B4FA", linewidths=0.8,
        ))

    def _draw_clip_plane_pv(self) -> None:
        geom = self._clip_plane_geom()
        if geom is None or not self.use_pyvista:
            return
        _, faces = geom
        n = len(faces)
        ff = np.hstack([np.full((n, 1), 3), np.arange(n * 3).reshape(-1, 3)])
        mesh = PolyData(faces.reshape(-1, 3), ff.flatten())
        actor = self.plotter.add_mesh(mesh, color="#89B4FA", opacity=0.18)
        self._pv_particle_actors.append(actor)

    def set_sim_fields(self, fields: dict | None) -> None:
        self._sim_fields = fields or {}
        self.render(self._anim_frac)

    def set_clip(self, enabled: bool, axis: int | None = None, frac: float | None = None) -> None:
        self.clip_enabled = bool(enabled)
        if axis is not None:
            self.clip_axis = int(axis) % 3
        if frac is not None:
            self.clip_frac = float(np.clip(frac, 0.0, 1.0))
        self.render(self._anim_frac)

    def _face_sim_field(self, verts: np.ndarray, key: str) -> np.ndarray | None:
        arr = self._sim_fields.get(key)
        if arr is None:
            return None
        arr = np.asarray(arr)
        if len(arr) != len(verts):
            # Concatenated world mesh — try matching total face count
            chunks = []
            for name, data in self.models.items():
                v = self._apply_transform(data["render_data"], self.transforms[name])
                chunks.append(len(v))
            total = int(sum(chunks))
            if len(arr) != total:
                return None
            # Caller passes one model's verts; find its slice
            offset = 0
            for name, data in self.models.items():
                v = self._apply_transform(data["render_data"], self.transforms[name])
                n = len(v)
                if n == len(verts) and np.allclose(v[:1], verts[:1], atol=1e-3):
                    return arr[offset:offset + n]
                offset += n
            return None
        return arr

    def _scalar_rgba(self, values: np.ndarray, cmap: str = "coolwarm") -> np.ndarray:
        v = np.asarray(values, dtype=float)
        if len(v) == 0:
            return np.zeros((0, 4))
        lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
        t = (v - lo) / max(hi - lo, 1e-9)
        try:
            return np.asarray(_cm.get_cmap(cmap)(t))
        except Exception:
            rgba = np.zeros((len(t), 4))
            rgba[:, 0] = t
            rgba[:, 2] = 1.0 - t
            rgba[:, 3] = 1.0
            return rgba

    def _result_colors(self, name: str, verts: np.ndarray) -> np.ndarray:
        mode = self.overlay_mode
        if mode == "hotspot":
            thick = self._face_thickness(name, verts)
            return self._scalar_rgba(thick, "hot")
        if mode == "xray":
            rgba = np.tile(np.array(self._metal_rgb() + (0.14,)), (len(verts), 1))
            return rgba
        key = {"freeze": "freeze", "fill": "fill", "porosity": "porosity",
               "niyama": "niyama"}.get(mode)
        if key:
            field = self._face_sim_field(verts, key)
            if field is not None:
                cmap = "coolwarm" if key != "niyama" else "viridis"
                if key == "niyama":
                    field = -np.asarray(field)  # low Ny (risk) → hot
                return self._scalar_rgba(field, cmap)
            if mode == "freeze":
                thick = self._face_thickness(name, verts)
                return self._scalar_rgba(thick, "hot")
        return np.tile(np.array(self._metal_rgb() + (1.0,)), (len(verts), 1))

    def _add_mpl_result_overlay(self, name: str, verts: np.ndarray) -> None:
        colors = self._result_colors(name, verts)
        keep = self._clip_mask(verts)
        if not np.any(keep):
            return
        self.ax.add_collection3d(
            Poly3DCollection(verts[keep], facecolors=colors[keep], edgecolors="none")
        )

    def _add_pv_result_overlay(self, name: str, verts: np.ndarray) -> None:
        colors = self._result_colors(name, verts)[:, :3]
        keep = self._clip_mask(verts)
        if not np.any(keep):
            return
        fv, rgb = verts[keep], colors[keep]
        n_f = len(fv)
        ff = np.hstack([np.full((n_f, 1), 3), np.arange(n_f * 3).reshape(-1, 3)])
        fmesh = PolyData(fv.reshape(-1, 3), ff.flatten())
        opacity = 0.18 if self.overlay_mode == "xray" else 1.0
        actor = self.plotter.add_mesh(
            fmesh, scalars=rgb, rgb=True, smooth_shading=True, opacity=opacity,
        )
        self._pv_actors[name]["fill"] = actor

    def _draw_chills_mpl(self, z_part: float) -> None:
        if not self.chills:
            return
        rgb = self._hex_to_rgb(CHILL_COLOR)
        for c in self.chills:
            faces = self._make_cylinder_mesh(
                cx=float(c[0]), cy=float(c[1]),
                z_bottom=float(c[2]) - 4.0, r_bottom=8.0, r_top=8.0, height=8.0, sides=12,
            )
            colors = self._shade_faces(faces, rgb, alpha=0.9)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True,
            ))

    def _add_pv_chills(self, z_part: float) -> None:
        for c in self.chills:
            faces = self._make_cylinder_mesh(
                cx=float(c[0]), cy=float(c[1]),
                z_bottom=float(c[2]) - 4.0, r_bottom=8.0, r_top=8.0, height=8.0, sides=12,
            )
            self._add_pv_gating_mesh(faces, CHILL_COLOR, 0.9)

    def _draw_xray_points_mpl(self) -> None:
        hot = np.asarray(self._sim_fields.get("hot_xyz", np.zeros((0, 3))))
        poro = np.asarray(self._sim_fields.get("porosity_xyz", np.zeros((0, 3))))
        if hot.ndim != 2 or hot.shape[-1] != 3:
            hot = np.zeros((0, 3))
        if poro.ndim != 2 or poro.shape[-1] != 3:
            poro = np.zeros((0, 3))
        if len(hot):
            self.ax.scatter(hot[:, 0], hot[:, 1], hot[:, 2], c="#FAB387", s=12, alpha=0.7)
        if len(poro):
            self.ax.scatter(poro[:, 0], poro[:, 1], poro[:, 2], c="#F38BA8", s=22, alpha=0.9)

    def _draw_xray_points_pv(self) -> None:
        if not self.use_pyvista:
            return
        hot = np.asarray(self._sim_fields.get("hot_xyz", np.zeros((0, 3))))
        poro = np.asarray(self._sim_fields.get("porosity_xyz", np.zeros((0, 3))))
        if hot.ndim != 2 or hot.shape[-1] != 3:
            hot = np.zeros((0, 3))
        if poro.ndim != 2 or poro.shape[-1] != 3:
            poro = np.zeros((0, 3))
        if len(hot) >= 1:
            cloud = pv.PolyData(hot)
            self._pv_particle_actors.append(
                self.plotter.add_mesh(cloud, color="#FAB387", point_size=8, render_points_as_spheres=True)
            )
        if len(poro) >= 1:
            cloud = pv.PolyData(poro)
            self._pv_particle_actors.append(
                self.plotter.add_mesh(cloud, color="#F38BA8", point_size=12, render_points_as_spheres=True)
            )

    def set_solid_frac(self, frac: float) -> None:
        """Scrub solid fraction (0 = liquid, 1 = frozen). Feeding stops ~0.7."""
        self._solidify_frac = float(np.clip(frac, 0.0, 1.0))
        self._solid_frac_label = self._solidify_frac > 0
        if self.models:
            self.render(max(self._anim_frac, 1.0 if self._solidify_frac > 0 else 0.0))

    def place_gating(self, kind: str, x: float, y: float, z: float | None = None) -> None:
        """Drop sprue / gate / riser / chill at a clicked world XY."""
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        names = list(self.gating)
        zz = float(zmin if z is None else z)
        if kind == "sprue":
            self.sprue_offset = np.array([x, y], dtype=float)
            if "Tapered Sprue" not in names:
                names.append("Tapered Sprue")
            self.selected_gating = "Tapered Sprue"
        elif kind == "gate":
            self.sprue_offset = np.array([x, y], dtype=float)
            for n in ("Fan Gate", "Tapered Sprue", "Runner (Horizontal)"):
                if n not in names:
                    names.append(n)
            self.selected_gating = "Fan Gate"
        elif kind == "riser":
            self.riser_offset = np.array([x, y], dtype=float)
            if "Riser (Open)" not in names:
                names.append("Riser (Open)")
            self.selected_gating = "Riser (Open)"
        elif kind == "filter":
            # parked on the runner just past the sprue
            self.sprue_offset = np.array([x, y], dtype=float)
            if "Foam Filter" not in names:
                names.append("Foam Filter")
            if "Runner (Horizontal)" not in names:
                names.append("Runner (Horizontal)")
            self.selected_gating = "Foam Filter"
        elif kind == "gate2":
            self.gate2_offset = np.array([x, y], dtype=float)
            if "Second Gate" not in names:
                names.append("Second Gate")
            if "Fan Gate" not in names:
                names.append("Fan Gate")
            self.selected_gating = "Second Gate"
        elif kind == "chill":
            self.chills.append(np.array([x, y, zz], dtype=float))
        self.gating = names
        self.pick_mode = ""
        self.render(self._anim_frac)
        self.gating_moved.emit({
            "sprue_x": float(self.sprue_offset[0]),
            "sprue_y": float(self.sprue_offset[1]),
            "riser_x": float(self.riser_offset[0]),
            "riser_y": float(self.riser_offset[1]),
        })
        self.gating_list_changed.emit(list(self.gating))
        if kind != "chill" and self.selected_gating:
            self.gating_selected.emit(self.selected_gating)

    def _clock_label(self) -> str:
        if self._solid_frac_label and self._solidify_frac > 0:
            fs = self._solidify_frac
            extra = "   ·   feeding stopped" if fs >= FEEDING_STOP_FRAC else "   ·   still feeding"
            return f"Solid fraction {fs:.2f}{extra}"
        if self._solidify_frac > 0 and self._clock_solidify_min:
            t = self._solidify_frac * self._clock_solidify_min
            return f"Solidify {t:.2f} / {self._clock_solidify_min:.2f} min"
        if self._anim_frac > 0 and self._clock_fill_s:
            t = self._anim_frac * self._clock_fill_s
            extra = "   thin → first freeze" if False else ""
            return f"Fill {t:.1f} / {self._clock_fill_s:.1f} s"
        if self._solidify_frac > 0:
            return "Solidify  (thin walls first)"
        return ""

    def _draw_clock_mpl(self) -> None:
        label = self._clock_label()
        if self._solidify_frac > 0:
            label = (label + "   ·   thin walls freeze first").strip(" ·")
        if not label:
            return
        self.ax.text2D(0.02, 0.97, label, transform=self.ax.transAxes,
                       color="#CDD6F4", fontsize=9, va="top")

    def _draw_clock_pv(self) -> None:
        label = self._clock_label()
        if self._solidify_frac > 0:
            label = (label + "   ·   thin walls freeze first").strip()
        if label:
            actor = self.plotter.add_text(label, position="upper_left", font_size=10, color="#CDD6F4")
            self._pv_particle_actors.append(actor)

    def _draw_choke_marker(self, z_part: float, zmax: float) -> None:
        loc = choke_location(
            self.restrictive_elem,
            (float(self.sprue_offset[0]), float(self.sprue_offset[1])),
            (float(self.riser_offset[0]), float(self.riser_offset[1])),
            z_part, zmax,
        )
        if loc is None:
            return
        x, y, z = loc
        t = np.linspace(0, 2 * math.pi, 24)
        r = 8.0
        self.ax.plot(x + r * np.cos(t), y + r * np.sin(t), np.full_like(t, z),
                     color="#F9E2AF", linewidth=2.0)

    def _draw_choke_marker_pv(self, z_part: float, zmax: float) -> None:
        loc = choke_location(
            self.restrictive_elem,
            (float(self.sprue_offset[0]), float(self.sprue_offset[1])),
            (float(self.riser_offset[0]), float(self.riser_offset[1])),
            z_part, zmax,
        )
        if loc is None or not self.use_pyvista:
            return
        t = np.linspace(0, 2 * math.pi, 25)
        r = 8.0
        pts = np.column_stack([
            loc[0] + r * np.cos(t), loc[1] + r * np.sin(t), np.full_like(t, loc[2]),
        ])
        line = pv.PolyData(pts)
        line.lines = np.array([len(pts), *range(len(pts))])
        actor = self.plotter.add_mesh(line, color="#F9E2AF", line_width=3)
        self._pv_gating_actors.append(actor)

    def _inspect_colors(self, verts: np.ndarray) -> np.ndarray:
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        z_part = zmin + max(zmax - zmin, 1.0) * self.parting_z
        if self.overlay_mode == "undercut":
            hints = undercut_hints(verts, z_part)
            mask = hints["mask"]
            colors = np.tile(np.array(self._hex_to_rgb(COPE_COLOR) + (0.85,)), (len(verts), 1))
            colors[mask] = (0.95, 0.55, 0.22, 1.0)
            return colors
        draft = draft_analysis(verts, min_deg=DRAFT_MIN_DEG)
        colors = np.zeros((len(verts), 4))
        colors[:, 1] = 0.72
        colors[:, 2] = 0.45
        colors[:, 3] = 0.95
        colors[draft["lock_mask"]] = (0.95, 0.35, 0.45, 1.0)
        return colors

    def _add_mpl_inspect_overlay(self, name: str, verts: np.ndarray) -> None:
        colors = self._inspect_colors(verts)
        keep = self._clip_mask(verts)
        if not np.any(keep):
            return
        self.ax.add_collection3d(
            Poly3DCollection(verts[keep], facecolors=colors[keep], edgecolors="none")
        )

    def _add_pv_inspect_overlay(self, name: str, verts: np.ndarray) -> None:
        colors = self._inspect_colors(verts)[:, :3]
        keep = self._clip_mask(verts)
        if not np.any(keep):
            return
        fv, rgb = verts[keep], colors[keep]
        n_f = len(fv)
        ff = np.hstack([np.full((n_f, 1), 3), np.arange(n_f * 3).reshape(-1, 3)])
        fmesh = PolyData(fv.reshape(-1, 3), ff.flatten())
        actor = self.plotter.add_mesh(fmesh, scalars=rgb, rgb=True, smooth_shading=True)
        self._pv_actors[name]["fill"] = actor

    def set_show_as_cast(self, on: bool) -> None:
        self.show_as_cast = bool(on)
        self.render(self._anim_frac)

    def set_overlay_mode(self, mode: str) -> None:
        self.overlay_mode = mode or ""
        self.render(self._anim_frac)

    def set_selected_gating(self, name: str) -> None:
        self.selected_gating = name or ""
        self.render(self._anim_frac)

    def set_restrictive(self, name: str) -> None:
        self.restrictive_elem = name or ""
        self.render(self._anim_frac)

    def snap_gating_to_part(self) -> dict:
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        sx, sy = snap_xy_to_silhouette(
            float(self.sprue_offset[0]), float(self.sprue_offset[1]),
            xmin, xmax, ymin, ymax, margin=12.0,
        )
        rx, ry = snap_xy_to_silhouette(
            float(self.riser_offset[0]), float(self.riser_offset[1]),
            xmin, xmax, ymin, ymax, margin=18.0,
        )
        self.sprue_offset = np.array([sx, sy])
        self.riser_offset = np.array([rx, ry])
        self.render(self._anim_frac)
        data = {
            "sprue_x": sx, "sprue_y": sy,
            "riser_x": rx, "riser_y": ry,
        }
        self.gating_moved.emit(data)
        return data

    def look_at(self, x: float, y: float, z: float) -> None:
        if self.use_pyvista:
            try:
                cam = self.plotter.camera
                cam.SetFocalPoint(float(x), float(y), float(z))
                self.plotter.reset_camera_clipping_range()
                self.plotter.render()
            except Exception:
                self.set_view("Iso")
        else:
            self.set_view("Iso")

    def world_meshes(self) -> np.ndarray | None:
        """Display-space assembly (as-cast or shrink, matching the viewport)."""
        return self.assembled_mesh(scale=None)

    def assembled_mesh(self, scale: float | None = None) -> np.ndarray | None:
        """Concatenated world triangles at an explicit scale.

        ``scale=None`` follows the as-cast checkbox. Pass ``1.0`` for as-cast
        export geometry, or the shrink factor for the mould cavity used in sim.
        """
        chunks = [
            self._apply_transform(data["render_data"], self.transforms[name], scale=scale)
            for name, data in self.models.items()
        ]
        if not chunks:
            return None
        return np.concatenate(chunks, axis=0)

    def _face_thickness(self, name: str, verts: np.ndarray) -> np.ndarray:
        data = self.models.get(name) or {}
        stored = data.get("thickness")
        if stored is not None and len(stored) == len(verts):
            return np.asarray(stored, dtype=np.float64) * float(self.shrink_scale)
        return local_thickness(verts)

    def _add_mpl_solidify_overlay(self, name: str, verts: np.ndarray) -> None:
        """Surface-first freeze: thin local sections solidify first."""
        depths = self._face_sim_field(verts, "freeze")
        if depths is None:
            depths = self._face_thickness(name, verts)
        if len(depths) == 0:
            return
        dmax = max(float(depths.max()), 1e-9)
        frozen = (depths / dmax) <= self._solidify_frac
        heat = self._compute_heat_colors(verts, 1.0)
        metal = np.array(self._metal_rgb() + (1.0,))
        colors = np.array(heat)
        colors[frozen] = metal
        self.ax.add_collection3d(
            Poly3DCollection(verts, facecolors=colors, edgecolors="none")
        )

    def _add_pv_solidify_overlay(self, name: str, verts: np.ndarray) -> None:
        depths = self._face_sim_field(verts, "freeze")
        if depths is None:
            depths = self._face_thickness(name, verts)
        if len(depths) == 0:
            return
        dmax = max(float(depths.max()), 1e-9)
        frozen = (depths / dmax) <= self._solidify_frac
        heat = self._compute_heat_colors(verts, 1.0)[:, :3]
        metal = np.array(self._metal_rgb())
        rgb = np.array(heat)
        rgb[frozen] = metal
        n_f = len(verts)
        ff = np.hstack([np.full((n_f, 1), 3), np.arange(n_f * 3).reshape(-1, 3)])
        fmesh = PolyData(verts.reshape(-1, 3), ff.flatten())
        actor = self.plotter.add_mesh(
            fmesh, scalars=rgb, rgb=True, smooth_shading=True,
        )
        self._pv_actors[name]["fill"] = actor

    def set_shrink_scale(self, scale: float) -> None:
        self.shrink_scale = max(1.0, min(1.15, float(scale)))
        self.render(self._anim_frac)

    def set_gating_dimensions(
        self,
        sprue_top_r: float | None = None,
        sprue_bot_r: float | None = None,
        sprue_height: float | None = None,
        runner_width: float | None = None,
        runner_height: float | None = None,
        gate_area: float | None = None,
        riser_r: float | None = None,
        riser_h: float | None = None,
    ) -> None:
        if sprue_top_r is not None:
            self.sprue_top_radius = float(sprue_top_r)
        if sprue_bot_r is not None:
            self.sprue_bottom_radius = float(sprue_bot_r)
        if sprue_height is not None:
            self.sprue_height = float(sprue_height)
        if runner_width is not None:
            self.runner_width = float(runner_width)
        if runner_height is not None:
            self.runner_height = float(runner_height)
        if gate_area is not None:
            self.gate_area = float(gate_area)
        if riser_r is not None:
            self.riser_radius = float(riser_r)
        if riser_h is not None:
            self.riser_height = float(riser_h)
        self.render(self._anim_frac)

    def defect_sites(self) -> dict:
        """World-space defect marker positions derived from loaded meshes."""
        chunks = [
            self._apply_transform(data["render_data"], self.transforms[name])
            for name, data in self.models.items()
        ]
        if not chunks:
            return {}
        return find_defect_sites(
            np.concatenate(chunks, axis=0),
            sprue_xy=(float(self.sprue_offset[0]), float(self.sprue_offset[1])),
        )

    def screenshot(self, path: str) -> None:
        if self.use_pyvista:
            self.plotter.screenshot(path)
        else:
            self.fig.savefig(path, facecolor=self.fig.get_facecolor(), dpi=120)

    def screenshot_png_bytes(self) -> bytes:
        import io
        import os
        import tempfile
        if self.use_pyvista:
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                self.plotter.screenshot(path)
                with open(path, "rb") as fh:
                    return fh.read()
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        buf = io.BytesIO()
        self.fig.savefig(buf, format="png", facecolor=self.fig.get_facecolor(), dpi=100)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Transform setters
    # ------------------------------------------------------------------

    def set_transformation(self, dx: float, dy: float, dz: float, rot_z: float) -> None:
        if not self.active_model or self.active_model not in self.transforms:
            return
        self.transforms[self.active_model] = {
            "offset":   np.array([float(dx), float(dy), float(dz)]),
            "rotation": float(rot_z),
        }
        self.render(self._anim_frac)



    def set_gating_offset(self, sprue_x: float, sprue_y: float, runner_y: float, riser_x: float, riser_y: float) -> None:
        self.sprue_offset     = np.array([float(sprue_x), float(sprue_y)])
        self.runner_y_offset  = float(runner_y)
        self.riser_offset     = np.array([float(riser_x), float(riser_y)])
        self.render(self._anim_frac)



    def set_flask(self, size_tuple: tuple, height_in: float | None = None) -> None:
        if len(size_tuple) >= 2:
            self.flask_size = (float(size_tuple[0]), float(size_tuple[1]))
        if height_in is not None:
            self.flask_height_in = float(height_in)
        elif len(size_tuple) >= 3:
            self.flask_height_in = float(size_tuple[2])
        self.render(self._anim_frac)

    def set_mold_process(self, kind: str, shell_mm: float | None = None,
                         printed_mm: float | None = None) -> None:
        if kind == "shell":
            self.mold_kind = "shell"
        elif kind == "printed":
            self.mold_kind = "printed"
        else:
            self.mold_kind = "sand"
        if shell_mm is not None:
            self.shell_mm = float(shell_mm)
        if printed_mm is not None:
            self.printed_mm = float(printed_mm)
        self._pv_flask_key = ()
        self.render(self._anim_frac)



    def set_parting(self, frac: float):
        self.parting_z = float(frac)
        self.render(self._anim_frac)



    def set_gating(self, components: list[str]) -> None:
        self.gating = [c for c in components if c != "None"]
        self.render(self._anim_frac)



    def update_gating_display(self, selected: list):
        self.set_gating(selected)



    def set_view(self, view_name: str):
        if self.use_pyvista:
            if view_name == "Iso":
                self.plotter.view_isometric()
                return
            pv_views = {
                "Top":    ("xy", False),
                "Bottom": ("xy", True),
                "Front":  ("xz", False),
                "Back":   ("xz", True),
                "Left":   ("yz", True),
                "Right":  ("yz", False),
            }
            pair = pv_views.get(view_name)
            if pair:
                axis, negative = pair
                getattr(self.plotter, f"view_{axis}")(negative=negative)
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

    def fit_view(self) -> None:
        """Frame the part (or flask) in the camera."""
        if self.use_pyvista:
            try:
                self.plotter.reset_camera()
                self.plotter.view_isometric()
            except Exception:
                pass
            return
        self.set_view("Iso")

    def set_pour_rate(self, rate: float):
        self.pour_rate = max(0.5, min(3.0, rate))



    def _gating_state_key(self, z_part: float, zmax: float) -> tuple:
        """Cache key covering every param that rebuilds gating meshes."""
        return (
            tuple(sorted(self.gating)),
            round(float(z_part), 2), round(float(zmax), 2),
            tuple(float(v) for v in self.sprue_offset),
            round(self.runner_y_offset, 2),
            tuple(float(v) for v in self.riser_offset),
            tuple(float(v) for v in self.gate2_offset),
            self.sprue_top_radius, self.sprue_bottom_radius, self.sprue_height,
            self.runner_width, self.runner_height, round(self._effective_runner_length(), 1), self.gate_area,
            self.selected_gating, self.restrictive_elem,
            round(self.riser_radius, 2), round(self.riser_height, 2),
            round(self.neck_radius, 2), round(self.neck_height, 2),
            bool(self.riser_blind),
            round(self.filter_area, 1), round(self.basin_radius, 1), round(self.basin_height, 1),
            len(self.chills),
        )

    def get_gating_params(self, scale: float | None = None) -> dict:
        has_sprue  = "Tapered Sprue" in self.gating
        has_runner = "Runner (Horizontal)" in self.gating
        has_gate   = "Fan Gate" in self.gating
        has_gate2  = "Second Gate" in self.gating


        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds(scale)
        part_h = max(zmax - zmin, 1.0)
        z_part = zmin + part_h * self.parting_z
        cope_mm = max(0.0, zmax - z_part)
        head_mm = self.sprue_height + cope_mm
        run_len = self._effective_runner_length(scale) if has_runner else None

        return {
            "has_sprue":        has_sprue,
            "has_runner":       has_runner,
            "has_gate":         has_gate,
            "has_gate2":        has_gate2,
            "has_filter":       "Foam Filter" in self.gating,
            "has_basin":        "Pour Basin" in self.gating,
            "sprue_top_r":      self.sprue_top_radius if has_sprue else None,
            "sprue_bot_r":      self.sprue_bottom_radius if has_sprue else None,
            "sprue_height_mm":  head_mm,
            "runner_dia":       self.runner_diameter if has_runner else None,
            "runner_width_mm":  self.runner_width if has_runner else None,
            "runner_height_mm": self.runner_height if has_runner else None,
            "gate_area_mm2":    self.gate_area if (has_gate or has_gate2) else None,
            "filter_area_mm2":  self.filter_area if "Foam Filter" in self.gating else None,
            "basin_r_mm":       self.basin_radius if "Pour Basin" in self.gating else None,
            "basin_h_mm":       self.basin_height if "Pour Basin" in self.gating else None,
            "has_riser":        "Riser (Open)" in self.gating,
            "riser_blind":      bool(self.riser_blind),
            "neck_r_mm":        self.neck_radius if "Riser (Open)" in self.gating else None,
            "neck_h_mm":        self.neck_height if "Riser (Open)" in self.gating else None,
            "runner_length_mm": run_len,
            "riser_r_mm":       self.riser_radius if "Riser (Open)" in self.gating else None,
            "riser_h_mm":       self.riser_height if "Riser (Open)" in self.gating else None,
        }



    def draw_idle(self):
        if self.use_pyvista:
            self.plotter.render()
        else:
            self.canvas.draw_idle()



    # ------------------------------------------------------------------

    # Mouse interaction

    # ------------------------------------------------------------------



    def _bind_pyvista_drag(self) -> None:
        """Left-drag sprue, riser, or the active model in the PyVista view."""
        try:
            iren = self.plotter.iren
            interactor = getattr(iren, "interactor", iren)
            interactor.AddObserver("LeftButtonPressEvent", self._on_pv_press)
            interactor.AddObserver("MouseMoveEvent", self._on_pv_move)
            interactor.AddObserver("LeftButtonReleaseEvent", self._on_pv_release)
        except Exception:
            pass

    def _pv_event_xy(self, obj) -> tuple[int, int] | None:
        try:
            x, y = obj.GetEventPosition()
            return int(x), int(y)
        except Exception:
            return None

    def _pv_world_on_plane(self, x: int, y: int, z_plane: float) -> np.ndarray | None:
        """Intersect the camera ray through display (x, y) with z = z_plane."""
        try:
            renderer = self.plotter.renderer
            renderer.SetDisplayPoint(x, y, 0.0)
            renderer.DisplayToWorld()
            near = np.array(renderer.GetWorldPoint()[:3], dtype=float)
            renderer.SetDisplayPoint(x, y, 1.0)
            renderer.DisplayToWorld()
            far = np.array(renderer.GetWorldPoint()[:3], dtype=float)
            d = far - near
            if abs(d[2]) < 1e-9:
                return np.array([near[0], near[1], z_plane])
            t = (z_plane - near[2]) / d[2]
            p = near + t * d
            return p
        except Exception:
            return None

    def _on_pv_press(self, obj, event) -> None:
        xy = self._pv_event_xy(obj)
        if xy is None:
            return
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part = zmin + part_h * self.parting_z

        if self.pick_mode == "parting":
            z_hit = self._pv_ray_z(xy[0], xy[1], zmin, zmax)
            if z_hit is not None:
                frac = float(np.clip((z_hit - zmin) / part_h, 0.05, 0.95))
                self.pick_mode = ""
                self.parting_picked.emit(frac)
            try:
                obj.AbortFlagOn()
            except Exception:
                pass
            return

        if self.pick_mode in ("sprue", "gate", "riser", "chill", "filter", "gate2"):
            hit = self._pv_world_on_plane(xy[0], xy[1], z_part)
            z_hit = self._pv_ray_z(xy[0], xy[1], zmin, zmax)
            if hit is not None:
                self.place_gating(self.pick_mode, float(hit[0]), float(hit[1]), z_hit)
            try:
                obj.AbortFlagOn()
            except Exception:
                pass
            return

        if not self.models:
            return
        hit = self._pv_world_on_plane(xy[0], xy[1], z_part)
        if hit is None:
            return
        thresh = 25.0
        picked = ""
        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            if math.hypot(hit[0] - sx, hit[1] - sy) < thresh:
                picked = "Tapered Sprue"
        if not picked and "Fan Gate" in self.gating:
            sx, sy = self.sprue_offset
            if math.hypot(hit[0] - sx, hit[1] - (sy - 4.0)) < thresh:
                picked = "Fan Gate"
        if not picked and "Runner (Horizontal)" in self.gating:
            sx, sy = self.sprue_offset
            if abs(hit[0] - sx) < self._effective_runner_length() / 2 and abs(hit[1] - sy) < 20:
                picked = "Runner (Horizontal)"
        if not picked and "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            if math.hypot(hit[0] - rx, hit[1] - ry) < thresh:
                picked = "Riser (Open)"
        if picked:
            self.selected_gating = picked
            self.gating_selected.emit(picked)
            self._dragging_part = "sprue" if picked == "Tapered Sprue" else (
                "riser" if picked == "Riser (Open)" else None
            )
            self._drag_last = (hit[0], hit[1])
            if self._dragging_part:
                self.drag_began.emit()
            self.render(self._anim_frac)
            try:
                obj.AbortFlagOn()
            except Exception:
                pass
            return
        if self.active_model and self.active_model in self.transforms:
            self._dragging_part = "model"
            self._drag_last = (hit[0], hit[1])
            self.drag_began.emit()

    def _pv_ray_z(self, x: int, y: int, zmin: float, zmax: float) -> float | None:
        try:
            renderer = self.plotter.renderer
            renderer.SetDisplayPoint(x, y, 0.0)
            renderer.DisplayToWorld()
            near = np.array(renderer.GetWorldPoint()[:3], dtype=float)
            renderer.SetDisplayPoint(x, y, 1.0)
            renderer.DisplayToWorld()
            far = np.array(renderer.GetWorldPoint()[:3], dtype=float)
            d = far - near
            if abs(d[2]) < 1e-9:
                return float(np.clip(near[2], zmin, zmax))
            # Z at the mid-depth of the part AABB
            t = 0.5
            return float(np.clip((near + t * d)[2], zmin, zmax))
        except Exception:
            return None

    def _on_pv_move(self, obj, event) -> None:
        if not self._dragging_part:
            return
        xy = self._pv_event_xy(obj)
        if xy is None:
            return
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part = zmin + part_h * self.parting_z
        hit = self._pv_world_on_plane(xy[0], xy[1], z_part)
        if hit is None or self._drag_last is None:
            return
        dmm_x = hit[0] - self._drag_last[0]
        dmm_y = hit[1] - self._drag_last[1]
        self._drag_last = (hit[0], hit[1])
        if self._dragging_part == "sprue":
            self.sprue_offset += np.array([dmm_x, dmm_y])
            self.render(self._anim_frac)
            self.gating_moved.emit({
                "sprue_x": float(self.sprue_offset[0]),
                "sprue_y": float(self.sprue_offset[1]),
                "riser_x": float(self.riser_offset[0]),
                "riser_y": float(self.riser_offset[1]),
            })
        elif self._dragging_part == "riser":
            self.riser_offset += np.array([dmm_x, dmm_y])
            self.render(self._anim_frac)
            self.gating_moved.emit({
                "sprue_x": float(self.sprue_offset[0]),
                "sprue_y": float(self.sprue_offset[1]),
                "riser_x": float(self.riser_offset[0]),
                "riser_y": float(self.riser_offset[1]),
            })
        elif self._dragging_part == "model" and self.active_model:
            t = self.transforms[self.active_model]
            t["offset"] = t["offset"] + np.array([dmm_x, dmm_y, 0.0])
            self.render(self._anim_frac)
            self.model_moved.emit({
                "x": float(t["offset"][0]),
                "y": float(t["offset"][1]),
                "z": float(t["offset"][2]),
            })
        try:
            obj.AbortFlagOn()
        except Exception:
            pass

    def _on_pv_release(self, obj, event) -> None:
        self._dragging_part = None
        self._drag_last = None

    def _on_mouse_press(self, event):
        if event.inaxes != self.ax:
            return
        mx, my = event.x, event.y
        xmin, xmax, ymin, ymax, zmin, zmax = self._compute_bounds()
        part_h = max(zmax - zmin, 1.0)
        z_part = zmin + part_h * self.parting_z

        if self.pick_mode == "parting":
            bbox = self.ax.get_window_extent()
            frac = float(np.clip(1.0 - (my - bbox.y0) / max(bbox.height, 1), 0.05, 0.95))
            self.pick_mode = ""
            self.parting_picked.emit(frac)
            return

        if self.pick_mode in ("sprue", "gate", "riser", "chill", "filter", "gate2"):
            if event.xdata is not None and event.ydata is not None:
                self.place_gating(self.pick_mode, float(event.xdata), float(event.ydata), z_part)
            return

        picked = ""
        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            _z_bot, sprue_h = self._sprue_z_and_height(z_part, zmax)
            if self._is_near_point(mx, my, sx, sy, z_part + sprue_h * 0.5):
                picked = "Tapered Sprue"
        if not picked and "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            if self._is_near_point(mx, my, rx, ry, z_part + 30):
                picked = "Riser (Open)"
        if not picked and "Fan Gate" in self.gating:
            sx, sy = self.sprue_offset
            if self._is_near_point(mx, my, sx, sy - 4.0, z_part):
                picked = "Fan Gate"
        if picked:
            self.selected_gating = picked
            self.gating_selected.emit(picked)
            self._dragging_part = "sprue" if picked == "Tapered Sprue" else (
                "riser" if picked == "Riser (Open)" else None
            )
            self._drag_last = (mx, my)
            if self._dragging_part:
                self.drag_began.emit()
            self.render(self._anim_frac)
            return

        if self.active_model and self.active_model in self.transforms:
            self._dragging_part = "model"
            self._drag_last = (mx, my)
            self.drag_began.emit()



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
            self.model_moved.emit({
                "x": float(t["offset"][0]),
                "y": float(t["offset"][1]),
                "z": float(t["offset"][2]),
            })



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



    def start_fill_animation(
        self,
        duration_s: float = 3.0,
        on_done: "callable | None" = None,
        fill_s: float | None = None,
        solidify_min: float | None = None,
    ) -> None:
        self._anim_done_cb     = on_done
        self._anim_step        = 0
        self._anim_steps       = 120
        self._clock_fill_s     = float(fill_s if fill_s is not None else duration_s)
        self._clock_solidify_min = float(solidify_min if solidify_min is not None else 3.0)
        self._anim_interval_ms = max(16, int((duration_s * 1000) / self._anim_steps / self.pour_rate))
        self._anim_timer.start(self._anim_interval_ms)



    def _anim_tick(self):
        self._anim_step += 1
        t = self._anim_step / self._anim_steps
        # Ease-in-out quad: slow start/end, fast middle — mimics mold resistance
        self._anim_frac = t * t * (3.0 - 2.0 * t)
        self.render(self._anim_frac)
        if self._anim_step >= self._anim_steps:
            self._anim_frac = 1.0  # keep the cavity filled during solidification
            self.start_solidify_animation(
                duration_s=min(8.0, max(2.0, self._clock_solidify_min)),
                on_done=self._anim_done_cb,
            )
        else:
            # Single-shot: restart only after render completes; naturally skips
            # frames when the GPU/CPU render takes longer than the target interval.
            self._anim_timer.start(self._anim_interval_ms)



    def start_solidify_animation(self, duration_s: float = 3.0, on_done=None):

        """Start solidification animation - boundary moves inward from mold walls."""

        self._solidify_done_cb     = on_done
        self._solidify_step        = 0
        self._solidify_steps       = 120
        self._solidify_interval_ms = max(16, int((duration_s * 1000) / self._solidify_steps))
        self._solidify_timer.start(self._solidify_interval_ms)



    def _solidify_tick(self):

        """Update solidification animation tick."""

        self._solidify_step += 1
        self._solidify_frac  = self._solidify_step / self._solidify_steps
        self.render(1.0)
        if self._solidify_step >= self._solidify_steps:
            self._solidify_frac = 0.0
            if self._solidify_done_cb:
                self._solidify_done_cb()
        else:
            # Single-shot: restart only after render completes.
            self._solidify_timer.start(self._solidify_interval_ms)



    def reset_anim(self) -> None:
        """Stop animation timers and reset fractions; keep loaded models."""
        self._anim_timer.stop()
        self._solidify_timer.stop()
        self._anim_frac = 0.0
        self._solidify_frac = 0.0
        self._anim_step = 0
        self._solidify_step = 0
        if self.models:
            self.render(0.0)
        else:
            self._draw_idle_scene()

    def clear_scene(self) -> None:
        """Remove all loaded models and cached actors, then show the idle prompt."""
        self.reset_anim()
        self.models.clear()
        self.transforms.clear()
        self.active_model = ""
        self.chills = []
        self._sim_fields = {}

        self._gating_geo_cache.clear()
        self._gating_cache_key = ()
        self._mpl_model_collections.clear()
        if self.use_pyvista:
            for info in self._pv_actors.values():
                self.plotter.remove_actor(info["model"])
                if info["fill"]:
                    self.plotter.remove_actor(info["fill"])
            self._pv_actors.clear()
            for a in self._pv_flask_actors + self._pv_gating_actors + self._pv_particle_actors:
                self.plotter.remove_actor(a)
            self._pv_flask_actors.clear()
            self._pv_flask_key = ()
            self._pv_gating_actors.clear()
            self._pv_gating_key = ()
            self._pv_particle_actors.clear()

        self._draw_idle_scene()
