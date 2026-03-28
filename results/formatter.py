import textwrap


def build_results_text(r: dict) -> str:
    lines = []
    lines.append("=" * 46)
    lines.append("  SAND CASTING SIMULATION RESULTS")
    lines.append("=" * 46)
    lines.append(f"  Metal       : {r['metal']}")
    lines.append(f"  Pour temp   : {r['pour_f']:.0f} F")
    lines.append(f"  Mold temp   : {r['mold_f']:.0f} F")
    lines.append(f"  Superheat   : {r['superheat']:.1f} F")
    lines.append("-" * 46)
    lines.append(f"  Volume      : {r['vol_cm3']:.2f} cm3")
    lines.append(f"  Surface     : {r['surf_cm2']:.2f} cm2")
    lines.append(f"  V/S Ratio   : {r['vsr']:.4f} cm")
    lines.append("-" * 46)
    lines.append(f"  Fill time   : {r['fill_time_s']:.1f} s")
    lines.append(f"  Solidify    : {r['t_solidify_min']:.2f} min")
    lines.append("-" * 46)


    if r["defects"]:
        lines.append("  DEFECT RISKS:")
        for d in r["defects"]:
            for ln in textwrap.wrap(d, 42):
                lines.append(f"    - {ln}")
    else:
        lines.append("  No defect risks detected.")


    if r["warnings"]:
        lines.append("")
        lines.append("  WARNINGS:")
        for w in r["warnings"]:
            for ln in textwrap.wrap(w, 42):
                lines.append(f"    - {ln}")


    lines.append("=" * 46)
    return '\n'.join(lines)
