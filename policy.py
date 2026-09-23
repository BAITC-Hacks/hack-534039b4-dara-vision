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
    """Historical anchors first, with every remaining candidate still searchable."""
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
    selected_keys = {item.key for item in selected}
    return selected + [c for c in candidates if c.key not in selected_keys]


def adjusted_ratios(observations):
    """Shrink observed ratios toward zero; this is a heuristic, not a confidence bound."""
    totals = {}
    for item in observations:
        n, weighted = totals.get(item.candidate_key, (0, 0.0))
        totals[item.candidate_key] = (n + item.n_actual, weighted + item.ratio * item.n_actual)
    return {key: weighted / (n + 80) for key, (n, weighted) in totals.items()}


def conservative_ratios(observations):
    """A modest uncertainty charge for committing the whole audience.

    Charge up to 0.75 posterior standard deviations for small samples; retain
    that charge for all arms when the pooled observed effect is negative.
    This is a downside-risk heuristic, not a confidence interval after
    adaptive candidate selection.
    """
    means = adjusted_ratios(observations)
    counts = {}
    for item in observations:
        counts[item.candidate_key] = counts.get(item.candidate_key, 0) + item.n_actual
    total_n = sum(o.n_actual for o in observations)
    pooled_mean = sum(o.n_actual * o.ratio for o in observations) / max(total_n, 1)
    return {key: mean - .75 * (1. if pooled_mean < 0 else min(1., max(0., (200 - counts[key]) / 100)))
            * .804 / math.sqrt(counts[key] + 80) for key, mean in means.items()}


def pilot_sample_size(candidate, observations):
    measured = any(o.candidate_key == candidate.key for o in observations)
    size = 200 if len(observations) < 16 or measured else 100
    if candidate.cost_per_contact > 22:
        size = 50
    return min(size, candidate.cell.audience_count)


def _positive_normal(mean, std):
    """Expected positive part of a normal variable, in units of net gain."""
    if std <= 1e-12:
        return max(mean, 0.0)
    z = mean / std
    return std * math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) + mean * .5 * math.erfc(-z / math.sqrt(2))


def next_candidate(order, observations, tried, resources, can_test):
    """One-step value of information against each cell's incumbent.

    Noise scale comes from the public pilot contract. The normal approximation
    and weak zero-centred prior are decision heuristics, not coverage guarantees.
    Only directly piloted candidates can enter the final plan.
    """
    ratios = adjusted_ratios(observations)
    counts = {}
    for item in observations:
        counts[item.candidate_key] = counts.get(item.candidate_key, 0) + item.n_actual
    tested = [c for c in order if c.key in ratios]
    by_cell = {}
    for c in tested:
        by_cell.setdefault(c.cell.key, []).append((campaign_score(c, ratios[c.key]), c.key))
    # Establish measured anchors before distrust of observational history can
    # dominate allocation to large, otherwise uninformative audiences.
    if len(observations) < 16:
        best = max(tested, key=lambda c: (campaign_score(c, ratios[c.key]), c.key), default=None)
        if best is not None and counts[best.key] < 350 and can_test(best):
            return best
        for candidate in order:
            if candidate.key not in tried and can_test(candidate):
                return candidate
    # Learn a pessimistic location shift from repeated evidence, while retaining
    # uncertainty about transitions not represented in observational history.
    total_n = sum(o.n_actual for o in observations)
    pooled_mean = sum(o.n_actual * o.ratio for o in observations) / max(total_n, 1)
    pooled_se = .804 / math.sqrt(max(total_n, 1))
    negative_shift = min(0., pooled_mean + 2 * pooled_se)
    # Consistent negative feedback narrows the exploration distribution, but a
    # floor retains room for unseen improvements. Different channels/arms are
    # deliberately not treated as identical observations.
    arm_means = [sum(o.n_actual * o.ratio for o in observations if o.candidate_key == key) / count
                 for key, count in counts.items()]
    spread = sum((x - pooled_mean) ** 2 for x in arm_means) / max(len(arm_means), 1)
    noise = sum(.804 ** 2 / count for count in counts.values()) / max(len(counts), 1)
    prior_std = .804 / math.sqrt(80)
    if negative_shift < 0:
        prior_std = math.sqrt(max(.03 ** 2, spread - noise))

    if tested and max(campaign_score(c, ratios[c.key]) for c in tested) <= 0:
        # The contract requires one final campaign, even in a uniformly harmful
        # world. Measure a small free audience before accepting a large loss.
        fallback = min((c for c in order if c.cost_per_contact == 0 and can_test(c)),
                       key=lambda c: (c.cell.arpu_sum, -c.prior_score, c.key), default=None)
        if fallback is not None and fallback.key not in tried:
            return fallback
    best_choice, best_value = None, -math.inf
    for c in order:
        if not can_test(c):
            continue
        n = pilot_sample_size(c, observations)
        competitors = [score for score, key in by_cell.get(c.cell.key, []) if key != c.key]
        incumbent = max([0.] + competitors)
        if c.key in ratios:
            count = counts[c.key]
            if count >= 600:
                continue
            mean = campaign_score(c, ratios[c.key])
            variance = .804 ** 2 / (count + 80)
            # Spread of the updated posterior mean, not observation noise.
            std = c.cell.arpu_sum * math.sqrt(variance * n / (count + 80 + n))
            value = _positive_normal(mean - incumbent, std) - max(mean - incumbent, 0.)
        else:
            # History only weakly shifts the exploration prior, with a cap.
            gross_hint = (c.prior_score + c.cell.audience_count * c.cost_per_contact) / max(c.cell.arpu_sum, 1.)
            prior_ratio = max(-.12, min(.12, .25 * gross_hint)) + negative_shift
            mean = c.cell.arpu_sum * prior_ratio - c.cell.audience_count * c.cost_per_contact
            std = c.cell.arpu_sum * prior_std * math.sqrt(n / (80 + n))
            value = _positive_normal(mean - incumbent, std)
        # Every measurement uses real resources; repeated pilot contacts do not
        # create another full campaign's lift under scorer deduplication.
        expected_ratio = ratios[c.key] if c.key in ratios else prior_ratio
        value += min(0., expected_ratio) * c.cell.arpu_sum * n / c.cell.audience_count
        value -= n * c.cost_per_contact
        if value > best_value:
            best_choice, best_value = c, value
    return best_choice if best_value > 0 else None
