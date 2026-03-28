"""

Sand Casting Simulation  v1.0.0

PyQt6 + PyVista + CuPy/NumPy + numpy-stl



Major architectural upgrades from v0.1.0:

- PyVista for GPU-accelerated OpenGL rendering with PBR materials

- Real-time lighting and shadows

- CuPy acceleration (with NumPy fallback) for CUDA-enabled RTX 3090

- Per-triangle temperature tracking

- Voxel-based heat diffusion simulation

- Visual effects: heat glow, particle system, animated metal flow,
  solidification front animation, defect markers, sand texture

"""



import sys

import math

import hashlib

import textwrap

import time
import random



# Try CuPy first, fall back to NumPy

try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    cp = None
    CUPY_AVAILABLE = False


import numpy as np

from stl import mesh as stl_mesh



from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QCheckBox,
    QTextEdit, QScrollArea, QProgressBar, QListWidget,
    QFileDialog, QInputDialog, QMessageBox, QSizePolicy,
    QFrame
)

from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QTimer

# Unconditional matplotlib import for Poly3DCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection



# PyVista imports (with matplotlib fallback)

try:
    import pyvista as pv
    PV_AVAILABLE = True
    from pyvista import Plotter, PolyData
except ImportError:
    pv = None
    PV_AVAILABLE = False
    # Fallback to matplotlib
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure


from ui.collapsible import CollapsiblePanel

from constants import METAL_DEFAULTS, FLASK_SIZES, COPE_COLOR, DRAG_COLOR, \
    SPRUE_COLOR, RUNNER_COLOR, GATE_COLOR, RISER_COLOR, MODEL_COLORS



# ---------------------------------------------------------------------------

# Dark-theme QSS  (Catppuccin Mocha palette)

# ---------------------------------------------------------------------------



from ui.style import APP_STYLE





from simulation.worker import SimWorker



from viewport.viewport import Viewport3D

from ui.main_window import MainWindow






def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")


    app.setStyleSheet(APP_STYLE)


    win = MainWindow()
    win.show()


    original_resize = win.resizeEvent



    def new_resize(event):
        original_resize(event)
        try:
            win.viewport.fig.tight_layout()
            win.viewport.fig.canvas.draw_idle()
        except Exception:
            pass


    if not win.viewport.use_pyvista:
        win.resizeEvent = new_resize


    sys.exit(app.exec())




if __name__ == "__main__":
    main()