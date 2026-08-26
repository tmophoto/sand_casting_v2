"""Foundry helpers: mould type, gating metal, yield, draft, flask fit, verdicts.

Pure Python / NumPy — imported by the worker, viewport, and tests.
"""
from __future__ import annotations

import math
import numpy as np

from constants import FLASK_SIZES, METAL_DEFAULTS, MOLD_TYPES, DRAFT_MIN_DEG

# Open riser as drawn in the viewport (mm)
_RISER_R_MM = 20.0
_RISER_H_MM = 60.0
_GATE_LENGTH_MM = 6.0


def mold_factor(name: str) -> float:
    return float(MOLD_TYPES.get(name, 1.0))


def _circle_area_mm2(radius_mm: float) -> float:
    return math.pi * float(radius_mm) ** 2


def truncated_cone_cm3(r_top_mm: float, r_bot_mm: float, height_mm: float) -> float:
    R, r, h = float(r_top_mm), float(r_bot_mm), float(height_mm)
    return math.pi * h / 3.0 * (R * R + R * r + r * r) / 1000.0


def cylinder_cm3(radius_mm: float, height_mm: float) -> float:
    return math.pi * float(radius_mm) ** 2 * float(height_mm) / 1000.0


def gating_volumes_cm3(gating: dict) -> dict[str, float]:
    """Metal sitting in sprue / runner / gate / riser (cm³), matching viewport solids."""
    vols = {"sprue": 0.0, "runner": 0.0, "gate": 0.0, "riser": 0.0}
    if gating.get("has_sprue") and gating.get("sprue_bot_r"):
        top = gating.get("sprue_top_r") or gating["sprue_bot_r"]
        h = float(gating.get("sprue_height_mm") or 100.0)
        vols["sprue"] = truncated_cone_cm3(top, gating["sprue_bot_r"], h)
    if gating.get("has_runner"):
        w = float(gating.get("runner_width_mm") or 0.0)
        hh = float(gating.get("runner_height_mm") or 0.0)
        length = float(gating.get("runner_length_mm") or 160.0)
        if w > 0 and hh > 0:
            vols["runner"] = w * hh * length / 1000.0
        elif gating.get("runner_dia"):
            vols["runner"] = cylinder_cm3(gating["runner_dia"] / 2.0, length)
    if gating.get("has_gate") and gating.get("gate_area_mm2"):
        vols["gate"] = float(gating["gate_area_mm2"]) * _GATE_LENGTH_MM / 1000.0
    if gating.get("has_riser"):
        r = float(gating.get("riser_r_mm") or _RISER_R_MM)
        h = float(gating.get("riser_h_mm") or _RISER_H_MM)
        vols["riser"] = cylinder_cm3(r, h)
    vols["total"] = vols["sprue"] + vols["runner"] + vols["gate"] + vols["riser"]
    return vols


def casting_yield_pct(part_cm3: float, gating_cm3: float) -> float:
    total = float(part_cm3) + float(gating_cm3)
    if total <= 0:
        return 0.0
    return 100.0 * float(part_cm3) / total


def apply_gating_ratio(
    sprue_bot_r_mm: float,
    ratio: tuple[float, float, float] = (1.0, 2.0, 2.0),
    runner_height_mm: float = 8.0,
) -> dict:
    """Size runner width and gate area from sprue-exit area using a classic ratio."""
    rs, rr, rg = ratio
    a_sprue = _circle_area_mm2(sprue_bot_r_mm)
    a_runner = a_sprue * (rr / max(rs, 1e-9))
    a_gate = a_sprue * (rg / max(rs, 1e-9))
    height = max(float(runner_height_mm), 1.0)
    width = max(4.0, a_runner / height)
    return {
        "runner_width_mm": width,
        "runner_height_mm": height,
        "gate_area_mm2": a_gate,
        "sprue_area_mm2": a_sprue,
        "ratio": ratio,
    }


def snap_xy_to_silhouette(
    x: float, y: float,
    xmin: float, xmax: float, ymin: float, ymax: float,
    margin: float = 10.0,
) -> tuple[float, float]:
    """Place a point just outside the nearest XY AABB edge (part silhouette)."""
    candidates = [
        (abs(x - xmin), (xmin - margin, y)),
        (abs(x - xmax), (xmax + margin, y)),
        (abs(y - ymin), (x, ymin - margin)),
        (abs(y - ymax), (x, ymax + margin)),
    ]
    return min(candidates, key=lambda item: item[0])[1]


