import math
from PyQt6.QtCore import QObject, pyqtSignal
from constants import METAL_DEFAULTS


def volumetric_heat_j_cm3(metal: dict, pour_f: float) -> float:
    """Enthalpy to extract per cm³ from pour temperature down through freeze.

    ``density`` is g/cm³, ``specific_heat`` J/kg·K, ``latent_heat`` kJ/kg.
    Superheat is converted °F → K so the stored SI properties stay consistent.
    """
    dT_K = max(0.0, (float(pour_f) - float(metal["melt_temp_f"])) * 5.0 / 9.0)
    rho = float(metal["density"])
    cp = float(metal["specific_heat"])
    latent = float(metal["latent_heat"]) * 1000.0
    return (rho / 1000.0) * (cp * dT_K + latent)


def chvorinov_B(metal: dict, pour_f: float) -> float:
    """Chvorinov prefactor (min / cm²) including mould and metal thermal properties.

    ``B = 3.0 × mold_constant × (H / H_A356) × (k_A356 / k)``.
    A356 at its default pour temperature yields a thermal factor of 1, so
    existing aluminium timings are unchanged.
    """
    ref = METAL_DEFAULTS["A356 Aluminum"]
    heat = volumetric_heat_j_cm3(metal, pour_f)
    heat_ref = volumetric_heat_j_cm3(ref, ref["pour_temp_f"])
    k = max(float(metal["conductivity"]), 1e-9)
    k_ref = max(float(ref["conductivity"]), 1e-9)
    thermal = (heat / max(heat_ref, 1e-12)) * (k_ref / k)
    return 3.0 * float(metal["mold_constant"]) * thermal

# Torricelli / Bernoulli gating constants
_SPRUE_HEIGHT_MM = 100.0
_DISCHARGE_CD = 0.75
_G_MM_S2 = 9806.65  # mm/s²


def _circle_area_mm2(radius_mm: float) -> float:
    return math.pi * radius_mm ** 2


