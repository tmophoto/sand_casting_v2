"""Coarse voxel fill / freeze / porosity — MAGMA-looking results without CFD.

Pipeline (all NumPy, no scipy):
  1. Rasterize the STL into a padded occupancy grid (~32³).
  2. Gravity flood from the gate: downhill first, then lateral.
  3. Euclidean-ish distance to mold → freeze time ~ B × (dist)².
  4. Isolated-liquid porosity: last-to-freeze voxels not fed by a riser.
  5. Niyama proxy: freeze / (local gradient + ε) on the mesh faces.
  6. Map voxel fields onto triangle centroids for viewport paint.

This is SOLIDCast-class, not MAGMA. Grid stays coarse on purpose so a
hobby desktop finishes in well under a second.
"""
from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np


TARGET_CELLS = 32
MAX_CELLS = 40
PAD = 2


def _grid_shape(mins: np.ndarray, maxs: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int, int]]:
    span = np.maximum(maxs - mins, 1.0)
    pitch = float(np.max(span) / TARGET_CELLS)
    pitch = max(pitch, 0.5)
    n = np.ceil(span / pitch).astype(int) + 2 * PAD
    n = np.clip(n, 8, MAX_CELLS)
    return n, pitch, (int(n[0]), int(n[1]), int(n[2]))


def rasterize(vectors: np.ndarray, pitch: float | None = None) -> dict[str, Any]:
    """Stamp triangles then flood-fill the interior from the outside."""
    v = np.asarray(vectors, dtype=np.float64)
    if v.size == 0:
        empty = np.zeros((8, 8, 8), dtype=bool)
        return {
            "occ": empty,
            "mins": np.zeros(3),
            "pitch": 1.0,
            "shape": empty.shape,
        }
    mins = v.reshape(-1, 3).min(axis=0)
    maxs = v.reshape(-1, 3).max(axis=0)
    n, p, shape = _grid_shape(mins, maxs)
    if pitch is not None:
        p = float(pitch)
        span = np.maximum(maxs - mins, 1.0)
        n = np.clip(np.ceil(span / p).astype(int) + 2 * PAD, 8, MAX_CELLS)
        shape = (int(n[0]), int(n[1]), int(n[2]))
    origin = mins - PAD * p
    nx, ny, nz = shape
    surface = np.zeros(shape, dtype=bool)

    # Stamp each triangle's AABB (coarse but robust at this pitch).
    for tri in v:
        tmin = ((tri.min(axis=0) - origin) / p).astype(int)
        tmax = ((tri.max(axis=0) - origin) / p).astype(int)
        tmin = np.clip(tmin, 0, [nx - 1, ny - 1, nz - 1])
        tmax = np.clip(tmax, 0, [nx - 1, ny - 1, nz - 1])
        surface[tmin[0]:tmax[0] + 1, tmin[1]:tmax[1] + 1, tmin[2]:tmax[2] + 1] = True

    # Outside flood from a corner; interior = not-outside.
    outside = np.zeros(shape, dtype=bool)
    q: deque[tuple[int, int, int]] = deque()
    if not surface[0, 0, 0]:
        q.append((0, 0, 0))
        outside[0, 0, 0] = True
    while q:
        i, j, k = q.popleft()
        for di, dj, dk in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            ni, nj, nk = i + di, j + dj, k + dk
            if 0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz:
                if not outside[ni, nj, nk] and not surface[ni, nj, nk]:
                    outside[ni, nj, nk] = True
                    q.append((ni, nj, nk))
    occ = ~outside  # surface + interior
    return {
        "occ": occ,
        "surface": surface,
        "origin": origin,
        "mins": mins,
        "maxs": maxs,
        "pitch": p,
        "shape": shape,
    }


def world_to_ijk(xyz: np.ndarray, origin: np.ndarray, pitch: float, shape: tuple[int, int, int]) -> tuple[int, int, int]:
    ijk = ((np.asarray(xyz, dtype=np.float64) - origin) / pitch).astype(int)
    ijk = np.clip(ijk, 0, np.array(shape) - 1)
    return int(ijk[0]), int(ijk[1]), int(ijk[2])


def dist_to_mold(occ: np.ndarray) -> np.ndarray:
    """Chebyshev-ish distance (voxels) from metal to nearest mold cell.

    Iterative 6-neighbor grow — O(n) and good enough for freeze ranking.
    """
    dist = np.zeros(occ.shape, dtype=np.float32)
    dist[occ] = 1.0e6
    # seed: occupied cells that touch a mold cell
    nx, ny, nz = occ.shape
    changed = True
    # First pass: mark boundary
    occ_pad = np.pad(occ, 1, constant_values=False)
    inner = occ_pad[1:-1, 1:-1, 1:-1]
    neigh = (
        occ_pad[2:, 1:-1, 1:-1]
        & occ_pad[:-2, 1:-1, 1:-1]
        & occ_pad[1:-1, 2:, 1:-1]
        & occ_pad[1:-1, :-2, 1:-1]
        & occ_pad[1:-1, 1:-1, 2:]
        & occ_pad[1:-1, 1:-1, :-2]
    )
    boundary = inner & ~neigh
    dist[boundary] = 1.0
    # Grow inward
    cur = dist.copy()
    for d in range(2, max(occ.shape) + 2):
        pad = np.pad(cur < 1.0e5, 1, constant_values=False)
        grow = (
            pad[2:, 1:-1, 1:-1]
            | pad[:-2, 1:-1, 1:-1]
            | pad[1:-1, 2:, 1:-1]
            | pad[1:-1, :-2, 1:-1]
            | pad[1:-1, 1:-1, 2:]
            | pad[1:-1, 1:-1, :-2]
        )
        new = occ & (cur > 1.0e5) & grow
        if not np.any(new):
            break
        cur[new] = float(d)
    cur[cur > 1.0e5] = float(max(occ.shape))
    cur[~occ] = 0.0
    return cur