def flask_fit(
    xmin: float, xmax: float, ymin: float, ymax: float,
    flask_w_in: float, flask_d_in: float,
    margin_in: float = 0.5,
    presets: dict | None = None,
) -> dict:
    """Whether the current flask clears the part, plus the smallest preset that would."""
    need_w = (xmax - xmin) / 25.4 + 2.0 * margin_in
    need_d = (ymax - ymin) / 25.4 + 2.0 * margin_in
    fits = flask_w_in + 1e-6 >= need_w and flask_d_in + 1e-6 >= need_d
    table = presets if presets is not None else FLASK_SIZES
    best_name, best = None, None
    for name, size in table.items():
        w, d = float(size[0]), float(size[1])
        if w + 1e-6 >= need_w and d + 1e-6 >= need_d:
            area = w * d
            if best is None or area < best[0]:
                best = (area, w, d)
                best_name = name
    return {
        "fits": fits,
        "need_w_in": need_w,
        "need_d_in": need_d,
        "flask_w_in": flask_w_in,
        "flask_d_in": flask_d_in,
        "suggested": best_name,
        "suggested_size": None if best is None else (best[1], best[2]),
    }


def draft_analysis(
    vectors: np.ndarray,
    pull: tuple[float, float, float] = (0.0, 0.0, 1.0),
    min_deg: float = DRAFT_MIN_DEG,
) -> dict:
    """Per-face draft vs the cope/drag pull direction (default +Z).

    Draft is 90° minus the angle between the face normal and the pull axis.
    Vertical walls have ~0° of draft and lock in the sand below ``min_deg``.
    """
    verts = np.asarray(vectors, dtype=np.float64)
    n = len(verts)
    empty = {
        "n_faces": n,
        "lock_count": 0,
        "ok_count": 0,
        "lock_frac": 0.0,
        "min_draft_deg": 0.0,
        "draft_deg": np.zeros(0, dtype=np.float64),
        "lock_mask": np.zeros(0, dtype=bool),
    }
    if n == 0:
        return empty
    v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
    nrm = np.cross(v1 - v0, v2 - v0)
    lens = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.maximum(lens, 1e-12)
    p = np.asarray(pull, dtype=np.float64)
    p = p / max(float(np.linalg.norm(p)), 1e-12)
    cos_n = np.clip(np.abs(nrm @ p), 0.0, 1.0)
    # 0 → vertical wall, 1 → facing the pull (horizontal)
    draft = np.degrees(np.arcsin(np.clip(cos_n, 0.0, 1.0)))
    lock = draft < float(min_deg)
    return {
        "n_faces": n,
        "lock_count": int(np.sum(lock)),
        "ok_count": int(n - np.sum(lock)),
        "lock_frac": float(np.mean(lock)),
        "min_draft_deg": float(np.min(draft)),
        "draft_deg": draft,
        "lock_mask": lock,
    }


