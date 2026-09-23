# Tariff campaign agent – HackAlem Track 04

An offline Python agent selects tariff marketing campaigns from the public customer profile, tariff dictionary and pilot feedback. It runs against the organizer's `Agent.act(env)` interface and creates `submission.csv` with the unmodified organizer generator. No network access or credentials are needed at runtime.

## Setup

Python 3.11+ is required. From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

The official participant package is included unchanged. Its download URL, ZIP SHA-256 and per-file hashes are in `provenance.json`; attribution is in `THIRD_PARTY.md`.

## Run and test

```bash
python -m pytest -q
python local_eval.py
python scripts/evaluate.py --start 0 --stop 10 --out reports/development
python make_submission.py
sha256sum submission.csv
python make_submission.py
sha256sum submission.csv
```

`python scripts/evaluate.py --start 100 --stop 120 --out reports/reserved` runs the one-time paired reserved benchmark. It writes per-seed JSON, a readable Markdown report and a trace from the first seed. The comparison uses the unmodified `agent_template.py` on the same seeds. The script uses the official `local_eval.evaluate_agent` and `scoring_core`; it checks caps and sanitizer drops separately. Do not tune against reserved results while describing them as holdout.

Frozen policy commit `6830b8f26acae2a870f0ef8bc8157a2599945f85` was tested once on seeds 100–119. The local synthetic median net was **1,201,924.62**, median paired improvement over the template **1,779,790.20**, minimum net **1,005,866.63**, negative runs **0/20**, and recorded violations **0**. See `reports/reserved.md` and `reports/reserved.json` for every seed. This meets the team's local quality threshold, with the transfer limitation below.

## Demo path

1. Run `python local_eval.py` to see pilots and official scoring.
2. Inspect `reports/reserved-trace.json` for `pilot_observed`, `selection_updated` and `final_selected` events, including remaining resources.
3. Run `python make_submission.py` twice and compare the two CSV hashes.
4. Open `reports/reserved.md` for paired quality and constraint results.

The committed `submission.csv` SHA-256 is `82894553332e20afea27c4cba0554a04ab457681968393edbc4622cf8bf68bbc`. The generator produces three final campaigns; the evaluator also counts pilot contacts when reporting campaign activity.

## How the agent works

`planning.py` partitions the public profile by current tariff and ARPU segment, splitting oversized cells by data and call segments. It validates filters, final overlap and combined pilot/final resources. `policy.py` uses a weak ordering hint from migration history, explores feasible target/channel pairs, and updates estimates after each pilot. `agent.py` reserves a feasible tested campaign before further pilots and validates the final plan. If every estimated score is negative, it returns the feasible tested option with the smallest estimated loss and records emergency mode in the trace. The trace contains no customer IDs.

Historical migrations are observational and come from another population. The score adjustment is a heuristic, not a confidence interval. The mock's effects are synthetic and differ from hidden judging effects; local gains do not establish real customer impact or production ROI. The agent does not send messages or trigger production campaigns. An emergency plan may lose money and must not be used for automatic live deployment.
