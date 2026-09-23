import pandas as pd
import pytest

from contracts import Candidate, Cell, ResourceSnapshot
from planning import build_cells, can_pilot, filter_mask, select_campaigns, validate_plan


def profile(n=20):
    return pd.DataFrame({"ID_NUMBER": range(n), "current_tariff": ["a"] * n,
                         "arpu_segment": ["HIGH"] * n, "data_segment": ["HEAVY"] * n,
                         "call_segment": ["HIGH"] * n, "predicted_arpu": [100.0] * n})


def test_cell_filters_round_trip_and_missing_excluded():
    df = profile()
    df.loc[0, "current_tariff"] = None
    cells = build_cells(df)
    assert len(cells) == 1
    assert cells[0].audience_count == int(filter_mask(df, cells[0].filters).sum()) == 19


def test_oversized_cell_splits_without_overlap():
    df = profile(6000)
    df.loc[3000:, "data_segment"] = "LITE"
    cells = build_cells(df)
    assert len(cells) == 2
    assert all(c.audience_count == 3000 for c in cells)
    assert all("filter_data_segment" in c.filters for c in cells)


@pytest.mark.parametrize("change", [lambda d: d.drop(columns=["ID_NUMBER"]),
                                      lambda d: d.assign(predicted_arpu=-1),
                                      lambda d: d.assign(ID_NUMBER=0)])
def test_malformed_profile_rejected(change):
    with pytest.raises(ValueError):
        build_cells(change(profile()))


def test_reserve_and_free_channel():
    cell = Cell("a", {"filter_current_tariff": "a", "filter_arpu_segment": "HIGH"}, 20, 2000)
    free = Candidate("free", cell, "b", "push", 0, 0)
    paid = Candidate("paid", cell, "b", "sms", 4, 0)
    assert can_pilot(free, 10, ResourceSnapshot(0, 30, 1), free)
    assert not can_pilot(paid, 10, ResourceSnapshot(100, 30, 1), free)
    assert not can_pilot(free, 10, ResourceSnapshot(0, 29, 1), free)


def test_all_negative_least_loss_and_validation():
    df = profile()
    cell = build_cells(df)[0]
    free = Candidate("free", cell, "b", "push", 0, 0)
    paid = Candidate("paid", cell, "b", "sms", 4, 0)
    resources = ResourceSnapshot(100, 20, 0)
    chosen = select_campaigns([free, paid], {"free": -0.1, "paid": -0.1}, resources)
    assert chosen == [free]
    tariffs = pd.DataFrame({"tariff_plan_code": ["a", "b"]})
    channels = {"push": {"cost_per_contact": 0}, "sms": {"cost_per_contact": 4}}
    validate_plan(chosen, df, tariffs, channels, resources)
    with pytest.raises(ValueError, match="overlapping"):
        validate_plan([free, paid], df, tariffs, channels, ResourceSnapshot(100, 40, 0))


def test_numeric_text_arpu_matches_numeric_without_mutation():
    numeric = profile()
    text = numeric.assign(predicted_arpu="100.0")
    assert build_cells(text) == build_cells(numeric)
    assert text["predicted_arpu"].eq("100.0").all()


@pytest.mark.parametrize("column", ["arpu_segment", "data_segment", "call_segment"])
@pytest.mark.parametrize("value", [1, 1.5])
def test_numeric_segment_categories_rejected(column, value):
    df = profile().assign(**{column: pd.Categorical([value] * 20)})
    with pytest.raises(ValueError, match=f"invalid {column}"):
        build_cells(df)


def test_oversized_cell_splits_by_call_with_exact_disjoint_filters():
    df = profile(6000)
    df.loc[3000:, "call_segment"] = "LOW"
    cells = build_cells(df)
    assert len(cells) == 2
    masks = [filter_mask(df, cell.filters) for cell in cells]
    assert all(cell.audience_count == int(mask.sum()) == 3000
               for cell, mask in zip(cells, masks))
    assert not (masks[0] & masks[1]).any()
    assert (masks[0] | masks[1]).all()
    assert all("filter_data_segment" in cell.filters and "filter_call_segment" in cell.filters
               for cell in cells)


