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
    LB_G,
    METAL_DEFAULTS,
    SHOP_RECIPES,
    shrink_scale_from_slider,
)
from simulation.foundry import apply_gating_ratio, open_riser_modulus_cm


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


def write_pattern_stl(vectors: np.ndarray, path: str | Path, scale: float) -> None:
    """Write a shrink-compensated pattern mesh (numpy-stl)."""
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
