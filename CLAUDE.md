# Sand Casting Simulator — Claude Code Guide

## Project Overview

Desktop hobbyist tool for simulating sand casting processes. Users load STL files,
configure gating systems and metal types, then run physics-based simulations to
estimate fill time, solidification time, and identify defect risks.

## Running the App

```bash
python casting_sim.py
```

### Dependencies

```bash
pip install -r requirements.txt
```

Optional GPU acceleration (requires CUDA-capable NVIDIA GPU):

```bash
pip install cupy-cuda12x   # adjust to your CUDA version
pip install pyvista pyvistaqt
```

`requirements.txt` lists the mandatory deps (PyQt6, matplotlib, numpy, numpy-stl).
PyVista/CuPy are optional; the app falls back to matplotlib rendering and NumPy
automatically.

## Architecture

The codebase is split into a package structure. `casting_sim.py` is a thin
73-line entry point; all logic lives in the modules below.

```
casting_sim.py          # entry point — calls main()
constants.py            # METAL_DEFAULTS, FLASK_SIZES, colour constants
ui/
  style.py              # APP_STYLE QSS (Catppuccin Mocha dark theme)
  collapsible.py        # CollapsiblePanel widget
  main_window.py        # MainWindow — UI layout, signal wiring, event handlers
simulation/
  worker.py             # SimWorker — physics calculations in a QThread
  mesh_tools.py         # Mesh quality, QEM decimation, local thickness, defect sites
  foundry.py            # Yield, riser modulus, draft, flask fit, verdicts
  session.py            # Save/load .cast.json and recent files
viewport/
  viewport.py           # Viewport3D — 3D rendering, STL loading, animation
results/
  formatter.py          # build_results_text() — formats result dict → text
tests/
  test_simulation.py    # SimWorker physics (headless)
  test_formatter.py     # build_results_text output format
  test_geometry.py      # Geometry helpers and mesh generators
```

### Module Summary

| Module | Key class / function | Role |
|---|---|---|
| `constants.py` | — | All shared constants; no deps on other app modules |
| `ui/style.py` | `APP_STYLE` | QSS stylesheet string |
| `ui/collapsible.py` | `CollapsiblePanel` | Collapsible QFrame widget |
| `ui/main_window.py` | `MainWindow` | Top-level window, UI, signal wiring |
| `simulation/worker.py` | `SimWorker` | QObject worker; runs physics in QThread |
| `viewport/viewport.py` | `Viewport3D` | 3-D rendering (PyVista or matplotlib fallback) |
| `results/formatter.py` | `build_results_text()` | Formats simulation results → plain text |

### Dependency graph (no circular deps)

```
constants ← simulation/worker
constants ← viewport/viewport
constants ← ui/main_window
ui/style   ← ui/main_window
ui/collapsible ← ui/main_window
simulation/worker ← ui/main_window
viewport/viewport ← ui/main_window
results/formatter ← ui/main_window
ui/main_window ← casting_sim
```

## Physics

- **Solidification time** — Chvorinov's Rule: `t = B × (V/A)²`
  where `B = 3.0 × mold_constant × (H/H_A356) × (k_A356/k) × mold_factor`.
  `mold_factor` is 1.00 green sand, 1.15 dry sand, 0.85 resin/no-bake.
  Ceramic shell starts at 0.62 (thin cold 8 mm shell) then scales with fired
  thickness and shell preheat (hot shells freeze slower; extra coats insulate).
- **Fill time** — Bernoulli gating hydraulics using the most restrictive cross-section.
  Falls back to `max(3.0 s, volume_cm³ / 80.0)` when no gating is configured.
- **Yield** — melt mass is part + gating metal; casting yield is part / total.
- **Riser** — open-riser modulus must exceed 1.2 × part V/A on heavy sections.
- **Defect detection** — misrun, cold shut, burn-on (sand), low superheat, flask overflow,
  ceramic-shell preheat / breakthrough, plus Auto thin-wall from local mesh thickness (< 6 mm).

## Metals

| Metal | Pour (°F) | Melt (°F) | Shrinkage | Mold constant |
|---|---|---|---|---|
| A356 Aluminum | 1300 | 1075 | 6 % | 1.0 |
| Everdur Bronze (C52100) | 1950 | 1780 | 2 % | 1.4 |
| Gray Iron (ASTM A48) | 2600 | 2200 | 1 % | 1.6 |
| Ductile Iron (65-45-12) | 2650 | 2250 | 0.8 % | 1.6 |
| 316 Stainless Steel | 2900 | 2550 | 2.5 % | 1.8 |

## Rendering Backends

1. **PyVista** (preferred) — GPU-accelerated OpenGL, PBR materials, real-time
   lighting. Requires `pyvista` and `pyvistaqt`.
2. **Matplotlib 3D** (fallback) — software-rendered Poly3DCollection with per-face
   Phong shading. Always available.

`PV_AVAILABLE` in `viewport/viewport.py` gates which backend is used;
`Viewport3D.use_pyvista` records which was successfully initialised at runtime.

## STL Handling

`Viewport3D.load_stl()` performs these clean-up passes before rendering:
1. Remove NaN / Inf / zero-area (degenerate) triangles.
2. Deduplicate triangles by centroid hash.
3. Invert face winding when signed volume is negative.
4. Decimate to at most 25,000 triangles with Garland–Heckbert QEM (grid
   clustering as a last-resort fallback).

`_geometry_stats()` computes volume via the divergence theorem and surface area
from cross-product magnitudes — both in one vectorised NumPy pass — plus local
wall thickness for thin-wall auto-detect.

## Running Tests

```bash
python -m pytest tests/
```

Install test extras with `pip install -r requirements-dev.txt`. All tests are
headless (`QT_QPA_PLATFORM=offscreen`; no display required). The simulation and geometry tests
import modules directly; only `test_simulation.py` needs a QApplication instance
(created automatically inside the test file).

## Helper Scripts (not part of the app)

The root directory previously contained one-off `fix_*.py` / `part*.py` scripts.
Those have been deleted; they are not required to run the application.

## Git Branch

Active development happens on feature branches. Do not push directly to `master`.

## Common Tasks

### Add a new metal

1. Add an entry to `METAL_DEFAULTS` in `constants.py`.
2. `MainWindow._build_ui()` auto-populates the combo box from that dict —
   no other changes needed.

### Add a new gating component

1. Add the display name string to the checkbox list in `MainWindow._build_ui()`
   (`ui/main_window.py`).
2. Add rendering logic in `Viewport3D._draw_gating()` (matplotlib path) in
   `viewport/viewport.py`, and optionally in `_render_pyvista()`.
3. If it affects flow area, add a branch in
   `SimWorker._compute_fill_time_gating_hydraulics()` in `simulation/worker.py`.
4. Expose its dimensions in `Viewport3D.get_gating_params()`.

### Run a quick sanity check (no GUI)

```python
from simulation.worker import SimWorker

result = {}
w = SimWorker({"metal": "A356 Aluminum", "vol_cm3": 200, "surf_cm2": 180})
w.finished.connect(result.update)
w.run()
print(result)
```