def test_unsplittable_oversized_cell_is_excluded():
    assert build_cells(profile(5001)) == []


def test_final_gain_excludes_full_cell_pilot_coverage():
    from contracts import PilotObservation
    from planning import incremental_scores
    cell = Cell('cell', {}, 100, 100000)
    paid = Candidate('paid', cell, 'b', 'sms', 4, 0)
    observations = [PilotObservation('paid', 100, 400, .2)]
    assert incremental_scores([paid], {'paid': .2}, observations)['paid'] == -400


def test_partial_pilot_overlap_is_expected_not_added_twice():
    from contracts import PilotObservation
    from planning import incremental_scores
    cell = Cell('cell', {}, 100, 100000)
    candidate = Candidate('free', cell, 'b', 'push', 0, 0)
    observations = [PilotObservation('free', 50, 0, .2)] * 2
    # Independent half-cell pilots cover 75% in expectation; 25% remains.
    assert incremental_scores([candidate], {'free': .2}, observations)['free'] == pytest.approx(5000)


def test_pilot_with_stronger_channel_reduces_weaker_final_gain():
    from contracts import PilotObservation
    from planning import incremental_scores
    cell = Cell('cell', {}, 100, 100000)
    paid = Candidate('paid', cell, 'b', 'sms', 4, 0)
    free = Candidate('free', cell, 'b', 'push', 0, 0)
    scores = incremental_scores([paid, free], {'paid': .3, 'free': .2}, [PilotObservation('paid', 50, 200, .3)])
    assert scores['free'] == pytest.approx(10000)
    assert scores['paid'] == pytest.approx(14600)


def test_portfolio_avoids_greedy_contact_trap():
    large = Candidate('large', Cell('a', {}, 100, 1100), 'x', 'push', 0, 0)
    small1 = Candidate('small1', Cell('b', {}, 50, 700), 'x', 'push', 0, 0)
    small2 = Candidate('small2', Cell('c', {}, 50, 700), 'x', 'push', 0, 0)
    selected = select_campaigns([large, small1, small2], {c.key: 1 for c in [large, small1, small2]}, ResourceSnapshot(0, 100, 0))
    assert {c.key for c in selected} == {'small1', 'small2'}


def test_portfolio_matches_exhaustive_feasible_subsets():
    import itertools
    import random
    from planning import incremental_scores
    for seed in range(10):
        rng = random.Random(seed)
        candidates = [Candidate(str(i), Cell(str(i//2), {}, 10 + (i//2)*10, rng.uniform(100, 1000)),
                                str(i), 'sms', 4, 0) for i in range(8)]
        ratios = {c.key: rng.uniform(-.1, .9) for c in candidates}
        resources = ResourceSnapshot(350, 80, 0)
        scores = incremental_scores(candidates, ratios)
        feasible_values = []
        for n in range(1, len(candidates)+1):
            for subset in itertools.combinations(candidates, n):
                if (len({c.cell.key for c in subset}) == n
                        and sum(c.cell.audience_count for c in subset) <= resources.remaining_contacts
                        and sum(c.cell.audience_count*c.cost_per_contact for c in subset) <= resources.remaining_budget):
                    feasible_values.append(sum(scores[c.key] for c in subset))
        chosen = select_campaigns(candidates, ratios, resources)
        assert sum(scores[c.key] for c in chosen) == pytest.approx(max(feasible_values))


def test_exact_portfolio_obeys_money_and_ten_campaign_limit():
    candidates = [Candidate(str(i), Cell(str(i), {}, 10, 1000+i), 'x', 'sms', 4, 0) for i in range(20)]
    ratios = {c.key: 1. for c in candidates}
    for budget, count in [(100000, 10), (120, 3)]:
        selected = select_campaigns(candidates, ratios, ResourceSnapshot(budget, 15000, 0))
        assert len(selected) == count
        assert {c.key for c in selected} == {str(i) for i in range(20-count, 20)}
