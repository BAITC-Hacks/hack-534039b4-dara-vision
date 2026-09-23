"""Candidate ordering from public data, followed by pilot based estimates."""

import math
from pathlib import Path

import pandas as pd

from contracts import Candidate
from planning import campaign_score


HISTORY_PATH = Path(__file__).resolve().parent / "data" / "change_tariff.csv"


def historical_hints(path=HISTORY_PATH):
    """Observational migration history provides ordering only, never measured lift."""
    try:
        df = pd.read_csv(path, usecols=["AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M",
                                        "tariff_plan_code_from", "tariff_plan_code_to"])
        before = pd.to_numeric(df["AVG_ARPU_PREV_3M"], errors="coerce")
        after = pd.to_numeric(df["AVG_ARPU_NEXT_3M"], errors="coerce")
        valid = before.ge(100) & before.map(math.isfinite) & after.map(math.isfinite) & after.ge(0)
        df = df.loc[valid].copy()
        df["segment"] = pd.cut(before.loc[valid], [-math.inf, 1000, 5000, math.inf], labels=["LOW", "MID", "HIGH"])
        df["change"] = ((after.loc[valid] - before.loc[valid]) / before.loc[valid]).clip(-1, 3)
        grouped = df.groupby(["tariff_plan_code_from", "segment", "tariff_plan_code_to"], observed=True).agg(
            change=("change", "median"), count=("change", "size")
        ).reset_index()
        totals = grouped.groupby(["tariff_plan_code_from", "segment"], observed=True)["count"].transform("sum")
        grouped["hint"] = grouped["change"] * grouped["count"] / totals * grouped["count"] / (grouped["count"] + 20)
        return {(r.tariff_plan_code_from, str(r.segment), r.tariff_plan_code_to): float(r.hint)
                for r in grouped.itertuples()}, None
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        return {}, f"history unavailable: {type(exc).__name__}"


def make_candidates(cells, tariffs, channels, history):
    price = tariffs.set_index("tariff_plan_code")["price_tariff"].to_dict()
    median_price = max(float(tariffs["price_tariff"].median()), 1.0)
    candidates = []
    for cell in cells:
        current = cell.filters["filter_current_tariff"]
        segment = cell.filters["filter_arpu_segment"]
        for target in sorted(price):
            if target == current:
                continue
            delta = (float(price[target]) - float(price[current])) / median_price
            # A weak, capped fallback supplies ordering for unseen migrations.
            base = history.get((current, segment, target), 0.015 * max(-1.0, min(1.0, delta)))
            for channel in sorted(channels):
                detail = channels[channel]
                cost = float(detail["cost_per_contact"])
                multiplier = float(detail["conversion_multiplier"])
                if not math.isfinite(cost) or cost < 0 or not math.isfinite(multiplier) or multiplier < 0:
                    raise ValueError("invalid channel parameters")
                prior = base * multiplier * cell.arpu_sum - cost * cell.audience_count
                key = f"{cell.key}|target={target}|channel={channel}"
                candidates.append(Candidate(key, cell, target, channel, cost, float(prior)))
    return sorted(candidates, key=lambda c: (-c.prior_score, c.key))


def exploratory_order(candidates, limit=80):
    """Spread pilots across valuable cells, targets and channels."""
    selected = []
    per_cell, per_target, per_channel = {}, {}, {}
    for candidate in candidates:
        cell = candidate.cell.key
        if per_cell.get(cell, 0) >= 3 or per_target.get(candidate.target_tariff, 0) >= 5:
            continue
        if per_channel.get(candidate.channel, 0) >= max(3, limit // 2):
            continue
        selected.append(candidate)
        per_cell[cell] = per_cell.get(cell, 0) + 1
        per_target[candidate.target_tariff] = per_target.get(candidate.target_tariff, 0) + 1
        per_channel[candidate.channel] = per_channel.get(candidate.channel, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def adjusted_ratios(observations):
    """Shrink observed ratios toward zero; this is a heuristic, not a confidence bound."""
    totals = {}
    for item in observations:
        n, weighted = totals.get(item.candidate_key, (0, 0.0))
        totals[item.candidate_key] = (n + item.n_actual, weighted + item.ratio * item.n_actual)
    return {key: weighted / (n + 80) for key, (n, weighted) in totals.items()}


def next_candidate(order, observations, tried, resources, can_test):
    """Feedback changes the next pilot by changing which tested cell merits repetition."""
    ratios = adjusted_ratios(observations)
    tested = [c for c in order if c.key in ratios]
    best = max(tested, key=lambda c: (campaign_score(c, ratios[c.key]), c.key), default=None)
    if best is not None and sum(o.n_actual for o in observations if o.candidate_key == best.key) < 350:
        if can_test(best):
            return best
    for candidate in order:
        if candidate.key not in tried and can_test(candidate):
            return candidate
    return None
