METAL_DEFAULTS = {
    "A356 Aluminum": {
        "pour_temp_f": 1300,
        "melt_temp_f": 1075,
        "density": 2.67,
        "specific_heat": 963,
        "latent_heat": 389,
        "conductivity": 151,
        "color": "#C8C8C8",
        "mold_constant": 1.0,
        "shrinkage_pct": 6.0,
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
}