def gravity_flood(
    occ: np.ndarray,
    gate_ijk: tuple[int, int, int] | None,
) -> np.ndarray:
    """Fill order: 0 = empty/unfilled, 1..N = fill sequence.

    Prefers −Z (downhill) then lateral. Starts at the gate voxel, or the
    highest occupied cell if the gate is outside the part.
    """
    order = np.zeros(occ.shape, dtype=np.int32)
    if not np.any(occ):
        return order
    nx, ny, nz = occ.shape
    start = gate_ijk
    if start is None or not occ[start]:
        # highest occupied (pour from the top)
        zs = np.where(occ)
        start = (int(zs[0][np.argmax(zs[2])]), int(zs[1][np.argmax(zs[2])]), int(zs[2].max()))
    # Two-level BFS: downhill first
    q: deque[tuple[int, int, int]] = deque([start])
    order[start] = 1
    n = 1
    neigh = ((0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1))
    while q:
        i, j, k = q.popleft()
        # try downhill first by sorting neighbors
        cands = []
        for di, dj, dk in neigh:
            ni, nj, nk = i + di, j + dj, k + dk
            if 0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz:
                if occ[ni, nj, nk] and order[ni, nj, nk] == 0:
                    cands.append((dk, ni, nj, nk))  # dk=-1 first
        cands.sort(key=lambda t: t[0])
        for _, ni, nj, nk in cands:
            if order[ni, nj, nk] == 0:
                n += 1
                order[ni, nj, nk] = n
                q.append((ni, nj, nk))
    return order


def freeze_time_s(dist: np.ndarray, pitch_mm: float, B: float) -> np.ndarray:
    """Chvorinov-on-a-grid: t = B × (pitch×dist / 10 / 2)² minutes → seconds.

    dist is in voxels to mold; half-thickness ≈ pitch * dist.
    """
    thick_cm = (dist * pitch_mm) / 10.0  # voxel → cm (full thickness-ish)
    modulus = thick_cm / 2.0
    t_min = float(B) * modulus ** 2
    return t_min * 60.0


def isolated_porosity(
    occ: np.ndarray,
    freeze_s: np.ndarray,
    feeder_ijk: list[tuple[int, int, int]],
    top_frac: float = 0.18,
) -> np.ndarray:
    """True on last-to-freeze voxels that cannot feed from a riser/sprue.

    Feeding path: walk through voxels whose freeze time is ≥ the current
    voxel (still liquid when this one freezes).
    """
    if not np.any(occ):
        return np.zeros(occ.shape, dtype=bool)
    tmax = float(freeze_s[occ].max()) if np.any(occ) else 0.0
    hot = occ & (freeze_s >= (1.0 - top_frac) * tmax)
    if not np.any(hot):
        return np.zeros(occ.shape, dtype=bool)
    nx, ny, nz = occ.shape
    fed = np.zeros(occ.shape, dtype=bool)
    q: deque[tuple[int, int, int]] = deque()
    for ijk in feeder_ijk:
        i, j, k = ijk
        if 0 <= i < nx and 0 <= j < ny and 0 <= k < nz and occ[i, j, k]:
            fed[i, j, k] = True
            q.append((i, j, k))
    if not q:
        # no feeder in the part — every hot voxel is isolated
        return hot
    while q:
        i, j, k = q.popleft()
        t0 = freeze_s[i, j, k]
        for di, dj, dk in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            ni, nj, nk = i + di, j + dj, k + dk
            if 0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz:
                if occ[ni, nj, nk] and not fed[ni, nj, nk] and freeze_s[ni, nj, nk] >= t0 * 0.85:
                    fed[ni, nj, nk] = True
                    q.append((ni, nj, nk))
    return hot & ~fed


def apply_chills(dist: np.ndarray, occ: np.ndarray, chill_ijks: list[tuple[int, int, int]], radius: int = 2) -> np.ndarray:
    """Treat chill neighborhoods as extra mold (dist → 1)."""
    out = dist.copy()
    nx, ny, nz = occ.shape
    for i, j, k in chill_ijks:
        i0, i1 = max(0, i - radius), min(nx, i + radius + 1)
        j0, j1 = max(0, j - radius), min(ny, j + radius + 1)
        k0, k1 = max(0, k - radius), min(nz, k + radius + 1)
        sl = occ[i0:i1, j0:j1, k0:k1]
        out[i0:i1, j0:j1, k0:k1][sl] = np.minimum(out[i0:i1, j0:j1, k0:k1][sl], 1.0)
    return out


