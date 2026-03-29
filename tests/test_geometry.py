"""
Tests for geometry helpers in viewport/viewport.py:
  - Viewport3D._geometry_stats()
  - Viewport3D._make_cylinder_mesh()
  - Viewport3D._make_box_mesh()
  - Viewport3D._hex_to_rgb()

All tests are headless — the Viewport3D class is never instantiated
so no display is needed. The static/standalone functions are called directly.
"""

import math
import sys
import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewport.viewport import Viewport3D


# Convenient aliases for the static methods under test
make_cylinder = Viewport3D._make_cylinder_mesh
make_box      = Viewport3D._make_box_mesh
hex_to_rgb    = Viewport3D._hex_to_rgb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_mesh(vectors: np.ndarray):
    """Return a minimal object with a .vectors attribute."""
    class _Mesh:
        pass
    m = _Mesh()
    m.vectors = vectors
    return m


def unit_cube_mesh() -> np.ndarray:
    """
    Return the 12 triangles (2 per face × 6 faces) of a unit cube [0,1]³
    as an (12, 3, 3) float array.  All faces wound consistently outward.
    """
    v = np.array([
        [0,0,0],[1,0,0],[1,1,0],[0,1,0],  # bottom z=0
        [0,0,1],[1,0,1],[1,1,1],[0,1,1],  # top    z=1
    ], dtype=float)
    return np.array([
        # bottom (inward normal = -Z, but we just need consistent winding)
        [v[0], v[2], v[1]], [v[0], v[3], v[2]],
        # top
        [v[4], v[5], v[6]], [v[4], v[6], v[7]],
        # front  y=0
        [v[0], v[1], v[5]], [v[0], v[5], v[4]],
        # back   y=1
        [v[2], v[3], v[7]], [v[2], v[7], v[6]],
        # left   x=0
        [v[0], v[4], v[7]], [v[0], v[7], v[3]],
        # right  x=1
        [v[1], v[2], v[6]], [v[1], v[6], v[5]],
    ], dtype=float)


# ---------------------------------------------------------------------------
# _geometry_stats
# ---------------------------------------------------------------------------

class TestGeometryStats:

    def _stats(self, vectors):
        worker = Viewport3D.__new__(Viewport3D)   # skip __init__
        return worker._geometry_stats(make_mock_mesh(vectors))

    def test_returns_dict_with_correct_keys(self):
        s = self._stats(unit_cube_mesh())
        assert "vol_cm3" in s
        assert "surf_cm2" in s

    def test_unit_cube_volume(self):
        """Unit cube volume = 1 mm³ = 0.001 cm³."""
        s = self._stats(unit_cube_mesh())
        assert abs(s["vol_cm3"] - 0.001) < 1e-6

    def test_unit_cube_surface_area(self):
        """Unit cube surface area = 6 mm² = 0.06 cm²."""
        s = self._stats(unit_cube_mesh())
        assert abs(s["surf_cm2"] - 0.06) < 1e-6

    def test_scaled_cube_volume_scales_cubically(self):
        """A 10mm cube should have vol = 1000 mm³ = 1.0 cm³."""
        scaled = unit_cube_mesh() * 10.0
        s = self._stats(scaled)
        assert abs(s["vol_cm3"] - 1.0) < 1e-4

    def test_scaled_cube_surface_scales_quadratically(self):
        """A 10mm cube should have area = 600 mm² = 6.0 cm²."""
        scaled = unit_cube_mesh() * 10.0
        s = self._stats(scaled)
        assert abs(s["surf_cm2"] - 6.0) < 1e-4

    def test_volume_is_positive(self):
        s = self._stats(unit_cube_mesh())
        assert s["vol_cm3"] > 0

    def test_surface_area_is_positive(self):
        s = self._stats(unit_cube_mesh())
        assert s["surf_cm2"] > 0

    def test_larger_mesh_larger_volume(self):
        small = unit_cube_mesh() * 5.0
        large = unit_cube_mesh() * 20.0
        assert self._stats(large)["vol_cm3"] > self._stats(small)["vol_cm3"]


# ---------------------------------------------------------------------------
# _make_cylinder_mesh
# ---------------------------------------------------------------------------

