"""Mesh inspection, QEM decimation, local thickness, and defect-site heuristics.

Pure NumPy — no Qt — so the test suite can import this module headlessly.
"""
from __future__ import annotations

import math
import numpy as np

THIN_WALL_MM = 6.0


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


def invert_winding(vectors: np.ndarray) -> np.ndarray:
    """Swap the second and third vertices of each triangle (flip normals)."""
    out = np.asarray(vectors, dtype=np.float64).copy()
    if len(out) == 0:
        return out
    out[:, [1, 2], :] = out[:, [2, 1], :]
    return out


def _weld(vectors: np.ndarray, ndigits: int = 6) -> tuple[np.ndarray, np.ndarray]:
    pts = np.asarray(vectors, dtype=np.float64).reshape(-1, 3)
    keys = np.round(pts, ndigits)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    n_uniq = int(inv.max()) + 1
    acc = np.zeros((n_uniq, 3), dtype=np.float64)
    cnt = np.zeros(n_uniq, dtype=np.float64)
    np.add.at(acc, inv, pts)
    np.add.at(cnt, inv, 1.0)
    verts = acc / cnt[:, None]
    faces = inv.reshape(-1, 3)
    good = (
        (faces[:, 0] != faces[:, 1])
        & (faces[:, 1] != faces[:, 2])
        & (faces[:, 0] != faces[:, 2])
    )
    return verts, faces[good]


