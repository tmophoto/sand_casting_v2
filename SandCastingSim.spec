# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Sand Casting Simulator.

Run on Windows:
    pyinstaller SandCastingSim.spec

Output:
    dist\SandCastingSim\SandCastingSim.exe

The dist\SandCastingSim\ folder must stay together — the exe
depends on the DLLs alongside it. Zip the whole folder to share.
"""
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# ── Data files ────────────────────────────────────────────────────────────────
datas = [('README.md', '.')]

# matplotlib needs its mpl-data directory (fonts, style sheets, etc.)
datas += collect_data_files('matplotlib')
datas += collect_data_files('mpl_toolkits')

# ── Hidden imports PyInstaller may miss ───────────────────────────────────────
hiddenimports = [
    # matplotlib Qt6 backend (used when PyVista is absent)
    'matplotlib.backends.backend_qtagg',
    'matplotlib.backends.backend_qt',
    # 3-D axes used by the fallback renderer
    'mpl_toolkits.mplot3d',
    'mpl_toolkits.mplot3d.art3d',
    'mpl_toolkits.mplot3d.axes3d',
    'mpl_toolkits.mplot3d.proj3d',
    # numpy-stl
    'stl',
    'stl.mesh',
    # PyQt6 modules referenced at runtime
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtOpenGL',
    'PyQt6.QtOpenGLWidgets',
    'PyQt6.sip',
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['casting_sim.py'],
    pathex=['.'],           # project root on sys.path so sub-packages resolve
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude heavy optional deps — app falls back gracefully without them
    excludes=[
        'cupy', 'cupy_backends',
        'pyvista', 'pyvistaqt', 'vtk',
        'tests', 'pytest', '_pytest',
        'IPython', 'ipykernel',
        'tkinter',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── EXE (windowed — no console window on launch) ──────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],                     # binaries go into COLLECT below, not embedded here
    exclude_binaries=True,
    name='SandCastingSim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

# ── COLLECT — one-folder layout ───────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SandCastingSim',  # output: dist\SandCastingSim\
)
