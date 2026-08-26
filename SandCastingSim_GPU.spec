# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Sand Casting Simulator — GPU / PyVista build.

Bundles PyVista + VTK for GPU-accelerated OpenGL rendering.
CuPy (CUDA array acceleration) is NOT bundled — install it separately
on the target machine and the app will detect it automatically:
    pip install cupy-cuda12x   (adjust to your CUDA version)

Run on Windows (with pyvista + pyvistaqt already installed):
    pip install pyvista pyvistaqt
    pyinstaller SandCastingSim_GPU.spec

Output:  dist\\SandCastingSim_GPU\\SandCastingSim.exe
Size:    ~400-700 MB (VTK DLLs are large)

The dist\\SandCastingSim_GPU\\ folder must stay together.
Zip the whole folder to share or deploy.
"""
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ── Data files ────────────────────────────────────────────────────────────────
datas = [('README.md', '.')]

datas += collect_data_files('matplotlib')
datas += collect_data_files('mpl_toolkits')

# PyVista and VTK ship data files (colormaps, shaders, etc.)
tmp = collect_all('pyvista');    datas += tmp[0]
tmp = collect_all('pyvistaqt'); datas += tmp[0]

# ── Binaries (VTK DLLs auto-collected via collect_all) ────────────────────────
binaries = []
tmp = collect_all('vtkmodules'); binaries += tmp[1]
tmp = collect_all('pyvista');    binaries += tmp[1]
tmp = collect_all('pyvistaqt'); binaries += tmp[1]

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = [
    # matplotlib Qt6 fallback backend
    'matplotlib.backends.backend_qtagg',
    'matplotlib.backends.backend_qt',
    'mpl_toolkits.mplot3d',
    'mpl_toolkits.mplot3d.art3d',
    'mpl_toolkits.mplot3d.axes3d',
    'mpl_toolkits.mplot3d.proj3d',
    # numpy-stl
    'stl',
    'stl.mesh',
    # PyQt6
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtOpenGL',
    'PyQt6.QtOpenGLWidgets',
    'PyQt6.QtPrintSupport',
    'PyQt6.sip',
    # PyVista / VTK — VTK uses lazy loading so submodules need explicit listing
    'pyvista',
    'pyvistaqt',
    'vtkmodules',
    'vtkmodules.all',
    'vtkmodules.qt.QVTKRenderWindowInteractor',
    'vtkmodules.util',
    'vtkmodules.util.numpy_support',
]

# Collect ALL vtkmodules submodule names (VTK lazy-loads everything)
tmp = collect_all('vtkmodules'); hiddenimports += tmp[2]
tmp = collect_all('pyvista');    hiddenimports += tmp[2]
tmp = collect_all('pyvistaqt'); hiddenimports += tmp[2]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['casting_sim.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # CuPy excluded — install separately to match your CUDA version
        'cupy', 'cupy_backends',
        # Never needed at runtime
        'tests', 'pytest', '_pytest',
        'IPython', 'ipykernel',
        'tkinter',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SandCastingSim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,      # UPX + VTK DLLs can corrupt — leave off for GPU build
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SandCastingSim_GPU',   # output: dist\\SandCastingSim_GPU\\
)
