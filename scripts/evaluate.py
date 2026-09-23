"""Paired official mock benchmark and trace report."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import Agent
from agent_template import Agent as BaselineAgent
from local_eval import evaluate_agent
from mock_environment import make_mock_env
from reporting import render_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--out", default="reports/benchmark.json")
    args = parser.parse_args()
    rows = []
    for seed in args.seeds:
        ours = evaluate_agent(Agent(), seed=seed, verbose=False)
        baseline = evaluate_agent(BaselineAgent(), seed=seed, verbose=False)
        row = {"seed": seed, "net": float(ours["net_arpu_gain"]),
               "baseline_net": float(baseline["net_arpu_gain"]),
               "paired_difference": float(ours["net_arpu_gain"] - baseline["net_arpu_gain"]),
               "cost": float(ours["total_cost"]), "contacts": int(ours["total_contacts"]),
               "status": ours["status"], "final_campaigns": int(ours["n_campaigns"] - ours["n_pilots"]),
               "pilots": int(ours["n_pilots"]),
               "capped_campaigns": sum(any(d[key] for key in ("capped_at_campaign_limit", "capped_at_reach_budget", "capped_at_money_budget")) for d in ours["campaigns_detail"])}
        rows.append(row)
        print(f"seed {seed}: net={row['net']:.0f}, baseline={row['baseline_net']:.0f}, status={row['status']}")
    nets = sorted(r["net"] for r in rows)
    diffs = sorted(r["paired_difference"] for r in rows)
    def median(values):
        n = len(values)
        return (values[(n-1)//2] + values[n//2]) / 2
    result = {"mock_only": True, "rows": rows,
              "summary": {"median_net": median(nets), "median_paired_difference": median(diffs),
                          "minimum_net": min(nets), "negative_fraction": sum(v < 0 for v in nets)/len(nets),
                          "capped_campaigns": sum(r["capped_campaigns"] for r in rows)}}
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False))
    agent = Agent()
    env, _ = make_mock_env(seed=args.seeds[0], data_dir=str(ROOT / "data"), profile_path=str(ROOT / "customer_profile.csv"))
    campaigns = agent.act(env)
    report = render_report({"status": "degraded" if any(e["event"] in ("emergency", "history_unavailable") for e in agent.trace) else "completed",
                            "seed": args.seeds[0], "campaigns": campaigns, "trace": agent.trace,
                            "metrics": evaluate_agent(Agent(), seed=args.seeds[0], verbose=False),
                            "limitations": ["Mock effects differ from judging effects.", "Estimated final scores are not official realized net."]})
    path.with_suffix(".md").write_text(report)


if __name__ == "__main__":
    main()
