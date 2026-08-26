"""Mesh inspection, decimation, and defect-site heuristics.

Pure NumPy — no Qt — so the test suite can import this module headlessly.
"""
from __future__ import annotations

import math
import numpy as np


def inspect_mesh(vectors: np.ndarray) -> dict:
    """Classify a triangle array as watertight / inverted / empty.

    Edge manifold test: every undirected edge of a closed, consistently
    wound mesh is shared by exactly two triangles.
    """
    result = {
        "n_triangles": 0,
        "watertight": False,
        "inverted": False,
        "signed_vol_mm3": 0.0,
        "boundary_edges": 0,
        "nonmanifold_edges": 0,
        "warnings": [],
    }
    if vectors is None or len(vectors) == 0:
        result["warnings"].append("Mesh has no triangles.")
        return result

    verts = np.asarray(vectors, dtype=np.float64)
    result["n_triangles"] = int(len(verts))
    v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
    cross = np.cross(v1 - v0, v2 - v0)
    signed = float(np.sum(v0 * cross) / 6.0)
    result["signed_vol_mm3"] = signed
    result["inverted"] = signed < 0.0

    # Quantise vertices so coincident corners share an id
    q = np.round(verts.reshape(-1, 3), 6)
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    faces = inv.reshape(-1, 3)
    edges = np.concatenate(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0
    )
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    result["boundary_edges"] = int(np.sum(counts == 1))
    result["nonmanifold_edges"] = int(np.sum(counts > 2))
    result["watertight"] = (
        result["boundary_edges"] == 0
        and result["nonmanifold_edges"] == 0
        and abs(signed) > 1e-6
    )

    if abs(signed) < 1e-6:
        result["warnings"].append(
            "Volume is ~0 — the mesh may be open, flat, or have reversed faces."
        )
    if result["inverted"]:
        result["warnings"].append(
            "Signed volume is negative — face winding looks inverted."
        )
    if result["boundary_edges"] > 0:
        result["warnings"].append(
            f"Mesh is not watertight ({result['boundary_edges']} boundary edges). "
            "Volume and surface area may be wrong."
        )
    if result["nonmanifold_edges"] > 0:
        result["warnings"].append(
            f"Non-manifold mesh ({result['nonmanifold_edges']} edges shared by >2 faces)."
        )
    return result


def cluster_decimate(vectors: np.ndarray, max_tris: int = 25_000) -> np.ndarray:
    """Reduce triangle count by clustering vertices on a uniform grid.

    Preserves overall shape better than keeping every Nth triangle. If the
    clustered mesh is still over ``max_tris``, a uniform stride is applied
    as a last resort.
    """
    verts = np.asarray(vectors, dtype=np.float64)
    n = len(verts)
    if n <= max_tris:
        return verts

    pts = verts.reshape(-1, 3)
    bbmin = pts.min(axis=0)
    span = np.maximum(pts.max(axis=0) - bbmin, 1e-9)
    # Aim for enough cells that unique faces land near max_tris
    cells = max(6, int(round((max_tris * 2) ** (1.0 / 3.0) * 3)))
    res = span / cells
    keys = np.floor((pts - bbmin) / res).astype(np.int64)
    _, inv = np.unique(keys, axis=0, return_inverse=True)

    clustered = np.zeros((int(inv.max()) + 1, 3), dtype=np.float64)
    counts = np.zeros(clustered.shape[0], dtype=np.float64)
    np.add.at(clustered, inv, pts)
    np.add.at(counts, inv, 1.0)
    clustered /= counts[:, None]

    faces = inv.reshape(-1, 3)
    good = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    faces = faces[good]
    if len(faces) == 0:
        step = math.ceil(n / max_tris)
        return verts[::step]

    faces_sorted = np.sort(faces, axis=1)
    _, unique_idx = np.unique(faces_sorted, axis=0, return_index=True)
    faces = faces[np.sort(unique_idx)]
    out = clustered[faces]
    if len(out) > max_tris:
        step = math.ceil(len(out) / max_tris)
        out = out[::step]
    return out


def aabb_depths(vectors: np.ndarray) -> np.ndarray:
    """Per-face distance to the axis-aligned bounding box (mm).

    A cheap modulus proxy: small values are skin / thin walls (freeze first);
    large values are interior hot spots (freeze last).
    """
    verts = np.asarray(vectors, dtype=np.float64)
    if len(verts) == 0:
        return np.zeros(0, dtype=np.float64)
    centroids = verts.mean(axis=1)
    pts = verts.reshape(-1, 3)
    bbmin, bbmax = pts.min(axis=0), pts.max(axis=0)
    return np.minimum.reduce(
        [
            centroids[:, 0] - bbmin[0],
            bbmax[0] - centroids[:, 0],
            centroids[:, 1] - bbmin[1],
            bbmax[1] - centroids[:, 1],
            centroids[:, 2] - bbmin[2],
            bbmax[2] - centroids[:, 2],
        ]
    )


def find_defect_sites(
    vectors: np.ndarray, sprue_xy: tuple[float, float] | None = None
) -> dict[str, tuple[float, float, float]]:
    """Pick world-ish coordinates on the mesh for each defect family.

    * shrinkage / porosity — deepest AABB site (last to freeze)
    * cold shut — shallow face far from the XY centroid (thin extremity)
    * misrun — farthest from the sprue, biased toward high Z (end of fill)
    """
    verts = np.asarray(vectors, dtype=np.float64)
    if len(verts) == 0:
        origin = (0.0, 0.0, 0.0)
        return {
            "shrinkage_risk": origin,
            "cold_shut_risk": origin,
            "misrun_risk": origin,
        }

    centroids = verts.mean(axis=1)
    depths = aabb_depths(verts)
    vol_c = centroids.mean(axis=0)
    xy_dist = np.linalg.norm(centroids[:, :2] - vol_c[:2], axis=1)

    i_hot = int(np.argmax(depths))
    thin_score = xy_dist / (depths + 1e-3)
    i_thin = int(np.argmax(thin_score))

    if sprue_xy is None:
        sprue = vol_c[:2]
    else:
        sprue = np.asarray(sprue_xy, dtype=np.float64)
    pts = verts.reshape(-1, 3)
    zmin = float(pts[:, 2].min())
    d_sprue = np.linalg.norm(centroids[:, :2] - sprue, axis=1) + 0.3 * (
        centroids[:, 2] - zmin
    )
    i_mis = int(np.argmax(d_sprue))

    def _xyz(i: int) -> tuple[float, float, float]:
        c = centroids[i]
        return (float(c[0]), float(c[1]), float(c[2]))

    hot = _xyz(i_hot)
    return {
        "shrinkage_risk": hot,
        "cold_shut_risk": _xyz(i_thin),
        "misrun_risk": _xyz(i_mis),
    }


def scale_geometry(vol_cm3: float, surf_cm2: float, z_max: float, scale: float) -> tuple[float, float, float]:
    """Linear pattern scale → volume ∝ s³, area ∝ s², height ∝ s."""
    s = float(scale)
    return vol_cm3 * s ** 3, surf_cm2 * s ** 2, z_max * s
