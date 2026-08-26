"""Shop recipes, rigging wizard, melt ticket, pattern ticket."""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from constants import SHOP_RECIPES, FERROUS_METALS, shrink_scale_from_slider
from simulation.shop import (
    recipe, recipe_names, size_rigging, melt_ticket, pattern_ticket,
    write_pattern_stl, compare_setups, sand_mix_ticket,
)
from tests.test_geometry import unit_cube_mesh


class TestRecipes:

    def test_five_named_recipes(self):
        names = recipe_names()
        assert "A356 green sand" in names
        assert "Bronze ceramic shell" in names
        assert len(names) >= 5

    def test_shell_recipe_sets_process(self):
        rec = recipe("A356 ceramic shell")
        assert rec["process"] == "shell"
        assert rec["metal"] == "A356 Aluminum"
        assert rec["mold_temp_f"] >= 1000

    def test_iron_recipe_is_ferrous_ratio(self):
        rec = recipe("Gray iron sand")
        assert "1 : 4 : 4" in rec["gating_ratio"]
        assert rec["metal"] in FERROUS_METALS

    def test_printed_sand_recipe(self):
        rec = recipe("A356 printed sand")
        assert rec["process"] == "printed"
        assert rec["printed_mm"] == 15


class TestRiggingWizard:

    def test_sizes_positive(self):
        s = size_rigging(200.0, 180.0, "A356 Aluminum")
        assert s["sprue_bot_r_mm"] >= 3
        assert s["gate_area_mm2"] >= 10
        assert s["riser_r_mm"] >= 8
        assert s["runner_width_mm"] >= 4

    def test_ferrous_uses_1_4_4(self):
        s = size_rigging(200.0, 180.0, "Gray Iron (ASTM A48)")
        assert s["ferrous"] is True
        assert "1 : 4 : 4" in s["ratio_label"]

    def test_thicker_part_gets_bigger_riser(self):
        thin = size_rigging(100.0, 200.0, "A356 Aluminum")
        thick = size_rigging(400.0, 120.0, "A356 Aluminum")
        assert thick["riser_r_mm"] > thin["riser_r_mm"]

    def test_larger_volume_opens_gate(self):
        small = size_rigging(50.0, 80.0, "A356 Aluminum")
        big = size_rigging(800.0, 400.0, "A356 Aluminum")
        assert big["gate_area_mm2"] >= small["gate_area_mm2"]

    def test_wizard_includes_neck_and_basin(self):
        s = size_rigging(200.0, 180.0, "A356 Aluminum")
        assert s["neck_r_mm"] > 0
        assert s["basin_r_mm"] > 0
        assert s["filter_area_mm2"] > s["gate_area_mm2"]


class TestMeltTicket:

    def test_ingot_count(self):
        # 2000 g ≈ 4.41 lb → 5 × 1 lb ingots
        t = melt_ticket(2000.0, "A356 Aluminum", ingot_lb=1.0, furnace_lb=12.0)
        assert t["n_ingots"] == 5
        assert t["furnace_fits"] is True
        assert t["alloy_usd"] > 0

    def test_furnace_too_small(self):
        t = melt_ticket(10000.0, "Everdur Bronze (C52100)", furnace_lb=5.0)
        assert t["furnace_fits"] is False

    def test_zero_mass(self):
        t = melt_ticket(0.0, "A356 Aluminum")
        assert t["n_ingots"] == 0


class TestPatternTicket:

    def test_print_scale_matches_slider(self):
        t = pattern_ticket("A356 Aluminum", shrink_slider=106)
        assert abs(t["print_scale"] - shrink_scale_from_slider(106)) < 1e-9
        assert "×1.060" in t["hint"] or "×1.06" in t["hint"]

    def test_writes_stl(self):
        cube = unit_cube_mesh() * 10.0
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "pattern.stl")
            write_pattern_stl(cube, path, 1.06)
            assert os.path.getsize(path) > 80


class TestCompare:

    def test_delta_fill(self):
        a = {"fill_time_s": 4.0, "setup_label": "sand", "yield_pct": 70}
        b = {"fill_time_s": 6.0, "setup_label": "shell", "yield_pct": 55}
        d = compare_setups(a, b)
        assert abs(d["fill_time_s"]["d"] - 2.0) < 1e-9
        assert d["a_label"] == "sand"


class TestSandMixTicket:

    def test_green_sand_mix(self):
        t = sand_mix_ticket(
            mold_type="Green sand", part_cm3=200.0, gating_cm3=40.0,
            flask_w_in=8, flask_d_in=10, flask_h_in=6,
        )
        assert t["kind"] == "green"
        assert t["sand_lb"] > 0
        assert t["clay_lb"] > 0
        assert t["water_lb"] > 0

    def test_resin_mix(self):
        t = sand_mix_ticket(
            mold_type="Resin / no-bake", part_cm3=200.0, gating_cm3=40.0,
            flask_w_in=8, flask_d_in=10, flask_h_in=6,
        )
        assert t["kind"] == "resin"
        assert t["binder_g"] > 0

    def test_printed_mix(self):
        t = sand_mix_ticket(
            mold_type="Printed sand", part_cm3=200.0, gating_cm3=40.0,
            printed_mm=15, bbox_mm=(80, 60, 40), surf_cm2=180.0,
        )
        assert t["kind"] == "printed"
        assert t["n_vents"] >= 1
        assert t["sand_lb"] > 0
        assert "vent" in t["hint"].lower()

    def test_shell_has_no_sand_heap(self):
        t = sand_mix_ticket(mold_type="Ceramic shell", part_cm3=200.0, gating_cm3=20.0)
        assert t["kind"] == "shell"
        assert t["sand_lb"] == 0.0
