"""Headless Qt for the test suite (no display required)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
