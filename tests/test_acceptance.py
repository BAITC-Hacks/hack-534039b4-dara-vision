import hashlib
import socket

import pandas as pd

from agent import Agent
from contracts import Cell, Candidate, ResourceSnapshot
from make_submission import build_submission
from mock_environment import make_mock_env
from planning import can_pilot, filter_mask, select_campaigns, validate_plan


def test_free_channel_still_reserves_contacts():
    cell = Cell("a", {"current_tariff": "a", "arpu_segment": "MID"}, 100, 10000)
    candidate = Candidate("a|b|push", cell, "b", "push", 0, 0)
    assert not can_pilot(candidate, 50, ResourceSnapshot(0, 149, 1), candidate)
    assert can_pilot(candidate, 50, ResourceSnapshot(0, 150, 1), candidate)


def test_all_negative_fallback_takes_least_loss():
    a = Cell("a", {"current_tariff": "a"}, 100, 1000)
    b = Cell("b", {"current_tariff": "b"}, 50, 500)
    ca = Candidate("a", a, "b", "push", 0, 0)
    cb = Candidate("b", b, "a", "push", 0, 0)
    assert select_campaigns([ca, cb], {"a": -0.1, "b": -0.1}, ResourceSnapshot(0, 200, 0)) == [cb]


def test_validation_rejects_overlap_and_supports_tariff_list():
    profile = pd.DataFrame({"ID_NUMBER": [1, 2, 3], "current_tariff": ["a", "b", "a"],
                            "arpu_segment": ["MID"] * 3})
    assert filter_mask(profile, {"current_tariff": "a;b"}).sum() == 3
    tariffs = pd.DataFrame({"tariff_plan_code": ["a", "b", "c"]})
    base = {"campaign_name": "one", "filter_current_tariff": "a",
            "target_tariff": "c", "channel": "push"}
    second = {**base, "campaign_name": "two"}
    try:
        validate_plan([base, second], profile, tariffs,
                      {"push": {"cost_per_contact": 0}}, ResourceSnapshot(0, 10, 0))
    except ValueError as exc:
        assert "overlapping" in str(exc)
    else:
        raise AssertionError("overlap accepted")


def test_offline_act_and_official_evaluator(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network attempted")
    monkeypatch.setattr(socket, "socket", blocked)
    from local_eval import evaluate_agent
    agent = Agent()
    result = evaluate_agent(agent, seed=0, verbose=False)
    assert result is not None
    assert result["n_pilots"] >= 1
    assert result["total_contacts"] <= 15000
    assert result["total_cost"] <= 100000
    assert not any(any(detail.get(key) for key in
                       ("capped_at_campaign_limit", "capped_at_reach_budget", "capped_at_money_budget"))
                   for detail in result["campaigns_detail"])
    assert any(event["event"] == "pilot_observed" for event in agent.trace)


def test_submission_csv_round_trip_and_repeatability(tmp_path):
    first = build_submission(Agent()).to_csv(index=False).encode()
    second = build_submission(Agent()).to_csv(index=False).encode()
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    path = tmp_path / "submission.csv"
    path.write_bytes(first)
    frame = pd.read_csv(path)
    assert 1 <= len(frame) <= 10
    assert list(frame) == ["campaign_name", "filter_arpu_segment", "filter_data_segment",
                           "filter_call_segment", "filter_current_tariff", "target_tariff", "channel"]