class SimWorker(QObject):
    """Runs the casting simulation in a worker thread."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, params: dict) -> None:
        super().__init__()
        self.params = params

    @staticmethod
    def _compute_fill_time_gating_hydraulics(
        vol_cm3: float, gating: dict, pour_f: int = 0, metal: dict | None = None
    ) -> tuple[float, str, float]:
        """Fill time from Torricelli velocity at the most restrictive section.

        ``v = Cd × √(2 g h)`` with a consistent millimetre-based unit system.
        Returns ``(fill_time_s, restrictive_element, fill_velocity_mm_s)``.
        """
        candidates: list[tuple[str, float]] = []

        if gating.get("has_sprue") and gating.get("sprue_bot_r"):
            candidates.append(("sprue_exit", _circle_area_mm2(gating["sprue_bot_r"])))

        runner_area = None
        if gating.get("runner_width_mm") and gating.get("runner_height_mm"):
            runner_area = gating["runner_width_mm"] * gating["runner_height_mm"]
        elif gating.get("runner_dia"):
            runner_area = _circle_area_mm2(gating["runner_dia"] / 2.0)
        if gating.get("has_runner") and runner_area:
            candidates.append(("runner", runner_area))

        gate_area = gating.get("gate_area_mm2")
        if gating.get("has_gate") and gate_area:
            candidates.append(("gate", gate_area))

        if not candidates:
            return max(3.0, vol_cm3 / 80.0), "fallback", 0.0

        restrictive_elem, effective_area_mm2 = min(candidates, key=lambda item: item[1])
        if effective_area_mm2 <= 0:
            return max(3.0, vol_cm3 / 80.0), "fallback", 0.0

        head_mm = float(gating.get("sprue_height_mm") or _SPRUE_HEIGHT_MM)
        head_mm = max(10.0, head_mm)
        # v = Cd √(2gh)  → mm/s; Q = A × v  → mm³/s; convert to cm³/s for volume
        fill_velocity_mm_s = _DISCHARGE_CD * math.sqrt(2.0 * _G_MM_S2 * head_mm)
        flow_rate_cm3_s = (effective_area_mm2 * fill_velocity_mm_s) / 1000.0
        fill_time_s = vol_cm3 / flow_rate_cm3_s
        return max(1.5, fill_time_s), restrictive_elem, fill_velocity_mm_s

    def run(self) -> None:
        p = self.params
        metal_name = p.get("metal", "A356 Aluminum")
        metal = METAL_DEFAULTS[metal_name]

        vol_cm3 = p.get("vol_cm3", 100.0)
        surf_cm2 = p.get("surf_cm2", 120.0)
        if vol_cm3 <= 0:
            vol_cm3 = 100.0
        if surf_cm2 <= 0:
            surf_cm2 = 120.0

        pour_f = p.get("pour_temp_f", metal["pour_temp_f"])
        mold_f = p.get("mold_temp_f", 77)
        has_riser = p.get("has_riser", False)
        thin_wall = p.get("thin_wall", False)
        gating_params = p.get("gating_params", {})

        self.progress.emit(10, "Computing geometry ratios")
        vsr = vol_cm3 / surf_cm2

        self.progress.emit(30, "Applying Chvorinov Rule")
        B = chvorinov_B(metal, pour_f)
        t_solidify_min = B * (vsr ** 2)

        self.progress.emit(50, "Checking defect risks")
        superheat = pour_f - metal["melt_temp_f"]
        min_superheat = metal.get("min_superheat_f", 50)
        defects: list[str] = []
        warnings: list[str] = []

        if superheat < min_superheat:
            defects.append(
                f"Misrun risk — superheat {superheat:.0f} F below minimum {min_superheat} F"
            )
        if thin_wall and pour_f < metal["melt_temp_f"] + 150:
            defects.append("Cold shut risk — thin wall with low superheat")
        if mold_f > 120:
            warnings.append("Burn-on risk — mold temp above 120 F")
        if superheat < min_superheat * 2:
            warnings.append(
                f"Low superheat — {superheat:.0f} F (recommended ≥ {min_superheat * 2} F)"
            )

        self.progress.emit(70, "Computing gating hydraulics")
        fill_time_s, restrictive, fill_velocity_mm_s = (
            self._compute_fill_time_gating_hydraulics(vol_cm3, gating_params)
        )

        self.progress.emit(90, "Assembling results")

        cooling_rate = superheat / t_solidify_min if t_solidify_min > 0 else 0.0
        fill_possible = fill_time_s < (t_solidify_min * 60.0)
        if not fill_possible:
            warnings.append(
                f"Fill time ({fill_time_s:.0f}s) exceeds solidification time "
                f"({t_solidify_min * 60:.0f}s) — increase gating area or pour temp"
            )

        if vsr > 1.5 and t_solidify_min > 5.0 and not has_riser:
            warnings.append(
                "Porosity risk — thick section with no riser; add Riser (Open) to feed shrinkage"
            )

        shrink_scale = p.get("shrink_scale", 1.0 + (metal["shrinkage_pct"] / 100.0))
        z_max = p.get("z_max", 100.0)
        pour_mass_g = vol_cm3 * float(metal["density"])

        result = {
            "t_solidify_min": t_solidify_min,
            "chvorinov_B": B,
            "pour_mass_g": pour_mass_g,
            "fill_time_s": fill_time_s,
            "fill_velocity_mm_s": fill_velocity_mm_s,
            "fill_possible": fill_possible,
            "cooling_rate": cooling_rate,
            "restrictive_elem": restrictive,
            "vsr": vsr,
            "vol_cm3": vol_cm3,
            "surf_cm2": surf_cm2,
            "superheat": superheat,
            "min_superheat_f": min_superheat,
            "defects": defects,
            "warnings": warnings,
            "metal": metal_name,
            "pour_f": pour_f,
            "mold_f": mold_f,
            "shrink_scale": shrink_scale,
            "z_max": z_max,
        }

        self.progress.emit(100, "Done.")
        self.finished.emit(result)
