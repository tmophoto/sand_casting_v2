# Sand Casting Simulator

A desktop tool for hobbyist and small-shop foundry work. Load an STL part,
pick a process (green/resin sand, ceramic shell, or binder-jet printed sand),
place gating, and run a physics-based simulation that estimates fill time,
solidification time, melt/sand tickets, and defect risk — all in a real-time
3D viewer.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Running the App](#running-the-app)
5. [Quick Start — One-Click Demo](#quick-start--one-click-demo)
6. [User Interface Walkthrough](#user-interface-walkthrough)
7. [Casting Processes](#casting-processes)
8. [Simulation Physics](#simulation-physics)
9. [Supported Metals](#supported-metals)
10. [Gating System Components](#gating-system-components)
11. [Shop Tools](#shop-tools)
12. [STL File Handling](#stl-file-handling)
13. [Rendering Backends](#rendering-backends)
14. [Adding a New Metal](#adding-a-new-metal)
15. [Adding a New Gating Component](#adding-a-new-gating-component)
16. [Running Tests](#running-tests)
17. [Running a Headless Sanity Check](#running-a-headless-sanity-check)
18. [Building a Standalone Executable](#building-a-standalone-executable)
19. [Project Structure](#project-structure)
20. [Known Limitations](#known-limitations)
21. [Troubleshooting](#troubleshooting)

---

## Features

- **One-click demo** — Motor Mount Bracket on the top bar, gating already placed
- **STL / OBJ import** — drag-and-drop, millimetre or inch units, degenerate-triangle
  cleanup, winding repair, QEM decimation to 25,000 triangles, and thin-wall detection
- **Three shop processes** — sand flask, ceramic shell (investment / lost-wax),
  binder-jet printed sand (no flask, no draft)
- **Shop recipes** — named templates (A356 green sand, A356 ceramic shell,
  A356 printed sand, bronze, gray iron) that set metal, process, and temps
- **Top-bar workflow** — Open part, Simulate pour, Save/Open `.cast.json` jobs,
  recents, Undo (Ctrl+Z), Export, Traveler PDF
- **Click-to-gate** — click a face to drop sprue, fan gate, riser, chill,
  foam filter, or a second gate
- **Rigging wizard** — sizes sprue, runner, gate, riser, neck, and pour basin
  for the current metal and part
- **Gating as a layout tool** — click a piece in 3D to edit it; snap to the part
  silhouette; 1:2:2 / 1:4:4 area-ratio presets; choke ring at the restrictive section
- **Extra tree parts** — pour basin, ceramic foam filter, second gate, blind
  riser + neck, insulating sleeve
- **Fill animation** — metal spreads from the gate (distance order), with a fill clock
- **Solidification animation** — freeze order follows local wall thickness (thin first)
- **Solid-fraction slider** — scrub 0–1 after a pour; feeding is treated as
  stopped at ~70 % solid
- **Result layers** — hot-spot thickness, last-to-freeze, fill order, porosity,
  Niyama proxy, X-ray (ghosted skin + interior voxels)
- **Cut plane** — clip the mesh along X/Y/Z
- **Coarse voxels** — ~48³ gravity flood, freeze ranking, isolated-liquid porosity
  (hot band = last 30 % after feeding stops at 70 % solid), Niyama proxy,
  chills, and sleeve (SOLIDCast-class, not CFD)
- **Physics simulation** (background thread):
  - Solidification time via Chvorinov's Rule (metal × mould type, including
    ceramic-shell thickness/preheat and printed-sand factor)
  - Fill time via Bernoulli hydraulics at the most-restrictive section
    (sprue exit, runner, gate(s), or foam filter)
  - Casting yield and melt mass including gating metal
  - Open/blind riser modulus vs hot-spot V/A, plus neck freeze-off
  - Defect risk: misrun, cold shut, burn-on (sand), low superheat, flask overflow,
    cold/thin ceramic shell, isolated-liquid porosity, mold erosion
- **Actionable results** — Likely OK / Risky / Will probably fail, with
  click-to-fly “what to change” links
- **Melt / pattern / sand-mix tickets** — ingots and furnace fit; shrink-compensated
  pattern STL (scale applied **once**, independent of the as-cast preview);
  lb sand + clay/water or resin; printed-sand print box + vents
- **Shop traveler PDF** — one page: viewport screenshot, verdict, tickets, fixes
- **Keep as A** — store a pour (text deltas + screenshot thumbnail) and compare
  a second setup
- **Foundry checks** — draft overlay, undercut/core-print overlay, auto flask fit
- **Pattern vs as-cast** — shrinkage scale with a toggle to preview the frozen part
- **GPU array acceleration** — CuPy replaces NumPy on CUDA GPUs; falls back to NumPy
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
2. Click **Try demo** on the top bar.
3. A Motor Mount Bracket appears with gating already placed (A356, 10×12 flask).
4. Click **Simulate pour**.
5. Watch fill, then solidification, then defect markers.
6. Review the results — the demo is tuned to trigger cold-shut and low-superheat
   warnings so you can see how defect detection works.

Optional next clicks:

- **Process → Printed sand** (or **Ceramic shell**) and simulate again
- **Size sprue, runner, gate, riser** to auto-rig the tree
- **Keep as A**, change a gate, simulate, and read the COMPARE block
- **Traveler PDF** for a one-page shop sheet
- **Foundry checks → Result layer → X-ray** after a pour, then scrub
  **Solid fraction**

The Motor Mount Bracket is a procedurally generated part with a wide thin base
plate, a thick central body, a cylindrical boss, two thin mounting ears, and two
web ribs — mixing section thicknesses to exercise the physics.

---

## User Interface Walkthrough

The window is divided into three columns plus a top chrome bar:

| Area | Contents |
|---|---|
| **Top bar** | Try demo, Open part, Simulate pour, Reset, Save/Open job, Export, Traveler PDF |
| **Left** | Collapsible setup panels (scrollable) |
| **Centre** | 3D viewport |
| **Right** | View presets, Keep as A / Clear A, results |

### 1 — Load a part

Drop an STL or OBJ on the window, click **Open part…**, or **Try demo**.
Set **Import units** (millimetres or inches) before opening a file.
Volume, surface area, and thin-wall notes appear in the **Part** panel.
Recent jobs and meshes are listed underneath.

### 2 — Pick a process

**Process** has three buttons: **Sand mold**, **Ceramic shell**, **Printed sand**.
**Shop recipe** applies a named metal + process + temperature template.

See [Casting Processes](#casting-processes).

### 3 — Place gating

Click **Sprue**, **Gate**, **Riser**, **Chill**, **Filter**, or **Gate 2**, then
click a face in the viewport. Or tick components and use **Size sprue, runner,
gate, riser**. Ratio presets (1:2:2 non-ferrous, 1:4:4 ferrous) and **Snap to
part** sit under the checkboxes. Click a drawn piece to show its dimension sliders.

### 4 — Metal and temperatures

- **Alloy** — A356, Everdur bronze, gray iron, ductile iron, 316 stainless
- **Sand type** — green, dry, or resin (sand process only)
- **Pour temp** — recommended band is shown under the spin box
- **Mold temp** / **Shell preheat** — sand/printed vs fired shell
- **Thin wall** — Auto / No / Yes (Auto uses local mesh thickness < 6 mm)

### 5 — Flask, shell, or print box

The **Flask** panel retitles itself:

| Process | Panel | Controls |
|---|---|---|
| Sand | Flask | Preset, custom, auto-fit, stack height |
| Ceramic shell | Ceramic shell | Fired thickness 4–16 mm (default 8 mm) |
| Printed sand | Print box | Wall 8–40 mm (default 15 mm) and a vent hint |

Parting-line plane is still the sprue/gate height on shell and printed sand
(there is no cope/drag split).

### 6 — Foundry checks and result layers

- Draft overlay (red = lock). Printed sand treats draft as optional.
- Undercut / core-print overlay
- Hot-spot overlay (thickness)
- **Result layer** after a sim: last-to-freeze, fill order, porosity,
  Niyama proxy, **X-ray (interior)**
- **Cut plane** along X/Y/Z
- **Solid fraction** slider (feeding stops ~70 %)

### 7 — Shrinkage and pattern STL

The shrinkage slider is a print scale (100–110 → ×1.00–1.10).
**Show as-cast** previews the frozen part without pattern oversize — it does
**not** change the exported file or the simulated cavity.

**Export pattern STL…** writes as-cast geometry × shrink **once** (lost-PLA /
3D-print patterns). The mould-cavity simulation always uses that same
pattern size, even when the viewport is showing as-cast.

The runner bar spans the part silhouette (plus a short over-run) so yield
metal matches what you see, not a fixed 160 mm stick.

### 8 — Run the simulation

**Simulate pour** runs in a background thread:

1. Geometry ratios
2. Chvorinov's Rule
3. Defect risk checks
4. Gating hydraulics
5. Voxel fill / freeze
6. Assembling results (tickets, verdict, fixes)

Results show KPIs (fill, solidify, yield), melt / sand-mix / pattern tickets,
COMPARE if A is stored, and clickable **What to change** lines.

### 9 — Compare and traveler

**Keep as A** stores the last result plus a viewport thumbnail. Change the
setup, simulate again, and the results panel lists A → B deltas.

**Traveler PDF** writes a one-page light-themed sheet: screenshot, verdict,
tickets, and what to change.

**Export** can still write HTML, PDF of the results, or a PNG screenshot.

---

## Casting Processes

| Process | Mould factor (cold) | Flask? | Draft? | Notes |
|---|---|---|---|---|
| Green sand | 1.00 | Yes | Yes | Clay + water mix ticket |
| Dry sand | 1.15 | Yes | Yes | Slower freeze than green |
| Resin / no-bake | 0.85 | Yes | Yes | Sand + resin binder ticket |
| Ceramic shell | 0.62 at 8 mm cold | No | Optional (wax die) | Preheat + thickness scale Chvorinov B |
| Printed sand | 0.90 | No | No | Print-box wall, vents, furan binder |

Typical fired-shell preheat: A356 ~1100 °F; bronze ~1600 °F; iron ~1800 °F;
316 stainless ~1900 °F.

Printed sand skips flask-too-small and burn-on warnings. Undercuts are fine
(the binder-jet has no pull). Add vents so air can leave the print box.

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
is `volume × density` (grams).

`mold_factor` is 1.00 green sand, 1.15 dry sand, 0.85 resin/no-bake, 0.90
printed sand. Ceramic shell starts at 0.62 for a cold 8 mm shell, then scales
with fired thickness and preheat (hot shells freeze slower).

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
| `h` | Sprue height plus cope height above the parting plane |
| `A_effective` | Area of the most restrictive element (mm²) |

**Restriction candidates** — the smallest area wins:

1. Tapered sprue → exit (bottom) area
2. Horizontal runner → width × height
3. Fan gate → hydraulic area (×2 if Second Gate is on)
4. Foam filter → face area × 0.35 (≈ 10 ppi open area)
5. No gating → fallback: `max(3.0 s, volume_cm³ / 80.0)`

Fill time is clamped to a minimum of 1.5 s. Gate velocity above 500 mm/s
(sand / printed) or 750 mm/s (shell) flags mold-erosion risk.

### Voxels (coarse fill / freeze)

After the 0-D checks, a ~48³ occupancy grid:

1. Rasterizes the STL (cavity / pattern size, not the as-cast preview)
2. Gravity-floods from the gate
3. Ranks freeze time as `B × (distance-to-mold)²`
4. Marks isolated liquid (no feeder path) as porosity — hot band is the
   last `1 − 0.70` of freeze time (`FEEDING_STOP_FRAC`)
5. Builds a Niyama proxy `t / (|∇t| + ε)`
6. Maps fields onto mesh faces and X-ray point clouds
7. Reports a local hot-spot modulus for the riser check (max of global V/A
   and voxel half-thickness)

Chills locally shorten freeze distance; an insulating sleeve lengthens it
around the riser. This is hobby-desktop SOLIDCast-class work, not MAGMA CFD.

Feeding is treated as stopped at solid fraction **0.70** (`FEEDING_STOP_FRAC`).

### Defect Detection

| Condition | Category | Flag |
|---|---|---|
| Superheat below the alloy minimum | Defect | Misrun risk |
| Thin wall AND pour temp < melt + 150 °F (sand / printed; relaxed on a hot shell) | Defect | Cold shut risk |
| Isolated-liquid fraction ≥ 5 % | Defect | Shrinkage porosity |
| Mould temp > 120 °F (sand only) | Warning | Burn-on |
| Superheat < 2× minimum | Warning | Low superheat |
| Flask smaller than the part envelope (sand only) | Warning | Flask too small |
| Cold or thin ceramic shell | Warning / defect | Preheat / breakthrough |
| Riser modulus < 1.2 × max(part V/A, voxel hot-spot) | Warning | Riser may freeze first |
| Blind / pinched riser neck | Warning | Neck freeze-off |
| Gravity flood never reaches a lobe | Warning | Misrun (unfilled) |

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
Vertical channel, wider at the basin and narrower at the runner. The taper
keeps the channel full and prevents air aspiration. Rendered in orange.

### Runner (Horizontal)
Rectangular channel at the parting line from the sprue base toward the gate.
Rendered in gold.

### Fan Gate
Flat gate at the parting line. Default hydraulic area is 40 mm². Rendered in green.

### Second Gate
A second fan-gate copy (click **Gate 2**). Doubles gate area in the hydraulics
and in gating metal volume.

### Foam Filter
Ceramic foam block on the runner. Open area is modelled as 35 % of face area
and can become the choke.

### Pour Basin
Cup on top of the sprue (wizard enables it). Adds basin metal to the melt ticket.

### Riser (Open) / Blind riser + neck
Cylindrical feeder above the parting line. **Blind riser** caps the top (extra
cooling face — size it larger). **Neck** is the short cylinder into the casting;
modulus uses the lateral surface only (ends sit on the riser and the hot spot).
**Insulating sleeve** slows freeze around the riser in the voxel pass.

### Chill
Click **Chill** then a thick section. Shortens local freeze distance.

---

## Shop Tools

| Tool | Where | What it does |
|---|---|---|
| Shop recipe | Process panel | Metal + process + temps in one click |
| Rigging wizard | Gating panel | Sizes the tree for a ~6 s fill and riser modulus ≥ 1.25 × V/A |
| Melt ticket | Results | Pour weight, ingot count, furnace fit, alloy $ |
| Sand mix ticket | Results | Flask sand + clay/water or resin; printed box + binder + vents; shell is slurry/stucco |
| Pattern ticket | Results + **Export pattern STL…** | Shrink scale for a 3D-printed pattern |
| Keep as A | Results column | Screenshot + numeric deltas vs the next pour |
| Traveler PDF | Top bar | One-page shop sheet |
| Session | Save job / Open job | `.cast.json` including process, printed wall, blind/neck |

Named recipes in `SHOP_RECIPES` (`constants.py`):

- A356 green sand
- A356 ceramic shell
- A356 printed sand
- Bronze green sand
- Bronze ceramic shell
- Gray iron sand

---

## STL File Handling

`Viewport3D.load_stl()` runs these clean-up passes on every imported file:

1. **Degenerate triangle removal** — strips triangles whose vertices contain
   NaN/Inf, or whose area is ≤ 1×10⁻¹⁰ mm².
2. **Deduplication** — removes triangles with identical centroids (rounded to
   6 decimal places).
3. **Winding repair** — inverts faces when signed volume is negative.
4. **Decimation** — Garland–Heckbert QEM to at most 25,000 triangles
   (grid clustering only if QEM cannot reach the budget).

Geometry statistics use a single vectorised NumPy pass:

- **Volume** — divergence theorem: `V = |Σ v₀·(v₁×v₂)| / 6`
- **Surface area** — `A = Σ ‖(v₁−v₀)×(v₂−v₀)‖ / 2`
- **Local thickness** — Auto thin-wall flag when min wall < 6 mm

Both volume and area assume a closed, consistently wound mesh. Clean your STL
with Meshmixer or PrusaSlicer before importing if you get unexpected values.

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

- Software-rendered `Poly3DCollection`
- Persistent collections — model geometry is not cleared between frames;
  only fill/particle overlays are removed per step
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
    "min_superheat_f": 100,
}
```

Optionally add matching entries to `METAL_PBR` (PyVista), `SHELL_PREHEAT_DEFAULT_F`,
and `ALLOY_USD_PER_LB`. Ferrous alloys should also be listed in `FERROUS_METALS`
so the wizard picks 1:4:4.

The metal appears in the **Alloy** drop-down automatically — the combo box is
filled from `METAL_DEFAULTS`.

---

## Adding a New Gating Component

1. Add the display name to the checkbox list in `MainWindow._build_gating_panel()`
   (`ui/main_window.py`).
2. Draw it in `Viewport3D._draw_gating()` (Matplotlib) and
   `Viewport3D._build_pv_gating_actors()` (PyVista).
3. If it affects flow area or metal volume, add a branch in
   `SimWorker._compute_fill_time_gating_hydraulics()` and
   `gating_volumes_cm3()` (`simulation/foundry.py`).
4. Expose dimensions in `Viewport3D.get_gating_params()`.
5. If it is click-to-place, add a pick mode in `Viewport3D.place_gating()`.

### Adding a shop recipe

Add a dict to `SHOP_RECIPES` in `constants.py` with `metal`, `process`
(`sand` / `shell` / `printed`), temps, and optional `shell_mm` / `printed_mm` /
`gating_ratio`. The Process combo box picks it up automatically.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest tests/
```

All tests are headless (no display required). `tests/conftest.py` sets
`QT_QPA_PLATFORM=offscreen`. Only `test_simulation.py` needs a QApplication
(created automatically in that file).

| Test file | Coverage | Count |
|---|---|---|
| `tests/test_simulation.py` | SimWorker physics | 44 |
| `tests/test_formatter.py` | Results HTML, traveler, tickets | 54 |
| `tests/test_geometry.py` | Mesh helpers and generators | 49 |
| `tests/test_foundry.py` | Yield, riser/neck, processes, session | 42 |
| `tests/test_shop.py` | Recipes, wizard, melt/pattern/sand-mix | 21 |
| `tests/test_voxels.py` | Occupancy, flood, freeze, porosity | 12 |

**222 tests** at last count.

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
    "mold_type":     "Green sand",
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
print(f"Process   : {result['process']}")
print(f"Sand mix  : {result['sand_mix']['hint']}")
print(f"Defects   : {result['defects'] or 'none'}")
```

Printed sand (no flask warning even if `flask_fit` fails):

```python
w = SimWorker({
    "metal": "A356 Aluminum", "vol_cm3": 200, "surf_cm2": 180,
    "mold_type": "Printed sand", "printed_mm": 15,
    "bbox_mm": (80, 60, 40),
})
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
├── constants.py                # Metals, moulds, recipes, colours
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── CLAUDE.md                   # Developer guide for coding agents
├── run.bat
├── build_exe.bat / build_gpu.bat
│
├── ui/
│   ├── style.py                # APP_STYLE QSS
│   ├── collapsible.py          # CollapsiblePanel
│   ├── main_window.py          # Layout, signals, sessions, traveler
│   └── demo_part.py            # Motor Mount Bracket mesh
│
├── simulation/
│   ├── worker.py               # SimWorker — Chvorinov, hydraulics, voxels
│   ├── foundry.py              # Yield, riser/neck, draft, flask, verdicts
│   ├── shop.py                 # Recipes, wizard, melt/sand/pattern tickets
│   ├── voxels.py               # Coarse fill / freeze / porosity / Niyama
│   ├── session.py              # .cast.json + recents
│   └── mesh_tools.py           # QEM, thickness, defect sites
│
├── viewport/
│   └── viewport.py             # Viewport3D — PyVista or matplotlib
│
├── results/
│   └── formatter.py            # Results HTML + shop traveler HTML
│
└── tests/
    ├── conftest.py             # QT_QPA_PLATFORM=offscreen
    ├── test_simulation.py
    ├── test_formatter.py
    ├── test_geometry.py
    ├── test_foundry.py
    ├── test_shop.py
    └── test_voxels.py
```

---

## Known Limitations

- **Closed meshes only** — volume and surface area assume a watertight,
  consistently oriented STL. Open or inverted meshes produce wrong geometry
  values.
- **QEM decimation** — Garland–Heckbert edge collapse to 25,000 triangles;
  grid clustering is only used if QEM cannot reach the budget.
- **Single parting line** — sand molds are a two-part cope/drag split.
  Ceramic shell and printed sand have no cope/drag; the plane is only
  sprue/gate height. Multi-part moulds and sand cores are not modelled.
- **Voxels are coarse** — ~48³ cells, gravity flood, no turbulence, no
  microstructure, no stress. Isolated-liquid porosity is a feeder-path
  proxy, not a shrink-cavity CFD result. This is not MAGMA, FLOW-3D, or a
  CNC CAM kernel (no G-code / 5-axis toolpaths).
- **Pattern scale is applied once** — export and the cavity sim use as-cast
  geometry × the shrink slider. The as-cast checkbox is display-only.
- **Isothermal fill assumption** — metal is treated as a single-temperature
  incompressible fluid. Partial solidification during fill is captured only by
  the rule-based cold-shut warning.
- **Sprue head** — hydraulic head is the visible basin height plus cope height
  (parting line up to the part top).
- **Flask height** — XY flask presets are inches in plan; stack height is a
  separate control (default 6 in). Printed sand uses a print-box wall instead.
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
formula (`max(3 s, volume / 80 cm³/s)`) is used. A small foam filter (35 % open)
can become the choke.

**Printed sand still warns about draft**
Draft overlay is optional on printed sand; the simulation does not scold for
lock faces. Use **Foundry checks → Draft overlay** only if you care about a
wax die / pattern, not the print box.

**CuPy installed but not active**
Confirm it loads independently: `python -c "import cupy; print(cupy.__version__)"`.
A driver/wheel version mismatch causes a silent fallback to NumPy.
