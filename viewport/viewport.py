import math
import hashlib
import random
import time
import numpy as np
import matplotlib.cm as _cm
from stl import mesh as stl_mesh
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
                       GATE_COLOR, RISER_COLOR, MODEL_COLORS, METAL_PBR)

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


        # Gating dimensions (mm) — hydraulics must match the rendered mesh
        self.sprue_top_radius    = 7.5
        self.sprue_bottom_radius = 4.0
        self.runner_length       = 160.0
        self.runner_width        = 10.0   # cross-section depth
        self.runner_height       = 8.0    # cross-section height
        self.runner_diameter     = 12.0   # legacy circular approx; unused when width/height set
        self.gate_area           = 40.0


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

        # Pre-compute unit face normals for shading (Phase 4a — avoids per-frame recompute)
        _v0, _v1, _v2 = vectors[:, 0], vectors[:, 1], vectors[:, 2]
        _cross = np.cross(_v1 - _v0, _v2 - _v0).astype(np.float64)
        _lens = np.linalg.norm(_cross, axis=1, keepdims=True)
        _lens[_lens == 0] = 1e-9
        _cross /= _lens

        self.models[name] = {
            "mesh":        loaded,
            "render_data": vectors,
            "normals":     _cross,   # unit face normals in local space (n, 3)
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

        """Volume via divergence theorem, surface area from triangle cross-products.

        Uses GPU arrays (CuPy) when available, falls back to NumPy automatically.
        """

        verts = xp.asarray(mesh.vectors)
        if verts.shape[0] == 0:
            return {"vol_cm3": 0.0, "surf_cm2": 0.0, "z_min": 0.0, "z_max": 0.0}

        v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]

        cross   = xp.cross(v1 - v0, v2 - v0)
        vol_mm3 = float(abs(xp.sum(v0 * cross) / 6.0))

        area_mm2 = float(xp.sum(xp.linalg.norm(cross, axis=1)) / 2.0)

        return {
            "vol_cm3":  vol_mm3  / 1000.0,
            "surf_cm2": area_mm2 / 100.0,
            "z_min":    float(xp.min(verts[:, :, 2])),
            "z_max":    float(xp.max(verts[:, :, 2])),
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

            cope_colors = [cope_base + (1.0,)] * len(cope_verts)
            drag_colors = [drag_base + (1.0,)] * len(drag_verts)

            if name not in self._mpl_model_collections:
                # First render of this model: create collections
                cope_coll = drag_coll = None
                if len(cope_verts):
                    cope_coll = Poly3DCollection(cope_verts, facecolors=cope_colors,
                                                 edgecolors="none", linewidths=0, shade=True)
                    self.ax.add_collection3d(cope_coll)
                if len(drag_verts):
                    drag_coll = Poly3DCollection(drag_verts, facecolors=drag_colors,
                                                 edgecolors="none", linewidths=0, shade=True)
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

            # Fill animation overlay (always an overlay; plasma heat colours)
            if anim_frac > 0:
                fill_z    = zmin + part_h * anim_frac
                fill_mask = centroids_z <= fill_z
                if np.any(fill_mask):
                    heat_colors = self._compute_heat_colors(verts, anim_frac)
                    self.ax.add_collection3d(
                        Poly3DCollection(verts[fill_mask],
                                         facecolors=heat_colors[fill_mask],
                                         edgecolors="none"))

        self._draw_flask_outline(z_part)

        if self.models:
            self._draw_gating(z_part)
            if anim_frac > 0 and "Tapered Sprue" in self.gating:
                self._draw_sprue_particles(z_part, anim_frac)

        half_w = fw_mm / 2 + PAD
        half_h = fh_mm / 2 + PAD
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

        # ----------------------------------------------------------------
        # 3. Fill animation overlay — remove old, add new
        # ----------------------------------------------------------------
        for info in self._pv_actors.values():
            if info["fill"]:
                self.plotter.remove_actor(info["fill"])
                info["fill"] = None

        if anim_frac > 0:
            for name, data in self.models.items():
                verts = self._apply_transform(data["render_data"], self.transforms[name])
                heat_colors = self._compute_heat_colors(verts, anim_frac)
                centroids_z = verts[:, :, 2].mean(axis=1)
                fill_z      = zmin + part_h * anim_frac
                fill_mask   = centroids_z <= fill_z
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
        # 4. Flask outline — cached, rebuild only when bounds/size change
        # ----------------------------------------------------------------
        flask_key = (round(zmin, 1), round(zmax, 1), self.flask_size,
                     round(z_part, 1))
        if flask_key != self._pv_flask_key:
            for a in self._pv_flask_actors:
                self.plotter.remove_actor(a)
            self._pv_flask_actors.clear()
            self._pv_flask_key = flask_key
            fw_mm = self.flask_size[0] * 25.4
            fh_mm = self.flask_size[1] * 25.4
            hw, hh = fw_mm / 2, fh_mm / 2
            xs = [-hw, hw, hw, -hw, -hw]
            ys = [-hh, -hh, hh, hh, -hh]
            for z, col, lw in [(zmin - 5, "#45475A", 2),
                                (zmax + 5, "#45475A", 2),
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
        gating_key = (
            tuple(sorted(self.gating)),
            round(z_part, 2), round(float(zmax), 2),
            tuple(float(v) for v in self.sprue_offset),
            round(self.runner_y_offset, 2),
            tuple(float(v) for v in self.riser_offset),
            self.sprue_top_radius, self.sprue_bottom_radius,
        )
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
        """4×4 homogeneous transform (Z-rotation + XYZ offset) for PyVista actors."""
        off = t["offset"]
        rot = math.radians(t["rotation"])
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        mat = np.eye(4, dtype=np.float64)
        mat[0, 0], mat[0, 1] =  cos_r, -sin_r
        mat[1, 0], mat[1, 1] =  sin_r,  cos_r
        mat[0, 3], mat[1, 3], mat[2, 3] = float(off[0]), float(off[1]), float(off[2])
        return mat

    def _apply_transform(self, render_data: np.ndarray, t: dict) -> np.ndarray:
        """Return world-space vertex array by applying rotation + offset."""
        verts = render_data.copy()
        off = t["offset"]
        rot = math.radians(t["rotation"])
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        x_new = verts[:, :, 0] * cos_r - verts[:, :, 1] * sin_r
        y_new = verts[:, :, 0] * sin_r + verts[:, :, 1] * cos_r
        verts[:, :, 0] = x_new + off[0]
        verts[:, :, 1] = y_new + off[1]
        verts[:, :, 2] += off[2]
        return verts

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
        if "Tapered Sprue" in self.gating:
            sx, sy = self.sprue_offset
            faces = self._make_cylinder_mesh(
                cx=sx, cy=sy, z_bottom=zmax,
                r_bottom=self.sprue_bottom_radius,
                r_top=self.sprue_top_radius,
                height=100.0, sides=24,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Tapered Sprue"])

        if "Runner (Horizontal)" in self.gating:
            sx, sy = self.sprue_offset
            ry = sy + self.runner_y_offset
            faces = self._make_box_mesh(
                cx=sx, cy=ry, z_bottom=z_part - self.runner_height / 2.0,
                width=self.runner_length, depth=self.runner_width, height=self.runner_height,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Runner (Horizontal)"])

        if "Riser (Open)" in self.gating:
            rx, ry = self.riser_offset
            faces = self._make_cylinder_mesh(
                cx=rx, cy=ry, z_bottom=z_part,
                r_bottom=20.0, r_top=20.0, height=60.0, sides=24,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Riser (Open)"])

        if "Fan Gate" in self.gating:
            sx, sy = self.sprue_offset
            faces = self._make_box_mesh(
                cx=sx, cy=sy - 4.0, z_bottom=z_part - 3.0,
                width=60.0, depth=8.0, height=6.0,
            )
            self._add_pv_gating_mesh(faces, *_gating_colors["Fan Gate"])

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
        cache_key = (
            tuple(sorted(self.gating)),
            round(z_part, 2),
            round(float(zmax), 2),
            tuple(float(v) for v in self.sprue_offset),
            round(self.runner_y_offset, 2),
            tuple(float(v) for v in self.riser_offset),
            self.sprue_top_radius,
            self.sprue_bottom_radius,
        )
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
                faces = self._make_cylinder_mesh(
                    cx=sx, cy=sy, z_bottom=zmax,
                    r_bottom=self.sprue_bottom_radius,
                    r_top=self.sprue_top_radius,
                    height=100.0, sides=24,
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
                    width=self.runner_length, depth=self.runner_width, height=self.runner_height,
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
                    r_bottom=20.0, r_top=20.0, height=60.0, sides=24,
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
                faces = self._make_box_mesh(
                    cx=sx, cy=sy - 4.0, z_bottom=z_part - 3.0,
                    width=60.0, depth=8.0, height=6.0,
                )
                colors = self._shade_faces(faces, self._hex_to_rgb(GATE_COLOR), alpha=0.85)
                return faces, colors
            faces, colors = _get("gate", _build_gate)
            self.ax.add_collection3d(Poly3DCollection(
                faces, facecolors=colors[:, :3], edgecolor="none", shade=True
            ))



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
        top_z = zmax + 100

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
        top_z = zmax + 100

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



    def set_flask(self, size_tuple: tuple[float, float]) -> None:
        self.flask_size = size_tuple
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

    def set_pour_rate(self, rate: float):
        self.pour_rate = max(0.5, min(3.0, rate))



    def get_gating_params(self) -> dict:
        has_sprue  = "Tapered Sprue" in self.gating
        has_runner = "Runner (Horizontal)" in self.gating
        has_gate   = any(c in self.gating for c in ["Fan Gate"])


        return {
            "has_sprue":       has_sprue,
            "has_runner":      has_runner,
            "has_gate":        has_gate,
            "sprue_top_r":     self.sprue_top_radius if has_sprue else None,
            "sprue_bot_r":     self.sprue_bottom_radius if has_sprue else None,
            "runner_dia":      self.runner_diameter if has_runner else None,
            "runner_width_mm": self.runner_width if has_runner else None,
            "runner_height_mm": self.runner_height if has_runner else None,
            "gate_area_mm2":   self.gate_area if has_gate else None,
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



    def start_fill_animation(self, duration_s: float = 3.0, on_done: "callable | None" = None) -> None:
        self._anim_done_cb     = on_done
        self._anim_step        = 0
        self._anim_steps       = 120
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
            self.start_solidify_animation(duration_s=3.0, on_done=self._anim_done_cb)
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
        self.render(max(self._anim_frac, 1.0 if self._solidify_step else self._solidify_frac))
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
