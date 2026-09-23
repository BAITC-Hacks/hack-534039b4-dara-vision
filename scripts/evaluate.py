"""Run paired official local scoring and persist auditable results."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import Agent
from agent_template import Agent as TemplateAgent
from local_eval import evaluate_agent
from reporting import render_report
from scoring_core import sanitize_campaigns


class RecordingAgent:
    def __init__(self, agent):
        self.agent = agent
        self.campaigns = None

    def act(self, env):
        self.campaigns = self.agent.act(env)
        return self.campaigns


def run_one(agent, seed):
    wrapped = RecordingAgent(agent)
    output = io.StringIO()
    with redirect_stdout(output):
        result = evaluate_agent(wrapped, seed=seed, verbose=False)
    if result is None:
        return None, wrapped.campaigns, output.getvalue()
    return result, wrapped.campaigns, output.getvalue()


def violations(result, campaigns, stdout):
    errors = []
    if result is None or campaigns is None:
        return ["evaluation failed"]
    if not 1 <= len(campaigns) <= 10:
        errors.append("final campaign count")
    if len(sanitize_campaigns(campaigns, pd.read_csv("data/dict_tariff.csv"))) != len(campaigns):
        errors.append("sanitizer dropped final campaign")
    if "отброшена" in stdout:
        errors.append("evaluator dropped final campaign")
    if result["total_contacts"] > 15000 or result["total_cost"] > 100000:
        errors.append("combined resource cap")
    if not 1 <= result.get("n_pilots", 0) <= 20:
        errors.append("pilot count")
    for row in result["campaigns_detail"]:
        if any(row.get(k) for k in ("capped_at_campaign_limit", "capped_at_reach_budget", "capped_at_money_budget")):
            errors.append(f"scorer capped {row['name']}")
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--stop", type=int, default=10)
    p.add_argument("--out", default="reports/development")
    args = p.parse_args()
    if not 0 <= args.start < args.stop or args.stop - args.start > 100:
        p.error("invalid seed range")
    import os
    os.chdir(ROOT)  # The unmodified official evaluator resolves data relative to cwd.
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    rows = []
    trace = None
    failed = False
    for seed in range(args.start, args.stop):
        agent = Agent()
        result, campaigns, stdout = run_one(agent, seed)
        baseline, _, baseline_stdout = run_one(TemplateAgent(), seed)
        errors = violations(result, campaigns, stdout)
        if baseline is None:
            errors.append("baseline evaluation failed")
        failed = failed or bool(errors) or (result is not None and result.get("status") == "FAIL")
        row = {"seed": seed, "agent_net": result["net_arpu_gain"] if result else None,
               "template_net": baseline["net_arpu_gain"] if baseline else None,
               "cost": result["total_cost"] if result else None,
               "contacts": result["total_contacts"] if result else None,
               "pilots": result["n_pilots"] if result else None,
               "final_campaigns": len(campaigns) if campaigns is not None else None,
               "violations": errors}
        row["difference"] = (row["agent_net"] - row["template_net"]
                             if row["agent_net"] is not None and row["template_net"] is not None else None)
        rows.append(row)
        if trace is None:
            trace = {"seed": seed, "campaigns": campaigns, "trace": agent.trace,
                     "agent_stdout": stdout, "baseline_stdout": baseline_stdout}
        print(f"seed {seed}: net={row['agent_net']}, delta={row['difference']}, violations={errors}")
    report = {"status": "completed", "seed_range": f"{args.start}–{args.stop - 1}",
              "policy_commit": commit, "per_seed": rows,
              "limitations": ["Only local synthetic seeds were evaluated."]}
    prefix = Path(args.out)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    prefix.with_suffix(".md").write_text(render_report(report))
    prefix.with_name(prefix.name + "-trace.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
