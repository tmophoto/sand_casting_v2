import math
import hashlib
import random
import numpy as np
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
                       GATE_COLOR, RISER_COLOR, MODEL_COLORS)


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
