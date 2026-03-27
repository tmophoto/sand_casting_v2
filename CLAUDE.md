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

All application code lives in a single file: **`casting_sim.py`** (~1,800 lines).

| Component | Lines | Role |
|---|---|---|
| `CollapsiblePanel` | ~65 | Collapsible QFrame UI widget |
| `SimWorker` | ~100 | QObject worker (runs in QThread) for physics |
| `Viewport3D` | ~1,000 | 3-D rendering (PyVista or matplotlib fallback) |
| `build_results_text()` | ~50 | Formats simulation results dict → plain text |
| `MainWindow` | ~400 | Main application window, UI, signal wiring |

Constants defined at module level: `METAL_DEFAULTS`, `GATING_COMPONENTS`,
`FLASK_SIZES`, colour constants, `APP_STYLE` (Catppuccin Mocha dark theme QSS).

## Physics

- **Solidification time** — Chvorinov's Rule: `t = B × (V/A)²`
  where `B = 3.0 × mold_constant` and V/A is the volume-to-surface-area ratio.
- **Fill time** — Bernoulli gating hydraulics using the most restrictive cross-section.
  Falls back to `max(3.0 s, volume_cm³ / 80.0)` when no gating is configured.
- **Defect detection** — rule-based checks for misrun, cold shut, burn-on, and low
  superheat against configurable thresholds.

## Metals

| Metal | Pour (°F) | Melt (°F) | Shrinkage | Mold constant |
|---|---|---|---|---|
| A356 Aluminum | 1300 | 1075 | 6 % | 1.0 |
| Everdur Bronze (C52100) | 1950 | 1780 | 2 % | 1.4 |

## Rendering Backends

1. **PyVista** (preferred) — GPU-accelerated OpenGL, PBR materials, real-time
   lighting. Requires `pyvista` and `pyvistaqt`.
2. **Matplotlib 3D** (fallback) — software-rendered Poly3DCollection with per-face
   Phong shading. Always available.

The `PV_AVAILABLE` flag gates which backend is used; `Viewport3D.use_pyvista`
records which backend was successfully initialised at runtime.

## STL Handling

`Viewport3D.load_stl()` performs three clean-up passes before rendering:
1. Remove NaN / Inf / zero-area (degenerate) triangles.
2. Deduplicate triangles by centroid hash.
3. Decimate to at most 25,000 triangles (uniform stride sampling).

`_geometry_stats()` computes volume via the divergence theorem and surface area
from cross-product magnitudes — both in one vectorised NumPy pass.

## Helper Scripts (not part of the app)

The root directory contains several one-off scripts (`fix_*.py`, `part*.py`) that
were used during incremental development to patch earlier versions of the file.
They are **not** required to run the application and can be safely ignored.

## Git Branch

Active development branch: `claude/review-optimize-functions-79Odb`

Always develop on this branch; do not push directly to `master`.

## Common Tasks

### Add a new metal

1. Add an entry to `METAL_DEFAULTS` in `casting_sim.py`.
2. The `MainWindow._build_ui()` method auto-populates the combo box from that dict.

### Add a new gating component

1. Add the display name to `GATING_COMPONENTS`.
2. Add rendering logic in `Viewport3D._draw_gating()` (matplotlib) and optionally
   in `_render_pyvista()`.
3. Handle it in `SimWorker._compute_fill_time_gating_hydraulics()` if it affects
   flow area.

### Run a quick sanity check (no GUI)

```python
from casting_sim import SimWorker, METAL_DEFAULTS
w = SimWorker({"metal": "A356 Aluminum", "vol_cm3": 200, "surf_cm2": 180})
w.finished.connect(print)
w.run()
```
