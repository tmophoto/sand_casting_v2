"""Format simulation result dict → HTML string for QTextEdit / QTextBrowser."""
import html
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

_VERDICT = {
    "ok":   ("Likely OK", _C["ok"], "#1e3a2f"),
    "risky": ("Risky", _C["warn"], "#3a2e1e"),
    "fail": ("Will probably fail", _C["defect"], "#3a1e28"),
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


def _verdict_banner(r: dict) -> str:
    key = r.get("verdict") or ("fail" if r.get("defects") else ("risky" if r.get("warnings") else "ok"))
    title, fg, bg = _VERDICT.get(key, _VERDICT["risky"])
    return (
        f'<tr><td colspan="2" style="background:{bg};color:{fg};font-weight:bold;'
        f'padding:10px 8px;border-radius:8px;font-size:14px;">{html.escape(title)}</td></tr>'
    )


def _kpi_row(r: dict) -> str:
    y = r.get("yield_pct")
    y_str = f"{y:.0f}%" if y is not None else "—"
    fill = r.get("fill_time_s")
    sol = r.get("t_solidify_min")
    cells = [
        ("Fill", f"{fill:.1f} s" if fill is not None else "—"),
        ("Solidify", f"{sol:.2f} min" if sol is not None else "—"),
        ("Yield", y_str),
    ]
    inner = "".join(
        f'<td style="width:33%;text-align:center;padding:8px 4px;background:#1E1E2E;border-radius:8px;">'
        f'<div style="color:{_C["dim"]};font-size:10px;letter-spacing:0.4px;">{lab}</div>'
        f'<div style="color:{_C["value"]};font-size:14px;font-weight:700;padding-top:2px;">{val}</div>'
        f'</td>'
        for lab, val in cells
    )
    return f'<tr><td colspan="2" style="padding:6px 0;"><table style="width:100%;border-collapse:separate;border-spacing:6px 0;"><tr>{inner}</tr></table></td></tr>'


def empty_results_html() -> str:
    """Placeholder shown before the first pour."""
    return (
        f'<html><body style="background:{_C["bg"]};margin:16px;font-family:Segoe UI,sans-serif;">'
        f'<div style="color:{_C["heading"]};font-size:15px;font-weight:700;padding-bottom:8px;">Ready when you are</div>'
        f'<div style="color:{_C["label"]};font-size:12px;line-height:1.55;">'
        f'1. Drop a part (STL or OBJ) or try the demo<br>'
        f'2. Pick sand or ceramic shell<br>'
        f'3. Click a face to drop a sprue, or hit Size gating<br>'
        f'4. Hit <b style="color:{_C["value"]};">Simulate pour</b>'
        f'</div></body></html>'
    )


def build_results_text(r: dict) -> str:
    """Return an HTML string suitable for QTextBrowser.setHtml()."""
    vsr     = r.get("vsr", 0.0)
    defects = r.get("defects", [])
    warnings = r.get("warnings", [])
    fixes = r.get("fixes") or []

    vsr_label = _vsr_class(vsr)
    vsr_color = _C["warn"] if vsr_label == "Heavy" else (
        _C["ok"] if vsr_label == "Standard" else _C["value"]
    )

    vel = r.get("fill_velocity_mm_s", 0.0)
    vel_str = f"{vel:.0f} mm/s" if vel > 0 else "n/a (no gating)"

    fill_ok = r.get("fill_possible", True)
    fill_ok_str = "Yes" if fill_ok else "⚠ No — may freeze before full"
    fill_ok_color = _C["ok"] if fill_ok else _C["warn"]

    cr = r.get("cooling_rate", 0.0)
    cr_str = f"{cr:.0f} °F/min" if cr > 0 else "n/a"

    superheat = r.get("superheat", 0.0)
    min_sh = r.get("min_superheat_f", 50)
    sh_color = _C["defect"] if superheat < min_sh else (
        _C["warn"] if superheat < min_sh * 2 else _C["ok"]
    )

    rows = []
    rows.append(_verdict_banner(r))
    rows.append(_kpi_row(r))
    rows.append(_divider())

    rows.append(_section("INPUT"))
    rows.append(_row("Metal",     r.get("metal", "—")))
    mold_label = r.get("mold_type", "Green sand")
    if r.get("process") == "shell" and r.get("shell_mm"):
        mold_label = f"{mold_label} ({r['shell_mm']:.0f} mm)"
    rows.append(_row("Mold",      mold_label))
    rows.append(_row("Pour temp", f"{r.get('pour_f', 0):.0f} °F"))
    mold_temp_name = "Shell preheat" if r.get("process") == "shell" else "Mold temp"
    rows.append(_row(mold_temp_name, f"{r.get('mold_f', 0):.0f} °F"))
    rows.append(_row("Superheat", f"{superheat:.1f} °F", sh_color))
    rows.append(_divider())

    rows.append(_section("GEOMETRY"))
    rows.append(_row("Volume",   f"{r.get('vol_cm3', 0):.2f} cm³"))
    rows.append(_row("Surface",  f"{r.get('surf_cm2', 0):.2f} cm²"))
    mass_g = r.get("pour_mass_g")
    if mass_g is not None:
        rows.append(_row("Melt mass", f"{mass_g:.0f} g"))
    part_g = r.get("part_mass_g")
    if part_g is not None:
        rows.append(_row("Part mass", f"{part_g:.0f} g"))
    if r.get("gating_cm3") is not None:
        rows.append(_row("Gating vol", f"{r.get('gating_cm3', 0):.1f} cm³"))
    if r.get("yield_pct") is not None:
        y = r["yield_pct"]
        y_color = _C["ok"] if y >= 60 else (_C["warn"] if y >= 40 else _C["defect"])
        rows.append(_row("Casting yield", f"{y:.0f} %", y_color))
    rows.append(_row("V/S ratio", f"{vsr:.3f} cm  ({vsr_label})", vsr_color))
    rows.append(_divider())

    rows.append(_section("SIMULATION"))
    rows.append(_row("Fill time",    f"{r.get('fill_time_s', 0):.1f} s"))
    rows.append(_row("Fill vel",     vel_str))
    choke = r.get("restrictive_elem", "—")
    rows.append(_row("Choke",  choke))
    rows.append(_row("Fill OK?",     fill_ok_str, fill_ok_color))
    rows.append(_row("Solidify",     f"{r.get('t_solidify_min', 0):.2f} min"))
    rows.append(_row("Cooling",      cr_str))
    if r.get("porosity_frac") is not None:
        pf = float(r["porosity_frac"])
        pc = _C["defect"] if pf >= 0.05 else (_C["warn"] if pf >= 0.02 else _C["ok"])
        rows.append(_row("Unfed hot-spot", f"{100 * pf:.0f} % of volume", pc))
    if r.get("niyama_min") is not None:
        rows.append(_row("Niyama (min)", f"{r['niyama_min']:.2f}"))
    rows.append(_divider())

    mt = r.get("melt_ticket") or {}
    if mt:
        rows.append(_section("MELT TICKET"))
        rows.append(_row("Pour weight", f"{mt.get('pour_mass_lb', 0):.2f} lb  ({mt.get('pour_mass_g', 0):.0f} g)"))
        rows.append(_row("Ingots", f"{mt.get('n_ingots', 0)} × {mt.get('ingot_lb', 1):.1f} lb"))
        fits = mt.get("furnace_fits", True)
        rows.append(_row(
            "Furnace",
            f"{'Fits' if fits else 'TOO BIG for'} {mt.get('furnace_lb', 12):.0f} lb crucible",
            _C["ok"] if fits else _C["defect"],
        ))
        if mt.get("usd_per_lb"):
            rows.append(_row("Alloy $", f"${mt.get('alloy_usd', 0):.2f}  (${mt['usd_per_lb']:.2f}/lb)"))
        rows.append(_divider())

    pt = r.get("pattern_ticket") or {}
    if pt:
        rows.append(_section("PATTERN TICKET"))
        rows.append(_row("Catalog shrink", f"{pt.get('catalog_shrink_pct', 0):.1f} %"))
        rows.append(_row("Print this STL", f"×{pt.get('print_scale', 1):.3f}  ({pt.get('print_pct', 0):+.1f}%)"))
        rows.append(_divider())

    cmpd = r.get("compare") or {}
    if cmpd:
        rows.append(_section(f"COMPARE  {html.escape(str(cmpd.get('a_label', 'A')))} → {html.escape(str(cmpd.get('b_label', 'B')))}"))
        for key, label in (
            ("fill_time_s", "Fill"),
            ("t_solidify_min", "Solidify"),
            ("yield_pct", "Yield"),
            ("porosity_frac", "Unfed"),
        ):
            item = cmpd.get(key)
            if not item:
                continue
            d = item["d"]
            if key == "porosity_frac":
                txt = f"{100 * item['a']:.0f}% → {100 * item['b']:.0f}%  ({100 * d:+.0f} pt)"
            elif key == "yield_pct":
                txt = f"{item['a']:.0f}% → {item['b']:.0f}%  ({d:+.0f} pt)"
            elif key == "t_solidify_min":
                txt = f"{item['a']:.2f} → {item['b']:.2f} min  ({d:+.2f})"
            else:
                txt = f"{item['a']:.1f} → {item['b']:.1f} s  ({d:+.1f})"
            rows.append(_row(label, txt))
        rows.append(_divider())

    if fixes:
        rows.append(_section("WHAT TO CHANGE"))
        for item in fixes:
            kind = item.get("kind") or "other"
            body = item.get("fix") or item.get("text") or ""
            href = f"defect:{kind}"
            color = _C["defect"] if kind.endswith("risk") else _C["warn"]
            for line in textwrap.wrap(body, 44):
                safe = html.escape(line)
                rows.append(
                    f'<tr><td colspan="2" style="color:{color};padding:1px 4px 1px 12px;">'
                    f'• <a href="{href}" style="color:{color};text-decoration:underline;">{safe}</a>'
                    f'</td></tr>'
                )
            rows.append(
                f'<tr><td colspan="2" style="color:{_C["dim"]};padding:0 4px 4px 12px;font-size:10px;">'
                f'<a href="{href}" style="color:{_C["dim"]};">click to fly camera →</a></td></tr>'
            )
    elif defects:
        rows.append(_section("&#10007; DEFECT RISKS"))
        for d in defects:
            for line in textwrap.wrap(d, 44):
                rows.append(
                    f'<tr><td colspan="2" style="color:{_C["defect"]};padding:1px 4px 1px 12px;">'
                    f'• {html.escape(line)}</td></tr>'
                )
    else:
        rows.append(
            f'<tr><td colspan="2" style="color:{_C["ok"]};padding:2px 4px;">'
            f'&#10003; No defect risks detected.</td></tr>'
        )

    if warnings and not fixes:
        rows.append(_section("&#9888; WARNINGS"))
        for w in warnings:
            for line in textwrap.wrap(w, 44):
                rows.append(
                    f'<tr><td colspan="2" style="color:{_C["warn"]};padding:1px 4px 1px 12px;">'
                    f'• {html.escape(line)}</td></tr>'
                )

    table = (
        f'<table style="width:100%;border-collapse:collapse;font-family:Segoe UI,sans-serif;font-size:12px;">'
        + "".join(rows)
        + "</table>"
    )
    return f'<html><body style="background:{_C["bg"]};margin:4px;">{table}</body></html>'
