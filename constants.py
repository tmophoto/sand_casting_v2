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
