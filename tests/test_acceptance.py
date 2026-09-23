import hashlib
import socket

import pandas as pd

from agent import Agent
from make_submission import build_submission


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
