from scripts.evaluate import violations


def test_loss_is_not_a_contract_violation(monkeypatch):
    monkeypatch.setattr("scripts.evaluate.sanitize_campaigns", lambda campaigns, tariffs: campaigns)
    result = {"status": "FAIL", "net_arpu_gain": -100, "total_contacts": 100,
              "total_cost": 0, "n_pilots": 1, "campaigns_detail": []}
    assert violations(result, [{}], "") == []


def test_missing_pilots_and_scorer_caps_are_violations(monkeypatch):
    monkeypatch.setattr("scripts.evaluate.sanitize_campaigns", lambda campaigns, tariffs: campaigns)
    result = {"total_contacts": 100, "total_cost": 0, "n_pilots": 0,
              "campaigns_detail": [{"name": "oversized", "capped_at_campaign_limit": True}]}
    assert violations(result, [{}], "") == ["pilot count", "scorer capped oversized"]
