import hashlib
import json
import socket
import subprocess
import sys

import pandas as pd
import pytest

from agent import Agent
from make_submission import build_submission
from scripts import evaluate


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


@pytest.mark.parametrize("case, exit_code, errors", [
    ("pass", 0, []),
    ("loss", 1, []),
    ("violation", 1, ["pilot count"]),
    ("missing_agent", 1, ["evaluation failed"]),
    ("missing_baseline", 1, ["baseline evaluation failed"]),
])
def test_evaluator_exit_after_saving_reports(monkeypatch, tmp_path, case, exit_code, errors):
    result = {"status": "FAIL" if case == "loss" else "PASS",
              "net_arpu_gain": -100 if case == "loss" else 100,
              "total_contacts": 100, "total_cost": 0,
              "n_pilots": 0 if case == "violation" else 1, "campaigns_detail": []}
    baseline = dict(result, status="FAIL", net_arpu_gain=-200)
    runs = iter([(None if case == "missing_agent" else result, [{}], "agent output"),
                 (None if case == "missing_baseline" else baseline, [{}], "baseline output")])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluate, "run_one", lambda agent, seed: next(runs))
    monkeypatch.setattr(evaluate, "sanitize_campaigns", lambda campaigns, tariffs: campaigns)
    monkeypatch.setattr(evaluate.subprocess, "check_output", lambda *args, **kwargs: "test-commit\n")
    prefix = tmp_path / "reports" / "result"
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--stop", "1", "--out", str(prefix)])
    assert evaluate.main() == exit_code
    report = json.loads(prefix.with_suffix(".json").read_text())
    assert report["policy_commit"] == "test-commit"
    assert report["per_seed"][0]["violations"] == errors
    assert report["per_seed"][0]["agent_net"] == (None if case == "missing_agent" else result["net_arpu_gain"])
    assert "# Paired local benchmark" in prefix.with_suffix(".md").read_text()
    trace = json.loads(prefix.with_name("result-trace.json").read_text())
    assert trace["agent_stdout"] == "agent output"
    assert trace["baseline_stdout"] == "baseline output"


@pytest.mark.parametrize("error", [FileNotFoundError("git"),
                                  subprocess.CalledProcessError(128, ["git", "rev-parse", "HEAD"])])
def test_evaluator_without_git_metadata(monkeypatch, tmp_path, error):
    def unavailable(*args, **kwargs):
        raise error

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluate.subprocess, "check_output", unavailable)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--stop", "1", "--out", str(tmp_path / "result")])
    assert evaluate.main() == 0
    report = json.loads((tmp_path / "result.json").read_text())
    assert report["policy_commit"] == "unknown"
    assert report["per_seed"][0]["violations"] == []
