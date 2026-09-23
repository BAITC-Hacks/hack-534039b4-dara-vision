"""Pure Markdown rendering for local, official-mock evaluation results."""


def render_report(run: dict) -> str:
    rows = ["# Local evaluation", "", f"Status: **{run.get('status', 'unknown')}**", ""]
    rows += ["The measured net values below come from the official local scorer and its mock effects.",
             "They do not predict judging effects.", ""]
    if run.get("policy_commit"):
        rows += [f"Policy commit: `{run['policy_commit']}`", ""]
    rows += ["| Seed | Agent net | Baseline net | Paired difference | Cost | Contacts | Status |",
             "|---:|---:|---:|---:|---:|---:|---|"]
    for item in run.get("seeds", []):
        rows.append(f"| {item['seed']} | {item['net']:,.0f} | {item['baseline_net']:,.0f} | "
                    f"{item['difference']:,.0f} | {item['cost']:,.0f} | {item['contacts']:,} | {item['status']} |")
    rows += ["", f"Median agent net: **{run.get('median_net', float('nan')):,.0f}**",
             f"Median paired difference: **{run.get('median_difference', float('nan')):,.0f}**",
             f"Minimum agent net: **{run.get('minimum_net', float('nan')):,.0f}**",
             f"Negative share: **{run.get('negative_share', float('nan')):.1%}**",
             f"Violations: **{run.get('violations', 0)}**", ""]
    if run.get("trace"):
        rows += ["## One real trace", "", "```json", run["trace"], "```", ""]
    rows += ["## Limits", "", "History is observational and drawn from another population.",
             "Pilot ratio shrinkage is an uncalibrated heuristic. A positive mock score does not establish production ROI.", ""]
    return "\n".join(rows)
