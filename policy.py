"""Candidate ordering from public data, followed by pilot based estimates."""

import math
import hashlib
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
                candidates.append(Candidate(key, cell, target, channel, cost, float(prior), multiplier))
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
    # Preserve the historical prefix, but never discard the remaining actions.
    keys = {c.key for c in selected}
    return selected + [c for c in candidates if c.key not in keys]


def adjusted_ratios(observations):
    """Shrink observed ratios toward zero; this is a heuristic, not a confidence bound."""
    totals = {}
    for item in observations:
        n, weighted = totals.get(item.candidate_key, (0, 0.0))
        totals[item.candidate_key] = (n + item.n_actual, weighted + item.ratio * item.n_actual)
    return {key: weighted / (n + 80) for key, (n, weighted) in totals.items()}


def next_candidate(order, observations, tried, resources, can_test):
    """Alternate exploitation, history-free exploration and decision-focused repeats.

    The noise scale is the approximate per-customer spread documented in the
    public case. It is a decision heuristic, not a hidden-model parameter.
    """
    ratios = adjusted_ratios(observations)
    counts = {}
    for item in observations:
        counts[item.candidate_key] = counts.get(item.candidate_key, 0) + item.n_actual
    tested = [c for c in order if c.key in ratios]
    cell_best = {}
    cell_visits = {}
    for candidate in tested:
        key = candidate.cell.key
        cell_best[key] = max(cell_best.get(key, 0.), campaign_score(candidate, ratios[candidate.key]))
        cell_visits[key] = cell_visits.get(key, 0) + 1
    pairs = {(c.cell.key, c.target_tariff) for c in tested if 0 < c.multiplier <= 1}
    fresh = [c for c in order if c.key not in tried and can_test(c)
             and not (0 < c.multiplier <= 1 and (c.cell.key, c.target_tariff) in pairs)
             and (c.multiplier <= 1 or (c.cell.key, c.target_tariff) in pairs)]
    # SMS usually offers more information per money spent than ads; the public
    # multiplier handles custom channel tables without channel-name rules.
    preferred = {}
    for c in fresh:
        if not 0 < c.multiplier <= 1:
            continue
        key = (c.cell.key, c.target_tariff)
        utility = c.multiplier ** 2 / (1 + c.cost_per_contact / 8)
        if key not in preferred or utility > preferred[key][0]:
            preferred[key] = utility, c
    ordered, seen = [], set()
    for c in fresh:
        if 0 < c.multiplier <= 1:
            c = preferred[(c.cell.key, c.target_tariff)][1]
        if c.key not in seen:
            ordered.append(c)
            seen.add(c.key)
    fresh = ordered

    # One in four decisions ignores migration history entirely. A stable hash
    # breaks ties across targets without privileging tariff codes or prices.
    if len(observations) % 4 == 3 and fresh:
        return max(fresh, key=lambda c: (
            c.cell.arpu_sum / (1 + cell_visits.get(c.cell.key, 0))
            - c.cell.audience_count * c.cost_per_contact,
            hashlib.sha256(c.key.encode()).hexdigest()))

    # Re-measure only decisions near the break-even / competing-action boundary.
    # Certain winners and certain losers do not automatically consume two pilots.
    repeats = []
    for c in tested:
        n = counts[c.key]
        if n >= 400 or not can_test(c):
            continue
        competitors = [campaign_score(t, ratios[t.key]) for t in tested
                       if t.cell.key == c.cell.key and t.key != c.key]
        boundary = max([0.] + competitors)
        score = campaign_score(c, ratios[c.key])
        sd = 0.8 * math.sqrt(n) / (n + 80) * c.cell.arpu_sum
        if sd <= 0:
            continue
        distance = abs(score - boundary) / sd
        # Expected loss from choosing the wrong side of this decision boundary.
        regret = sd * (math.exp(-distance * distance / 2) / math.sqrt(2 * math.pi)
                       - distance * 0.5 * math.erfc(distance / math.sqrt(2)))
        repeats.append((regret, c))
    if repeats and len(observations) >= 6:
        regret, candidate = max(repeats, key=lambda item: (item[0], item[1].key))
        opportunity = max((max(0., c.prior_score - cell_best.get(c.cell.key, 0.))
                           for c in fresh[:80]), default=0.)
        if regret > opportunity and regret > 0:
            return candidate

    # Prefer a new cell/action over a prior already beaten by its measured rival.
    for candidate in fresh:
        if candidate.prior_score > cell_best.get(candidate.cell.key, 0.):
            return candidate
    return fresh[0] if fresh else None


def measured_candidates(candidates, observations, risk_penalty=1.0):
    """Pool evidence only where public channel multipliers cannot saturate.

    For multipliers <= 1, the scorer gives ratio = effect * conversion * m.
    The inverse-variance weight of a normalized observation is n*m*m.
    Channels above 1 retain their own directly measured estimate.
    """
    lookup = {c.key: c for c in candidates}
    totals = {}
    def group(c):
        return (c.cell.key, c.target_tariff, None if 0 < c.multiplier <= 1 else c.channel)
    for obs in observations:
        c = lookup[obs.candidate_key]
        scale = c.multiplier if 0 < c.multiplier <= 1 else 1.
        key = group(c)
        info, weighted = totals.get(key, (0., 0.))
        totals[key] = info + obs.n_actual * scale * scale, weighted + obs.n_actual * scale * obs.ratio
    measured, ratios = [], {}
    for c in candidates:
        if group(c) not in totals:
            continue
        info, weighted = totals[group(c)]
        scale = c.multiplier if 0 < c.multiplier <= 1 else 1.
        # Zero-centred shrinkage plus an explicit noise penalty suppresses
        # false-positive rollouts after searching many noisy actions.
        ratios[c.key] = scale * (weighted - risk_penalty * 0.8 * math.sqrt(info)) / (info + 20)
        measured.append(c)
    return measured, ratios
