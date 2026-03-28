"""
Tests for build_results_text() in results/formatter.py.

Pure function — no Qt, no display, no imports beyond the formatter itself.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from results.formatter import build_results_text


# ---------------------------------------------------------------------------
# Minimal result dict that satisfies all formatter fields
# ---------------------------------------------------------------------------

BASE_RESULT = {
    "metal":          "A356 Aluminum",
    "pour_f":         1300,
    "mold_f":         77,
    "superheat":      225.0,
    "vol_cm3":        200.0,
    "surf_cm2":       180.0,
    "vsr":            1.1111,
    "fill_time_s":    4.5,
    "t_solidify_min": 3.70,
    "defects":        [],
    "warnings":       [],
}


def build(overrides: dict = {}) -> str:
    return build_results_text({**BASE_RESULT, **overrides})


def lines(overrides: dict = {}) -> list[str]:
    return build(overrides).splitlines()


# ---------------------------------------------------------------------------
# Structure / separators
# ---------------------------------------------------------------------------

class TestStructure:

    def test_starts_with_equals_banner(self):
        text = build()
        assert text.startswith("=" * 46)

    def test_ends_with_equals_banner(self):
        text = build()
        assert text.rstrip().endswith("=" * 46)

    def test_title_present(self):
        assert "SAND CASTING SIMULATION RESULTS" in build()

    def test_contains_three_dash_separators(self):
        dashes = [l for l in lines() if l == "-" * 46]
        assert len(dashes) == 3

    def test_output_is_string(self):
        assert isinstance(build(), str)


# ---------------------------------------------------------------------------
# Field values
# ---------------------------------------------------------------------------

class TestFieldValues:

    def test_metal_name(self):
        assert "A356 Aluminum" in build()

    def test_pour_temp_formatted(self):
        assert "1300" in build()

    def test_mold_temp_formatted(self):
        assert "77" in build()

    def test_superheat_one_decimal(self):
        assert "225.0" in build()

    def test_volume_two_decimals(self):
        assert "200.00" in build()

    def test_surface_two_decimals(self):
        assert "180.00" in build()

    def test_vsr_four_decimals(self):
        assert "1.1111" in build()

    def test_fill_time_one_decimal(self):
        assert "4.5" in build()

    def test_solidify_two_decimals(self):
        assert "3.70" in build()

    def test_bronze_metal_name(self):
        text = build({"metal": "Everdur Bronze (C52100)"})
        assert "Everdur Bronze (C52100)" in text


# ---------------------------------------------------------------------------
# Defects section
# ---------------------------------------------------------------------------

class TestDefectsSection:

    def test_no_defects_message(self):
        assert "No defect risks detected." in build({"defects": []})

    def test_defect_risks_header_present(self):
        text = build({"defects": ["Misrun risk superheat below 50 F"]})
        assert "DEFECT RISKS:" in text

    def test_single_defect_listed(self):
        text = build({"defects": ["Misrun risk superheat below 50 F"]})
        assert "Misrun risk" in text

    def test_multiple_defects_all_listed(self):
        defects = [
            "Misrun risk superheat below 50 F",
            "Cold shut risk thin wall with low superheat",
        ]
        text = build({"defects": defects})
        assert "Misrun risk" in text
        assert "Cold shut risk" in text

    def test_defect_lines_prefixed_with_dash(self):
        text = build({"defects": ["Misrun risk superheat below 50 F"]})
        assert "    - " in text

    def test_no_defects_section_when_empty(self):
        text = build({"defects": []})
        assert "DEFECT RISKS:" not in text

    def test_long_defect_wrapped_within_width(self):
        long_defect = "A" * 80
        text = build({"defects": [long_defect]})
        for ln in text.splitlines():
            assert len(ln) <= 50, f"Line too long: {ln!r}"


# ---------------------------------------------------------------------------
# Warnings section
# ---------------------------------------------------------------------------

class TestWarningsSection:

    def test_no_warnings_section_when_empty(self):
        text = build({"warnings": []})
        assert "WARNINGS:" not in text

    def test_warnings_header_present(self):
        text = build({"warnings": ["Burn-on warning mold temp above 120 F"]})
        assert "WARNINGS:" in text

    def test_single_warning_listed(self):
        text = build({"warnings": ["Burn-on warning mold temp above 120 F"]})
        assert "Burn-on warning" in text

    def test_multiple_warnings_all_listed(self):
        warnings = [
            "Burn-on warning mold temp above 120 F",
            "Low superheat warning superheat below 100 F",
        ]
        text = build({"warnings": warnings})
        assert "Burn-on warning" in text
        assert "Low superheat warning" in text

    def test_warning_lines_prefixed_with_dash(self):
        text = build({"warnings": ["Burn-on warning mold temp above 120 F"]})
        assert "    - " in text

    def test_blank_line_before_warnings_section(self):
        """There should be an empty line separating defects/no-defects from warnings."""
        text = build({
            "defects":  [],
            "warnings": ["Burn-on warning mold temp above 120 F"],
        })
        ls = text.splitlines()
        warnings_idx = next(i for i, l in enumerate(ls) if "WARNINGS:" in l)
        assert ls[warnings_idx - 1] == ""


# ---------------------------------------------------------------------------
# Both defects and warnings together
# ---------------------------------------------------------------------------

class TestDefectsAndWarnings:

    def test_both_sections_present(self):
        text = build({
            "defects":  ["Misrun risk superheat below 50 F"],
            "warnings": ["Burn-on warning mold temp above 120 F"],
        })
        assert "DEFECT RISKS:" in text
        assert "WARNINGS:" in text

    def test_defects_appear_before_warnings(self):
        text = build({
            "defects":  ["Misrun risk superheat below 50 F"],
            "warnings": ["Burn-on warning mold temp above 120 F"],
        })
        assert text.index("DEFECT RISKS:") < text.index("WARNINGS:")
