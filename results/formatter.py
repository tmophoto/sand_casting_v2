"""Format simulation result dict → HTML string for QTextEdit rich text display."""
import textwrap


# Catppuccin Mocha palette (matches APP_STYLE)
_C = {
    "bg":      "#181825",
    "border":  "#45475A",
    "heading": "#89B4FA",   # blue
    "label":   "#A6ADC8",   # subtext1
    "value":   "#CDD6F4",   # text
    "ok":      "#A6E3A1",   # green
    "warn":    "#FAB387",   # peach / orange
    "defect":  "#F38BA8",   # red
    "dim":     "#585B70",   # surface2
}

_LABELS = {
    "Thin":     (0.0,  0.5),
    "Standard": (0.5,  1.5),
    "Heavy":    (1.5,  999),
}


def _vsr_class(vsr: float) -> str:
    for name, (lo, hi) in _LABELS.items():
        if lo <= vsr < hi:
            return name
    return "Heavy"


def _row(label: str, value: str, color: str = None) -> str:
    vc = color or _C["value"]
    return (
        f'<tr>'
        f'<td style="color:{_C["label"]};padding:1px 8px 1px 4px;white-space:nowrap;">{label}</td>'
        f'<td style="color:{vc};padding:1px 4px;">{value}</td>'
        f'</tr>'
    )


def _divider() -> str:
    return f'<tr><td colspan="2"><hr style="border:none;border-top:1px solid {_C["border"]};margin:3px 0;"/></td></tr>'


def _section(title: str) -> str:
    return (
        f'<tr><td colspan="2" style="color:{_C["heading"]};font-weight:bold;'
        f'padding:4px 4px 1px 4px;">{title}</td></tr>'
    )


def build_results_text(r: dict) -> str:
    """Return an HTML string suitable for QTextEdit.setHtml()."""
    vsr     = r.get("vsr", 0.0)
    defects = r.get("defects", [])
    warnings = r.get("warnings", [])

    # VSR classification
    vsr_label = _vsr_class(vsr)
    vsr_color = _C["warn"] if vsr_label == "Heavy" else (
        _C["ok"] if vsr_label == "Standard" else _C["value"]
    )

    # Fill velocity
    vel = r.get("fill_velocity_mm_s", 0.0)
    vel_str = f"{vel:.0f} mm/s" if vel > 0 else "n/a (no gating)"

    # Fill sanity
    fill_ok = r.get("fill_possible", True)
    fill_ok_str = "Yes" if fill_ok else "⚠ No — may freeze before full"
    fill_ok_color = _C["ok"] if fill_ok else _C["warn"]

    # Cooling rate
    cr = r.get("cooling_rate", 0.0)
    cr_str = f"{cr:.0f} °F/min" if cr > 0 else "n/a"

    # Superheat color — use the metal's own minimum when present
    superheat = r.get("superheat", 0.0)
    min_sh = r.get("min_superheat_f", 50)
    sh_color = _C["defect"] if superheat < min_sh else (
        _C["warn"] if superheat < min_sh * 2 else _C["ok"]
    )

    rows = []
    rows.append(_section("INPUT"))
    rows.append(_row("Metal",     r.get("metal", "—")))
    rows.append(_row("Pour temp", f"{r.get('pour_f', 0):.0f} °F"))
    rows.append(_row("Mold temp", f"{r.get('mold_f', 0):.0f} °F"))
    rows.append(_row("Superheat", f"{superheat:.1f} °F", sh_color))
    rows.append(_divider())

    rows.append(_section("GEOMETRY"))
    rows.append(_row("Volume",   f"{r.get('vol_cm3', 0):.2f} cm³"))
    rows.append(_row("Surface",  f"{r.get('surf_cm2', 0):.2f} cm²"))
    mass_g = r.get("pour_mass_g")
    if mass_g is not None:
        rows.append(_row("Pour mass", f"{mass_g:.0f} g"))
    rows.append(_row("V/S ratio", f"{vsr:.3f} cm  ({vsr_label})", vsr_color))
    rows.append(_divider())

    rows.append(_section("SIMULATION"))
    rows.append(_row("Fill time",    f"{r.get('fill_time_s', 0):.1f} s"))
    rows.append(_row("Fill vel",     vel_str))
    rows.append(_row("Restrictive",  r.get("restrictive_elem", "—")))
    rows.append(_row("Fill OK?",     fill_ok_str, fill_ok_color))
    rows.append(_row("Solidify",     f"{r.get('t_solidify_min', 0):.2f} min"))
    rows.append(_row("Cooling",      cr_str))
    rows.append(_divider())

    if defects:
        rows.append(_section("&#10007; DEFECT RISKS"))
        for d in defects:
            for line in textwrap.wrap(d, 44):
                rows.append(
                    f'<tr><td colspan="2" style="color:{_C["defect"]};padding:1px 4px 1px 12px;">'
                    f'• {line}</td></tr>'
                )
    else:
        rows.append(
            f'<tr><td colspan="2" style="color:{_C["ok"]};padding:2px 4px;">'
            f'&#10003; No defect risks detected.</td></tr>'
        )

    if warnings:
        rows.append(_section("&#9888; WARNINGS"))
        for w in warnings:
            for line in textwrap.wrap(w, 44):
                rows.append(
                    f'<tr><td colspan="2" style="color:{_C["warn"]};padding:1px 4px 1px 12px;">'
                    f'• {line}</td></tr>'
                )

    table = (
        f'<table style="width:100%;border-collapse:collapse;font-family:Consolas,monospace;font-size:11px;">'
        + "".join(rows)
        + "</table>"
    )
    return f'<html><body style="background:{_C["bg"]};margin:4px;">{table}</body></html>'
