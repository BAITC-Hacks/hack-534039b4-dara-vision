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
