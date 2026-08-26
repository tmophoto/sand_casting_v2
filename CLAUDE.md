# Sand Casting Simulator — Claude Code Guide

## Project Overview

Desktop hobbyist tool for simulating casting processes. Users load STL files,
pick **sand mold**, **ceramic shell**, or **printed sand**, place gating, then
run physics-based simulations to estimate fill time, solidification time, melt
and sand-mix tickets, and defect risk.

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

`casting_sim.py` is a thin entry point (`main()`). All logic lives in the
modules below.

```
casting_sim.py          # entry point
constants.py            # METAL_DEFAULTS, MOLD_TYPES, SHOP_RECIPES, colours
ui/
  style.py              # APP_STYLE QSS (Catppuccin Mocha)
  collapsible.py        # CollapsiblePanel widget
  main_window.py        # MainWindow — layout, signals, sessions, traveler
  demo_part.py          # Motor Mount Bracket
simulation/
  worker.py             # SimWorker — Chvorinov, hydraulics, voxels, tickets
  foundry.py            # Yield, riser/neck, draft, flask, process_kind, verdicts
  shop.py               # Recipes, wizard, melt / sand-mix / pattern tickets
  voxels.py             # ~48³ fill / freeze / porosity / Niyama / X-ray
  session.py            # .cast.json + recents
  mesh_tools.py         # QEM, thickness, transform_triangles (scale once)
viewport/
  viewport.py           # Viewport3D — PyVista or matplotlib
results/
  formatter.py          # build_results_text() + build_traveler_html()
tests/
  conftest.py           # QT_QPA_PLATFORM=offscreen
  test_simulation.py
  test_formatter.py
  test_geometry.py
  test_foundry.py
  test_shop.py
  test_voxels.py
```

### Module Summary

| Module | Key class / function | Role |
|---|---|---|
| `constants.py` | `METAL_DEFAULTS`, `MOLD_TYPES`, `SHOP_RECIPES` | Shared constants; no deps on other app modules |
| `ui/style.py` | `APP_STYLE` | QSS stylesheet |
| `ui/collapsible.py` | `CollapsiblePanel` | Collapsible QFrame |
| `ui/main_window.py` | `MainWindow` | Window, process picker, traveler, Keep as A |
| `simulation/worker.py` | `SimWorker` | Physics in a QThread |
| `simulation/foundry.py` | `process_kind`, `riser_ok`, `gating_volumes_cm3` | Foundry helpers |
| `simulation/shop.py` | `size_rigging`, `sand_mix_ticket` | Shop-floor extras |
| `simulation/mesh_tools.py` | `transform_triangles`, QEM, thickness | Mesh helpers; scale applied once |
| `simulation/voxels.py` | `analyze` | Coarse voxel pass (~48³) |
| `simulation/session.py` | `save_session`, `load_session` | Jobs and recents |
| `viewport/viewport.py` | `Viewport3D` | 3-D view, gating meshes, overlays |
| `results/formatter.py` | `build_results_text`, `build_traveler_html` | HTML for results / PDF |

### Dependency graph (no circular deps)

```
constants ← simulation/{worker,foundry,shop,session,voxels}
constants ← viewport/viewport
constants ← ui/main_window
ui/style, ui/collapsible ← ui/main_window
simulation/{worker,foundry,shop,session,mesh_tools} ← ui/main_window
viewport/viewport ← ui/main_window
results/formatter ← ui/main_window
ui/main_window ← casting_sim
foundry + shop + voxels ← simulation/worker
```

## Physics

- **Solidification time** — Chvorinov: `t = B × (V/A)²` with
  `B = 3.0 × mold_constant × (H/H_A356) × (k_A356/k) × mold_factor`.
  `mold_factor`: green 1.00, dry 1.15, resin 0.85, printed sand 0.90.
  Ceramic shell starts at 0.62 (cold 8 mm) then scales with fired thickness
  and preheat (`effective_mold_factor` / `shell_chvorinov_factor`).
- **Fill time** — Bernoulli at the smallest of sprue exit, runner, gate area
  (× number of gates), foam filter (`area × 0.35`). Fallback
  `max(3.0 s, volume_cm³ / 80.0)` when no gating is configured.
- **Yield** — melt mass is part + gating (sprue, runner, gate(s), riser, neck,
  basin, filter); casting yield is part / total.
- **Riser** — open cylinder modulus must exceed 1.2 × part V/A on heavy sections.
  Blind risers add the top as a cooling face. Neck modulus is **lateral only**
  (ends sit on riser and casting). Warn on blind or a pinched neck
  (`neck_r < 0.4 × riser_r`).
- **Voxels** — ~48³ occupancy, gravity flood from the gate, freeze ~
  `B × dist²`, isolated-liquid porosity (hot band = last 30 % when
  `FEEDING_STOP_FRAC` is 0.70), Niyama proxy, chills, sleeve.
  X-ray uses `porosity_xyz` / `hot_xyz`. Riser check uses
  `max(global V/A, voxel hot-spot modulus)`.
- **Pattern scale** — `assembled_mesh(1.0)` then `write_pattern_stl(..., scale)`
  so shrink is applied once. Simulate always uses cavity scale, not the
  as-cast preview.
