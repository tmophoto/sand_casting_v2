METAL_DEFAULTS = {
    "A356 Aluminum": {
        "pour_temp_f": 1300,
        "melt_temp_f": 1075,
        "density": 2.67,        # g/cm³
        "specific_heat": 963,   # J/kg·K
        "latent_heat": 389,     # kJ/kg
        "conductivity": 151,    # W/m·K
        "color": "#C8C8C8",
        "mold_constant": 1.0,
        "shrinkage_pct": 6.0,
        "min_superheat_f": 50,  # below this → misrun risk
    },
    "Everdur Bronze (C52100)": {
        "pour_temp_f": 1950,
        "melt_temp_f": 1780,
        "density": 8.8,
        "specific_heat": 380,
        "latent_heat": 175,
        "conductivity": 50,
        "color": "#CD7F32",
        "mold_constant": 1.4,
        "shrinkage_pct": 2.0,
        "min_superheat_f": 150,
    },
    "Gray Iron (ASTM A48)": {
        "pour_temp_f": 2600,
        "melt_temp_f": 2200,
        "density": 7.15,
        "specific_heat": 460,
        "latent_heat": 230,
        "conductivity": 50,
        "color": "#888888",
        "mold_constant": 1.6,
        "shrinkage_pct": 1.0,
        "min_superheat_f": 100,
    },
    "Ductile Iron (65-45-12)": {
        "pour_temp_f": 2650,
        "melt_temp_f": 2250,
        "density": 7.1,
        "specific_heat": 460,
        "latent_heat": 230,
        "conductivity": 36,
        "color": "#9A9A9A",
        "mold_constant": 1.6,
        "shrinkage_pct": 0.8,
        "min_superheat_f": 100,
    },
    "316 Stainless Steel": {
        "pour_temp_f": 2900,
        "melt_temp_f": 2550,
        "density": 7.99,
        "specific_heat": 500,
        "latent_heat": 270,
        "conductivity": 16,
        "color": "#C0C0C8",
        "mold_constant": 1.8,
        "shrinkage_pct": 2.5,
        "min_superheat_f": 150,
    },
}



FLASK_SIZES = {
    "6 x 6":   (6,  6),
    "6 x 8":   (6,  8),
    "8 x 10":  (8,  10),
    "10 x 12": (10, 12),
    "12 x 14": (12, 14),
    "14 x 20": (14, 20),
}

# Cope + drag stack height in inches (XY flask sizes do not include Z)
DEFAULT_FLASK_HEIGHT_IN = 6.0

# Mould material multiplier on Chvorinov B (green sand = 1).
# Ceramic shell uses this as the *cold* 8 mm baseline; preheat and thickness
# are applied on top in simulation.foundry.effective_mold_factor().
CERAMIC_SHELL = "Ceramic shell"
PRINTED_SAND = "Printed sand"
MOLD_TYPES = {
    "Green sand": 1.00,
    "Dry sand": 1.15,
    "Resin / no-bake": 0.85,
    CERAMIC_SHELL: 0.62,
    PRINTED_SAND: 0.90,  # furan binder-jet; more permeable than packed green
}

# Lost-wax / investment ceramic shell
DEFAULT_SHELL_MM = 8.0
SHELL_MM_MIN = 4
SHELL_MM_MAX = 16
SHELL_COLOR = "#E8D5B7"
# Binder-jet / 3D-printed sand (Voxeljet / ExOne style)
DEFAULT_PRINTED_MM = 15.0
PRINTED_MM_MIN = 8
PRINTED_MM_MAX = 40
PRINTED_SAND_COLOR = "#C4B59A"
# Typical fired-shell preheat by alloy (°F)
SHELL_PREHEAT_DEFAULT_F = {
    "A356 Aluminum": 1100,
    "Everdur Bronze (C52100)": 1600,
    "Gray Iron (ASTM A48)": 1800,
    "Ductile Iron (65-45-12)": 1800,
    "316 Stainless Steel": 1900,
}

# Sprue : runner : gate area ratios
GATING_RATIOS = {
    "1 : 2 : 2 (non-ferrous)": (1.0, 2.0, 2.0),
    "1 : 4 : 4 (ferrous)": (1.0, 4.0, 4.0),
}

DRAFT_MIN_DEG = 1.5

# Viewport colors
COPE_COLOR   = "#4A90D9"
DRAG_COLOR   = "#C0834A"
SPRUE_COLOR  = "#E87040"
RUNNER_COLOR = "#D4A030"
GATE_COLOR   = "#A0C840"
RISER_COLOR  = "#70A0FF"

MODEL_COLORS = [
    "#BEC1D2", "#89DCEB", "#A6E3A1",
    "#FAB387", "#F38BA8", "#CBA6F7",
]

