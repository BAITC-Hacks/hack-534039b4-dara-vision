"""Run paired local mock evaluation and save a reproducible report."""

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import Agent
from agent_template import Agent as BaselineAgent
from local_eval import evaluate_agent
from reporting import render_report


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "development.md")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("count must be positive")
    rows = []
    trace = None
    for seed in range(args.start, args.start + args.count):
        agent = Agent()
        own = evaluate_agent(agent, seed=seed, verbose=False)
        baseline = evaluate_agent(BaselineAgent(), seed=seed, verbose=False)
        if own is None or baseline is None:
            raise RuntimeError(f"missing score at seed {seed}")
        if trace is None:
            trace = json.dumps(agent.trace[:8] + agent.trace[-5:], ensure_ascii=False, indent=2)
        rows.append({"seed": seed, "net": float(own["net_arpu_gain"]),
                     "baseline_net": float(baseline["net_arpu_gain"]),
                     "difference": float(own["net_arpu_gain"] - baseline["net_arpu_gain"]),
                     "cost": float(own["total_cost"]), "contacts": int(own["total_contacts"]),
                     "status": str(own["status"]), "pilots": int(own["n_pilots"])})
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    report = {"status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
              "policy_commit": commit, "seeds": rows,
              "median_net": statistics.median(row["net"] for row in rows),
              "median_difference": statistics.median(row["difference"] for row in rows),
              "minimum_net": min(row["net"] for row in rows),
              "negative_share": sum(row["net"] < 0 for row in rows) / len(rows),
              "violations": sum(row["status"] != "PASS" for row in rows), "trace": trace}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(report), encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {args.output}; median net {report['median_net']:,.0f}; median paired difference {report['median_difference']:,.0f}")


if __name__ == "__main__":
    main()
