"""Foundry helpers, session round-trip, and verdicts."""
import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.foundry import (
    mold_factor, gating_volumes_cm3, casting_yield_pct, apply_gating_ratio,
    snap_xy_to_silhouette, flask_fit, draft_analysis, undercut_hints,
    open_riser_modulus_cm, riser_ok, verdict_from_result, suggested_fixes,
)
from simulation.session import save_session, load_session, default_session
from simulation.worker import SimWorker
from tests.test_geometry import unit_cube_mesh
from tests.test_simulation import run_sim, BASE_PARAMS
from constants import METAL_DEFAULTS, FLASK_SIZES


class TestMoldAndYield:

    def test_green_sand_is_unity(self):
        assert abs(mold_factor("Green sand") - 1.0) < 1e-12

    def test_resin_is_faster_than_green(self):
        assert mold_factor("Resin / no-bake") < mold_factor("Green sand")

    def test_casting_yield(self):
        assert abs(casting_yield_pct(100, 25) - 80.0) < 1e-9

    def test_empty_gating_volume_is_zero(self):
        v = gating_volumes_cm3({})
        assert v["total"] == 0.0

    def test_sprue_volume_positive(self):
        v = gating_volumes_cm3({
            "has_sprue": True, "sprue_top_r": 8, "sprue_bot_r": 4, "sprue_height_mm": 100,
        })
        assert v["sprue"] > 0
        assert abs(v["total"] - v["sprue"]) < 1e-9


class TestGatingLayout:

    def test_ratio_1_2_2_gate_is_twice_sprue(self):
        sized = apply_gating_ratio(4.0, (1, 2, 2), runner_height_mm=8.0)
        a_s = math.pi * 16.0
        assert abs(sized["gate_area_mm2"] - 2 * a_s) < 1e-6
        assert abs(sized["runner_width_mm"] * 8.0 - 2 * a_s) < 1e-6

    def test_snap_goes_outside_aabb(self):
        x, y = snap_xy_to_silhouette(0, 0, -10, 10, -5, 5, margin=4)
        assert x <= -14 or x >= 14 or y <= -9 or y >= 9

    def test_flask_fit_too_small(self):
        # 200 mm square ≈ 7.9 in; with 0.5 in margin needs ~8.9 in — 6×6 fails
        info = flask_fit(-100, 100, -100, 100, 6, 6, presets=FLASK_SIZES)
        assert info["fits"] is False
        assert info["suggested"] is not None


class TestDraftUndercut:

    def test_cube_has_vertical_walls(self):
        cube = unit_cube_mesh() * 20.0
        d = draft_analysis(cube, min_deg=1.5)
        assert d["lock_count"] > 0

    def test_undercut_on_inverted_lip(self):
        # Two triangles: one above parting facing down, one below facing up
        mesh = np.array([
            [[0, 0, 10], [0, 1, 10], [1, 0, 10]],    # -Z, above parting → cope undercut
            [[0, 0, -10], [1, 0, -10], [0, 1, -10]],  # +Z, below parting → drag undercut
        ], dtype=float)
        u = undercut_hints(mesh, z_part=0.0)
        assert u["count"] == 2


class TestRiser:

    def test_modulus_positive(self):
        assert open_riser_modulus_cm() > 0.3

    def test_heavy_section_needs_riser(self):
        r = riser_ok(2.0, has_riser=False)
        assert r["needed"] is True
        assert r["adequate"] is False


class TestVerdictAndFixes:

    def test_ok_verdict(self):
        assert verdict_from_result({"defects": [], "warnings": [], "fill_possible": True}) == "ok"

    def test_fail_on_defect(self):
        assert verdict_from_result({"defects": ["Misrun"], "warnings": [], "fill_possible": True}) == "fail"

    def test_fixes_for_misrun(self):
        r = run_sim({**BASE_PARAMS, "pour_temp_f": 900})
        assert r["verdict"] == "fail"
        assert any("pour" in (f.get("fix") or "").lower() for f in r["fixes"])


class TestWorkerFoundry:

    def test_resin_mould_solidifies_faster(self):
        green = run_sim({**BASE_PARAMS, "mold_type": "Green sand"})
        resin = run_sim({**BASE_PARAMS, "mold_type": "Resin / no-bake"})
        assert resin["t_solidify_min"] < green["t_solidify_min"]

    def test_gating_metal_added_to_melt_mass(self):
        gating = {
            "has_sprue": True, "sprue_top_r": 8, "sprue_bot_r": 4,
            "sprue_height_mm": 100, "has_riser": True,
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating, "has_riser": True})
        part = 200.0 * 2.67
        assert r["pour_mass_g"] > part
        assert r["yield_pct"] < 100.0

    def test_new_result_keys(self):
        r = run_sim(BASE_PARAMS)
        for k in ("verdict", "fixes", "yield_pct", "gating_cm3", "mold_type", "part_mass_g"):
            assert k in r


class TestSession:

    def test_round_trip(self, tmp_path=None):
        data = default_session()
        data["metal"] = "316 Stainless Steel"
        data["pour_temp_f"] = 2800
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "job.cast.json")
            save_session(path, data)
            loaded = load_session(path)
        assert loaded["metal"] == "316 Stainless Steel"
        assert loaded["pour_temp_f"] == 2800
