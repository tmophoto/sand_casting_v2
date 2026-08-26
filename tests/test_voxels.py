"""Coarse voxel occupancy, gravity flood, freeze ranking, porosity."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.voxels import (
    rasterize, gravity_flood, dist_to_mold, freeze_time_s,
    isolated_porosity, analyze, map_to_faces, world_to_ijk,
)
from tests.test_geometry import unit_cube_mesh
from tests.test_simulation import run_sim, BASE_PARAMS


def _cube(mm: float = 40.0) -> np.ndarray:
    return unit_cube_mesh() * mm


class TestRasterize:

    def test_cube_has_interior(self):
        grid = rasterize(_cube(40.0))
        assert int(grid["occ"].sum()) > 20
        assert grid["pitch"] > 0

    def test_empty_mesh(self):
        grid = rasterize(np.zeros((0, 3, 3)))
        assert grid["occ"].shape[0] >= 8


class TestFloodAndFreeze:

    def test_flood_reaches_most_of_the_cube(self):
        grid = rasterize(_cube(40.0))
        order = gravity_flood(grid["occ"], None)
        filled = int((order > 0).sum())
        metal = int(grid["occ"].sum())
        assert filled >= 0.8 * metal

    def test_center_is_thicker_than_skin(self):
        grid = rasterize(_cube(40.0))
        dist = dist_to_mold(grid["occ"])
        assert float(dist[grid["occ"]].max()) > float(dist[grid["occ"]].min())

    def test_freeze_scales_with_B(self):
        grid = rasterize(_cube(40.0))
        dist = dist_to_mold(grid["occ"])
        t1 = freeze_time_s(dist, grid["pitch"], 1.0)
        t2 = freeze_time_s(dist, grid["pitch"], 2.0)
        assert float(t2.max()) > float(t1.max())


class TestPorosityAndAnalyze:

    def test_no_feeder_marks_hot_voxels(self):
        grid = rasterize(_cube(40.0))
        dist = dist_to_mold(grid["occ"])
        freeze = freeze_time_s(dist, grid["pitch"], 3.0)
        poro = isolated_porosity(grid["occ"], freeze, [])
        assert int(poro.sum()) > 0

    def test_analyze_returns_face_fields(self):
        mesh = _cube(40.0)
        out = analyze(mesh, B=3.0, gate_xyz=np.array([20.0, 0.0, 20.0]))
        assert len(out["face_freeze"]) == len(mesh)
        assert out["n_metal"] > 0
        assert "porosity_frac" in out

    def test_map_to_faces_length(self):
        mesh = _cube(40.0)
        grid = rasterize(mesh)
        field = grid["occ"].astype(np.float32)
        faces = map_to_faces(mesh, field, grid["origin"], grid["pitch"])
        assert len(faces) == len(mesh)


class TestWorkerVoxels:

    def test_mesh_adds_porosity_keys(self):
        mesh = _cube(40.0)
        r = run_sim({**BASE_PARAMS, "mesh_vectors": mesh,
                     "gate_xyz": np.array([20.0, 0.0, 20.0])})
        assert "porosity_frac" in r
        assert "melt_ticket" in r
        assert "pattern_ticket" in r
        assert r["melt_ticket"]["pour_mass_g"] > 0
