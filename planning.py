"""Representable audience cells and exact campaign resource accounting."""
import math

import pandas as pd

from contracts import Cell, Candidate, ResourceSnapshot, FILTER_FIELDS


def filter_mask(profile, filters):
    if not set(filters).issubset(FILTER_FIELDS):
        raise ValueError("unsupported filter")
    mask = pd.Series(True, index=profile.index)
    for field, value in filters.items():
        if field not in profile:
            raise ValueError(f"missing {field}")
        if field == "current_tariff":
            wanted = [s.strip() for s in str(value).split(";") if s.strip()]
            if not wanted:
                raise ValueError("empty tariff filter")
            mask &= profile[field].isin(wanted)
        else:
            mask &= profile[field].eq(value)
    return mask


def build_cells(profile):
    required = {"ID_NUMBER", "predicted_arpu", *FILTER_FIELDS}
    if not required.issubset(profile.columns) or profile.empty:
        raise ValueError("missing or empty profile")
    if profile["ID_NUMBER"].isna().any() or profile["ID_NUMBER"].duplicated().any():
        raise ValueError("customer IDs must be unique and present")
    arpu = pd.to_numeric(profile["predicted_arpu"], errors="coerce")
    if arpu.isna().any() or not arpu.map(math.isfinite).all() or (arpu < 0).any():
        raise ValueError("predicted_arpu must be finite and nonnegative")
    profile = profile.dropna(subset=["current_tariff", "arpu_segment"])
    cells = []

    def add(group, filters, remaining):
        n = len(group)
        if n > 5000 and remaining:
            field = remaining[0]
            for value, child in group.groupby(field, sort=True, observed=True):
                add(child, {**filters, field: str(value)}, remaining[1:])
            return
        if 10 <= n <= 5000:
            key = "|".join(f"{field}={filters[field]}" for field in FILTER_FIELDS if field in filters)
            cells.append(Cell(key, filters, n, float(arpu.loc[group.index].sum())))

    for (tariff, segment), group in profile.groupby(["current_tariff", "arpu_segment"], sort=True, observed=True):
        add(group, {"current_tariff": str(tariff), "arpu_segment": str(segment)},
            ("data_segment", "call_segment"))
    return sorted(cells, key=lambda c: c.key)


def snapshot(env):
    budget = float(env.remaining_budget)
    contacts = int(env.remaining_contacts)
    pilots = int(env.pilots_left)
    if not math.isfinite(budget) or budget < 0 or contacts < 0 or pilots < 0:
        raise ValueError("invalid resource counters")
    return ResourceSnapshot(budget, contacts, pilots)


def can_pilot(candidate, n, resources, reserved_candidate):
    if not isinstance(n, int) or not 10 <= n <= min(200, candidate.cell.audience_count):
        return False
    if resources.pilots_left <= 0:
        return False
    reserve = reserved_candidate or candidate
    if candidate.cost_per_contact < 0 or reserve.cost_per_contact < 0:
        return False
    return (resources.remaining_contacts >= n + reserve.cell.audience_count and
            resources.remaining_budget + 1e-8 >=
            n * candidate.cost_per_contact + reserve.cell.audience_count * reserve.cost_per_contact)


def candidate_score(candidate, estimated_ratio):
    return estimated_ratio * candidate.cell.arpu_sum - candidate.cell.audience_count * candidate.cost_per_contact


def select_campaigns(candidates, estimated_ratios, resources):
    rows = [(candidate_score(c, estimated_ratios[c.key]), c) for c in candidates
            if c.key in estimated_ratios and math.isfinite(estimated_ratios[c.key])]
    positive = sorted((r for r in rows if r[0] > 0), key=lambda x: (-x[0], x[1].key))
    chosen, used_cells = [], set()
    budget, contacts = resources.remaining_budget, resources.remaining_contacts
    for score, c in positive:
        if len(chosen) >= 10:
            break
        if c.cell.key in used_cells or c.cell.audience_count > contacts:
            continue
        cost = c.cell.audience_count * c.cost_per_contact
        if cost > budget + 1e-8:
            continue
        chosen.append(c)
        used_cells.add(c.cell.key)
        budget -= cost
        contacts -= c.cell.audience_count
    if chosen:
        return chosen
    for _, c in sorted(rows, key=lambda x: (-x[0], x[1].cell.audience_count, x[1].key)):
        if c.cell.audience_count <= contacts and c.cell.audience_count * c.cost_per_contact <= budget + 1e-8:
            return [c]
    return []


def campaign_dict(candidate, index):
    f = candidate.cell.filters
    return {"campaign_name": f"campaign_{index:02d}_{candidate.key.replace('|', '_').replace('=', '-')}",
            "filter_arpu_segment": f.get("arpu_segment"),
            "filter_data_segment": f.get("data_segment"),
            "filter_call_segment": f.get("call_segment"),
            "filter_current_tariff": f.get("current_tariff"),
            "target_tariff": candidate.target_tariff, "channel": candidate.channel}


def validate_plan(campaigns, profile, tariffs, channels, resources):
    if not 1 <= len(campaigns) <= 10:
        raise ValueError("plan must have 1–10 campaigns")
    tariff_set = set(tariffs["tariff_plan_code"])
    budget, contacts = 0.0, 0
    used = pd.Series(False, index=profile.index)
    names = set()
    for c in campaigns:
        if c["campaign_name"] in names or c["target_tariff"] not in tariff_set or c["channel"] not in channels:
            raise ValueError("duplicate name or unsupported target/channel")
        names.add(c["campaign_name"])
        filters = {field: c.get("filter_" + field) for field in FILTER_FIELDS
                   if c.get("filter_" + field) is not None}
        mask = filter_mask(profile, filters)
        count = int(mask.sum())
        if not 1 <= count <= 5000 or (used & mask).any():
            raise ValueError("empty, oversized or overlapping campaign")
        if "current_tariff" in filters and c["target_tariff"] in filters["current_tariff"].split(";"):
            raise ValueError("target equals current tariff")
        used |= mask
        price = float(channels[c["channel"]]["cost_per_contact"])
        if not math.isfinite(price) or price < 0:
            raise ValueError("invalid channel price")
        contacts += count
        budget += count * price
    if contacts > resources.remaining_contacts or budget > resources.remaining_budget + 1e-8:
        raise ValueError("resource limit exceeded")
