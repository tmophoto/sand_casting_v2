"""

Sand Casting Simulation  v1.0.0

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

from PyQt6.QtWidgets import QApplication
from ui.style import APP_STYLE
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
