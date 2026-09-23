"""Representable, disjoint audiences and exact campaign resource checks."""

import math

import pandas as pd

from contracts import Cell, ResourceSnapshot


SEGMENT_VALUES = {
    "arpu_segment": {"LOW", "MID", "HIGH"},
    "data_segment": {"NON_USER", "LITE", "HEAVY"},
    "call_segment": {"LOW", "MEDIUM", "HIGH"},
}


def filter_mask(profile, filters):
    mask = pd.Series(True, index=profile.index)
    for key, value in filters.items():
        if key == "filter_current_tariff":
            wanted = {part.strip() for part in str(value).split(";") if part.strip()}
            mask &= profile["current_tariff"].isin(wanted)
        elif key in ("filter_arpu_segment", "filter_data_segment", "filter_call_segment"):
            mask &= profile[key.removeprefix("filter_")].eq(value)
        else:
            raise ValueError(f"unsupported filter: {key}")
    return mask


def build_cells(profile):
    required = {"ID_NUMBER", "current_tariff", "arpu_segment", "data_segment", "call_segment", "predicted_arpu"}
    if not required.issubset(profile.columns):
        raise ValueError(f"missing profile columns: {sorted(required - set(profile.columns))}")
    if profile.empty or profile["ID_NUMBER"].isna().any() or profile["ID_NUMBER"].duplicated().any():
        raise ValueError("profile must have unique nonmissing IDs")
    arpu = pd.to_numeric(profile["predicted_arpu"], errors="coerce")
    if not arpu.map(math.isfinite).all() or (arpu < 0).any():
        raise ValueError("predicted_arpu must be finite and nonnegative")
    for col, allowed in SEGMENT_VALUES.items():
        if not profile[col].dropna().isin(allowed).all():
            raise ValueError(f"invalid {col}")
    cells = []

    def add_or_split(group, filters, depth):
        size = len(group)
        if size <= 5000:
            if size >= 10:
                key = "|".join(f"{k}={filters[k]}" for k in sorted(filters))
                cells.append(Cell(key, filters, size, float(group["predicted_arpu"].sum())))
            return
        if depth == 2:
            return
        col = ("data_segment", "call_segment")[depth]
        for value, child in group.dropna(subset=[col]).groupby(col, sort=True, observed=True):
            add_or_split(child, {**filters, "filter_" + col: str(value)}, depth + 1)

    for (tariff, segment), group in profile.dropna(subset=["current_tariff", "arpu_segment"]).groupby(
        ["current_tariff", "arpu_segment"], sort=True, observed=True
    ):
        add_or_split(group, {"filter_current_tariff": str(tariff), "filter_arpu_segment": str(segment)}, 0)
    return sorted(cells, key=lambda c: c.key)


def snapshot(env):
    budget = float(env.remaining_budget)
    contacts = int(env.remaining_contacts)
    pilots = int(env.pilots_left)
    if not math.isfinite(budget) or budget < -1e-6 or contacts < 0 or pilots < 0:
        raise ValueError("invalid resource snapshot")
    return ResourceSnapshot(budget, contacts, pilots)


def can_pilot(candidate, n, resources, reserved_candidate=None):
    if not (10 <= n <= 200 and n <= candidate.cell.audience_count and resources.pilots_left > 0):
        return False
    cost = n * candidate.cost_per_contact
    if resources.remaining_contacts < n or resources.remaining_budget + 1e-7 < cost:
        return False
    reserve = reserved_candidate or candidate
    for plan in (candidate, reserve):
        if (resources.remaining_contacts - n < plan.cell.audience_count or
                resources.remaining_budget - cost + 1e-7 < plan.cell.audience_count * plan.cost_per_contact):
            return False
    return True


def campaign_score(candidate, ratio):
    return ratio * candidate.cell.arpu_sum - candidate.cell.audience_count * candidate.cost_per_contact


def select_campaigns(candidates, estimated_ratios, resources):
    ranked = [(campaign_score(c, estimated_ratios[c.key]), c) for c in candidates if c.key in estimated_ratios]
    positives = sorted((item for item in ranked if item[0] > 0), key=lambda item: (-item[0], item[1].key))
    selected, used_cells = [], set()
    budget, contacts = resources.remaining_budget, resources.remaining_contacts
    for score, candidate in positives:
        if len(selected) >= 10:
            break
        if candidate.cell.key in used_cells or candidate.cell.audience_count > contacts:
            continue
        cost = candidate.cell.audience_count * candidate.cost_per_contact
        if cost > budget + 1e-7:
            continue
        selected.append(candidate)
        used_cells.add(candidate.cell.key)
        budget -= cost
        contacts -= candidate.cell.audience_count
    if selected:
        return selected
    feasible = [(score, c) for score, c in ranked if c.cell.audience_count <= resources.remaining_contacts
                and c.cell.audience_count * c.cost_per_contact <= resources.remaining_budget + 1e-7]
    return [min(feasible, key=lambda item: (-item[0], item[1].cell.audience_count, item[1].key))[1]] if feasible else []


def validate_plan(campaigns, profile, tariffs, channels, resources):
    if not 1 <= len(campaigns) <= 10:
        raise ValueError("plan must contain 1–10 campaigns")
    valid_tariffs = set(tariffs["tariff_plan_code"].dropna())
    seen = pd.Series(False, index=profile.index)
    budget, contacts = 0.0, 0
    for candidate in campaigns:
        if candidate.target_tariff not in valid_tariffs or candidate.channel not in channels:
            raise ValueError("unknown target or channel")
        if candidate.target_tariff in candidate.cell.filters["filter_current_tariff"].split(";"):
            raise ValueError("target equals current tariff")
        mask = filter_mask(profile, candidate.cell.filters)
        n = int(mask.sum())
        if n != candidate.cell.audience_count or n < 10 or n > 5000 or (seen & mask).any():
            raise ValueError("invalid or overlapping audience")
        seen |= mask
        cost = float(channels[candidate.channel]["cost_per_contact"])
        if not math.isfinite(cost) or cost < 0 or abs(cost - candidate.cost_per_contact) > 1e-7:
            raise ValueError("invalid channel cost")
        budget += n * cost
        contacts += n
    if budget > resources.remaining_budget + 1e-6 or contacts > resources.remaining_contacts:
        raise ValueError("plan exceeds resources")
