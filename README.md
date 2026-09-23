# HackAlem tariff campaign agent

Offline Python agent for the Beeline Tariff Marketing Campaigns case. It builds representable, disjoint audience cells, ranks tariff/channel hypotheses using public data and optional migration history, runs sequential pilots, and selects feasible final campaigns from observed pilot feedback. Pilot and final contacts share the same resource limits.

## Setup and run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest
python local_eval.py --runs 10
python make_submission.py
sha256sum submission.csv
```

Runtime is offline after installation. `Agent.act(env)` is the entry point. `agent.trace` contains pilot requests, feedback, selection changes, and final selection. `python scripts/evaluate.py --seeds 0 1 2 3 4 5 6 7 8 9 --out reports/development.json` writes a paired benchmark and Markdown trace report. The bundled `agent_template.py` is the unchanged baseline.

## Limits and interpretation

The strategy returns 1–10 campaigns, each with 10–5,000 customers, and reserves resources for at least one final campaign before each pilot. It permits at most 20 pilot attempts and validates the final plan against remaining contacts and budget. If every tested plan has a negative estimated score, the least harmful feasible one is returned as a contest fallback; that does not authorize a real campaign.

The fixed-policy check on reserved mock seeds 100–119 had median net −65,419 and median paired improvement +518,094 against the bundled template, with zero capped campaigns. The positive-net target was **not met**. Per-seed results and interpretation are in [reports/quality.md](reports/quality.md).

Historical migrations are a weak ordering hint, not causal evidence. Pilot uncertainty uses a heuristic shrinkage and penalty, not a calibrated confidence interval. The local mock tests mechanics only; judging effects can differ. Official realized net comes from `local_eval.py`, not from the agent's estimated score. See [THIRD_PARTY.md](THIRD_PARTY.md) for source attribution.