- **Defect detection** — misrun, cold shut, burn-on (**sand only**), low
  superheat, flask overflow (**sand only**), ceramic-shell preheat /
  breakthrough, isolated liquid, erosion, gravity-flood unfilled lobes.
  Auto thin-wall from local mesh thickness (< 6 mm).

## Processes

| `process_kind` | `mold_type` string | Flask | Draft scolding | UI panel |
|---|---|---|---|---|
| `sand` | Green / Dry / Resin | Yes | Yes | Flask |
| `shell` | Ceramic shell | No | Optional (wax die) | Fired shell mm + preheat |
| `printed` | Printed sand | No | No | Print-box wall mm + vents |

Helpers: `is_shell_mold()`, `is_printed_sand()`, `process_kind()` in
`simulation/foundry.py`. Printed sand must **not** add a warning on every
pour (that would force verdict=`risky`).

## Metals

| Metal | Pour (°F) | Melt (°F) | Shrinkage | Mold constant |
|---|---|---|---|---|
| A356 Aluminum | 1300 | 1075 | 6 % | 1.0 |
| Everdur Bronze (C52100) | 1950 | 1780 | 2 % | 1.4 |
| Gray Iron (ASTM A48) | 2600 | 2200 | 1 % | 1.6 |
| Ductile Iron (65-45-12) | 2650 | 2250 | 0.8 % | 1.6 |
| 316 Stainless Steel | 2900 | 2550 | 2.5 % | 1.8 |

## Rendering Backends

1. **PyVista** (preferred) — GPU OpenGL, PBR, SSAO, shadows. Requires
   `pyvista` and `pyvistaqt`.
2. **Matplotlib 3D** (fallback) — `Poly3DCollection`. Always available.

`PV_AVAILABLE` in `viewport/viewport.py` gates the backend;
`Viewport3D.use_pyvista` records what initialised at runtime.

Do **not** pass `shade=True` with `edgecolors="none"` on Matplotlib
collections — current matplotlib shades empty edgecolours and aborts.
Cope/drag collections use `shade=False`.

X-ray: hide/ghost the skin (`overlay_mode == "xray"`), scatter peach
last-to-freeze and pink porosity points. Never write
`np.asarray(arr or default)` — a non-empty ndarray is ambiguous in boolean
context.

## STL Handling

`Viewport3D.load_stl()`:

1. Remove NaN / Inf / zero-area triangles.
2. Deduplicate by centroid hash.
3. Invert winding when signed volume is negative.
4. QEM decimate to ≤ 25,000 triangles (grid clustering as last resort).

`_geometry_stats()` computes volume (divergence theorem) and surface area
(cross-product magnitudes) in one vectorised NumPy pass, plus local wall
thickness for thin-wall Auto.

## Running Tests

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/
```

Install extras with `pip install -r requirements-dev.txt`. All tests are
headless. `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`.
`test_simulation.py` creates a QApplication for `pyqtSignal`.

| File | Focus |
|---|---|
| `test_simulation.py` | SimWorker physics |
| `test_formatter.py` | Results + traveler HTML |
| `test_geometry.py` | Mesh helpers |
| `test_foundry.py` | Processes, riser/neck, session |
| `test_shop.py` | Recipes, wizard, tickets |
| `test_voxels.py` | Rasterize / flood / porosity |

**222 tests** at last count.

## Git Branch

Active work for output-quality (single shrink, feeding-stop porosity, hotspot
riser) lives on `cursor/output-quality-55e2`. Do not push directly to `master`.

## Common Tasks

### Add a new metal

1. Add an entry to `METAL_DEFAULTS` in `constants.py` (include `min_superheat_f`).
2. Optional: `METAL_PBR`, `SHELL_PREHEAT_DEFAULT_F`, `ALLOY_USD_PER_LB`,
   `FERROUS_METALS` (wizard uses 1:4:4 for ferrous).
3. The alloy combo is filled from `METAL_DEFAULTS` — no other UI changes.

### Add a new gating component

1. Checkbox name in `MainWindow._build_gating_panel()`.
2. Draw in `_draw_gating()` and `_build_pv_gating_actors()`.
3. Hydraulics in `SimWorker._compute_fill_time_gating_hydraulics()` if it
   chokes flow; volume in `gating_volumes_cm3()`.
4. `Viewport3D.get_gating_params()` and, if click-to-place, `place_gating()`.
5. Include new fields in `_gating_state_key()` so PyVista/MPL caches rebuild.

### Add a shop recipe

Add a dict to `SHOP_RECIPES` with `metal`, `process` (`sand` / `shell` /
`printed`), temps, and optional `shell_mm` / `printed_mm` / `gating_ratio`.
`MainWindow._on_recipe` applies it.

### Add a casting process

1. `MOLD_TYPES` factor + `is_*` / `process_kind()` in `foundry.py`.
2. Process button + Flask-panel box in `MainWindow`.
3. `Viewport3D.set_mold_process` + envelope draw.
4. Worker: skip flask/burn-on where appropriate; `sand_mix_ticket` branch.
5. Tests in `test_foundry.py` / `test_shop.py`.

Do not emit a process-wide warning on every sim (verdict becomes `risky`).

### Run a quick sanity check (no GUI)

```python
from simulation.worker import SimWorker

result = {}
w = SimWorker({"metal": "A356 Aluminum", "vol_cm3": 200, "surf_cm2": 180})
w.finished.connect(result.update)
w.run()
print(result["process"], result["sand_mix"], result["verdict"])
```
