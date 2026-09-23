"""Candidate ordering from public data, followed by feedback-based estimates."""
import math
from pathlib import Path

import pandas as pd

from contracts import Candidate, PilotObservation
from planning import candidate_score


def history_table(path=None):
    path = Path(path) if path else Path(__file__).resolve().parent / "data" / "change_tariff.csv"
    try:
        h = pd.read_csv(path)
        needed = {"tariff_plan_code_from", "tariff_plan_code_to", "AVG_ARPU_PREV_3M", "AVG_ARPU_NEXT_3M"}
        if not needed.issubset(h):
            return {}, "history columns unavailable"
        h = h[list(needed)].copy()
        h["AVG_ARPU_PREV_3M"] = pd.to_numeric(h["AVG_ARPU_PREV_3M"], errors="coerce")
        h["AVG_ARPU_NEXT_3M"] = pd.to_numeric(h["AVG_ARPU_NEXT_3M"], errors="coerce")
        h = h[h["AVG_ARPU_PREV_3M"] >= 100].copy()
        h["ratio"] = ((h["AVG_ARPU_NEXT_3M"] - h["AVG_ARPU_PREV_3M"]) / h["AVG_ARPU_PREV_3M"]).clip(-1, 3)
        h = h[h["ratio"].map(math.isfinite)]
        grouped = h.groupby(["tariff_plan_code_from", "tariff_plan_code_to"], observed=True)["ratio"].agg(["mean", "size"])
        return {(str(a), str(b)): (float(row["mean"]), int(row["size"]))
                for (a, b), row in grouped.iterrows()}, None
    except (OSError, ValueError, KeyError) as exc:
        return {}, f"history unavailable: {type(exc).__name__}"


def make_candidates(cells, tariffs, channels, history):
    prices = tariffs.set_index("tariff_plan_code")["price_tariff"].to_dict()
    if not prices:
        raise ValueError("no tariffs")
    median_price = max(float(pd.Series(prices).median()), 1.0)
    candidates = []
    for cell in cells:
        current = cell.filters["current_tariff"]
        if current not in prices:
            raise ValueError("profile tariff missing in tariff dictionary")
        for target, target_price in sorted(prices.items()):
            if target == current:
                continue
            delta = (float(target_price) - float(prices[current])) / median_price
            hist_ratio, n_hist = history.get((current, target), (0.0, 0))
            # Historical migrations are observational. Shrink their order-only hint.
            hint = (n_hist / (n_hist + 80.0)) * max(-0.5, min(0.5, hist_ratio))
            heuristic = 0.08 * max(-1.0, min(1.0, delta)) + 0.18 * hint
            for channel, spec in sorted(channels.items()):
                price = float(spec["cost_per_contact"])
                if not math.isfinite(price) or price < 0:
                    raise ValueError("invalid channel price")
                if price * cell.audience_count > 100_000:
                    continue
                key = f"{cell.key}|target={target}|channel={channel}"
                prior = heuristic * cell.arpu_sum - cell.audience_count * price
                candidates.append(Candidate(key, cell, str(target), str(channel), price, prior))
    return sorted(candidates, key=lambda c: (-c.prior_score, c.key))


def estimate_ratios(observations, candidates):
    lookup = {c.key: c for c in candidates}
    totals = {}
    for o in observations:
        weighted, n = totals.get(o.candidate_key, (0.0, 0))
        totals[o.candidate_key] = (weighted + o.ratio * o.n_actual, n + o.n_actual)
    estimates = {}
    for key, (weighted, n) in totals.items():
        c = lookup[key]
        # Weak zero-centred shrinkage and a support penalty; neither is a CI.
        mean = weighted / (n + 40.0)
        estimates[key] = mean - 0.035 * math.sqrt(100.0 / max(n, 1))
    return estimates


def next_exploration(candidates, tested_keys, resources, reserved, can_pilot):
    tested_cells = {c.cell.key for c in candidates if c.key in tested_keys}
    tested_targets = {c.target_tariff for c in candidates if c.key in tested_keys}
    tested_channels = {c.channel for c in candidates if c.key in tested_keys}
    eligible = []
    for c in candidates:
        if c.key in tested_keys or c.cell.key in tested_cells:
            continue
        n = min(100, c.cell.audience_count)
        if can_pilot(c, n, resources, reserved):
            eligible.append((c, n))
    if len(tested_keys) >= 6:
        alternative = [item for item in eligible if item[0].channel not in tested_channels]
        if alternative:
            return alternative[0]
    if len(tested_keys) >= 3:
        alternative = [item for item in eligible if item[0].target_tariff not in tested_targets]
        if alternative:
            return alternative[0]
    if eligible:
        return eligible[0]
    for c in candidates:
        if c.key not in tested_keys:
            n = min(100, c.cell.audience_count)
            if can_pilot(c, n, resources, reserved):
                return c, n
    return None


def next_repeat(candidates, observations, resources, reserved, can_pilot):
    estimates = estimate_ratios(observations, candidates)
    options = [c for c in candidates if c.key in estimates]
    options.sort(key=lambda c: (-candidate_score(c, estimates[c.key]), c.key))
    counts = {c.key: 0 for c in options}
    for obs in observations:
        counts[obs.candidate_key] += 1
    for c in options:
        n = min(200, c.cell.audience_count)
        if counts[c.key] < 2 and can_pilot(c, n, resources, reserved):
            return c, n
    return None
