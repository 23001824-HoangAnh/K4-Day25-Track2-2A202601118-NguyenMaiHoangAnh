"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(
    baseline_usd: float,
    optimized_usd: float,
    levers: dict,
    sustainability: dict | None = None,
    period: str = "monthly",
    unit_economics: dict | None = None,
    sections: dict[str, list[str]] | None = None,
) -> str:
    """Return a Markdown cost-optimization report with optional analysis sections."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}  ",
        f"**Baseline spend:** ${baseline_usd:,.0f}  ",
        f"**Optimized spend:** ${optimized_usd:,.0f}  ",
        f"**Projected savings:** ${savings:,.0f}  (**{pct:.0f}%**)",
    ]
    if unit_economics:
        baseline_per_m = float(unit_economics.get("baseline_per_m", 0.0))
        optimized_per_m = float(unit_economics.get("optimized_per_m", 0.0))
        unit_pct = (1.0 - optimized_per_m / baseline_per_m) * 100 if baseline_per_m else 0.0
        lines += [
            "",
            "## Inference unit economics",
            "",
            "| Metric | Baseline | Optimized | Reduction |",
            "|---|---:|---:|---:|",
            f"| $/1M-token | ${baseline_per_m:.3f} | ${optimized_per_m:.3f} | {unit_pct:.1f}% |",
            f"| Daily inference cost | ${unit_economics.get('baseline_daily', 0):,.2f} | "
            f"${unit_economics.get('optimized_daily', 0):,.2f} | {unit_pct:.1f}% |",
        ]
    lines += [
        "",
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---:|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")
    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per representative query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query in us-east-1: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Electricity per query in us-east-1: ${sustainability.get('energy_cost_usd', 0):.6f}",
            f"- Cheapest+cleanest region: {sustainability.get('best_region', 'n/a')}",
            f"- Moving that query to the recommended region cuts carbon by "
            f"{sustainability.get('carbon_reduction_pct', 0):.1f}% and electricity cost by "
            f"{sustainability.get('energy_cost_reduction_pct', 0):.1f}%.",
        ]
    for title, body in (sections or {}).items():
        lines += ["", f"## {title}", ""]
        lines.extend(body)
    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str) -> str:
    """Write a simple savings bar chart PNG. Returns the path. No-op if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    names = list(levers.keys())
    vals = [levers[n] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, vals, color="#2e548a")
    ax.set_ylabel("Savings (USD / month)")
    ax.set_title("GPU cost savings by FinOps lever")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
