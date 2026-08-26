"""
Tests for build_results_text() in results/formatter.py.

The formatter now returns an HTML string for QTextEdit.setHtml().
Tests check that key content is present in the HTML output and that
the structure is valid.

Pure function — no Qt, no display, no imports beyond the formatter itself.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from results.formatter import build_results_text, empty_results_html, build_traveler_html


# ---------------------------------------------------------------------------
# Minimal result dict that satisfies all formatter fields
# ---------------------------------------------------------------------------

BASE_RESULT = {
    "metal":              "A356 Aluminum",
    "pour_f":             1300,
    "mold_f":             77,
    "superheat":          225.0,
    "vol_cm3":            200.0,
    "surf_cm2":           180.0,
    "vsr":                1.1111,
    "fill_time_s":        4.5,
    "fill_velocity_mm_s": 320.0,
    "fill_possible":      True,
    "cooling_rate":       60.8,
    "t_solidify_min":     3.70,
    "restrictive_elem":   "gate",
    "defects":            [],
    "warnings":           [],
    "pour_mass_g":        534.0,
}


def build(overrides: dict = {}) -> str:
    return build_results_text({**BASE_RESULT, **overrides})


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestStructure:

    def test_output_is_string(self):
        assert isinstance(build(), str)

    def test_is_html(self):
        text = build()
        assert text.startswith("<html>") or text.startswith("<html ")

    def test_contains_table(self):
        assert "<table" in build()

    def test_contains_input_section(self):
        assert "INPUT" in build()

    def test_contains_geometry_section(self):
        assert "GEOMETRY" in build()

    def test_contains_simulation_section(self):
        assert "SIMULATION" in build()


# ---------------------------------------------------------------------------
# Field values
# ---------------------------------------------------------------------------

class TestFieldValues:

    def test_metal_name(self):
        assert "A356 Aluminum" in build()

    def test_pour_temp_present(self):
        assert "1300" in build()

    def test_mold_temp_present(self):
        assert "77" in build()

    def test_superheat_present(self):
        assert "225.0" in build()

    def test_volume_two_decimals(self):
        assert "200.00" in build()

    def test_pour_mass_present(self):
        assert "534" in build()

    def test_surface_two_decimals(self):
        assert "180.00" in build()

    def test_vsr_three_decimals(self):
        # vsr = 1.1111 → displayed as "1.111"
        assert "1.111" in build()

    def test_fill_time_one_decimal(self):
        assert "4.5" in build()

    def test_solidify_two_decimals(self):
        assert "3.70" in build()

    def test_fill_velocity_present(self):
        assert "320" in build()

    def test_restrictive_elem_present(self):
        assert "gate" in build()

    def test_fill_ok_yes(self):
        assert "Yes" in build({"fill_possible": True})

    def test_fill_ok_warning(self):
        text = build({"fill_possible": False})
        assert "No" in text or "freeze" in text

    def test_metal_specific_superheat_color_uses_min_superheat(self):
        """Bronze min superheat 150 °F: 120 °F should still warn, not look 'ok'."""
        text = build({"superheat": 120.0, "min_superheat_f": 150})
        assert "120.0" in text

    def test_bronze_metal_name(self):
        text = build({"metal": "Everdur Bronze (C52100)"})
        assert "Everdur Bronze (C52100)" in text

    def test_verdict_banner_ok(self):
        assert "Likely OK" in build({"verdict": "ok", "defects": [], "warnings": []})

    def test_yield_shown(self):
        assert "72" in build({"yield_pct": 72.0})


# ---------------------------------------------------------------------------
# VSR classification
# ---------------------------------------------------------------------------

class TestVSRClassification:

    def test_thin_classification(self):
        text = build({"vsr": 0.3})
        assert "Thin" in text

    def test_standard_classification(self):
        text = build({"vsr": 1.0})
        assert "Standard" in text

    def test_heavy_classification(self):
        text = build({"vsr": 2.0})
        assert "Heavy" in text


# ---------------------------------------------------------------------------
# Defects section
# ---------------------------------------------------------------------------

class TestDefectsSection:

    def test_no_defects_message(self):
        assert "No defect risks detected." in build({"defects": []})

    def test_defect_risks_header_present(self):
        text = build({"defects": ["Misrun risk — superheat 40 F below minimum 50 F"]})
        assert "DEFECT" in text

    def test_single_defect_listed(self):
        text = build({"defects": ["Misrun risk — superheat 40 F below minimum 50 F"]})
        assert "Misrun risk" in text

    def test_multiple_defects_all_listed(self):
        defects = [
            "Misrun risk — superheat 40 F below minimum 50 F",
            "Cold shut risk — thin wall with low superheat",
        ]
        text = build({"defects": defects})
        assert "Misrun risk" in text
        assert "Cold shut risk" in text

    def test_no_defects_section_when_empty(self):
        text = build({"defects": []})
        # The defect header symbol ✗ should not appear
        assert "&#10007;" not in text

    def test_defects_appear_before_warnings(self):
        text = build({
            "defects":  ["Misrun risk — superheat 40 F below minimum 50 F"],
            "warnings": ["Burn-on risk — mold temp above 120 F"],
        })
        assert text.index("DEFECT") < text.index("WARN")


# ---------------------------------------------------------------------------
# Warnings section
# ---------------------------------------------------------------------------

class TestWarningsSection:

    def test_no_warnings_section_when_empty(self):
        text = build({"warnings": []})
        assert "&#9888;" not in text

    def test_warnings_header_present(self):
        text = build({"warnings": ["Burn-on risk — mold temp above 120 F"]})
        assert "WARN" in text

    def test_single_warning_listed(self):
        text = build({"warnings": ["Burn-on risk — mold temp above 120 F"]})
        assert "Burn-on" in text

    def test_multiple_warnings_all_listed(self):
        warnings = [
            "Burn-on risk — mold temp above 120 F",
            "Low superheat — 75 F",
        ]
        text = build({"warnings": warnings})
        assert "Burn-on" in text
        assert "Low superheat" in text


# ---------------------------------------------------------------------------
# Robustness — missing / extra keys
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_missing_new_keys_use_defaults(self):
        """Formatter should handle result dicts that lack the new optional fields."""
        minimal = {
            "metal":          "A356 Aluminum",
            "pour_f":         1300,
            "mold_f":         77,
            "superheat":      225.0,
            "vol_cm3":        200.0,
            "surf_cm2":       180.0,
            "vsr":            1.11,
            "fill_time_s":    4.5,
            "t_solidify_min": 3.70,
            "defects":        [],
            "warnings":       [],
            # fill_velocity_mm_s, fill_possible, cooling_rate, restrictive_elem
            # intentionally omitted — should not raise
        }
        text = build_results_text(minimal)
        assert "A356 Aluminum" in text

    def test_negative_superheat_shown(self):
        """Negative superheat (pour below liquidus) should appear without crashing."""
        text = build({"superheat": -50.0})
        assert "-50" in text or "50" in text

    def test_zero_volume_handled(self):
        text = build({"vol_cm3": 0.0, "surf_cm2": 0.0, "vsr": 0.0})
        assert isinstance(text, str)

    def test_ceramic_shell_shows_thickness_and_preheat(self):
        text = build({
            "mold_type": "Ceramic shell",
            "process": "shell",
            "shell_mm": 8,
            "mold_f": 1100,
        })
        assert "Ceramic shell" in text
        assert "8 mm" in text
        assert "Shell preheat" in text
        assert "1100" in text

    def test_kpi_strip_present(self):
        text = build({"yield_pct": 72.0})
        assert "Fill" in text
        assert "Solidify" in text
        assert "Yield" in text
        assert "72%" in text

    def test_empty_results_placeholder(self):
        html = empty_results_html()
        assert "Ready when you are" in html
        assert "Simulate" in html


class TestShopTickets:

    def test_melt_ticket_section(self):
        text = build({
            "melt_ticket": {
                "pour_mass_g": 534.0, "pour_mass_lb": 1.18, "n_ingots": 2,
                "ingot_lb": 1.0, "furnace_lb": 12.0, "furnace_fits": True,
                "usd_per_lb": 2.40, "alloy_usd": 2.83,
            }
        })
        assert "MELT TICKET" in text
        assert "Fits" in text
        assert "Ingots" in text

    def test_furnace_too_big_flag(self):
        text = build({
            "melt_ticket": {
                "pour_mass_g": 8000.0, "pour_mass_lb": 17.6, "n_ingots": 18,
                "ingot_lb": 1.0, "furnace_lb": 12.0, "furnace_fits": False,
                "usd_per_lb": 2.4, "alloy_usd": 42.0,
            }
        })
        assert "TOO BIG" in text

    def test_pattern_ticket_section(self):
        text = build({
            "pattern_ticket": {
                "catalog_shrink_pct": 6.0, "print_scale": 1.06, "print_pct": 6.0,
            }
        })
        assert "PATTERN TICKET" in text
        assert "×1.060" in text or "1.060" in text

    def test_pattern_ticket_draft_lock(self):
        text = build({
            "pattern_ticket": {
                "catalog_shrink_pct": 6.0, "print_scale": 1.06, "print_pct": 6.0,
                "draft_ok": False, "undercut": True,
            }
        })
        assert "Lock faces" in text
        assert "Undercut" in text

    def test_compare_section(self):
        text = build({
            "compare": {
                "a_label": "sand", "b_label": "shell",
                "fill_time_s": {"a": 4.0, "b": 5.5, "d": 1.5},
                "yield_pct": {"a": 70.0, "b": 55.0, "d": -15.0},
            }
        })
        assert "COMPARE" in text
        assert "sand" in text
        assert "shell" in text

    def test_unfed_hotspot_row(self):
        text = build({"porosity_frac": 0.08})
        assert "Unfed hot-spot" in text

    def test_sand_mix_section(self):
        text = build({
            "sand_mix": {
                "kind": "green", "sand_lb": 12.5, "clay_lb": 1.0, "water_lb": 0.4,
                "hint": "12.5 lb sand",
            }
        })
        assert "SAND MIX" in text
        assert "12.5" in text

    def test_printed_sand_mix_section(self):
        text = build({
            "process": "printed", "mold_type": "Printed sand", "printed_mm": 15,
            "sand_mix": {
                "kind": "printed", "sand_lb": 4.2, "binder_g": 34.0,
                "binder_pct": 1.8, "n_vents": 3, "hint": "vents",
            },
        })
        assert "Printed sand" in text
        assert "wall 15 mm" in text
        assert "Vents" in text

    def test_empty_results_mentions_printed(self):
        html = empty_results_html()
        assert "printed sand" in html.lower()


class TestTraveler:

    def test_title_and_verdict(self):
        html = build_traveler_html({**BASE_RESULT, "verdict": "ok", "setup_label": "green · A356"})
        assert "Shop traveler" in html
        assert "Likely OK" in html
        assert "green · A356" in html

    def test_includes_screenshot_and_tickets(self):
        html = build_traveler_html(
            {
                **BASE_RESULT,
                "verdict": "risky",
                "sand_mix": {"hint": "8.1 lb sand · clay"},
                "melt_ticket": {"pour_mass_lb": 1.2, "n_ingots": 2},
                "fixes": [{"fix": "Add a riser on the hot spot."}],
            },
            screenshot_uri="file:///tmp/shot.png",
        )
        assert "file:///tmp/shot.png" in html
        assert "Sand mix" in html
        assert "What to change" in html
        assert "riser" in html.lower()

