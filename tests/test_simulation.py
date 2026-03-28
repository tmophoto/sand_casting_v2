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
from simulation.worker import SimWorker
from constants import METAL_DEFAULTS

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
        expected = 3.0 * metal["mold_constant"] * vsr ** 2
        assert abs(r["t_solidify_min"] - expected) < 1e-9

    def test_bronze_solidification_time(self):
        params = {**BASE_PARAMS, "metal": "Everdur Bronze (C52100)",
                  "pour_temp_f": 1950}
        r = run_sim(params)
        metal = METAL_DEFAULTS["Everdur Bronze (C52100)"]
        vsr = 200.0 / 180.0
        expected = 3.0 * metal["mold_constant"] * vsr ** 2
        assert abs(r["t_solidify_min"] - expected) < 1e-9

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


# ---------------------------------------------------------------------------
# Result dict completeness
# ---------------------------------------------------------------------------

class TestResultDict:

    REQUIRED_KEYS = {
        "t_solidify_min", "fill_time_s", "restrictive_elem",
        "vsr", "vol_cm3", "surf_cm2", "superheat",
        "defects", "warnings", "metal", "pour_f", "mold_f", "shrink_scale",
    }

    def test_all_keys_present(self):
        r = run_sim(BASE_PARAMS)
        assert self.REQUIRED_KEYS.issubset(r.keys())

    def test_metal_name_echoed(self):
        r = run_sim(BASE_PARAMS)
        assert r["metal"] == "A356 Aluminum"

    def test_pour_and_mold_temps_echoed(self):
        r = run_sim(BASE_PARAMS)
        assert r["pour_f"] == BASE_PARAMS["pour_temp_f"]
        assert r["mold_f"] == BASE_PARAMS["mold_temp_f"]
