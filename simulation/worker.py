import math
from PyQt6.QtCore import QObject, pyqtSignal
from constants import (
    METAL_DEFAULTS, DEFAULT_SHELL_MM,
    EROSION_VEL_SAND_MM_S, EROSION_VEL_SHELL_MM_S,
)
from simulation.foundry import (
    gating_volumes_cm3, casting_yield_pct, riser_ok,
    verdict_from_result, suggested_fixes, is_shell_mold, effective_mold_factor,
    recommended_shell_preheat_f,
)
from simulation.shop import melt_ticket, pattern_ticket


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
        mold_name = p.get("mold_type", "Green sand")
        shell_mm = float(p.get("shell_mm", DEFAULT_SHELL_MM))
        shell = is_shell_mold(mold_name)
        B = chvorinov_B(metal, pour_f) * effective_mold_factor(
            mold_name, shell_mm=shell_mm, mold_f=mold_f, pour_f=pour_f,
        )
        t_solidify_min = B * (vsr ** 2)

        self.progress.emit(50, "Checking defect risks")
        superheat = pour_f - metal["melt_temp_f"]
        min_superheat = metal.get("min_superheat_f", 50)
        defects: list[str] = []
        warnings: list[str] = []

        rec_preheat = recommended_shell_preheat_f(metal_name) if shell else 0
        hot_shell = shell and mold_f >= rec_preheat - 250
        # A fired hot shell fills thin sections more easily than cold sand.
        effective_min_sh = min_superheat
        if hot_shell:
            effective_min_sh = max(20.0, min_superheat * 0.55)

        if superheat < effective_min_sh:
            defects.append(
                f"Misrun risk — superheat {superheat:.0f} F below minimum {effective_min_sh:.0f} F"
            )
        cold_shut_need = metal["melt_temp_f"] + 150
        if thin_wall and pour_f < cold_shut_need and not hot_shell:
            defects.append("Cold shut risk — thin wall with low superheat")
        if not shell and mold_f > 120:
            warnings.append("Burn-on risk — mold temp above 120 F")
        if superheat < effective_min_sh * 2:
            warnings.append(
                f"Low superheat — {superheat:.0f} F (recommended ≥ {effective_min_sh * 2:.0f} F)"
            )

        if shell:
            if shell_mm < 5.0:
                warnings.append(
                    f"Thin shell — {shell_mm:.0f} mm fired thickness risks metal breakthrough"
                )
            if shell_mm < 6.0 and vol_cm3 >= 400.0:
                defects.append(
                    f"Shell breakthrough risk — {shell_mm:.0f} mm shell is light for a "
                    f"{vol_cm3:.0f} cm³ pour"
                )
            if mold_f > pour_f + 25:
                warnings.append(
                    f"Shell hotter than pour ({mold_f:.0f} °F > {pour_f:.0f} °F)"
                )
            elif mold_f < rec_preheat - 350:
                warnings.append(
                    f"Cold shell — preheat closer to {rec_preheat} °F for fill"
                )

        self.progress.emit(70, "Computing gating hydraulics")
        fill_time_s, restrictive, fill_velocity_mm_s = (
            self._compute_fill_time_gating_hydraulics(vol_cm3, gating_params)
        )

        gating_vols = gating_volumes_cm3({
            **gating_params,
            "has_riser": has_riser or gating_params.get("has_riser"),
        })
        gating_cm3 = gating_vols["total"]
        yield_pct = casting_yield_pct(vol_cm3, gating_cm3)
        pour_mass_g = (vol_cm3 + gating_cm3) * float(metal["density"])
        part_mass_g = vol_cm3 * float(metal["density"])

        riser = riser_ok(
            vsr, has_riser,
            radius_mm=gating_params.get("riser_r_mm"),
            height_mm=gating_params.get("riser_h_mm"),
        )
        if riser["needed"] and not has_riser:
            if not any("riser" in w.lower() or "porosity" in w.lower() for w in warnings):
                warnings.append(
                    "Porosity risk — thick section with no riser; add Riser (Open) to feed shrinkage"
                )
        elif has_riser and not riser["adequate"]:
            warnings.append(
                f"Riser may freeze before the hot spot — feeder modulus "
                f"{riser['m_riser_cm']:.2f} cm < {riser['m_need_cm']:.2f} cm needed"
            )

        erosion_lim = EROSION_VEL_SHELL_MM_S if shell else EROSION_VEL_SAND_MM_S
        if fill_velocity_mm_s > erosion_lim:
            warnings.append(
                f"Mold erosion risk — gate velocity {fill_velocity_mm_s:.0f} mm/s "
                f"exceeds {erosion_lim:.0f} mm/s for this mould"
            )

        flask_info = p.get("flask_fit") or {}
        if (not shell) and flask_info.get("fits") is False:
            sug = flask_info.get("suggested") or "a larger flask"
            warnings.append(
                f"Flask is too small for the part + {flask_info.get('need_w_in', 0):.1f}×"
                f"{flask_info.get('need_d_in', 0):.1f} in envelope — try {sug}"
            )

        self.progress.emit(82, "Voxel fill / freeze")
        voxel_faces: dict = {}
        porosity_frac = 0.0
        n_porosity = 0
        n_unfilled = 0
        niyama_min = None
        mesh = p.get("mesh_vectors")
        if mesh is not None:
            try:
                from simulation.voxels import analyze as voxel_analyze
                vx = voxel_analyze(
                    mesh, B,
                    gate_xyz=p.get("gate_xyz"),
                    riser_xyz=p.get("riser_xyz"),
                    sprue_xyz=p.get("sprue_xyz"),
                    chills_xyz=p.get("chills_xyz") or None,
                    sleeve=bool(p.get("sleeve")),
                )
                porosity_frac = float(vx.get("porosity_frac") or 0.0)
                n_porosity = int(vx.get("n_porosity") or 0)
                n_unfilled = int(vx.get("n_unfilled") or 0)
                ny = vx.get("face_niyama")
                if ny is not None and len(ny):
                    niyama_min = float(ny.min())
                voxel_faces = {
                    "fill": vx.get("face_fill"),
                    "freeze": vx.get("face_freeze"),
                    "porosity": vx.get("face_porosity"),
                    "niyama": vx.get("face_niyama"),
                    "dist": vx.get("face_dist"),
                }
                if n_unfilled > 0:
                    warnings.append(
                        f"Misrun (gravity flood) — {n_unfilled} cavity cells never filled from the gate"
                    )
                if porosity_frac >= 0.05:
                    defects.append(
                        f"Isolated-liquid porosity — {100 * porosity_frac:.0f}% of the volume "
                        "freezes without a feeder path"
                    )
                elif porosity_frac >= 0.02:
                    warnings.append(
                        f"Hot-spot porosity risk — {100 * porosity_frac:.0f}% last-to-freeze is unfed"
                    )
            except Exception:
                voxel_faces = {}

        self.progress.emit(90, "Assembling results")

        cooling_rate = superheat / t_solidify_min if t_solidify_min > 0 else 0.0
        fill_possible = fill_time_s < (t_solidify_min * 60.0)
        if not fill_possible:
            warnings.append(
                f"Fill time ({fill_time_s:.0f}s) exceeds solidification time "
                f"({t_solidify_min * 60:.0f}s) — increase gating area or pour temp"
            )

        shrink_scale = p.get("shrink_scale", 1.0 + (metal["shrinkage_pct"] / 100.0))
        z_max = p.get("z_max", 100.0)

        result = {
            "t_solidify_min": t_solidify_min,
            "chvorinov_B": B,
            "pour_mass_g": pour_mass_g,
            "part_mass_g": part_mass_g,
            "gating_cm3": gating_cm3,
            "gating_volumes": gating_vols,
            "yield_pct": yield_pct,
            "mold_type": mold_name,
            "shell_mm": shell_mm if shell else None,
            "process": "shell" if shell else "sand",
            "riser": riser,
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
        result["verdict"] = verdict_from_result(result)
        result["fixes"] = suggested_fixes(result, gating_params)
        result["melt_ticket"] = melt_ticket(pour_mass_g, metal_name)
        result["pattern_ticket"] = pattern_ticket(
            metal_name, shrink_slider=int(round(shrink_scale * 100)),
        )
        result["porosity_frac"] = porosity_frac
        result["n_porosity"] = n_porosity
        result["n_unfilled"] = n_unfilled
        result["niyama_min"] = niyama_min
        result["n_warnings"] = len(warnings)
        result["setup_label"] = p.get("setup_label") or (
            f"{'shell' if shell else 'sand'} · {metal_name}"
        )
        result["voxel_faces"] = voxel_faces

        self.progress.emit(100, "Done.")
        self.finished.emit(result)
