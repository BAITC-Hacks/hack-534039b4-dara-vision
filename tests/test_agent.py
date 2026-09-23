from types import SimpleNamespace

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