def _vertex_quadrics(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    Q = np.zeros((len(verts), 4, 4), dtype=np.float64)
    if len(faces) == 0:
        return Q
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    lens = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(lens, 1e-12)
    d = -np.sum(n * v0, axis=1)
    planes = np.concatenate([n, d[:, None]], axis=1)
    K = planes[:, :, None] * planes[:, None, :]
    np.add.at(Q, faces[:, 0], K)
    np.add.at(Q, faces[:, 1], K)
    np.add.at(Q, faces[:, 2], K)
    return Q


def _optimal_contract(
    Q1: np.ndarray, Q2: np.ndarray, p1: np.ndarray, p2: np.ndarray
) -> tuple[float, np.ndarray]:
    Q = Q1 + Q2
    A = Q[:3, :3]
    b = -Q[:3, 3]
    target = 0.5 * (p1 + p2)
    try:
        if abs(np.linalg.det(A)) > 1e-12:
            solved = np.linalg.solve(A, b)
            if np.isfinite(solved).all():
                target = solved
    except np.linalg.LinAlgError:
        pass
    v = np.array([target[0], target[1], target[2], 1.0], dtype=np.float64)
    err = float(v @ Q @ v)
    if not np.isfinite(err) or err < 0.0:
        err = float(np.sum((p1 - p2) ** 2))
    return err, target


def qem_decimate(vectors: np.ndarray, max_tris: int = 25_000) -> np.ndarray:
    """Reduce triangle count with Garland–Heckbert quadric-error edge collapses.

    Vertices are welded, per-vertex 4×4 quadrics are accumulated from face
    planes, and lowest-error independent edges are contracted until the mesh
    is at most ``max_tris``. Falls back to grid clustering if QEM cannot
    reduce far enough (highly degenerate input).
    """
    verts_in = np.asarray(vectors, dtype=np.float64)
    n = len(verts_in)
    if n <= max_tris:
        return verts_in

    V, F = _weld(verts_in)
    if len(F) <= max_tris:
        return V[F]

    for _pass in range(48):
        if len(F) <= max_tris:
            break
        Q = _vertex_quadrics(V, F)
        edges = np.concatenate(
            [F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=0
        )
        edges.sort(axis=1)
        edges = np.unique(edges, axis=0)
        if len(edges) == 0:
            break

        costs = np.empty(len(edges), dtype=np.float64)
        targets = np.empty((len(edges), 3), dtype=np.float64)
        for i, (a, b) in enumerate(edges):
            costs[i], targets[i] = _optimal_contract(Q[a], Q[b], V[a], V[b])

        order = np.argsort(costs)
        used = np.zeros(len(V), dtype=bool)
        new_V = V.copy()
        collapse_from: dict[int, int] = {}
        # Each manifold collapse removes ~2 triangles.
        need = max(1, (len(F) - max_tris + 1) // 2)
        limit = max(need, max(1, int(len(V) * 0.18)))
        n_collapse = 0
        for ei in order:
            a = int(edges[ei, 0])
            b = int(edges[ei, 1])
            if used[a] or used[b]:
                continue
            used[a] = True
            used[b] = True
            new_V[a] = targets[ei]
            collapse_from[b] = a
            n_collapse += 1
            if n_collapse >= limit:
                break
        if n_collapse == 0:
            break

        remap = np.arange(len(V), dtype=np.int64)
        for src, dst in collapse_from.items():
            remap[src] = dst
        F = remap[F]
        good = (
            (F[:, 0] != F[:, 1])
            & (F[:, 1] != F[:, 2])
            & (F[:, 0] != F[:, 2])
        )
        F = F[good]
        if len(F) == 0:
            break
        used_idx = np.unique(F)
        inv = np.full(len(V), -1, dtype=np.int64)
        inv[used_idx] = np.arange(len(used_idx), dtype=np.int64)
        V = new_V[used_idx]
        F = inv[F]

    out = V[F] if len(F) else verts_in
    if len(out) > max_tris:
        out = cluster_decimate(out, max_tris=max_tris)
    return out


def cluster_decimate(vectors: np.ndarray, max_tris: int = 25_000) -> np.ndarray:
    """Fallback: cluster vertices on a uniform grid, then stride if needed."""
    verts = np.asarray(vectors, dtype=np.float64)
    n = len(verts)
    if n <= max_tris:
        return verts

    pts = verts.reshape(-1, 3)
    bbmin = pts.min(axis=0)
    span = np.maximum(pts.max(axis=0) - bbmin, 1e-9)
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
    good = (
        (faces[:, 0] != faces[:, 1])
        & (faces[:, 1] != faces[:, 2])
        & (faces[:, 0] != faces[:, 2])
    )
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
    """Per-face distance to the axis-aligned bounding box (mm). Fallback modulus."""
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


def _moller_trumbore_first_hit(
    origins: np.ndarray,
    dirs: np.ndarray,
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    skip: np.ndarray | None,
    max_t: float,
) -> np.ndarray:
    """First positive hit distance for each ray against a triangle soup.

    ``origins`` / ``dirs`` are (R, 3); triangles (T, 3). Returns (R,) with
    ``max_t`` when there is no hit.
    """
    e1 = v1 - v0
    e2 = v2 - v0
    n_r = len(origins)
    hits = np.full(n_r, max_t, dtype=np.float64)
    eps = 1e-8
    # Process rays one-at-a-time against all triangles — NumPy still vectorises
    # the triangle axis, and peak memory stays O(T) instead of O(R·T).
    for i in range(n_r):
        o = origins[i]
        d = dirs[i]
        pvec = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, pvec)
        valid = np.abs(det) > eps
        inv_det = np.zeros_like(det)
        inv_det[valid] = 1.0 / det[valid]
        tvec = o - v0
        u = np.einsum("ij,ij->i", tvec, pvec) * inv_det
        qvec = np.cross(tvec, e1)
        v = np.einsum("ij,ij->i", np.broadcast_to(d, e1.shape), qvec) * inv_det
        t = np.einsum("ij,ij->i", e2, qvec) * inv_det
        hit = valid & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > 1e-4) & (t < max_t)
        if skip is not None:
            hit[skip[i]] = False
        if np.any(hit):
            hits[i] = float(t[hit].min())
    return hits


def local_thickness(vectors: np.ndarray, max_occluders: int = 8_000) -> np.ndarray:
    """Approximate local wall thickness (mm) by an inward ray from each face.

    From each triangle centroid, shoot along ``-normal`` and measure the
    first intersection with another face. Open meshes that miss return the
    AABB-depth fallback for that face.
    """
    verts = np.asarray(vectors, dtype=np.float64)
    n = len(verts)
    if n == 0:
        return np.zeros(0, dtype=np.float64)

    v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
    nrm = np.cross(v1 - v0, v2 - v0)
    lens = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.maximum(lens, 1e-12)
    centroids = (v0 + v1 + v2) / 3.0
    signed = float(np.sum(v0 * np.cross(v1 - v0, v2 - v0)) / 6.0)
    if signed < 0.0:
        nrm = -nrm

    pts = verts.reshape(-1, 3)
    diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    max_t = max(diag, 1.0)
    fallback = aabb_depths(verts)

    step = max(1, int(math.ceil(n / max_occluders)))
    occ = np.arange(0, n, step)
    ov0, ov1, ov2 = v0[occ], v1[occ], v2[occ]

    origins = centroids - nrm * 1e-3
    dirs = -nrm
    thick = np.array(fallback, dtype=np.float64, copy=True)

    chunk = 64
    occ_index = {int(j): k for k, j in enumerate(occ)}
    for start in range(0, n, chunk):
        sl = slice(start, min(start + chunk, n))
        idx = np.arange(start, min(start + chunk, n))
        skip = np.zeros((len(idx), len(occ)), dtype=bool)
        for row, fi in enumerate(idx):
            k = occ_index.get(int(fi))
            if k is not None:
                skip[row, k] = True
        hits = _moller_trumbore_first_hit(
            origins[sl], dirs[sl], ov0, ov1, ov2, skip, max_t
        )
        use = hits < max_t * 0.999
        thick[sl] = np.where(use, hits, fallback[sl])
    return thick


def find_defect_sites(
    vectors: np.ndarray, sprue_xy: tuple[float, float] | None = None
) -> dict[str, tuple[float, float, float]]:
    """Pick world-ish coordinates on the mesh for each defect family.

    * shrinkage / porosity — thickest local section (last to freeze)
    * cold shut — thinnest face far from the XY centroid
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
    depths = local_thickness(verts)
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

    return {
        "shrinkage_risk": _xyz(i_hot),
        "cold_shut_risk": _xyz(i_thin),
        "misrun_risk": _xyz(i_mis),
    }


def min_wall_mm(vectors: np.ndarray) -> float:
    t = local_thickness(np.asarray(vectors, dtype=np.float64))
    if len(t) == 0:
        return 0.0
    return float(np.min(t))


def scale_geometry(vol_cm3: float, surf_cm2: float, z_max: float, scale: float) -> tuple[float, float, float]:
    """Linear pattern scale → volume ∝ s³, area ∝ s², height ∝ s."""
    s = float(scale)
    return vol_cm3 * s ** 3, surf_cm2 * s ** 2, z_max * s


def load_obj_triangles(path: str) -> np.ndarray:
    """Load a triangulated (or fan-triangulated) Wavefront OBJ as (N, 3, 3) mm."""
    verts: list[list[float]] = []
    tris: list[list[list[float]]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts[0] == "v" and len(parts) >= 4:
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == "f" and len(parts) >= 4:
                idx = []
                for p in parts[1:]:
                    i = int(p.split("/")[0])
                    i = i - 1 if i > 0 else len(verts) + i
                    idx.append(i)
                for k in range(1, len(idx) - 1):
                    tris.append([verts[idx[0]], verts[idx[k]], verts[idx[k + 1]]])
    if not tris:
        raise ValueError("OBJ file has no triangular faces.")
    return np.asarray(tris, dtype=np.float64)


def load_mesh_vectors(path: str) -> np.ndarray:
    """Load STL or OBJ triangles as an (N, 3, 3) array."""
    from pathlib import Path
    suf = Path(path).suffix.lower()
    if suf == ".obj":
        return load_obj_triangles(path)
    if suf in {".stl", ""}:
        from stl import mesh as stl_mesh
        loaded = stl_mesh.Mesh.from_file(path)
        return np.asarray(loaded.vectors, dtype=np.float64)
    raise ValueError(f"Unsupported mesh type '{suf}'. Use STL or OBJ.")