# Per-metal PBR material settings for PyVista renderer
METAL_PBR = {
    "A356 Aluminum": {
        "color": "#C8C8D0",   # cool silver
        "metallic": 0.85,
        "roughness": 0.25,
    },
    "Everdur Bronze (C52100)": {
        "color": "#CD7F32",   # warm copper-bronze
        "metallic": 0.90,
        "roughness": 0.20,
    },
    "Gray Iron (ASTM A48)": {
        "color": "#888888",
        "metallic": 0.50,
        "roughness": 0.70,
    },
    "Ductile Iron (65-45-12)": {
        "color": "#9A9A9A",
        "metallic": 0.55,
        "roughness": 0.65,
    },
    "316 Stainless Steel": {
        "color": "#C0C0C8",
        "metallic": 0.95,
        "roughness": 0.15,
    },
}


def shrink_scale_from_slider(slider_value: int) -> float:
    """Map the 100–110 shrinkage slider onto a linear scale factor (1.00–1.10)."""
    return slider_value / 100.0


FERROUS_METALS = {
    "Gray Iron (ASTM A48)",
    "Ductile Iron (65-45-12)",
    "316 Stainless Steel",
}

CHILL_COLOR = "#89DCEB"
FILTER_COLOR = "#F5E0C3"
BASIN_COLOR = "#E8A0BF"
GATE2_COLOR = "#94E2D5"

# Gate velocity above this (mm/s) is treated as mold-erosion risk
EROSION_VEL_SAND_MM_S = 500.0
EROSION_VEL_SHELL_MM_S = 750.0

# Melt ticket defaults (hobby crucible)
LB_G = 453.592
DEFAULT_INGOT_LB = 1.0
DEFAULT_FURNACE_LB = 12.0
# Packed moulding sand (g/cm³) and shop mix fractions
SAND_BULK_G_CM3 = 1.55
GREEN_SAND_CLAY_PCT = 8.0
GREEN_SAND_WATER_PCT = 3.0
RESIN_BINDER_PCT = 1.2
PRINTED_BINDER_PCT = 1.8
IN3_TO_CM3 = 16.387064
FEEDING_STOP_FRAC = 0.70  # solid fraction where feeding freezes off
ALLOY_USD_PER_LB = {
    "A356 Aluminum": 2.40,
    "Everdur Bronze (C52100)": 6.50,
    "Gray Iron (ASTM A48)": 0.90,
    "Ductile Iron (65-45-12)": 1.20,
    "316 Stainless Steel": 4.80,
}

# Named shop recipes — metal + process + temps in one click
SHOP_RECIPES = {
    "A356 green sand": {
        "metal": "A356 Aluminum",
        "process": "sand",
        "mold_type": "Green sand",
        "pour_temp_f": 1300,
        "mold_temp_f": 100,
        "gating_ratio": "1 : 2 : 2 (non-ferrous)",
        "thin_wall": "Auto",
    },
    "A356 ceramic shell": {
        "metal": "A356 Aluminum",
        "process": "shell",
        "mold_type": "Ceramic shell",
        "pour_temp_f": 1300,
        "mold_temp_f": 1100,
        "shell_mm": 8,
        "gating_ratio": "1 : 2 : 2 (non-ferrous)",
        "thin_wall": "Auto",
    },
    "Bronze green sand": {
        "metal": "Everdur Bronze (C52100)",
        "process": "sand",
        "mold_type": "Green sand",
        "pour_temp_f": 1950,
        "mold_temp_f": 100,
        "gating_ratio": "1 : 2 : 2 (non-ferrous)",
        "thin_wall": "Auto",
    },
    "Bronze ceramic shell": {
        "metal": "Everdur Bronze (C52100)",
        "process": "shell",
        "mold_type": "Ceramic shell",
        "pour_temp_f": 1950,
        "mold_temp_f": 1600,
        "shell_mm": 8,
        "gating_ratio": "1 : 2 : 2 (non-ferrous)",
        "thin_wall": "Auto",
    },
    "Gray iron sand": {
        "metal": "Gray Iron (ASTM A48)",
        "process": "sand",
        "mold_type": "Green sand",
        "pour_temp_f": 2600,
        "mold_temp_f": 100,
        "gating_ratio": "1 : 4 : 4 (ferrous)",
        "thin_wall": "No",
    },
    "A356 printed sand": {
        "metal": "A356 Aluminum",
        "process": "printed",
        "mold_type": "Printed sand",
        "pour_temp_f": 1300,
        "mold_temp_f": 80,
        "printed_mm": 15,
        "gating_ratio": "1 : 2 : 2 (non-ferrous)",
        "thin_wall": "Auto",
    },
}
