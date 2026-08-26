# Sand Casting Simulator

A desktop tool for hobbyist and small-shop foundry work. Load an STL part file,
configure your gating system and metal, and run a physics-based simulation that
estimates fill time, solidification time, and flags common casting defects — all
in a real-time 3D viewer.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Running the App](#running-the-app)
5. [Quick Start — One-Click Demo](#quick-start--one-click-demo)
6. [User Interface Walkthrough](#user-interface-walkthrough)
7. [Simulation Physics](#simulation-physics)
8. [Supported Metals](#supported-metals)
9. [Gating System Components](#gating-system-components)
10. [STL File Handling](#stl-file-handling)
11. [Rendering Backends](#rendering-backends)
12. [Adding a New Metal](#adding-a-new-metal)
13. [Adding a New Gating Component](#adding-a-new-gating-component)
14. [Running Tests](#running-tests)
15. [Running a Headless Sanity Check](#running-a-headless-sanity-check)
16. [Building a Standalone Executable](#building-a-standalone-executable)
17. [Project Structure](#project-structure)
18. [Known Limitations](#known-limitations)
19. [Troubleshooting](#troubleshooting)

---

## Features

- **One-click demo** — pre-built Motor Mount Bracket; **▶ Try Demo** lives on the top bar
- **STL import** with automatic mesh cleanup — degenerate triangle removal,
  winding repair, QEM decimation to 25,000 triangles, and thin-wall detection
- **Top-bar workflow** — Load, Simulate, Save/Open `.cast.json` sessions, recents, Undo (Ctrl+Z)
- **Gating as a layout tool** — click a piece in 3D to edit it; snap to the part silhouette;
  1:2:2 / 1:4:4 area-ratio presets; choke ring at the restrictive section
- **Fill animation** — metal spreads from the gate (distance order), with a fill/solidify clock
- **Solidification animation** — freeze order follows local wall thickness (thin first)
- **Physics simulation** (background thread):
  - Solidification time via Chvorinov's Rule (metal properties × mould type,
    including ceramic-shell thickness and preheat)
  - Fill time via Bernoulli gating hydraulics using the most-restrictive cross-section
  - Casting yield and melt mass including gating metal
  - Riser modulus check vs hot-spot V/A
  - Defect risk detection: misrun, cold shut, burn-on, low superheat, flask overflow,
    cold/thin ceramic shell
- **Actionable results** — Likely OK / Risky / Will probably fail, with click-to-fly fixes
- **Foundry checks** — draft overlay, undercut/core-print overlay, auto flask fit
- **Ceramic shell (investment / lost-wax)** — fired-shell thickness, shell preheat,
  no sand flask, envelope overlay in the viewport
- **Pattern vs as-cast** — shrinkage scale with a toggle to preview the frozen part
- **Defect markers** — coloured spheres rendered at risk locations after simulation
- **Shrinkage compensation** — configurable scale factor per metal
- **GPU array acceleration** — CuPy replaces NumPy transparently on CUDA GPUs;
  falls back to NumPy automatically when unavailable
- **Dark theme** — Catppuccin Mocha palette throughout
- **Windows launcher** (`run.bat`) with automatic dependency installation

---

## Requirements

### Mandatory

| Package | Minimum version |
|---|---|
| Python | 3.10 |
| PyQt6 | 6.4.0 |
| matplotlib | 3.7.0 |
| numpy | 1.24.0 |
| numpy-stl | 3.0.0 |

### Optional — GPU acceleration

| Package | Purpose |
|---|---|
| pyvista + pyvistaqt | GPU-accelerated OpenGL renderer with PBR, SSAO, shadows |
| cupy-cuda12x | CUDA array backend (replaces NumPy on CUDA GPUs) |

Without PyVista the app falls back to a Matplotlib software renderer.
Without CuPy all array maths runs on NumPy — performance is fine for most
part sizes.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/tmophoto/sand_casting_v2.git
cd sand_casting_v2

# Install mandatory dependencies
pip install -r requirements.txt

# Optional: tests
pip install -r requirements-dev.txt

# Optional: GPU-accelerated renderer
pip install pyvista pyvistaqt

# Optional: CUDA array acceleration (adjust version to match your CUDA toolkit)
pip install cupy-cuda12x
```

A virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Running the App

```bash
python casting_sim.py
```

**Windows shortcut:** double-click `run.bat`. It checks for PyQt6, installs all
requirements automatically if missing, then launches the app.

---

## Quick Start — One-Click Demo

No STL file required to try the app.

1. Launch the app (`python casting_sim.py` or `run.bat` on Windows).
2. Click the green **▶ Try Demo** button in the *STL File* panel.
3. A Motor Mount Bracket appears in the viewport with all settings
   pre-configured (A356 Aluminum, 10×12 flask, full gating system).
4. Click **Simulate Pour** in the right panel.
5. Watch the fill animation, solidification animation, and defect markers.
6. Review the results — the demo is tuned to trigger cold-shut and low-superheat
   warnings so you can see how defect detection works.

The Motor Mount Bracket is a procedurally generated part with a wide thin base
plate, a thick central body, a cylindrical boss, two thin mounting ears, and two
web ribs — deliberately mixing section thicknesses to exercise every part of the
physics engine.

---

## User Interface Walkthrough

The window is divided into three panels:

| Panel | Contents |
|---|---|
| **Left** | Collapsible control panels |
| **Centre** | 3D viewport + view preset buttons |
| **Right** | Simulation results, Simulate and Reset buttons |

### 1 — Load a Part

**Option A — Load your own STL file**
Click **Load STL…** in the *STL File* panel and choose any binary or ASCII `.stl`
file. The part appears in the 3D viewport immediately. Volume and surface area are
shown beneath the button. You can load multiple STL files; each becomes a
separately movable model.

**Option B — Use the built-in demo**
Click **▶ Try Demo** to load the pre-built Motor Mount Bracket with all settings
pre-configured. See [Quick Start](#quick-start--one-click-demo) above.

### 2 — Set the Parting Line

The **Parting Line** slider sets where the mould splits, as a percentage of the
part's total height (5 %–95 %). The blue horizontal plane in the viewport updates
live. Faces above the parting line are shown in blue (cope half); faces below in
brown (drag half).

### 3 — Flask or ceramic shell

**Sand molds** — pick a standard flask from the **Flask** drop-down (6×6 through
14×20 inches) or click **+ Custom**. Auto-fit chooses the smallest preset that
clears the part. The dashed outline in the viewport is the flask.

**Ceramic shell** — under **Mold**, choose **Ceramic shell**. The flask panel
becomes fired-shell thickness (4–16 mm) and **Shell preheat**. The viewport
draws a ceramic envelope around the part instead of a sand flask. Typical
preheat is ~1100 °F for A356 and ~1600–1900 °F for bronze, iron, and stainless.

### 4 — Configure the Gating System

Check any combination of components in the **Gating System** panel:

- **Tapered Sprue** — vertical tapered channel that carries metal from the top of
  the cope down to the parting line.
- **Runner (Horizontal)** — horizontal channel at the parting line that distributes
  metal across to the gate.
- **Fan Gate** — flattened gate at the parting line that spreads the metal stream
  into the mould cavity.
- **Riser (Open)** — cylindrical reservoir above the parting line that feeds
  shrinkage during solidification.

Use the **Gating Placement** sliders to position the sprue and riser in X/Y, or
drag them directly in the 3D viewport by clicking near the component.

### 5 — Select Metal and Temperature

The **Metal & Temperature** panel provides:

- **Metal** drop-down — A356 Aluminum or Everdur Bronze; pour temperature and
  shrinkage defaults update automatically.
- **Mold** drop-down — Green sand, dry sand, resin/no-bake, or ceramic shell
  (investment / lost-wax).
- **Pour Temp** spin box (800–3,200 °F) — override the metal's default pour
  temperature. The range covers aluminium through stainless steel.
- **Mold Temp** (sand, 32–400 °F) — mould pre-heat; values above 120 °F trigger
  a burn-on warning.
- **Shell preheat** (ceramic shell, 200–2,200 °F) — fired-shell temperature at
  pour. A hot shell fills thin walls more easily and freezes slower than a
  cold shell. Burn-on does not apply.
- **Thin Wall?** — flag that tightens the cold-shut superheat threshold.

### 6 — Position the Model

The **Model Placement** sliders move and rotate the active model:

| Slider | Range | Effect |
|---|---|---|
| X Offset | ±500 mm | Translate along X |
| Y Offset | ±500 mm | Translate along Y |
| Z Offset | ±200 mm | Translate along Z |
| Rotation | 0–360 ° | Rotate about the Z axis |

You can also drag the model directly in the 3D viewport.

### 7 — Shrinkage Compensation

The **Shrinkage Compensation** slider adjusts the scale factor applied to the
part geometry (100 %–110 %). The label shows the metal's nominal shrinkage
percentage so you can match your pattern allowance to the simulation.

### 8 — Run the Simulation

Click **Simulate Pour**. The progress bar tracks five stages:

1. Geometry ratios
2. Chvorinov's Rule
3. Defect risk checks
4. Gating hydraulics
5. Assembling results

When complete:

- The results panel shows fill time, solidification time, V/S ratio, and any
  defect warnings.
- The fill animation plays — metal rises from the bottom, coloured by temperature.
- The solidification animation follows — heat front sweeps inward.
- Defect markers appear at risk locations: **red** = shrinkage risk,
  **yellow** = cold shut risk.

### 9 — Reset

Click **Reset** to stop all animations, clear the results panel, uncheck all
gating components, and return all sliders to their defaults.

### 10 — View Presets

The seven buttons at the top of the centre panel (Top, Bottom, Front, Back, Left,
Right, Iso) snap the camera to standard orthographic and isometric positions. The
scroll wheel zooms in the Matplotlib backend.

---

## Simulation Physics

### Solidification Time — Chvorinov's Rule

```
t_solidify = B × (V / A)²
```

| Symbol | Meaning |
|---|---|
| `t_solidify` | Solidification time (minutes) |
| `B` | `3.0 × mold_constant × (H / H_A356) × (k_A356 / k) × mold_factor` |
| `H` | Volumetric enthalpy `ρ (c ΔT + L)` from pour through freeze |
| `V` | Part volume (cm³) |
| `A` | Part surface area (cm²) |

A356 at its catalogue pour temperature has `(H / H_A356) × (k_A356 / k) = 1`,
so its freeze time matches the original `B = 3.0 × mold_constant` scale. Other
alloys pick up density, specific heat, latent heat, and conductivity. Pour mass
is `volume × density` (grams). `mold_factor` is 1.00 green sand, 1.15 dry sand,
0.85 resin/no-bake. Ceramic shell starts at 0.62 for a cold 8 mm shell, then
scales with fired thickness and preheat (hot shells freeze slower).

### Fill Time — Bernoulli Gating Hydraulics

When at least one gating component is active, fill time is calculated from the
most restrictive cross-section using Torricelli's theorem:

```
v = Cd × √(2 g h)
Q = A_effective × v
t_fill = V / Q
```

| Symbol | Meaning |
|---|---|
| `Cd` | Discharge coefficient = 0.75 |
| `g` | Gravitational acceleration = 9,806.65 mm/s² |
| `h` | Effective sprue head = 100 mm |
| `A_effective` | Area of the most restrictive element (mm²) |

**Restriction priority** — among every enabled component, the smallest area wins:

1. Tapered sprue → exit (bottom) area
2. Horizontal runner → rectangular width × height (10 × 8 mm)
3. Fan gate → hydraulic area (default 40 mm²)
4. No gating → fallback: `max(3.0 s, volume_cm³ / 80.0)`

Fill time is clamped to a minimum of 1.5 s.

### Defect Detection

| Condition | Category | Flag |
|---|---|---|
| Superheat < 50 °F | Defect | Misrun risk |
| Thin wall AND pour temp < melt temp + 150 °F | Defect | Cold shut risk |
| Mould temp > 120 °F | Warning | Burn-on warning |
| Superheat < 100 °F | Warning | Low superheat |

*Superheat* = pour temperature − liquidus temperature.

---

## Supported Metals

| Metal | Pour °F | Liquidus °F | Density | Shrinkage | Mould constant |
|---|---|---|---|---|---|
| A356 Aluminum | 1,300 | 1,075 | 2.67 g/cm³ | 6 % | 1.0 |
| Everdur Bronze (C52100) | 1,950 | 1,780 | 8.8 g/cm³ | 2 % | 1.4 |
| Gray Iron (ASTM A48) | 2,600 | 2,200 | 7.15 g/cm³ | 1 % | 1.6 |
| Ductile Iron (65-45-12) | 2,650 | 2,250 | 7.1 g/cm³ | 0.8 % | 1.6 |
| 316 Stainless Steel | 2,900 | 2,550 | 7.99 g/cm³ | 2.5 % | 1.8 |

See [Adding a New Metal](#adding-a-new-metal) to extend this list.

---

## Gating System Components

### Tapered Sprue
Vertical channel, wider at top (7.5 mm radius) and narrower at bottom (4.0 mm).
The taper compensates for metal acceleration under gravity, keeping the channel
full and preventing air aspiration. Rendered in orange.

### Runner (Horizontal)
Rectangular channel (160 × 10 × 8 mm) at the parting line distributing metal
from the sprue base to the gate. Rendered in gold.

### Fan Gate
Flat rectangular gate (60 × 8 × 6 mm) at the parting line that spreads the
metal stream. Default hydraulic area is 40 mm². Rendered in green.

### Riser (Open)
Cylindrical reservoir (20 mm radius, 60 mm tall) above the parting line.
Feeds volumetric shrinkage during solidification and vents gas. Rendered in blue.

---

## STL File Handling

`Viewport3D.load_stl()` runs three clean-up passes on every imported file:

1. **Degenerate triangle removal** — strips triangles whose vertices contain
   NaN/Inf, or whose area is ≤ 1×10⁻¹⁰ mm².
2. **Deduplication** — removes triangles with identical centroids (rounded to
   6 decimal places).
3. **Decimation** — if more than 25,000 triangles remain, a uniform stride
   keeps every Nth triangle. Fine detail on very complex meshes may be lost.

Geometry statistics use a single vectorised NumPy pass:

- **Volume** — divergence theorem: `V = |Σ v₀·(v₁×v₂)| / 6`
- **Surface area** — `A = Σ ‖(v₁−v₀)×(v₂−v₀)‖ / 2`

Both formulas assume a closed, consistently wound mesh. Clean your STL with
Meshmixer or PrusaSlicer before importing if you get unexpected geometry values.

---

## Rendering Backends

### PyVista (preferred)
Activated when `pyvista` and `pyvistaqt` are both importable.

- GPU-accelerated OpenGL via VTK
- PBR materials with per-metal metallic and roughness values
- Screen-space ambient occlusion (SSAO) and shadow rendering
- 3-point lighting rig (key, fill, rim)
- Incremental actor updates — model actors persist across frames; only the
  fill overlay is rebuilt per animation step
- `pyvistaqt.BackgroundPlotter` embeds directly in the Qt window

### Matplotlib 3D (fallback)
Used when PyVista is unavailable.

- Software-rendered `Poly3DCollection` with per-face vectorised Phong shading
- Persistent collections — model geometry is not cleared between frames;
  only fill/particle overlays are removed per step
- Three-light rig (key, fill, rim) computed with a single matrix multiply
- Scroll-wheel zoom; click-drag to reposition models and gating
- `FigureCanvasQTAgg` embedded in a `QVBoxLayout`

---

## Adding a New Metal

Open `constants.py` and add an entry to `METAL_DEFAULTS`:

```python
METAL_DEFAULTS["Gray Iron (ASTM A48)"] = {
    "pour_temp_f":    2500,
    "melt_temp_f":    2200,
    "density":        7.15,   # g/cm³
    "specific_heat":  460,    # J/kg·K
    "latent_heat":    230,    # kJ/kg
    "conductivity":   50,     # W/m·K
    "color":          "#888888",
    "mold_constant":  1.6,
    "shrinkage_pct":  1.0,
}
```

Optionally add a matching entry to `METAL_PBR` in `constants.py` for PyVista
PBR rendering:

```python
METAL_PBR["Gray Iron (ASTM A48)"] = {
    "color": "#888888", "metallic": 0.6, "roughness": 0.5
}
```

The metal appears in the **Metal** drop-down automatically — `_build_ui()`
iterates over `METAL_DEFAULTS` to populate the combo box.

---

## Adding a New Gating Component

1. Add the display name string to the checkbox list in `MainWindow._build_ui()`
   (`ui/main_window.py`).
2. Add a rendering block inside `Viewport3D._draw_gating()` (Matplotlib path)
   and optionally inside `_render_pyvista()` in `viewport/viewport.py`.
3. If the component affects flow area, add a branch in
   `SimWorker._compute_fill_time_gating_hydraulics()` in `simulation/worker.py`.
4. Expose its dimensions in `Viewport3D.get_gating_params()` so the worker
   receives the correct cross-section area.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

All tests are headless (`QT_QPA_PLATFORM=offscreen`; no display required).

| Test file | Coverage |
|---|---|
| `tests/test_simulation.py` | SimWorker physics |
| `tests/test_formatter.py` | `build_results_text()` output format |
| `tests/test_geometry.py` | Geometry helpers and mesh generators |

---

## Running a Headless Sanity Check

Test the simulation worker without a display:

```python
from simulation.worker import SimWorker

result = {}
w = SimWorker({
    "metal":         "A356 Aluminum",
    "vol_cm3":       200.0,
    "surf_cm2":      180.0,
    "pour_temp_f":   1300,
    "mold_temp_f":   77,
    "gating_params": {
        "has_sprue":      True,
        "has_gate":       True,
        "sprue_top_r":    7.5,
        "sprue_bot_r":    4.0,
        "gate_area_mm2":  40.0,
    },
})
w.finished.connect(lambda r: result.update(r))
w.run()

print(f"Fill time : {result['fill_time_s']:.1f} s  ({result['restrictive_elem']})")
print(f"Solidify  : {result['t_solidify_min']:.2f} min")
print(f"Defects   : {result['defects'] or 'none'}")
```

Or use the demo part directly:

```python
from ui.demo_part import build_demo_mesh
triangles, normals, stats = build_demo_mesh()
print(f"{len(triangles)} triangles, {stats['vol_cm3']:.1f} cm³")
```

---

## Building a Standalone Executable

PyInstaller must run on the **same OS** as the target machine. To build a
Windows `.exe`, run the following commands on a Windows machine:

```bat
pip install pyinstaller
build_exe.bat
```

Output: `dist/SandCastingSim/SandCastingSim.exe` (folder build — zip the whole folder).

GPU / PyVista build (much larger, includes VTK):

```bat
build_gpu.bat
```

Output: `dist/SandCastingSim_GPU/SandCastingSim.exe`.

---

## Project Structure

```
sand_casting_v2/
├── casting_sim.py              # Entry point — calls main()
├── constants.py                # METAL_DEFAULTS, FLASK_SIZES, METAL_PBR, colour constants
├── requirements.txt            # Mandatory Python dependencies
├── README.md                   # This file
├── CLAUDE.md                   # Developer guide for Claude Code sessions
├── run.bat                     # Windows launcher (auto-installs deps)
├── build_exe.bat               # PyInstaller CPU/folder build (run on Windows)
├── build_gpu.bat               # PyInstaller PyVista/VTK GPU build (run on Windows)
├── SandCastingSim.spec
├── SandCastingSim_GPU.spec
│
├── ui/
│   ├── style.py                # APP_STYLE QSS (Catppuccin Mocha dark theme)
│   ├── collapsible.py          # CollapsiblePanel widget
│   ├── main_window.py          # MainWindow — UI layout, signal wiring, event handlers
│   └── demo_part.py            # build_demo_mesh() — procedural Motor Mount Bracket
│
├── simulation/
│   ├── worker.py               # SimWorker — physics calculations in a QThread
│   └── mesh_tools.py           # Watertight check, QEM decimation, local thickness
│
├── viewport/
│   └── viewport.py             # Viewport3D — 3D rendering, STL loading, animation
│
├── results/
│   └── formatter.py            # build_results_text() — formats result dict → text
│
└── tests/
    ├── test_simulation.py      # SimWorker physics (30 tests)
    ├── test_formatter.py       # build_results_text output format (27 tests)
    └── test_geometry.py        # Geometry helpers and mesh generators (37 tests)
```

---

## Known Limitations

- **Closed meshes only** — volume and surface area assume a watertight,
  consistently oriented STL. Open or inverted meshes produce wrong geometry
  values.
- **QEM decimation** — Garland–Heckbert edge collapse to 25,000 triangles;
  grid clustering is only used if QEM cannot reach the budget.
- **Single parting line** — sand molds are a simple two-part cope/drag split.
  Ceramic shell has no cope/drag; the plane is only sprue/gate height. Multi-part
  moulds and sand cores are not modelled.
- **Isothermal fill assumption** — metal is treated as a single-temperature
  incompressible fluid. Partial solidification during fill is captured only by
  the rule-based cold-shut warning. The fill overlay still rises with height.
- **Sprue head** — hydraulic head is the visible basin height plus cope height
  (parting line up to the part top). The sprue mesh spans the parting plane to
  the pouring basin so it meets the runner.
- **Flask height** — XY flask presets are inches in plan; stack height is a
  separate control (default 6 in).
- **PyVista drag interaction** — click-drag of the sprue, riser, and model works
  in both Matplotlib and PyVista. Camera rotate still uses the default VTK
  interactor when you are not near a gating component.

---

## Troubleshooting

**Blank viewport on launch**
Resize the window once to trigger a matplotlib `tight_layout` redraw.

**`ModuleNotFoundError: No module named 'PyQt6'`**
Run `pip install -r requirements.txt` in the correct Python environment, or
use `run.bat` on Windows (it handles this automatically).

**PyVista fails to initialise**
The app falls back to Matplotlib automatically. On headless Linux, set
`DISPLAY=:0` or use `Xvfb`.

**Volume reads as 0 after loading STL**
The mesh is not watertight or has reversed normals. Repair with Meshmixer
(*Edit → Make Solid*) or PrusaSlicer (*Fix through Netfabb*).

**Fill time is unrealistically long**
Check that at least one gating component is ticked. Without gating the fallback
formula (`max(3 s, volume / 80 cm³/s)`) is used.

**CuPy installed but not active**
Confirm it loads independently: `python -c "import cupy; print(cupy.__version__)"`.
A driver/wheel version mismatch causes a silent fallback to NumPy.
