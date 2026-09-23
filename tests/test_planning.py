import pandas as pd
import pytest

from contracts import Candidate, ResourceSnapshot
from planning import build_cells, filter_mask, can_pilot, select_campaigns, validate_plan


def profile(n=100):
    return pd.DataFrame({"ID_NUMBER": range(n), "current_tariff": ["t1"] * n,
                         "arpu_segment": ["HIGH"] * n, "data_segment": ["HEAVY"] * n,
                         "call_segment": ["LOW"] * n, "predicted_arpu": [100.0] * n})


def test_filter_roundtrip_and_free_push_reserve():
    p = profile()
    cell = build_cells(p)[0]
    assert len(p[filter_mask(p, cell.filters)]) == cell.audience_count == 100
    candidate = Candidate("k", cell, "t2", "push", 0, 0)
    assert can_pilot(candidate, 10, ResourceSnapshot(0, 110, 1), candidate)
    assert not can_pilot(candidate, 11, ResourceSnapshot(0, 110, 1), candidate)
    assert select_campaigns([candidate], {"k": -0.1}, ResourceSnapshot(0, 100, 0)) == [candidate]
    validate_plan([candidate], p, pd.DataFrame({"tariff_plan_code": ["t1", "t2"]}),
                  {"push": {"cost_per_contact": 0}}, ResourceSnapshot(0, 100, 0))
    with pytest.raises(ValueError, match="overlapping"):
        validate_plan([candidate, candidate], p, pd.DataFrame({"tariff_plan_code": ["t1", "t2"]}),
                      {"push": {"cost_per_contact": 0}}, ResourceSnapshot(0, 200, 0))


def test_oversized_split_and_bad_profile():
    p = profile(6000)
    p.loc[3000:, "data_segment"] = "LITE"
    cells = build_cells(p)
    assert len(cells) == 2
    assert sum(c.audience_count for c in cells) == 6000
    p.loc[0, "predicted_arpu"] = -1
    with pytest.raises(ValueError, match="predicted_arpu"):
        build_cells(p)


def test_numeric_text_arpu_is_summed_as_numbers():
    p = profile(10)
    p["predicted_arpu"] = ["100.0"] * 10
    assert build_cells(p)[0].arpu_sum == 1000.0
