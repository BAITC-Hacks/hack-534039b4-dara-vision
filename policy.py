"""Candidate ordering from public data; pilot feedback remains the decision signal."""

import math
from pathlib import Path
import pandas as pd

from contracts import Candidate


def historical_priors(path=None):
    source = Path(path) if path else Path(__file__).resolve().parent / "data" / "change_tariff.csv"
    try:
        frame = pd.read_csv(source, usecols=["AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M", "tariff_plan_code_from", "tariff_plan_code_to"])
        frame = frame[pd.to_numeric(frame["AVG_ARPU_PREV_3M"], errors="coerce") >= 100].copy()
        frame["change"] = ((frame["AVG_ARPU_NEXT_3M"] - frame["AVG_ARPU_PREV_3M"]) / frame["AVG_ARPU_PREV_3M"]).clip(-1, 3)
        grouped = frame.groupby(["tariff_plan_code_from", "tariff_plan_code_to"])["change"].agg(["mean", "size"])
        totals = frame.groupby("tariff_plan_code_from").size()
        return {(src, dst): (float(row["mean"]), int(row["size"]) / int(totals[src]))
                for (src, dst), row in grouped.iterrows()}, None
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as error:
        return {}, f"History unavailable: {type(error).__name__}"


def build_candidates(cells, tariffs, channels, history):
    price = {str(row.tariff_plan_code): float(row.price_tariff) for row in tariffs.itertuples()}
    if not price or any(not math.isfinite(p) or p < 0 for p in price.values()):
        raise ValueError("Invalid tariffs")
    costs = {name: float(info["cost_per_contact"]) for name, info in channels.items()}
    if not costs or any(not math.isfinite(v) or v < 0 for v in costs.values()):
        raise ValueError("Invalid channels")
    median_price = max(float(pd.Series(price).median()), 1.0)
    output = []
    for cell in cells:
        current = cell.filters["filter_current_tariff"]
        if current not in price:
            raise ValueError(f"Unknown current tariff: {current}")
        for target in sorted(price):
            if target == current:
                continue
            hist_change, hist_frequency = history.get((current, target), (0.0, 0.0))
            price_signal = max(-0.5, min(0.7, (price[target] - price[current]) / median_price))
            # A weak prior for exploration only, not a causal lift estimate.
            prior_ratio = 0.04 * price_signal + 0.04 * max(-1, min(1, hist_change)) * min(1, 4 * hist_frequency)
            for channel in sorted(costs):
                key = f"{cell.key}|target={target}|channel={channel}"
                prior_score = prior_ratio * cell.arpu_sum - cell.audience_count * costs[channel]
                output.append(Candidate(key, cell, target, channel, costs[channel], prior_score))
    return sorted(output, key=lambda c: (-c.prior_score, c.key))


def adjusted_ratios(observations, candidates):
    by_key = {}
    for obs in observations:
        total, count = by_key.get(obs.candidate_key, (0.0, 0))
        by_key[obs.candidate_key] = (total + obs.n_actual * obs.ratio, count + obs.n_actual)
    lookup = {c.key: c for c in candidates}
    return {key: (total / count) * (count / (count + 40)) - 0.025 * math.sqrt(100 / count)
            for key, (total, count) in by_key.items() if key in lookup}
