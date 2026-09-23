"""Offline tariff-campaign agent. Only public environment fields are read."""
import math

from contracts import PilotObservation
from planning import (build_cells, campaign_dict, can_pilot, select_campaigns,
                      snapshot, validate_plan)
from policy import (estimate_ratios, history_table, make_candidates,
                    next_exploration, next_repeat)


class Agent:
    def __init__(self):
        self.trace = []

    def _event(self, event, **details):
        self.trace.append({"schema_version": 1, "event": event,
                           "step": len(self.trace), **details})

    def act(self, env):
        self.trace = []
        cells = build_cells(env.customer_profile)
        if not cells:
            self._event("failed", reason="no representable cells")
            raise ValueError("no representable cells")
        if "tariff_plan_code" not in env.tariffs or "price_tariff" not in env.tariffs:
            raise ValueError("invalid tariff dictionary")
        if env.tariffs["tariff_plan_code"].isna().any() or env.tariffs["tariff_plan_code"].duplicated().any():
            raise ValueError("invalid tariff codes")
        start = snapshot(env)
        self._event("input_validated", cells=len(cells), tariffs=len(env.tariffs),
                    channels=sorted(env.channels), resources=start.__dict__)
        history, history_error = history_table()
        if history_error:
            self._event("history_unavailable", reason=history_error)
        candidates = make_candidates(cells, env.tariffs, env.channels, history)
        observations = []
        tested = set()
        reserved = None
        attempts = 0
        while attempts < 20:
            before = snapshot(env)
            if len(tested) < 12:
                next_item = next_exploration(candidates, tested, before, reserved, can_pilot)
            else:
                next_item = next_repeat(candidates, observations, before, reserved, can_pilot)
            if next_item is None:
                break
            candidate, n = next_item
            attempts += 1
            self._event("pilot_requested", candidate_key=candidate.key,
                        filters=candidate.cell.filters, target=candidate.target_tariff,
                        channel=candidate.channel, requested_n=n, resources_before=before.__dict__)
            args = {"target_tariff": candidate.target_tariff, "channel": candidate.channel,
                    "n_customers": n,
                    **{"filter_" + k: v for k, v in candidate.cell.filters.items()}}
            try:
                result = env.run_pilot(**args)
            except Exception as exc:
                after = snapshot(env)
                self._event("pilot_failed", candidate_key=candidate.key,
                            reason=type(exc).__name__, resources_after=after.__dict__)
                if after != before:
                    break
                tested.add(candidate.key)
                continue
            after = snapshot(env)
            try:
                actual = int(result["n_customers"])
                cost = float(result["cost"])
                ratio = float(result["observed_lift_ratio"])
                valid = (10 <= actual <= n and math.isfinite(cost) and cost >= 0 and
                         math.isfinite(ratio) and
                         abs((before.remaining_contacts - after.remaining_contacts) - actual) == 0 and
                         abs((before.remaining_budget - after.remaining_budget) - cost) < 1e-6 and
                         before.pilots_left - after.pilots_left == 1 and
                         abs(cost - actual * candidate.cost_per_contact) < 1e-6)
            except (KeyError, TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                self._event("pilot_failed", candidate_key=candidate.key,
                            reason="invalid feedback or inconsistent counters",
                            resources_after=after.__dict__)
                break
            observations.append(PilotObservation(candidate.key, actual, cost, ratio))
            tested.add(candidate.key)
            self._event("pilot_observed", candidate_key=candidate.key, actual_n=actual,
                        ratio=ratio, cost=cost, resources_after=after.__dict__)
            estimates = estimate_ratios(observations, candidates)
            chosen = select_campaigns([c for c in candidates if c.key in tested], estimates, after)
            if chosen:
                reserved = chosen[0]
            self._event("selection_updated", selected_keys=[c.key for c in chosen],
                        reserve=reserved.key if reserved else None,
                        estimated_scores={c.key: round(estimates[c.key] * c.cell.arpu_sum -
                                                       c.cell.audience_count * c.cost_per_contact, 3)
                                          for c in chosen})
            if reserved is None:
                break
        if not observations:
            self._event("failed", reason="no successful pilot")
            raise RuntimeError("no successful pilot")
        remaining = snapshot(env)
        estimates = estimate_ratios(observations, candidates)
        selected = select_campaigns([c for c in candidates if c.key in tested], estimates, remaining)
        if not selected:
            self._event("failed", reason="no feasible tested campaign")
            raise RuntimeError("no feasible tested campaign")
        if all(estimates[c.key] * c.cell.arpu_sum - c.cell.audience_count * c.cost_per_contact <= 0
               for c in selected):
            self._event("emergency", reason="no estimated profitable plan")
        campaigns = [campaign_dict(c, i + 1) for i, c in enumerate(selected)]
        validate_plan(campaigns, env.customer_profile, env.tariffs, env.channels, remaining)
        self._event("final_selected", candidate_keys=[c.key for c in selected],
                    campaign_count=len(campaigns), resources=remaining.__dict__)
        return campaigns
