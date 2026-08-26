"""Shop recipes, rigging wizard, melt ticket, pattern ticket.

These are the SOLIDCast / foundry-floor extras CAE tools skip:
size the whole gating tree in one click, tell the caster how many
ingots to melt, and print a shrink-compensated pattern STL.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from constants import (
    ALLOY_USD_PER_LB,
    DEFAULT_FURNACE_LB,
    DEFAULT_INGOT_LB,
    FERROUS_METALS,
    GREEN_SAND_CLAY_PCT,
    GREEN_SAND_WATER_PCT,
    IN3_TO_CM3,
    LB_G,
    METAL_DEFAULTS,
    PRINTED_BINDER_PCT,
    RESIN_BINDER_PCT,
    SAND_BULK_G_CM3,
    SHOP_RECIPES,
    shrink_scale_from_slider,
)
from simulation.foundry import apply_gating_ratio, is_printed_sand, is_shell_mold, open_riser_modulus_cm


# Target fill time for the wizard (seconds). Short enough to avoid
# misruns, long enough to keep gate velocity below erosion.
WIZARD_FILL_S = 6.0
_CD = 0.75
_G = 9.80665  # m/s²
RISER_SAFETY = 1.25


def recipe_names() -> list[str]:
    return list(SHOP_RECIPES.keys())


def recipe(name: str) -> dict[str, Any]:
    return dict(SHOP_RECIPES.get(name, {}))


def size_rigging(
    vol_cm3: float,
    surf_cm2: float,
    metal: str,
    sprue_h_mm: float = 100.0,
) -> dict[str, Any]:
    """Pick sprue / runner / gate / riser for this metal and part.

    Hydraulics: Bernoulli velocity from sprue height, then A = Q / (Cd v)
    for a target fill of WIZARD_FILL_S. Ratio 1:2:2 (non-ferrous) or
    1:4:4 (ferrous). Riser diameter from modulus ≥ 1.25 × casting V/A.
    """
    vol = max(float(vol_cm3), 1.0)
    surf = max(float(surf_cm2), 1.0)
    h_m = max(float(sprue_h_mm), 20.0) / 1000.0
    vel = _CD * math.sqrt(2.0 * _G * h_m)
    q_m3_s = (vol * 1e-6) / WIZARD_FILL_S
    a_gate_mm2 = (q_m3_s / max(vel, 0.05)) * 1e6

    ferrous = metal in FERROUS_METALS
    ratio = (1.0, 4.0, 4.0) if ferrous else (1.0, 2.0, 2.0)
    a_sprue = a_gate_mm2 * ratio[0] / max(ratio[2], 1e-9)
    sprue_bot_r = math.sqrt(max(a_sprue, 1.0) / math.pi)
    sprue_bot_r = float(min(16.0, max(3.0, sprue_bot_r)))
    runner_h = 8.0
    sized = apply_gating_ratio(sprue_bot_r, ratio, runner_height_mm=runner_h)

    va = vol / surf  # cm
    # Open cylinder H = 1.5 D → modulus ≈ D/6 (cm) → D_mm = 10 × 6 × safety × V/A
    riser_d_mm = 10.0 * 6.0 * RISER_SAFETY * va
    riser_d_mm = float(min(80.0, max(16.0, riser_d_mm)))
    riser_h_mm = float(min(120.0, max(30.0, 1.5 * riser_d_mm)))
    riser_r = riser_d_mm / 2.0
    sprue_top_r = float(min(24.0, max(sprue_bot_r + 2.0, sprue_bot_r * 1.8)))

    return {
        "sprue_bot_r_mm": round(sprue_bot_r, 1),
        "sprue_top_r_mm": round(sprue_top_r, 1),
        "sprue_h_mm": round(float(sprue_h_mm), 1),
        "runner_width_mm": round(min(50.0, max(4.0, sized["runner_width_mm"])), 1),
        "runner_height_mm": round(runner_h, 1),
        "gate_area_mm2": round(min(400.0, max(10.0, sized["gate_area_mm2"])), 1),
        "riser_r_mm": round(riser_r, 1),
        "riser_h_mm": round(riser_h_mm, 1),
        "ratio": ratio,
        "ratio_label": "1 : 4 : 4 (ferrous)" if ferrous else "1 : 2 : 2 (non-ferrous)",
        "ferrous": ferrous,
        "target_fill_s": WIZARD_FILL_S,
        "casting_va_cm": round(va, 3),
        "riser_mod_cm": round(open_riser_modulus_cm(riser_r, riser_h_mm), 3),
        "neck_r_mm": round(max(4.0, min(20.0, riser_r * 0.5)), 1),
        "neck_h_mm": 12.0,
        "basin_r_mm": round(min(40.0, max(12.0, sprue_top_r * 2.2)), 1),
        "basin_h_mm": 22.0,
        "filter_area_mm2": round(min(900.0, max(100.0, sized["gate_area_mm2"] * 4.0)), 1),
    }


def melt_ticket(
    pour_mass_g: float,
    metal: str,
    ingot_lb: float = DEFAULT_INGOT_LB,
    furnace_lb: float = DEFAULT_FURNACE_LB,
    usd_per_lb: float | None = None,
) -> dict[str, Any]:
    """Pour weight, ingot count, furnace fit, optional alloy $."""
    mass_g = max(float(pour_mass_g), 0.0)
    mass_lb = mass_g / LB_G
    ingot = max(float(ingot_lb), 0.1)
    furnace = max(float(furnace_lb), 0.1)
    n_ingots = int(math.ceil(mass_lb / ingot - 1e-9)) if mass_lb > 0 else 0
    fits = mass_lb <= furnace + 1e-6
    if usd_per_lb is None:
        usd_per_lb = float(ALLOY_USD_PER_LB.get(metal, 0.0))
    cost = mass_lb * float(usd_per_lb)
    return {
        "pour_mass_g": round(mass_g, 1),
        "pour_mass_lb": round(mass_lb, 3),
        "ingot_lb": ingot,
        "n_ingots": n_ingots,
        "furnace_lb": furnace,
        "furnace_fits": fits,
        "usd_per_lb": round(float(usd_per_lb), 2),
        "alloy_usd": round(cost, 2),
        "metal": metal,
        "density_g_cm3": float(METAL_DEFAULTS.get(metal, {}).get("density", 2.7)),
    }


def pattern_ticket(
    metal: str,
    shrink_slider: int = 100,
    draft_ok: bool | None = None,
    undercut: bool | None = None,
) -> dict[str, Any]:
    """Shrink, print-scale, and as-cast notes for a 3D-printed pattern."""
    shrink_pct = float(METAL_DEFAULTS.get(metal, {}).get("shrinkage_pct", 0.0))
    scale = shrink_scale_from_slider(int(shrink_slider))
    print_pct = (scale - 1.0) * 100.0
    return {
        "metal": metal,
        "catalog_shrink_pct": round(shrink_pct, 2),
        "slider": int(shrink_slider),
        "print_scale": round(scale, 4),
        "print_pct": round(print_pct, 2),
        "draft_ok": draft_ok,
        "undercut": undercut,
        "hint": (
            f"Print the pattern STL at ×{scale:.3f} "
            f"({print_pct:+.1f}% vs as-cast) for lost-PLA / 3D-print patterns."
        ),
    }


def sand_mix_ticket(
    *,
    mold_type: str,
    part_cm3: float,
    gating_cm3: float,
    flask_w_in: float = 8.0,
    flask_d_in: float = 10.0,
    flask_h_in: float = 6.0,
    printed_mm: float = 15.0,
    bbox_mm: tuple[float, float, float] | None = None,
    surf_cm2: float = 0.0,
) -> dict:
    """Pounds of sand (and clay / water / binder) for this flask or print box."""
    cavity = max(float(part_cm3) + float(gating_cm3), 0.0)
    if is_shell_mold(mold_type):
        return {
            "kind": "shell",
            "sand_lb": 0.0,
            "hint": "Ceramic shell — no sand heap. Weigh slurry and stucco by coat, not by flask.",
        }
    if is_printed_sand(mold_type):
        if bbox_mm:
            sx, sy, sz = bbox_mm
        else:
            sx = sy = sz = max(cavity ** (1.0 / 3.0) * 10.0, 40.0)
        t = float(printed_mm)
        env_cm3 = ((sx + 2 * t) * (sy + 2 * t) * (sz + 2 * t)) / 1000.0
        print_cm3 = max(env_cm3 - cavity, 0.0)
        sand_g = print_cm3 * SAND_BULK_G_CM3
        binder_g = sand_g * PRINTED_BINDER_PCT / 100.0
        n_vents = max(1, int(math.ceil(max(float(surf_cm2), 50.0) / 80.0)))
        return {
            "kind": "printed",
            "print_cm3": round(print_cm3, 1),
            "sand_lb": round(sand_g / LB_G, 2),
            "binder_g": round(binder_g, 1),
            "binder_pct": PRINTED_BINDER_PCT,
            "wall_mm": t,
            "n_vents": n_vents,
            "hint": (
                f"Print box ~{print_cm3:.0f} cm³ of furan sand "
                f"({sand_g / LB_G:.1f} lb) + {binder_g:.0f} g binder. "
                f"Add ~{n_vents} vents — no draft, no flask."
            ),
        }
    flask_cm3 = float(flask_w_in) * float(flask_d_in) * float(flask_h_in) * IN3_TO_CM3
    sand_cm3 = max(flask_cm3 - cavity, 0.0)
    sand_g = sand_cm3 * SAND_BULK_G_CM3
    sand_lb = sand_g / LB_G
    resin = "resin" in str(mold_type).lower() or "no-bake" in str(mold_type).lower()
    if resin:
        binder_g = sand_g * RESIN_BINDER_PCT / 100.0
        return {
            "kind": "resin",
            "flask_cm3": round(flask_cm3, 1),
            "sand_cm3": round(sand_cm3, 1),
            "sand_lb": round(sand_lb, 2),
            "binder_g": round(binder_g, 1),
            "binder_pct": RESIN_BINDER_PCT,
            "hint": (
                f"{sand_lb:.1f} lb sand in a {flask_w_in:.0f}×{flask_d_in:.0f}×{flask_h_in:.0f} in flask "
                f"+ {binder_g:.0f} g resin ({RESIN_BINDER_PCT} %)."
            ),
        }
    clay_lb = sand_lb * GREEN_SAND_CLAY_PCT / 100.0
    water_lb = sand_lb * GREEN_SAND_WATER_PCT / 100.0
    return {
        "kind": "green",
        "flask_cm3": round(flask_cm3, 1),
        "sand_cm3": round(sand_cm3, 1),
        "sand_lb": round(sand_lb, 2),
        "clay_lb": round(clay_lb, 2),
        "water_lb": round(water_lb, 2),
        "clay_pct": GREEN_SAND_CLAY_PCT,
        "water_pct": GREEN_SAND_WATER_PCT,
        "hint": (
            f"{sand_lb:.1f} lb sand · {clay_lb:.2f} lb clay ({GREEN_SAND_CLAY_PCT:.0f} %) · "
            f"{water_lb:.2f} lb water ({GREEN_SAND_WATER_PCT:.0f} %)."
        ),
    }


def write_pattern_stl(vectors: np.ndarray, path: str | Path, scale: float) -> None:
    """Write a shrink-compensated pattern mesh (numpy-stl).

    ``vectors`` must be as-cast / scale-1 world triangles. ``scale`` is
    applied here once (e.g. 1.06 for 6 % shrink). Passing an already
    pattern-scaled mesh will oversize the file.
    """
    from stl import mesh as stl_mesh

    v = np.asarray(vectors, dtype=np.float32) * float(scale)
    if v.ndim != 3 or v.shape[1:] != (3, 3):
        raise ValueError("vectors must be (n, 3, 3) triangles")
    m = stl_mesh.Mesh(np.zeros(len(v), dtype=stl_mesh.Mesh.dtype))
    m.vectors = v
    m.save(str(path))


def compare_setups(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Delta two result dicts (same part, different process / gates)."""
    keys = (
        "fill_time_s",
        "t_solidify_min",
        "yield_pct",
        "vsr",
        "pour_mass_g",
        "fill_velocity_mm_s",
        "porosity_frac",
        "n_porosity",
        "n_warnings",
    )
    delta: dict[str, Any] = {
        "a_label": a.get("setup_label", "A"),
        "b_label": b.get("setup_label", "B"),
    }
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta[k] = {"a": va, "b": vb, "d": vb - va}
    return delta
