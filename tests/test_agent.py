import pandas as pd

from agent import Agent


class FakeEnv:
    def __init__(self, sign):
        self.customer_profile = pd.DataFrame({"ID_NUMBER": range(200),
            "current_tariff": ["t1"] * 100 + ["t2"] * 100,
            "arpu_segment": ["HIGH"] * 200, "data_segment": ["HEAVY"] * 200,
            "call_segment": ["LOW"] * 200, "predicted_arpu": [100.0] * 200})
        self.tariffs = pd.DataFrame({"tariff_plan_code": ["t1", "t2"], "price_tariff": [1000, 2000]})
        self.channels = {"push": {"cost_per_contact": 0}}
        self.remaining_budget = 0
        self.remaining_contacts = 400
        self.pilots_left = 20
        self.pilot_history = []
        self.sign = sign

    def run_pilot(self, target_tariff, channel, n_customers, **filters):
        self.remaining_contacts -= n_customers
        self.pilots_left -= 1
        ratio = self.sign if filters["filter_current_tariff"] == "t1" else -self.sign
        result = {"n_customers": n_customers, "cost": 0, "observed_lift_ratio": ratio}
        self.pilot_history.append(result)
        return result


def test_feedback_reversal_changes_plan():
    a, b = Agent(), Agent()
    positive = a.act(FakeEnv(0.4))
    negative = b.act(FakeEnv(-0.4))
    assert positive != negative
    assert any(e["event"] == "pilot_observed" for e in a.trace)
    assert a.trace[-1]["event"] == "final_selected"
