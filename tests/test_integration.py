import pandas as pd

from agent import Agent


class FeedbackEnv:
    def __init__(self, good_target):
        self.customer_profile = pd.DataFrame({
            "ID_NUMBER": list(range(60)), "current_tariff": ["a"] * 60,
            "arpu_segment": ["MID"] * 60, "data_segment": ["LIGHT"] * 60,
            "call_segment": ["LOW"] * 60, "predicted_arpu": [1000.] * 60})
        self.tariffs = pd.DataFrame({"tariff_plan_code": ["a", "b", "c"],
                                     "price_tariff": [100, 200, 200]})
        self.channels = {"push": {"cost_per_contact": 0}}
        self.remaining_budget = 100000
        self.remaining_contacts = 15000
        self.pilots_left = 20
        self.good_target = good_target

    def run_pilot(self, *, target_tariff, channel, n_customers, **filters):
        self.remaining_contacts -= n_customers
        self.pilots_left -= 1
        return {"n_customers": n_customers, "cost": 0,
                "observed_lift_ratio": 0.4 if target_tariff == self.good_target else -0.4}


def test_reversed_feedback_changes_final_target(monkeypatch):
    monkeypatch.setattr("agent.history_table", lambda: ({}, "test fixture"))
    a = Agent().act(FeedbackEnv("b"))
    b = Agent().act(FeedbackEnv("c"))
    assert a[0]["target_tariff"] == "b"
    assert b[0]["target_tariff"] == "c"
