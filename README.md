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
5. [User Interface Walkthrough](#user-interface-walkthrough)
6. [Simulation Physics](#simulation-physics)
7. [Supported Metals](#supported-metals)
8. [Gating System Components](#gating-system-components)
9. [STL File Handling](#stl-file-handling)
10. [Rendering Backends](#rendering-backends)
11. [Adding a New Metal](#adding-a-new-metal)
12. [Adding a New Gating Component](#adding-a-new-gating-component)
13. [Running a Headless Sanity Check](#running-a-headless-sanity-check)
14. [Building a Standalone Executable](#building-a-standalone-executable)
15. [Project Structure](#project-structure)
16. [Known Limitations](#known-limitations)
17. [Troubleshooting](#troubleshooting)

---

## Features

- **STL import** with automatic mesh cleanup — degenerate triangle removal,
  deduplication, and decimation to 25,000 triangles
- **Real-time 3D viewer** — GPU-accelerated via PyVista/OpenGL, or software
  fallback via Matplotlib
- **Multi-model scene** — load and position several STL parts simultaneously
- **Gating system** — place tapered sprue, horizontal runner, fan gate, and open
  riser; drag them interactively in the 3D viewport or use placement sliders
- **Fill animation** — animated metal pour with per-triangle heat colouring and
  a particle stream from the sprue
- **Solidification animation** — solidification front sweeps inward after fill
  completes
- **Physics simulation** (runs in a background thread so the UI stays responsive):
  - Solidification time via Chvorinov's Rule
  - Fill time via Bernoulli gating hydraulics using the most-restrictive
    cross-section
  - Defect risk detection: misrun, cold shut, burn-on, low superheat
- **Defect markers** — coloured spheres rendered at risk locations after simulation
- **Shrinkage compensation** — configurable scale factor per metal
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
| pyvista + pyvistaqt | GPU-accelerated OpenGL renderer (preferred backend) |
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

## User Interface Walkthrough

The window is divided into three panels:

| Panel | Contents |
|---|---|
| **Left** | Collapsible control panels |
| **Centre** | 3D viewport + view preset buttons |
| **Right** | Simulation results, Simulate and Reset buttons |

### 1 — Load an STL File

Click **Load STL…** in the *STL File* panel and choose any binary or ASCII `.stl`
file. The part appears in the 3D viewport immediately. Volume and surface area are
shown beneath the button. You can load multiple STL files; each becomes a
separately movable model.

### 2 — Set the Parting Line

The **Parting Line** slider sets where the mould splits, as a percentage of the
part's total height (5 %–95 %). The blue horizontal plane in the viewport updates
live. Faces above the parting line are shown in blue (cope half); faces below in
brown (drag half).

### 3 — Choose a Flask Size

Pick a standard flask from the **Flask Size** drop-down (6×6 through 14×20 inches)
or click **+ Custom** to enter an arbitrary width and height. The dashed outline in
the viewport reflects the selected flask.

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
- **Pour Temp** slider (1,000–2,500 °F) — override the metal's default pour
  temperature.
- **Mold Temp** slider (32–300 °F) — mould pre-heat temperature; values above
  120 °F trigger a burn-on warning.
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
gating components, and return all sliders to their defaults. Loaded STL models
are also cleared from the scene.

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
| `B` | Mould constant = `3.0 × metal.mold_constant` |
| `V` | Part volume (cm³) |
| `A` | Part surface area (cm²) |

The `mold_constant` scales B for different metal/mould heat-transfer
characteristics — 1.0 for aluminium, 1.4 for bronze in a dry-sand mould.

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

**Restriction priority** (smallest area wins):

1. Sprue + gate present → compare sprue exit vs gate area
2. Sprue + runner present → compare sprue exit vs runner area
3. Sprue only → use sprue exit area
4. Gate only → use gate area
5. No gating → fallback: `max(3.0 s, volume_cm³ / 80.0)`

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
- PBR materials with metallic and roughness values
- `pyvistaqt.BackgroundPlotter` embeds directly in the Qt window

### Matplotlib 3D (fallback)
Used when PyVista is unavailable.

- Software-rendered `Poly3DCollection` with per-face Phong shading
- Three-light rig (key, fill, rim) computed per frame
- Scroll-wheel zoom; click-drag to reposition models and gating
- `FigureCanvasQTAgg` embedded in a `QVBoxLayout`

---

## Adding a New Metal

Open `casting_sim.py` and add an entry to `METAL_DEFAULTS`:

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

The metal appears in the **Metal** drop-down automatically — `_build_ui()`
iterates over `METAL_DEFAULTS` to populate the combo box.

---

## Adding a New Gating Component

1. Add the display name string to `GATING_COMPONENTS` in `casting_sim.py`.
2. Add a rendering block inside `Viewport3D._draw_gating()` (Matplotlib path)
   and optionally inside `_render_pyvista()`.
3. If the component affects flow area, add a branch in
   `SimWorker._compute_fill_time_gating_hydraulics()`.
4. Expose its dimensions in `Viewport3D.get_gating_params()` so the worker
   receives the correct cross-section area.

---

## Running a Headless Sanity Check

Test the simulation worker without a display:

```python
from casting_sim import SimWorker, METAL_DEFAULTS

results = {}

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
w.finished.connect(lambda r: results.update(r))
w.run()

print(f"Fill time : {results['fill_time_s']:.1f} s  ({results['restrictive_elem']})")
print(f"Solidify  : {results['t_solidify_min']:.2f} min")
print(f"Defects   : {results['defects'] or 'none'}")
```

---

## Building a Standalone Executable

`build_exe.bat` (Windows) uses PyInstaller to produce a single-file executable:

```bat
build_exe.bat
```

Output: `dist/SandCastingSim.exe`. `README.md` is bundled alongside it.

To build manually or on Linux/macOS:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SandCastingSim casting_sim.py
```

---

## Project Structure

```
sand_casting_v2/
├── casting_sim.py          # Entire application (~2,500 lines)
├── requirements.txt        # Mandatory Python dependencies
├── README.md               # This file
├── CLAUDE.md               # Developer guide for Claude Code sessions
├── run.bat                 # Windows launcher (auto-installs deps)
├── build_exe.bat           # PyInstaller build script
│
└── legacy helper scripts (not needed to run the app)
    ├── fix_casting_sim.py
    ├── fix_duplicates.py
    ├── fix_orientation.py
    ├── part2.py / part3_partA.py / part3_partB.py
    └── temp_append.py / mainwindow_part1.py / test_append.py
```

### `casting_sim.py` Internal Structure

| Class / Function | Role |
|---|---|
| `CollapsiblePanel` | Reusable collapsible QFrame widget |
| `SimWorker` | QObject that runs all physics in a QThread |
| `Viewport3D` | 3D rendering, STL loading, animation, mouse interaction |
| `build_results_text()` | Formats the result dict into a plain-text report |
| `MainWindow` | Top-level window, UI layout, signal wiring, event handlers |
| `main()` | Entry point — creates QApplication and shows MainWindow |

---

## Known Limitations

- **Closed meshes only** — volume and surface area assume a watertight,
  consistently oriented STL. Open or inverted meshes produce wrong geometry
  values.
- **Uniform-stride decimation** — fine detail on complex meshes may be lost.
  No edge-collapse or QEM simplification is implemented.
- **Single parting line** — simple two-part cope/drag mould only. Multi-part
  moulds and sand cores are not modelled.
- **Isothermal fill assumption** — metal is treated as a single-temperature
  incompressible fluid. Partial solidification during fill is captured only by
  the rule-based cold-shut warning.
- **Fixed 100 mm sprue head** — the Bernoulli calculation uses a hard-coded
  sprue height. Adjust `sprue_height_mm` in `_compute_fill_time_gating_hydraulics`
  for very tall or short sprues.
- **PyVista drag interaction** — interactive click-drag of gating components is
  Matplotlib-only. In PyVista mode, use the Gating Placement sliders.

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
