"""Render agent traces and official results without side effects."""
import json


def render_report(run: dict) -> str:
    metrics = run.get("metrics") or {}
    lines = ["# Tariff campaign run", "", f"Status: {run.get('status', 'unknown')}", f"Seed: {run.get('seed', 'unknown')}", "", "## Official metrics", ""]
    for key in ("net_arpu_gain", "gross_arpu_lift", "total_cost", "total_contacts", "n_pilots", "status"):
        lines.append(f"- {key}: {json.dumps(metrics.get(key), default=str)}")
    lines += ["", "## Final campaigns", ""]
    for campaign in run.get("campaigns") or []:
        lines.append(f"- {json.dumps(campaign, ensure_ascii=False, sort_keys=True)}")
    lines += ["", "## Trace", ""]
    for event in run.get("trace") or []:
        lines.append(f"- {json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)}")
    lines += ["", "## Limitations", ""]
    for item in run.get("limitations") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
