"""Save / load casting sessions and a short recent-files list."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QSettings

SCHEMA_VERSION = 2
_ORG = "SandCastingSim"
_APP = "SandCastingSim"
_RECENT_KEY = "recent_projects"
_MAX_RECENT = 8


def default_session() -> dict:
    return {
        "version": SCHEMA_VERSION,
        "stl_path": None,
        "demo": False,
        "metal": "A356 Aluminum",
        "pour_temp_f": 1300,
        "mold_temp_f": 100,
        "mold_type": "Green sand",
        "shell_mm": 8,
        "thin_wall": "Auto",
        "parting_pct": 50,
        "flask": "8 x 10",
        "flask_height_in": 6,
        "gating": [],
        "sprue_top_r": 8,
        "sprue_bot_r": 4,
        "sprue_height": 100,
        "runner_width": 10,
        "runner_height": 8,
        "gate_area": 40,
        "sprue_x": 0,
        "sprue_y": 0,
        "riser_x": 0,
        "riser_y": 0,
        "model_x": 0,
        "model_y": 0,
        "model_z": 0,
        "model_rot": 0,
        "shrink_slider": 106,
        "gating_ratio": "1 : 2 : 2 (non-ferrous)",
    }


def save_session(path: str | Path, data: dict) -> None:
    payload = {**default_session(), **data, "version": SCHEMA_VERSION}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_session(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Session file is not a JSON object.")
    out = default_session()
    out.update(raw)
    out["version"] = SCHEMA_VERSION
    return out


def _settings() -> QSettings:
    return QSettings(_ORG, _APP)


def recent_projects() -> list[str]:
    vals = _settings().value(_RECENT_KEY, [], list)
    if isinstance(vals, str):
        vals = [vals] if vals else []
    return [p for p in vals if p]


def remember_project(path: str) -> list[str]:
    path = str(Path(path).resolve())
    items = [path] + [p for p in recent_projects() if p != path]
    items = items[:_MAX_RECENT]
    _settings().setValue(_RECENT_KEY, items)
    return items


def remember_stl(path: str) -> list[str]:
    return remember_project(path)
