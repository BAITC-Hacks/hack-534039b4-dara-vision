"""Render measured official evaluator results without converting unknowns to zero."""
from statistics import median


def render_report(run):
    rows = run.get("per_seed", [])
    lines = ["# Paired local benchmark", "", f"Status: {run.get('status', 'unknown')}",
             f"Seeds: {run.get('seed_range', 'unknown')}",
             f"Policy commit: `{run.get('policy_commit', 'unknown')}`", "",
             "| Seed | Agent net | Template net | Difference | Cost | Contacts | Violations |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        def f(value):
            return "null" if value is None else f"{value:,.2f}"
        lines.append(f"| {r['seed']} | {f(r.get('agent_net'))} | {f(r.get('template_net'))} | "
                     f"{f(r.get('difference'))} | {f(r.get('cost'))} | "
                     f"{r.get('contacts', 'null')} | {', '.join(r.get('violations', [])) or 'none'} |")
    valid = [r for r in rows if r.get("agent_net") is not None and r.get("difference") is not None]
    lines += ["", "## Summary", ""]
    if valid:
        nets = [r["agent_net"] for r in valid]
        diffs = [r["difference"] for r in valid]
        lines += [f"Median agent net: {median(nets):,.2f}",
                  f"Median paired difference: {median(diffs):,.2f}",
                  f"Minimum agent net: {min(nets):,.2f}",
                  f"Loss share: {sum(x < 0 for x in nets)}/{len(nets)}", ""]
    lines += ["## Interpretation", "",
              "The evaluator uses synthetic mock effects. The report measures local behavior and does not establish production ROI or transfer to hidden effects.",
              "Pilot and final contacts are both counted by the official scorer. Caps in campaign detail are recorded as violations. Team predictions are heuristics, not calibrated confidence intervals.", ""]
    for limitation in run.get("limitations", []):
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"