def undercut_hints(
    vectors: np.ndarray,
    z_part: float,
    pull: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> dict:
    """Faces that face against the pull on their side of the parting line.

    Cope (above parting) pulled +Z: a downward-facing face is an undercut.
    Drag (below parting) pulled −Z: an upward-facing face is an undercut.
    """
    verts = np.asarray(vectors, dtype=np.float64)
    if len(verts) == 0:
        return {"count": 0, "frac": 0.0, "mask": np.zeros(0, dtype=bool)}
    v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
    nrm = np.cross(v1 - v0, v2 - v0)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    centroids = (v0 + v1 + v2) / 3.0
    p = np.asarray(pull, dtype=np.float64)
    p = p / max(float(np.linalg.norm(p)), 1e-12)
    nz = nrm @ p
    cope = centroids[:, 2] >= z_part
    # Undercut if the face points against the local pull
    mask = (cope & (nz < -0.15)) | ((~cope) & (nz > 0.15))
    return {
        "count": int(np.sum(mask)),
        "frac": float(np.mean(mask)),
        "mask": mask,
    }


def open_riser_modulus_cm(radius_mm: float = _RISER_R_MM, height_mm: float = _RISER_H_MM) -> float:
    """V/A for an open-top cylinder (lateral + bottom only), in cm."""
    r = float(radius_mm) / 10.0
    h = float(height_mm) / 10.0
    vol = math.pi * r * r * h
    area = 2.0 * math.pi * r * h + math.pi * r * r
    return vol / max(area, 1e-9)


def riser_ok(part_vsr_cm: float, has_riser: bool, safety: float = 1.2) -> dict:
    """Compare an open riser's modulus to the part V/A (hot-spot proxy)."""
    m_riser = open_riser_modulus_cm()
    need = float(part_vsr_cm) * safety
    adequate = bool(has_riser) and m_riser + 1e-9 >= need
    return {
        "has_riser": bool(has_riser),
        "m_riser_cm": m_riser,
        "m_need_cm": need,
        "adequate": adequate,
        "needed": float(part_vsr_cm) > 1.5,
    }


def choke_location(restrictive: str, sprue_xy, riser_xy, z_part: float, zmax: float) -> tuple[float, float, float] | None:
    sx, sy = sprue_xy
    if restrictive == "sprue_exit":
        return (float(sx), float(sy), float(z_part))
    if restrictive == "runner":
        return (float(sx), float(sy), float(z_part))
    if restrictive == "gate":
        return (float(sx), float(sy) - 4.0, float(z_part))
    return None


def recommended_pour_band(metal: dict) -> tuple[int, int]:
    melt = int(metal["melt_temp_f"])
    lo = melt + int(metal.get("min_superheat_f", 50))
    hi = melt + int(metal.get("min_superheat_f", 50)) * 3
    return lo, hi


def verdict_from_result(r: dict) -> str:
    """``ok``, ``risky``, or ``fail``."""
    defects = r.get("defects") or []
    warnings = r.get("warnings") or []
    if defects or not r.get("fill_possible", True):
        return "fail"
    if warnings:
        return "risky"
    return "ok"


def suggested_fixes(r: dict, gating: dict | None = None) -> list[dict]:
    """Actionable one-liners for each defect/warning, with optional fill-time estimate."""
    from simulation.worker import SimWorker

    gating = gating or {}
    fixes: list[dict] = []
    metal_name = r.get("metal", "A356 Aluminum")
    metal = METAL_DEFAULTS.get(metal_name, METAL_DEFAULTS["A356 Aluminum"])
    pour = r.get("pour_f", metal["pour_temp_f"])
    vol = r.get("vol_cm3", 200.0)

    def _fill_with(g: dict) -> float:
        t, _, _ = SimWorker._compute_fill_time_gating_hydraulics(vol, g)
        return t

    for d in r.get("defects") or []:
        low = d.lower()
        if "misrun" in low:
            target = metal["melt_temp_f"] + metal.get("min_superheat_f", 50) * 2
            fixes.append({
                "kind": "misrun_risk",
                "text": d,
                "fix": f"Raise pour temp to ~{target:.0f} °F (2× minimum superheat).",
            })
        elif "cold shut" in low:
            target = metal["melt_temp_f"] + 160
            fixes.append({
                "kind": "cold_shut_risk",
                "text": d,
                "fix": f"Pour at ≥ {target:.0f} °F, or thicken walls above 6 mm.",
            })
        else:
            fixes.append({"kind": "other", "text": d, "fix": ""})

    for w in r.get("warnings") or []:
        low = w.lower()
        if "porosity" in low or "riser" in low:
            rs = riser_ok(r.get("vsr", 1.0), False)
            fixes.append({
                "kind": "shrinkage_risk",
                "text": w,
                "fix": (
                    f"Add Riser (Open). Hot-spot modulus {r.get('vsr', 0):.2f} cm needs "
                    f"a feeder ≥ {rs['m_need_cm']:.2f} cm."
                ),
            })
        elif "fill time" in low:
            g = dict(gating)
            bot = float(g.get("sprue_bot_r") or 4.0)
            g["has_sprue"] = True
            g["sprue_bot_r"] = bot + 2.0
            t_now = r.get("fill_time_s", 0)
            t_new = _fill_with(g)
            fixes.append({
                "kind": "choke",
                "text": w,
                "fix": (
                    f"Sprue exit {bot:.0f} mm is the choke → try {bot + 2:.0f} mm "
                    f"(est. fill {t_now:.1f} s → {t_new:.1f} s)."
                ),
            })
        elif "superheat" in low:
            target = metal.get("min_superheat_f", 50) * 2
            fixes.append({
                "kind": "superheat",
                "text": w,
                "fix": f"Increase superheat to ≥ {target:.0f} °F.",
            })
        elif "burn-on" in low:
            fixes.append({
                "kind": "burnon",
                "text": w,
                "fix": "Drop mold temperature to ≤ 120 °F, or use a mold wash.",
            })
        elif "riser may freeze" in low or "feeder" in low:
            fixes.append({
                "kind": "shrinkage_risk",
                "text": w,
                "fix": "Use a larger open riser (or a side riser on the hot spot).",
            })
        elif "flask" in low:
            fixes.append({
                "kind": "flask",
                "text": w,
                "fix": w,
            })
        else:
            fixes.append({"kind": "other", "text": w, "fix": ""})
    return fixes
