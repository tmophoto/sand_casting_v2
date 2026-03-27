# Sand Casting Simulator
**Version 0.1.0** — PyQt6 + matplotlib + numpy-stl

Desktop hobbyist tool for simulating sand casting. Load an STL, configure your
gating system and metal, then run a simulation to estimate fill time,
solidification time, and defect risks. A fill animation plays after each run.

---

## Quick Start

Double-click `run.bat` — it installs dependencies on first run, then launches.

Or manually:
```
pip install -r requirements.txt
python casting_sim.py
```

---

## Workflow

1. **Load STL** — click "Load STL…", pick your part file. Volume and surface
   area are computed automatically.
2. **Set Parting Line** — drag the slider to position the cope/drag split.
3. **Choose Flask Size** — pick a preset or add a custom size with "+".
4. **Configure Gating** — check Tapered Sprue, Runner, Riser etc. Drag them
   in the 3D viewport or use the Gating Placement sliders.
5. **Set Metal & Temps** — choose A356 Aluminum or Everdur Bronze. Pour and
   mold temps auto-fill from the metal defaults.
6. **Position Part** — use the X/Y/Z and rotation sliders under Model Placement.
7. **Simulate Pour** — click the blue button. Watch the fill animation, then
   read the results panel.
8. **Reset** — red button clears everything back to defaults.

---

## Simulation Physics

- **Chvorinov's Rule**: `t_solidify = B × (V/A)²`  where `B = 3.0 × mold_constant`
- **Fill time**: `max(3.0 s, volume_cm³ / 80.0)`
- **Defect checks**: misrun, shrinkage porosity, cold shut, burn-on, low superheat
- **Shrinkage compensation**: scale factor applied to simulation params (1.00×–1.10×)

---

## Metals

| Metal | Pour °F | Melt °F | Shrink | Mold Constant |
|-------|---------|---------|--------|---------------|
| A356 Aluminum | 1300 | 1075 | 6 % | 1.0 |
| Everdur Bronze (C52100) | 1950 | 1780 | 2 % | 1.4 |

---

## Requirements

- Python 3.10+
- PyQt6 ≥ 6.4
- matplotlib ≥ 3.7
- numpy ≥ 1.24
- numpy-stl ≥ 3.0

---

## Project Structure

```
sand_casting_v2/
├── casting_sim.py      # entire application (single file)
├── requirements.txt    # pip dependencies
├── run.bat             # double-click launcher (Windows)
└── README.md           # this file
```
