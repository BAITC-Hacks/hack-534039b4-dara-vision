# Integration review — 2026-09-23

## Decision and branch comparison

Agent 3 is sole integrator on `hackalem/agent-3`. Reviewed all three handoffs,
shared decision/architecture/tasks, implementation modules, tests and reports;
compared branches with `git diff` and inspected sources with `git show`.

| Branch tip reviewed | Reserved median net | Decision |
|---|---:|---|
| Agent 1 `794c22bc7c692609e95703c6a863259e7e8b91b5` | 3,421,236 | Select policy, contracts, planning, tests and demo |
| Agent 2 `cef7e3f2f3b9231b98c4d95e1db16fa0e4d2a80a` | −65,419 | Port numeric-text ARPU aggregation fix |
| Agent 3 `6e047b19c4a1dc52771b3efa4287c6961f157371` | 1,201,925 | Retain official package provenance, reporting, full traces and acceptance tests |

Agent 1 uses segment-conditioned observational history for exploration,
feedback-dependent repeats, a 25% pilot spending ceiling and a tested campaign
reserve. Its policy has no fixed winning tariff or hidden-state access. It has
stronger malformed-feedback checks and broader focused tests. Agent 2's numeric
aggregation fix avoids concatenating numeric strings after accepting them as
valid ARPU. Agent 3's reporting checks sanitizer drops and actual scorer caps;
Agent 1's original reporter incorrectly counted negative-profit `FAIL` as a
constraint violation. Original report JSON files remain in `reports/comparison/`.
Their violation fields must be interpreted under their original runner semantics.

Integration uses selective file restoration, not a whole-branch merge. Agent 1's
agent/policy/contracts remain unchanged; its planning module gains numeric
aggregation only. This resolves incompatible internal filter representations
by using Agent 1's `filter_*` keys consistently. Its validator accepts Candidate
objects before final dictionary serialization. No other worktree was edited.
No policy parameter tuning occurred. Prior reserved seeds informed selection,
so the integrated replay is a reproduction check, not a new untouched holdout.

## Independently verified sources

Retrieved 2026-09-23 by direct HTTPS after browser export failed:

- [Official Track 04 brief](https://docs.google.com/document/d/1bt_tgnIXnsnGMMjeaqbOY165MXmYQOTllRCDwcKySKI/export?format=txt): synthetic dataset; public pilot contract; 1–10 final campaigns, 5,000 per campaign, 15,000 contacts including pilots, budget 100,000, 20 pilots of 10–200; judging effects differ from mock.
- [Official participant ZIP](https://drive.google.com/uc?export=download&id=1cQUKtE_cm9TVXgzpcFwQYYUpmuFaJHHT): fresh SHA-256 `df1d955fb97816ff6de8ceb142ed589915d969f43f840a650dcdfbe12734f20b`; all 15 vendored files match the fresh archive and local provenance byte for byte.

The business pain is the sponsor's stated task, not independently measured
Beeline losses. No market, production ROI or external API feasibility claim is
made. Local execution establishes the offline interface feasibility. No UI is
in scope. The configured team Git remote is retained; organizer ownership was
not independently re-established during integration.

## Demo

After README setup, run `python local_eval.py`, then
`python scripts/evaluate.py --start 0 --stop 10 --out reports/development`.
Inspect `reports/development-trace.json` for pilot feedback and final selection.
Run `python make_submission.py` twice and `sha256sum submission.csv` after each.
Expected CSV SHA-256: `79450c91f9d1ab68e249a8ed0fa1ef6908b00df9f406b8108f38e4d7625669ad`.
Explain combined pilot/final resources and distinguish estimates from official
mock net. Do not present synthetic scores as hidden-judge predictions.

## Validation

Initial integrated suite: 15 passed; README checker passed. Final clean-environment
checks and replay results will be recorded after the integration code commit.
