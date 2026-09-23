# Fixed-policy quality check

Policy commit: `bfaab944b780bd91bfa68669cc7c7c1fd97b7154`. The policy and its parameters were committed before inspecting reserved seeds 100–119. Input ZIP SHA-256: `df1d955fb97816ff6de8ceb142ed589915d969f43f840a650dcdfbe12734f20b`. Versions: Python 3.14.7, pandas 2.3.3, NumPy 2.5.2. The baseline is the unchanged `agent_template.py`; both agents ran through the official local mock evaluator on the same seeds. Per-seed net, paired difference, cost, contacts, profit status, pilot count, final count, and cap count are in `holdout.json`.

| Set | Median net | Median paired difference | Minimum net | Negative share | Capped campaigns |
|---|---:|---:|---:|---:|---:|
| Development 0–9 | −25,406 | +360,509 | −259,386 | 70% | 0 |
| Reserved 100–119 | −65,419 | +518,094 | −287,014 | 55% | 0 |

**Quality hypothesis failed:** both median net values are negative, despite positive paired improvements. The official scorer's `FAIL` status means negative net; it does not itself indicate a limit violation. Cap counts were derived from the scorer's per-campaign cap flags. The CSV has three final campaigns on seed 42 and was regenerated twice with the same SHA-256 `d6889b66ac6f3049016ee826c5c05c28f2e43b678a9fd652460774604cb48fe7`.

This mock uses a synthetic effect model and cannot establish production or hidden-judge profitability. No changes to policy were made after viewing the reserved seeds. The implementation meets the technical demo contract but should not be described as a profitable campaign recommendation.
