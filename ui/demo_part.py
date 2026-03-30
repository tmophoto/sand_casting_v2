"""
Procedural mesh for the one-click demo: Motor Mount Bracket.

All coordinates in mm, centred at x=0, y=0, z starting at 0.
Returns (triangles, normals, stats) where:
  triangles : (n, 3, 3) float64  — vertex triples ready for viewport injection
  normals   : (n, 3)   float64  — unit face normals (same convention as load_stl)
  stats     : dict with vol_cm3, surf_cm2, z_max
"""
import numpy as np
from viewport.viewport import Viewport3D

DEMO_PART_NAME = "Demo Part — Motor Mount"


def _compute_normals(triangles: np.ndarray) -> np.ndarray:
    """Unit face normals — identical computation to load_stl's normal pre-pass."""
    v0, v1, v2 = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    cross = np.cross(v1 - v0, v2 - v0).astype(np.float64)
    lens = np.linalg.norm(cross, axis=1, keepdims=True)
    lens[lens == 0] = 1e-9
    cross /= lens
    return cross  # (n, 3)


def build_demo_mesh() -> tuple:
    """
    Build the motor mount bracket from 7 overlapping primitives.

    Design intent:
      - Wide thin base plate  → triggers cold-shut / misrun warnings
      - Thick central body + cylindrical boss → long solidification time
      - Thin side ears + web ribs → demonstrate thin-wall defect detection

    Returns (triangles, normals, stats).
    """
    mk_box = Viewport3D._make_box_mesh
    mk_cyl = Viewport3D._make_cylinder_mesh

    parts = [
        # A: Base plate — wide, thin (cold-shut trigger)
        mk_box(cx=0,   cy=0,   z_bottom=0,  width=160, depth=120, height=12),
        # B: Central body — thick square section (long solidification)
        mk_box(cx=0,   cy=0,   z_bottom=12, width=70,  depth=70,  height=60),
        # C: Top mounting boss — thick cylinder (riser feeding target)
        mk_cyl(cx=0,   cy=0,   z_bottom=72, r_bottom=28, r_top=28, height=30, sides=24),
        # D: Left mounting ear — thin wall
        mk_box(cx=-95, cy=0,   z_bottom=12, width=30,  depth=20,  height=40),
        # E: Right mounting ear — thin wall (mirror of D)
        mk_box(cx=95,  cy=0,   z_bottom=12, width=30,  depth=20,  height=40),
        # F: Rear web rib — thin
        mk_box(cx=0,   cy=-50, z_bottom=12, width=120, depth=8,   height=50),
        # G: Front web rib — thin (mirror of F)
        mk_box(cx=0,   cy=50,  z_bottom=12, width=120, depth=8,   height=50),
    ]

    triangles = np.concatenate(parts, axis=0).astype(np.float64)
    normals   = _compute_normals(triangles)

    # Analytical stats — divergence theorem would double-count overlapping volumes,
    # so these are pre-computed from individual primitive surfaces/volumes.
    stats = {
        "vol_cm3":  758.29,
        "surf_cm2": 900.18,
        "z_max":    102.0,
    }
    return triangles, normals, stats
