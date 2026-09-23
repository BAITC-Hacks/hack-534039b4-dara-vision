from types import SimpleNamespace
import socket

import pandas as pd
import pytest

import agent as agent_module
from agent import Agent


def fake_env(sign):
    profile = pd.DataFrame({
        "ID_NUMBER": range(80), "current_tariff": ["a"] * 40 + ["b"] * 40,
        "arpu_segment": ["HIGH"] * 80, "data_segment": ["HEAVY"] * 80,
        "call_segment": ["HIGH"] * 80, "predicted_arpu": [10000.0] * 80,
    })
    tariffs = pd.DataFrame({"tariff_plan_code": ["a", "b", "c"], "price_tariff": [100, 200, 300]})
    env = SimpleNamespace(customer_profile=profile, tariffs=tariffs,
                          channels={"push": {"cost_per_contact": 0, "conversion_multiplier": 0.5}},
                          remaining_budget=100_000, remaining_contacts=5000, pilots_left=20)

    def run_pilot(target_tariff, channel, n_customers, **filters):
        env.remaining_contacts -= n_customers
        env.pilots_left -= 1
        return {"n_customers": n_customers, "cost": 0,
                "observed_lift_ratio": sign * (0.2 if target_tariff == "c" else -0.2)}

    env.run_pilot = run_pilot
    return env


def test_feedback_changes_final_decision(monkeypatch):
    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    positive, negative = Agent(), Agent()
    plans = [positive.act(fake_env(1)), negative.act(fake_env(-1))]
    assert plans[0] != plans[1]
    assert any(t["event"] == "pilot_observed" for t in positive.trace)
    assert all(t["event"] != "failed" for t in positive.trace)


def test_failed_pilot_terminates_without_retry(monkeypatch):
    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    env = fake_env(1)
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        env.remaining_contacts -= kwargs["n_customers"]
        raise RuntimeError("partial debit")

    env.run_pilot = fail
    with pytest.raises(RuntimeError, match="no successful pilot"):
        Agent().act(env)
    assert len(calls) == 1


def test_trace_resets_between_runs(monkeypatch):
    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    agent = Agent()
    agent.act(fake_env(1))
    count = len(agent.trace)
    agent.act(fake_env(1))
    assert len(agent.trace) == count


def test_fractional_pilot_count_is_rejected(monkeypatch):
    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    env = fake_env(1)

    def malformed(target_tariff, channel, n_customers, **filters):
        env.remaining_contacts -= n_customers
        env.pilots_left -= 1
        return {"n_customers": n_customers + 0.5, "cost": 0,
                "observed_lift_ratio": 0.2}

    env.run_pilot = malformed
    agent = Agent()
    with pytest.raises(RuntimeError, match="no successful pilot"):
        agent.act(env)
    assert any(t["event"] == "pilot_failed" for t in agent.trace)


def test_official_submission_is_offline_and_reproducible(monkeypatch):
    from make_submission import build_submission
    from mock_environment import make_mock_env

    def no_network(*args, **kwargs):
        raise AssertionError("network access during agent run")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    first_env, _ = make_mock_env(seed=42)
    first_agent = Agent()
    first_plan = first_agent.act(first_env)
    assert 1 <= len(first_plan) <= 10
    assert any(t["event"] == "pilot_observed" for t in first_agent.trace)
    assert first_env.pilots_left < 20
    assert first_env.remaining_budget >= 0
    assert first_env.remaining_contacts >= 0
    assert build_submission(Agent(), seed=42).equals(build_submission(Agent(), seed=42))


@pytest.mark.parametrize("reported_n", [True, False, 40.5])
def test_invalid_pilot_count_never_becomes_an_observation(monkeypatch, reported_n):
    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    env = fake_env(1)
    original = env.run_pilot

    def malformed(**kwargs):
        return {**original(**kwargs), "n_customers": reported_n}

    env.run_pilot = malformed
    agent = Agent()
    with pytest.raises(RuntimeError, match="no successful pilot"):
        agent.act(env)
    assert sum(t["event"] == "pilot_requested" for t in agent.trace) == 1
    assert any(t["event"] == "pilot_failed" for t in agent.trace)
    assert not any(t["event"] == "pilot_observed" for t in agent.trace)


def test_duplicate_tariff_codes_rejected_before_pilot():
    env = fake_env(1)
    env.tariffs = pd.concat([env.tariffs, env.tariffs.iloc[[0]]], ignore_index=True)
    agent = Agent()
    with pytest.raises(ValueError, match="tariff codes must be unique"):
        agent.act(env)
    assert agent.trace == []
    assert env.pilots_left == 20
    assert env.remaining_contacts == 5000


def test_missing_history_still_produces_tested_plan(monkeypatch, tmp_path):
    from policy import historical_hints

    monkeypatch.setattr(agent_module, "historical_hints",
                        lambda: historical_hints(tmp_path / "missing.csv"))
    agent = Agent()
    assert 1 <= len(agent.act(fake_env(1))) <= 10
    assert any(t["event"] == "history_unavailable" for t in agent.trace)
    assert any(t["event"] == "pilot_observed" for t in agent.trace)


def test_all_negative_feedback_returns_one_tested_emergency_campaign(monkeypatch):
    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    env = fake_env(1)
    original = env.run_pilot

    def negative(**kwargs):
        return {**original(**kwargs), "observed_lift_ratio": -0.2}

    env.run_pilot = negative
    agent = Agent()
    assert len(agent.act(env)) == 1
    tested = {t["candidate_key"] for t in agent.trace if t["event"] == "pilot_observed"}
    selected = [t for t in agent.trace if t["event"] == "final_selected"]
    assert len(selected) == 1
    assert selected[0]["candidate_key"] in tested
    assert selected[0]["estimated_score"] < 0
    assert any(t["event"] == "emergency" for t in agent.trace)


@pytest.mark.parametrize("successful_first", [False, True])
def test_failed_pilot_without_debit_stops_and_preserves_tested_reserve(monkeypatch, successful_first):
    from planning import snapshot

    monkeypatch.setattr(agent_module, "historical_hints", lambda: ({}, None))
    env = fake_env(1)
    original = env.run_pilot
    calls = []
    failed_resources = []

    def fail(**kwargs):
        calls.append(kwargs)
        if successful_first and len(calls) == 1:
            return original(**kwargs)
        failed_resources.append(snapshot(env))
        raise RuntimeError("no debit")

    env.run_pilot = fail
    agent = Agent()
    if successful_first:
        assert len(agent.act(env)) == 1
        tested = {t["candidate_key"] for t in agent.trace if t["event"] == "pilot_observed"}
        assert all(t["candidate_key"] in tested for t in agent.trace if t["event"] == "final_selected")
    else:
        with pytest.raises(RuntimeError, match="no successful pilot"):
            agent.act(env)
    assert len(calls) == 1 + int(successful_first)
    assert failed_resources == [snapshot(env)]
    assert sum(t["event"] == "pilot_failed" for t in agent.trace) == 1
