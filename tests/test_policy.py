import pandas as pd
import pytest

from policy import historical_hints


@pytest.mark.parametrize("invalid", ["not-a-number", "", "NaN", "inf", "-inf"])
def test_history_coerces_arpu_and_excludes_invalid_rows(tmp_path, invalid):
    path = tmp_path / "history.csv"
    pd.DataFrame({
        "AVG_ARPU_PREV_3M": ["200", invalid, "200"],
        "AVG_ARPU_NEXT_3M": ["300", "300", invalid],
        "tariff_plan_code_from": ["a"] * 3,
        "tariff_plan_code_to": ["b"] * 3,
    }).to_csv(path, index=False)
    hints, reason = historical_hints(path)
    assert reason is None
    assert hints == {("a", "LOW", "b"): pytest.approx(0.5 / 21)}


def test_history_with_only_nonnumeric_arpu_is_empty(tmp_path):
    path = tmp_path / "history.csv"
    pd.DataFrame({
        "AVG_ARPU_PREV_3M": ["invalid"],
        "AVG_ARPU_NEXT_3M": ["invalid"],
        "tariff_plan_code_from": ["a"],
        "tariff_plan_code_to": ["b"],
    }).to_csv(path, index=False)
    assert historical_hints(path) == ({}, None)


def test_missing_history_returns_fallback_reason(tmp_path):
    hints, reason = historical_hints(tmp_path / "missing.csv")
    assert hints == {}
    assert reason == "history unavailable: FileNotFoundError"


def test_search_keeps_candidates_outside_historical_shortlist():
    from contracts import Candidate, Cell
    from policy import exploratory_order
    cell = Cell('same', {}, 100, 10000)
    candidates = [Candidate(str(i), cell, str(i), 'push', 0, 100-i) for i in range(100)]
    order = exploratory_order(candidates)
    assert len(order) == 100
    assert len({c.key for c in order}) == 100
    assert order[:3] == candidates[:3]


def test_information_value_explores_instead_of_repeating_clear_winner():
    from contracts import Candidate, Cell, PilotObservation, ResourceSnapshot
    from policy import next_candidate
    known = Candidate('known', Cell('one', {}, 1000, 100000), 'a', 'push', 0, 0)
    unknown = Candidate('unknown', Cell('two', {}, 1000, 100000), 'b', 'push', 0, 0)
    observations = [PilotObservation('known', 25, 0, .8) for _ in range(16)]
    chosen = next_candidate([known, unknown], observations, {'known'}, ResourceSnapshot(100000, 15000, 4), lambda c: True)
    assert chosen == unknown


def test_information_value_remeasures_borderline_large_campaign():
    from contracts import Candidate, Cell, PilotObservation, ResourceSnapshot
    from policy import next_candidate
    known = Candidate('known', Cell('one', {}, 1000, 1000000), 'a', 'sms', 4, 0)
    unknown = Candidate('unknown', Cell('two', {}, 10, 10), 'b', 'sms', 4, 0)
    observations = [PilotObservation('known', 25, 100, .02) for _ in range(16)]
    assert next_candidate([known, unknown], observations, {'known'}, ResourceSnapshot(100000, 15000, 4), lambda c: True) == known


def test_negative_feedback_measures_small_free_emergency_audience():
    from contracts import Candidate, Cell, PilotObservation, ResourceSnapshot
    from policy import next_candidate
    known = Candidate('known', Cell('one', {}, 1000, 1000000), 'a', 'push', 0, 0)
    small = Candidate('small', Cell('two', {}, 10, 100), 'b', 'push', 0, 0)
    observations = [PilotObservation('known', 25, 0, -.2) for _ in range(16)]
    assert next_candidate([known, small], observations, {'known'}, ResourceSnapshot(100000, 15000, 4), lambda c: True) == small


def test_sample_size_and_downside_penalty_use_feedback():
    from contracts import Candidate, Cell, PilotObservation
    from policy import pilot_sample_size, conservative_ratios, adjusted_ratios
    candidate = Candidate('new', Cell('one', {}, 1000, 1000000), 'a', 'push', 0, 0)
    negative = [PilotObservation('known', 25, 0, -.2) for _ in range(16)]
    assert pilot_sample_size(candidate, []) == 200
    assert pilot_sample_size(candidate, negative) == 100
    assert pilot_sample_size(candidate, negative + [PilotObservation('new', 100, 0, .1)]) == 200
    assert conservative_ratios(negative)['known'] < adjusted_ratios(negative)['known']
    positive = [PilotObservation('known', 200, 0, .2)]
    assert conservative_ratios(positive) == adjusted_ratios(positive)
    small_positive = [PilotObservation("known", 100, 0, .2)]
    assert conservative_ratios(small_positive)["known"] < adjusted_ratios(small_positive)["known"]
