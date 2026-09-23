import hashlib
import socket
import time

from agent import Agent
from make_submission import build_submission
from mock_environment import make_mock_env
from planning import validate_plan, snapshot, build_cells


def test_offline_submission_and_limits(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network call during agent runtime")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    start = time.monotonic()
    env, _ = make_mock_env(seed=42)
    agent = Agent()
    campaigns = agent.act(env)
    assert time.monotonic() - start < 300
    assert 1 <= len(campaigns) <= 10
    assert env.pilots_left < 20
    cells = {c.filters["filter_current_tariff"] + "|" + c.filters["filter_arpu_segment"] +
             "|" + c.filters.get("filter_data_segment", "") + "|" + c.filters.get("filter_call_segment", ""): c
             for c in build_cells(env.customer_profile)}
    selected = []
    from contracts import Candidate
    for campaign in campaigns:
        filters = {k: v for k, v in campaign.items() if k.startswith("filter_")}
        key = filters["filter_current_tariff"] + "|" + filters["filter_arpu_segment"] + "|" + filters.get("filter_data_segment", "") + "|" + filters.get("filter_call_segment", "")
        cell = cells[key]
        selected.append(Candidate(campaign["campaign_name"], cell, campaign["target_tariff"], campaign["channel"],
                                  env.channels[campaign["channel"]]["cost_per_contact"], 0))
    validate_plan(selected, env.customer_profile, env.tariffs, env.channels, snapshot(env))
    first = build_submission(Agent()).to_csv(index=False).encode()
    second = build_submission(Agent()).to_csv(index=False).encode()
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