def apply_sleeve(dist: np.ndarray, occ: np.ndarray, riser_ijk: tuple[int, int, int], radius: int = 3) -> np.ndarray:
    """Insulating sleeve: inflate distance (slower freeze) around the riser."""
    out = dist.copy()
    nx, ny, nz = occ.shape
    i, j, k = riser_ijk
    i0, i1 = max(0, i - radius), min(nx, i + radius + 1)
    j0, j1 = max(0, j - radius), min(ny, j + radius + 1)
    k0, k1 = max(0, k - radius), min(nz, k + radius + 1)
    sl = occ[i0:i1, j0:j1, k0:k1]
    out[i0:i1, j0:j1, k0:k1][sl] = out[i0:i1, j0:j1, k0:k1][sl] * 1.6
    return out


def niyama_proxy(freeze_s: np.ndarray, pitch_mm: float) -> np.ndarray:
    """Ny ≈ t / (|∇t| + ε). Low values → shrinkage risk."""
    gx = np.gradient(freeze_s, axis=0)
    gy = np.gradient(freeze_s, axis=1)
    gz = np.gradient(freeze_s, axis=2)
    grad = np.sqrt(gx * gx + gy * gy + gz * gz) / max(pitch_mm, 0.5)
    return freeze_s / (grad + 1.0)


def map_to_faces(
    vectors: np.ndarray,
    field: np.ndarray,
    origin: np.ndarray,
    pitch: float,
) -> np.ndarray:
    """Sample a voxel field at each triangle centroid."""
    v = np.asarray(vectors, dtype=np.float64)
    if v.size == 0:
        return np.zeros(0, dtype=np.float32)
    cents = v.mean(axis=1)
    ijk = ((cents - origin) / pitch).astype(int)
    nx, ny, nz = field.shape
    ijk[:, 0] = np.clip(ijk[:, 0], 0, nx - 1)
    ijk[:, 1] = np.clip(ijk[:, 1], 0, ny - 1)
    ijk[:, 2] = np.clip(ijk[:, 2], 0, nz - 1)
    return field[ijk[:, 0], ijk[:, 1], ijk[:, 2]].astype(np.float32)


def analyze(
    vectors: np.ndarray,
    B: float,
    gate_xyz: np.ndarray | None = None,
    riser_xyz: np.ndarray | None = None,
    sprue_xyz: np.ndarray | None = None,
    chills_xyz: list[np.ndarray] | None = None,
    sleeve: bool = False,
) -> dict[str, Any]:
    """Full voxel pass. Returns occupancy, fill order, freeze, porosity, Ny."""
    grid = rasterize(vectors)
    occ = grid["occ"]
    origin = grid["origin"]
    pitch = float(grid["pitch"])
    shape = grid["shape"]

    def _ijk(xyz):
        if xyz is None:
            return None
        return world_to_ijk(np.asarray(xyz, dtype=np.float64), origin, pitch, shape)

    gate_ijk = _ijk(gate_xyz)
    fill = gravity_flood(occ, gate_ijk)
    dist = dist_to_mold(occ)
    if chills_xyz:
        chill_ijks = [ijk for ijk in (_ijk(c) for c in chills_xyz if c is not None) if ijk]
        if chill_ijks:
            dist = apply_chills(dist, occ, chill_ijks)
    riser_ijk = _ijk(riser_xyz)
    if sleeve and riser_ijk is not None:
        dist = apply_sleeve(dist, occ, riser_ijk)
    freeze = freeze_time_s(dist, pitch, B)
    feeders = []
    for pnt in (riser_xyz, sprue_xyz, gate_xyz):
        ijk = _ijk(pnt)
        if ijk is not None:
            feeders.append(ijk)
    poro = isolated_porosity(occ, freeze, feeders)
    ny = niyama_proxy(freeze, pitch)

    n_metal = int(occ.sum())
    n_poro = int(poro.sum())
    n_unfilled = int(occ.sum() - (fill > 0).sum())
    return {
        "occ": occ,
        "origin": origin,
        "pitch": pitch,
        "shape": shape,
        "fill_order": fill,
        "dist": dist,
        "freeze_s": freeze,
        "porosity": poro,
        "niyama": ny,
        "n_metal": n_metal,
        "n_porosity": n_poro,
        "porosity_frac": (n_poro / n_metal) if n_metal else 0.0,
        "n_unfilled": n_unfilled,
        "face_fill": map_to_faces(vectors, fill.astype(np.float32), origin, pitch),
        "face_freeze": map_to_faces(vectors, freeze, origin, pitch),
        "face_porosity": map_to_faces(vectors, poro.astype(np.float32), origin, pitch),
        "face_niyama": map_to_faces(vectors, ny, origin, pitch),
        "face_dist": map_to_faces(vectors, dist, origin, pitch),
    }
