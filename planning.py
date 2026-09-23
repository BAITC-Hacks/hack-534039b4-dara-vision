import math
import pandas as pd

from contracts import Cell, Candidate, ResourceSnapshot, FILTER_COLUMNS

PROFILE_COLUMNS = ("ID_NUMBER", "current_tariff", "arpu_segment", "data_segment", "call_segment", "predicted_arpu")
FILTER_TO_PROFILE = dict(zip(FILTER_COLUMNS, ("arpu_segment", "data_segment", "call_segment", "current_tariff")))


def filter_mask(profile, filters):
    mask = pd.Series(True, index=profile.index)
    for field, value in filters.items():
        if field not in FILTER_TO_PROFILE or not isinstance(value, str) or not value:
            raise ValueError(f"Unsupported filter: {field}")
        col = FILTER_TO_PROFILE[field]
        values = [v.strip() for v in value.split(";")] if field == "filter_current_tariff" else [value]
        mask &= profile[col].isin(values)
    return mask


def build_cells(profile):
    if not isinstance(profile, pd.DataFrame) or profile.empty or any(c not in profile for c in PROFILE_COLUMNS):
        raise ValueError("Missing or empty customer profile")
    if profile["ID_NUMBER"].isna().any() or profile["ID_NUMBER"].duplicated().any():
        raise ValueError("Customer IDs must be unique")
    arpu = pd.to_numeric(profile["predicted_arpu"], errors="coerce")
    if not arpu.map(math.isfinite).all() or (arpu < 0).any():
        raise ValueError("Invalid predicted_arpu")
    result = []

    def split(frame, filters, depth):
        if len(frame) <= 5000:
            if len(frame) >= 10:
                ordered = "|".join(f"{k}={filters[k]}" for k in FILTER_COLUMNS if k in filters)
                result.append(Cell(ordered, dict(filters), len(frame), float(frame["predicted_arpu"].sum())))
            return
        if depth >= 2:
            return
        col, key = (("data_segment", "filter_data_segment"), ("call_segment", "filter_call_segment"))[depth]
        for value, child in frame.groupby(col, sort=True, dropna=False):
            if pd.notna(value):
                split(child, {**filters, key: str(value)}, depth + 1)

    for (tariff, segment), frame in profile.groupby(["current_tariff", "arpu_segment"], sort=True):
        split(frame, {"filter_current_tariff": str(tariff), "filter_arpu_segment": str(segment)}, 0)
    return sorted(result, key=lambda c: c.key)


def snapshot(env):
    values = (float(env.remaining_budget), int(env.remaining_contacts), int(env.pilots_left))
    if not math.isfinite(values[0]) or any(v < 0 for v in values):
        raise ValueError("Invalid resource counters")
    return ResourceSnapshot(*values)


def can_pilot(candidate, n, resources, reserved_candidate=None):
    if not isinstance(n, int) or not 10 <= n <= min(200, candidate.cell.audience_count):
        return False
    if resources.pilots_left <= 0 or resources.remaining_contacts < n:
        return False
    if resources.remaining_budget + 1e-9 < n * candidate.cost_per_contact:
        return False
    reserve = reserved_candidate or candidate
    return (resources.remaining_contacts - n >= reserve.cell.audience_count and
            resources.remaining_budget - n * candidate.cost_per_contact + 1e-9 >=
            reserve.cell.audience_count * reserve.cost_per_contact)


def score(candidate, ratio):
    return float(ratio) * candidate.cell.arpu_sum - candidate.cell.audience_count * candidate.cost_per_contact


def select_campaigns(candidates, estimated_ratios, resources):
    feasible = [c for c in candidates if c.key in estimated_ratios and
                c.cell.audience_count <= resources.remaining_contacts and
                c.cell.audience_count * c.cost_per_contact <= resources.remaining_budget + 1e-9]
    feasible.sort(key=lambda c: (-score(c, estimated_ratios[c.key]), c.key))
    chosen = []
    used_cells = set()
    budget, contacts = resources.remaining_budget, resources.remaining_contacts
    for c in feasible:
        if score(c, estimated_ratios[c.key]) <= 0 or len(chosen) >= 10:
            break
        if c.cell.key in used_cells or contacts < c.cell.audience_count or budget + 1e-9 < c.cell.audience_count * c.cost_per_contact:
            continue
        chosen.append(c)
        used_cells.add(c.cell.key)
        contacts -= c.cell.audience_count
        budget -= c.cell.audience_count * c.cost_per_contact
    if chosen:
        return chosen
    return sorted(feasible, key=lambda c: (-score(c, estimated_ratios[c.key]), c.cell.audience_count, c.key))[:1]


def validate_plan(campaigns, profile, tariffs, channels, resources):
    if not 1 <= len(campaigns) <= 10:
        raise ValueError("Final campaign count must be 1–10")
    valid_tariffs = set(tariffs["tariff_plan_code"])
    seen = pd.Series(False, index=profile.index)
    contacts, cost = 0, 0.0
    for c in campaigns:
        if c.target_tariff not in valid_tariffs or c.channel not in channels:
            raise ValueError("Unknown target or channel")
        if c.cell.filters["filter_current_tariff"] == c.target_tariff:
            raise ValueError("Same source and target tariff")
        mask = filter_mask(profile, c.cell.filters)
        n = int(mask.sum())
        if n != c.cell.audience_count or not 10 <= n <= 5000 or bool((seen & mask).any()):
            raise ValueError("Empty, oversized, changed or overlapping segment")
        seen |= mask
        contacts += n
        cost += n * float(channels[c.channel]["cost_per_contact"])
    if contacts > resources.remaining_contacts or cost > resources.remaining_budget + 1e-9:
        raise ValueError("Final campaign exceeds remaining resources")
