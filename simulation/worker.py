import math
from PyQt6.QtCore import QObject, pyqtSignal
from constants import METAL_DEFAULTS


class SimWorker(QObject):

    """Runs the casting simulation in a worker thread."""



    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)



    def __init__(self, params: dict) -> None:
        super().__init__()
        self.params = params



    @staticmethod

    def _compute_fill_time_gating_hydraulics(
        vol_cm3: float, gating: dict, pour_f: int, metal: dict
    ) -> tuple[float, str]:

        """

        Compute fill time using proper gating hydraulics.


        Uses Bernoullis equation with the restrictive element determining flow rate.
        Returns (fill_time_seconds, description_of_restrictive_element).

        """

        sprue_height_mm = 100.0


        Cd = 0.75
        g = 9806.65



        def area_mm2(radius_mm: float) -> float:
            return math.pi * radius_mm ** 2


        sprue_top_area = area_mm2(gating["sprue_top_r"]) if gating.get("sprue_top_r") else None
        sprue_bot_area = area_mm2(gating["sprue_bot_r"]) if gating.get("sprue_bot_r") else None
        runner_area = (math.pi * (gating["runner_dia"] / 2) ** 2) if gating.get("runner_dia") else None
        gate_area = gating.get("gate_area_mm2", 40.0)


        restrictive_elem = "sprue"
        effective_area_mm2 = None


        if gating.get("has_sprue") and gating.get("has_gate"):
            if sprue_bot_area and gate_area:
                if sprue_bot_area < gate_area * 0.85:
                    restrictive_elem = "sprue_exit"
                    effective_area_mm2 = sprue_bot_area
                else:
                    restrictive_elem = "gate"
                    effective_area_mm2 = gate_area


        elif gating.get("has_sprue") and gating.get("has_runner"):
            if sprue_bot_area and runner_area:
                if sprue_bot_area < runner_area * 0.85:
                    restrictive_elem = "sprue_exit"
                    effective_area_mm2 = sprue_bot_area
                else:
                    restrictive_elem = "runner"
                    effective_area_mm2 = runner_area


        elif gating.get("has_sprue"):
            if sprue_bot_area:
                effective_area_mm2 = sprue_bot_area


        elif gating.get("gate_area_mm2"):
            effective_area_mm2 = gate_area
            restrictive_elem = "gate"


        if effective_area_mm2 and effective_area_mm2 > 0:
            velocity_ms = Cd * math.sqrt(g * sprue_height_mm / 1000.0)
            area_cm2 = effective_area_mm2 / 100.0
            velocity_cm_s = velocity_ms * 100.0
            flow_rate_cm3s = area_cm2 * velocity_cm_s
            # Physical exit velocity via Torricelli (2·g·h, g in mm/s², h in mm → mm/s)
            fill_velocity_mm_s = Cd * math.sqrt(2.0 * g * sprue_height_mm)


            if flow_rate_cm3s > 0:
                fill_time_s = vol_cm3 / flow_rate_cm3s
                return max(1.5, fill_time_s), restrictive_elem, fill_velocity_mm_s


        return max(3.0, vol_cm3 / 80.0), "fallback", 0.0



    def run(self) -> None:
        p = self.params
        metal_name = p.get("metal", "A356 Aluminum")
        metal      = METAL_DEFAULTS[metal_name]


        vol_cm3  = p.get("vol_cm3",  100.0)
        surf_cm2 = p.get("surf_cm2", 120.0)
        if vol_cm3  <= 0: vol_cm3  = 100.0
        if surf_cm2 <= 0: surf_cm2 = 120.0


        pour_f  = p.get("pour_temp_f", metal["pour_temp_f"])
        mold_f  = p.get("mold_temp_f", 77)
        has_riser = p.get("has_riser", False)
        thin_wall = p.get("thin_wall",  False)
        gating_params = p.get("gating_params", {})


        self.progress.emit(10, "Computing geometry ratios")
        vsr = vol_cm3 / surf_cm2


        self.progress.emit(30, "Applying Chvorinov Rule")
        B = 3.0 * metal["mold_constant"]
        t_solidify_min = B * (vsr ** 2)


        self.progress.emit(50, "Checking defect risks")
        superheat = pour_f - metal["melt_temp_f"]
        min_superheat = metal.get("min_superheat_f", 50)
        defects  = []
        warnings = []


        if superheat < min_superheat:
            defects.append(f"Misrun risk — superheat {superheat:.0f} F below minimum {min_superheat} F")
        if thin_wall and pour_f < metal["melt_temp_f"] + 150:
            defects.append("Cold shut risk — thin wall with low superheat")
        if mold_f > 120:
            warnings.append("Burn-on risk — mold temp above 120 F")
        if superheat < min_superheat * 2:
            warnings.append(f"Low superheat — {superheat:.0f} F (recommended ≥ {min_superheat * 2} F)")


        self.progress.emit(70, "Computing gating hydraulics")
        fill_time_s, restrictive, fill_velocity_mm_s = self._compute_fill_time_gating_hydraulics(
            vol_cm3, gating_params, pour_f, metal
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
            warnings.append("Porosity risk — thick section with no riser; add Riser (Open) to feed shrinkage")


        # Use shrink_scale from params if provided, otherwise compute from metal defaults
        shrink_scale = p.get("shrink_scale", 1.0 + (metal["shrinkage_pct"] / 100.0))


        result = {
            "t_solidify_min":    t_solidify_min,
            "fill_time_s":       fill_time_s,
            "fill_velocity_mm_s": fill_velocity_mm_s,
            "fill_possible":     fill_possible,
            "cooling_rate":      cooling_rate,
            "restrictive_elem":  restrictive,
            "vsr":               vsr,
            "vol_cm3":           vol_cm3,
            "surf_cm2":          surf_cm2,
            "superheat":         superheat,
            "defects":           defects,
            "warnings":          warnings,
            "metal":             metal_name,
            "pour_f":            pour_f,
            "mold_f":            mold_f,
            "shrink_scale":      shrink_scale,
        }


        self.progress.emit(100, "Done.")
        self.finished.emit(result)