class TestMakeCylinderMesh:

    def test_returns_ndarray(self):
        faces = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0, sides=12)
        assert isinstance(faces, np.ndarray)

    def test_shape_is_n_by_3_by_3(self):
        """Each row is one triangle with 3 vertices of 3 coords each."""
        faces = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0, sides=12)
        assert faces.ndim == 3
        assert faces.shape[1] == 3
        assert faces.shape[2] == 3

    def test_face_count_straight_cylinder(self):
        """sides=N → 2N side + N bottom cap + N top cap = 4N faces."""
        for n in (8, 12, 24):
            faces = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0, sides=n)
            assert faces.shape[0] == 4 * n, f"expected {4*n} faces for sides={n}"

    def test_face_count_tapered_cone(self):
        faces = make_cylinder(0, 0, 0, 4.0, 7.5, 100.0, sides=24)
        assert faces.shape[0] == 4 * 24

    def test_z_range(self):
        """All bottom vertices at z_bottom, all top vertices at z_bottom+height."""
        faces = make_cylinder(0, 0, 10.0, 5.0, 5.0, 30.0, sides=12)
        z_vals = faces[:, :, 2].ravel()
        assert z_vals.min() >= 10.0 - 1e-9
        assert z_vals.max() <= 40.0 + 1e-9

    def test_centred_at_cx_cy(self):
        cx, cy = 15.0, -8.0
        faces = make_cylinder(cx, cy, 0, 5.0, 5.0, 10.0, sides=24)
        # All x and y coords should be within radius of centre
        xs = faces[:, :, 0].ravel()
        ys = faces[:, :, 1].ravel()
        assert xs.min() >= cx - 5.0 - 1e-9
        assert xs.max() <= cx + 5.0 + 1e-9
        assert ys.min() >= cy - 5.0 - 1e-9
        assert ys.max() <= cy + 5.0 + 1e-9

    def test_dtype_is_float(self):
        faces = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0)
        assert np.issubdtype(faces.dtype, np.floating)

    def test_no_nan_or_inf(self):
        faces = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0)
        assert np.isfinite(faces).all()

    def test_default_sides_is_24(self):
        faces_default = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0)
        faces_explicit = make_cylinder(0, 0, 0, 5.0, 5.0, 10.0, sides=24)
        assert faces_default.shape == faces_explicit.shape


# ---------------------------------------------------------------------------
# _make_box_mesh
# ---------------------------------------------------------------------------

class TestMakeBoxMesh:

    def test_returns_ndarray(self):
        assert isinstance(make_box(0, 0, 0, 10, 5, 3), np.ndarray)

    def test_shape_is_12_by_3_by_3(self):
        """A box has 6 faces × 2 triangles = 12 triangles."""
        faces = make_box(0, 0, 0, 10, 5, 3)
        assert faces.shape == (12, 3, 3)

    def test_z_range(self):
        """Vertices span z_bottom to z_bottom + height."""
        faces = make_box(0, 0, 5.0, 10.0, 10.0, 6.0)
        z_vals = faces[:, :, 2].ravel()
        assert z_vals.min() >= 5.0 - 1e-9
        assert z_vals.max() <= 5.0 + 6.0 + 1e-9

    def test_x_range(self):
        faces = make_box(0, 0, 0, 20.0, 10.0, 5.0)
        xs = faces[:, :, 0].ravel()
        assert xs.min() >= -10.0 - 1e-9
        assert xs.max() <=  10.0 + 1e-9

    def test_y_range(self):
        faces = make_box(0, 0, 0, 20.0, 10.0, 5.0)
        ys = faces[:, :, 1].ravel()
        assert ys.min() >= -5.0 - 1e-9
        assert ys.max() <=  5.0 + 1e-9

    def test_dtype_is_float(self):
        assert np.issubdtype(make_box(0, 0, 0, 5, 5, 5).dtype, np.floating)

    def test_no_nan_or_inf(self):
        assert np.isfinite(make_box(0, 0, 0, 5, 5, 5)).all()

    def test_offset_by_cx_cy(self):
        cx, cy = 30.0, -20.0
        faces = make_box(cx, cy, 0, 10.0, 10.0, 10.0)
        xs = faces[:, :, 0].ravel()
        ys = faces[:, :, 1].ravel()
        assert xs.min() >= cx - 5.0 - 1e-9
        assert xs.max() <= cx + 5.0 + 1e-9
        assert ys.min() >= cy - 5.0 - 1e-9
        assert ys.max() <= cy + 5.0 + 1e-9


# ---------------------------------------------------------------------------
# _hex_to_rgb
# ---------------------------------------------------------------------------

class TestHexToRgb:

    def test_black(self):
        assert hex_to_rgb("#000000") == (0.0, 0.0, 0.0)

    def test_white(self):
        r, g, b = hex_to_rgb("#FFFFFF")
        assert abs(r - 1.0) < 1e-9
        assert abs(g - 1.0) < 1e-9
        assert abs(b - 1.0) < 1e-9

    def test_red(self):
        r, g, b = hex_to_rgb("#FF0000")
        assert abs(r - 1.0) < 1e-9
        assert g == 0.0
        assert b == 0.0

    def test_returns_tuple_of_three(self):
        result = hex_to_rgb("#89B4FA")
        assert len(result) == 3

    def test_values_in_zero_to_one(self):
        for color in ["#4A90D9", "#C0834A", "#E87040", "#D4A030"]:
            r, g, b = hex_to_rgb(color)
            assert 0.0 <= r <= 1.0
            assert 0.0 <= g <= 1.0
            assert 0.0 <= b <= 1.0

    def test_lowercase_hex(self):
        r1, g1, b1 = hex_to_rgb("#ff0000")
        r2, g2, b2 = hex_to_rgb("#FF0000")
        assert abs(r1 - r2) < 1e-9
        assert abs(g1 - g2) < 1e-9
        assert abs(b1 - b2) < 1e-9

    def test_known_cope_color(self):
        """#4A90D9 → (74/255, 144/255, 217/255)."""
        r, g, b = hex_to_rgb("#4A90D9")
        assert abs(r - 74/255)  < 1e-6
        assert abs(g - 144/255) < 1e-6
        assert abs(b - 217/255) < 1e-6
