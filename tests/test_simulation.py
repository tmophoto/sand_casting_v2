"""
Tests for SimWorker physics calculations.

These tests run entirely headless — no display or Qt event loop required.
SimWorker.run() is called directly (not via QThread) and the finished
signal is captured with a simple lambda.
"""

import math
import sys
import os

# Make sure the project root is on sys.path regardless of where pytest is run from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from simulation.worker import SimWorker, chvorinov_B
from constants import METAL_DEFAULTS, shrink_scale_from_slider

# A QApplication instance is required for pyqtSignal to work, even headlessly
_app = QApplication.instance() or QApplication(sys.argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_sim(params: dict) -> dict:
    """Synchronously run a simulation and return the result dict."""
    result = {}
    worker = SimWorker(params)
    worker.finished.connect(lambda r: result.update(r))
    worker.run()
    return result


BASE_PARAMS = {
    "metal": "A356 Aluminum",
    "vol_cm3": 200.0,
    "surf_cm2": 180.0,
    "pour_temp_f": 1300,
    "mold_temp_f": 77,
    "thin_wall": False,
    "gating_params": {},
}


# ---------------------------------------------------------------------------
# Chvorinov's Rule  —  t = B × (V/A)²
# ---------------------------------------------------------------------------

class TestChvorinovRule:

    def test_aluminum_solidification_time(self):
        r = run_sim(BASE_PARAMS)
        metal = METAL_DEFAULTS["A356 Aluminum"]
        vsr = 200.0 / 180.0
        expected = chvorinov_B(metal, BASE_PARAMS["pour_temp_f"]) * vsr ** 2
        assert abs(r["t_solidify_min"] - expected) < 1e-9
        assert abs(chvorinov_B(metal, 1300) - 3.0) < 1e-9

    def test_bronze_solidification_time(self):
        params = {**BASE_PARAMS, "metal": "Everdur Bronze (C52100)",
                  "pour_temp_f": 1950}
        r = run_sim(params)
        metal = METAL_DEFAULTS["Everdur Bronze (C52100)"]
        vsr = 200.0 / 180.0
        expected = chvorinov_B(metal, 1950) * vsr ** 2
        assert abs(r["t_solidify_min"] - expected) < 1e-9

    def test_pour_mass_is_volume_times_density(self):
        r = run_sim(BASE_PARAMS)
        assert abs(r["pour_mass_g"] - 200.0 * 2.67) < 1e-9

    def test_higher_pour_increases_aluminum_B(self):
        r_hot = run_sim({**BASE_PARAMS, "pour_temp_f": 1400})
        r_nom = run_sim(BASE_PARAMS)
        assert r_hot["t_solidify_min"] > r_nom["t_solidify_min"]

    def test_higher_vsr_means_longer_solidification(self):
        """Larger V/A ratio → longer solidification (Chvorinov's law)."""
        r_small = run_sim({**BASE_PARAMS, "vol_cm3": 100.0, "surf_cm2": 200.0})
        r_large = run_sim({**BASE_PARAMS, "vol_cm3": 400.0, "surf_cm2": 200.0})
        assert r_large["t_solidify_min"] > r_small["t_solidify_min"]

    def test_vsr_reported_correctly(self):
        r = run_sim(BASE_PARAMS)
        assert abs(r["vsr"] - 200.0 / 180.0) < 1e-9

    def test_zero_volume_uses_default(self):
        """vol_cm3 <= 0 is clamped to 100.0 to avoid division by zero."""
        r = run_sim({**BASE_PARAMS, "vol_cm3": 0.0})
        assert r["vol_cm3"] == 100.0

    def test_zero_surface_uses_default(self):
        r = run_sim({**BASE_PARAMS, "surf_cm2": 0.0})
        assert r["surf_cm2"] == 120.0


# ---------------------------------------------------------------------------
# Fill time — Bernoulli hydraulics
# ---------------------------------------------------------------------------

class TestFillTimeHydraulics:

    def test_no_gating_uses_fallback(self):
        r = run_sim({**BASE_PARAMS, "gating_params": {}})
        expected = max(3.0, 200.0 / 80.0)
        assert abs(r["fill_time_s"] - expected) < 1e-9
        assert r["restrictive_elem"] == "fallback"

    def test_sprue_only(self):
        gating = {"has_sprue": True, "sprue_top_r": 7.5, "sprue_bot_r": 4.0}
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["fill_time_s"] > 0
        assert r["restrictive_elem"] in ("sprue_exit", "sprue")

    def test_sprue_plus_gate_gate_is_restrictive(self):
        """Sprue exit area >> gate area → gate is the restriction."""
        gating = {
            "has_sprue": True, "has_gate": True,
            "sprue_top_r": 20.0, "sprue_bot_r": 20.0,  # large sprue
            "gate_area_mm2": 10.0,                       # small gate
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["restrictive_elem"] == "gate"

    def test_sprue_plus_gate_sprue_is_restrictive(self):
        """Sprue exit area << gate area → sprue exit is the restriction."""
        gating = {
            "has_sprue": True, "has_gate": True,
            "sprue_top_r": 2.0, "sprue_bot_r": 2.0,   # tiny sprue
            "gate_area_mm2": 400.0,                     # large gate
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["restrictive_elem"] == "sprue_exit"

    def test_sprue_plus_runner(self):
        gating = {
            "has_sprue": True, "has_runner": True,
            "sprue_top_r": 7.5, "sprue_bot_r": 4.0,
            "runner_dia": 12.0,
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["restrictive_elem"] in ("sprue_exit", "runner")

    def test_fill_time_minimum_is_1_5s_with_gating(self):
        """Hydraulic fill time is clamped to ≥ 1.5 s."""
        gating = {
            "has_sprue": True, "has_gate": True,
            "sprue_top_r": 50.0, "sprue_bot_r": 50.0,
            "gate_area_mm2": 5000.0,
        }
        r = run_sim({**BASE_PARAMS, "vol_cm3": 0.01, "gating_params": gating})
        assert r["fill_time_s"] >= 1.5

    def test_fill_time_minimum_is_3s_fallback(self):
        """Fallback fill time is clamped to ≥ 3.0 s."""
        r = run_sim({**BASE_PARAMS, "vol_cm3": 0.01, "gating_params": {}})
        assert r["fill_time_s"] >= 3.0

    def test_sprue_fill_time_matches_torricelli(self):
        """Fill time and velocity share a single Cd × √(2gh) calculation."""
        gating = {"has_sprue": True, "sprue_top_r": 7.5, "sprue_bot_r": 4.0}
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        cd, g, h = 0.75, 9806.65, 100.0
        v_mm_s = cd * math.sqrt(2.0 * g * h)
        area_mm2 = math.pi * 4.0 ** 2
        q_cm3_s = (area_mm2 * v_mm_s) / 1000.0
        expected = max(1.5, 200.0 / q_cm3_s)
        assert abs(r["fill_time_s"] - expected) < 1e-9
        assert abs(r["fill_velocity_mm_s"] - v_mm_s) < 1e-9
        assert r["fill_time_s"] > 1.5  # must not be stuck on the 1.5 s clamp

    def test_rectangular_runner_uses_width_times_height(self):
        """A tiny rectangular runner is more restrictive than a 4 mm sprue exit."""
        gating = {
            "has_sprue": True, "has_runner": True,
            "sprue_top_r": 7.5, "sprue_bot_r": 4.0,
            "runner_width_mm": 2.0, "runner_height_mm": 2.0,
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["restrictive_elem"] == "runner"

    def test_all_gating_elements_compared(self):
        """Sprue + runner + gate: the smallest area wins, even if it is the runner."""
        gating = {
            "has_sprue": True, "has_runner": True, "has_gate": True,
            "sprue_top_r": 20.0, "sprue_bot_r": 20.0,
            "runner_width_mm": 2.0, "runner_height_mm": 2.0,
            "gate_area_mm2": 400.0,
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["restrictive_elem"] == "runner"

    def test_larger_volume_takes_longer_to_fill(self):
        gating = {"has_sprue": True, "sprue_top_r": 7.5, "sprue_bot_r": 4.0}
        r_small = run_sim({**BASE_PARAMS, "vol_cm3": 50.0,  "gating_params": gating})
        r_large = run_sim({**BASE_PARAMS, "vol_cm3": 500.0, "gating_params": gating})
        assert r_large["fill_time_s"] > r_small["fill_time_s"]


# ---------------------------------------------------------------------------
# Defect detection
# ---------------------------------------------------------------------------

class TestDefectDetection:

    def test_no_defects_normal_conditions(self):
        r = run_sim(BASE_PARAMS)   # superheat = 1300 - 1075 = 225 F
        assert r["defects"] == []

    def test_misrun_risk_low_superheat(self):
        """Superheat < 50 F triggers misrun defect."""
        params = {**BASE_PARAMS, "pour_temp_f": 1110}  # superheat = 35 F
        r = run_sim(params)
        assert any("misrun" in d.lower() for d in r["defects"])

    def test_cold_shut_thin_wall_low_superheat(self):
        """Thin wall + pour < melt + 150 F triggers cold shut defect."""
        params = {
            **BASE_PARAMS,
            "thin_wall": True,
            "pour_temp_f": 1100,  # 1100 < 1075 + 150 = 1225
        }
        r = run_sim(params)
        assert any("cold shut" in d.lower() for d in r["defects"])

    def test_no_cold_shut_without_thin_wall_flag(self):
        """Cold shut only triggers when thin_wall is True."""
        params = {**BASE_PARAMS, "thin_wall": False, "pour_temp_f": 1100}
        r = run_sim(params)
        assert not any("cold shut" in d.lower() for d in r["defects"])

    def test_burn_on_warning_high_mold_temp(self):
        """Mold temp > 120 F triggers burn-on warning."""
        params = {**BASE_PARAMS, "mold_temp_f": 150}
        r = run_sim(params)
        assert any("burn-on" in w.lower() for w in r["warnings"])

    def test_no_burn_on_warning_at_100f_mold(self):
        params = {**BASE_PARAMS, "mold_temp_f": 100}
        r = run_sim(params)
        assert not any("burn-on" in w.lower() for w in r["warnings"])

    def test_low_superheat_warning(self):
        """Superheat < 100 F triggers a warning (not a defect)."""
        params = {**BASE_PARAMS, "pour_temp_f": 1150}  # superheat = 75 F
        r = run_sim(params)
        assert any("superheat" in w.lower() for w in r["warnings"])

    def test_superheat_calculated_correctly(self):
        r = run_sim(BASE_PARAMS)
        metal = METAL_DEFAULTS["A356 Aluminum"]
        assert r["superheat"] == BASE_PARAMS["pour_temp_f"] - metal["melt_temp_f"]


# ---------------------------------------------------------------------------
# Shrinkage scale
# ---------------------------------------------------------------------------

class TestShrinkageScale:

    def test_default_shrink_scale_from_metal(self):
        r = run_sim(BASE_PARAMS)
        metal = METAL_DEFAULTS["A356 Aluminum"]
        expected = 1.0 + metal["shrinkage_pct"] / 100.0
        assert abs(r["shrink_scale"] - expected) < 1e-9

    def test_explicit_shrink_scale_overrides_default(self):
        params = {**BASE_PARAMS, "shrink_scale": 1.08}
        r = run_sim(params)
        assert abs(r["shrink_scale"] - 1.08) < 1e-9

    def test_bronze_shrink_scale(self):
        params = {**BASE_PARAMS, "metal": "Everdur Bronze (C52100)",
                  "pour_temp_f": 1950}
        r = run_sim(params)
        metal = METAL_DEFAULTS["Everdur Bronze (C52100)"]
        expected = 1.0 + metal["shrinkage_pct"] / 100.0
        assert abs(r["shrink_scale"] - expected) < 1e-9

    def test_slider_scale_matches_percent(self):
        """Slider 106 → ×1.06, not ×1.006."""
        assert abs(shrink_scale_from_slider(100) - 1.00) < 1e-12
        assert abs(shrink_scale_from_slider(106) - 1.06) < 1e-12
        assert abs(shrink_scale_from_slider(110) - 1.10) < 1e-12


# ---------------------------------------------------------------------------
# Result dict completeness
# ---------------------------------------------------------------------------

class TestResultDict:

    REQUIRED_KEYS = {
        "t_solidify_min", "fill_time_s", "fill_velocity_mm_s",
        "fill_possible", "cooling_rate", "restrictive_elem",
        "vsr", "vol_cm3", "surf_cm2", "superheat",
        "defects", "warnings", "metal", "pour_f", "mold_f", "shrink_scale",
        "min_superheat_f", "z_max", "pour_mass_g", "chvorinov_B",
    }

    def test_all_keys_present(self):
        r = run_sim(BASE_PARAMS)
        assert self.REQUIRED_KEYS.issubset(r.keys())

    def test_metal_name_echoed(self):
        r = run_sim(BASE_PARAMS)
        assert r["metal"] == "A356 Aluminum"

    def test_z_max_echoed_from_params(self):
        r = run_sim({**BASE_PARAMS, "z_max": 102.0})
        assert r["z_max"] == 102.0

    def test_pour_and_mold_temps_echoed(self):
        r = run_sim(BASE_PARAMS)
        assert r["pour_f"] == BASE_PARAMS["pour_temp_f"]
        assert r["mold_f"] == BASE_PARAMS["mold_temp_f"]


# ---------------------------------------------------------------------------
# Robustness & new physics
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_unknown_metal_raises_key_error(self):
        """A typo in the metal name should fail loudly, not silently produce nonsense."""
        import pytest
        with pytest.raises(KeyError):
            run_sim({**BASE_PARAMS, "metal": "6061 Aluminum"})

    def test_negative_superheat_flagged_as_defect(self):
        """Pour temp below liquidus → superheat < 0 → misrun defect."""
        params = {**BASE_PARAMS, "pour_temp_f": 900}  # well below A356 liquidus 1075
        r = run_sim(params)
        assert r["superheat"] < 0
        assert len(r["defects"]) > 0

    def test_fill_before_solidify_sanity(self):
        """For a well-gated part, fill should complete before solidification."""
        gating = {
            "has_sprue": True, "has_gate": True,
            "sprue_top_r": 7.5, "sprue_bot_r": 4.0, "gate_area_mm2": 40.0,
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["fill_possible"] is True

    def test_bronze_min_superheat_higher_than_aluminum(self):
        """Bronze requires more superheat than aluminum — min_superheat_f = 150."""
        from constants import METAL_DEFAULTS
        al_min  = METAL_DEFAULTS["A356 Aluminum"]["min_superheat_f"]
        br_min  = METAL_DEFAULTS["Everdur Bronze (C52100)"]["min_superheat_f"]
        assert br_min > al_min

    def test_new_metals_present_in_defaults(self):
        """All three new metals must be in METAL_DEFAULTS and have required keys."""
        from constants import METAL_DEFAULTS, METAL_PBR
        for name in ["Gray Iron (ASTM A48)", "Ductile Iron (65-45-12)", "316 Stainless Steel"]:
            assert name in METAL_DEFAULTS, f"Missing from METAL_DEFAULTS: {name}"
            assert name in METAL_PBR,      f"Missing from METAL_PBR: {name}"
            assert "min_superheat_f" in METAL_DEFAULTS[name]

    def test_fill_velocity_zero_without_gating(self):
        """Without gating the hydraulics fallback returns 0 velocity."""
        r = run_sim({**BASE_PARAMS, "gating_params": {}})
        assert r["fill_velocity_mm_s"] == 0.0

    def test_fill_velocity_positive_with_gating(self):
        """With a sprue and gate, fill velocity should be a positive number."""
        gating = {
            "has_sprue": True, "has_gate": True,
            "sprue_top_r": 7.5, "sprue_bot_r": 4.0, "gate_area_mm2": 40.0,
        }
        r = run_sim({**BASE_PARAMS, "gating_params": gating})
        assert r["fill_velocity_mm_s"] > 0

    def test_porosity_warning_without_riser(self):
        """Heavy section (high VSR) with no riser should trigger a porosity warning."""
        heavy = {**BASE_PARAMS, "vol_cm3": 2000.0, "surf_cm2": 600.0, "has_riser": False}
        r = run_sim(heavy)
        assert any("porosity" in w.lower() for w in r["warnings"])

    def test_taller_sprue_head_increases_velocity(self):
        gating = {"has_sprue": True, "sprue_top_r": 7.5, "sprue_bot_r": 4.0,
                  "sprue_height_mm": 100.0}
        r_low = run_sim({**BASE_PARAMS, "gating_params": gating})
        r_hi = run_sim({**BASE_PARAMS, "gating_params": {**gating, "sprue_height_mm": 400.0}})
        assert r_hi["fill_velocity_mm_s"] > r_low["fill_velocity_mm_s"]
        assert r_hi["fill_time_s"] < r_low["fill_time_s"]
