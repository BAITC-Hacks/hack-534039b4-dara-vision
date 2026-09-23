"""Offline tariff campaign agent. Only public environment data and pilot feedback are read."""

import math

from contracts import PilotObservation
from planning import build_cells, can_pilot, campaign_score, select_campaigns, snapshot, validate_plan
from policy import transfer_channel_evidence, adjusted_ratios, exploratory_order, historical_hints, make_candidates, next_candidate


class Agent:
    def __init__(self):
        self.trace = []

    def _event(self, name, **fields):
        self.trace.append({"schema_version": 1, "event": name, "step": len(self.trace), **fields})

    def act(self, env):
        self.trace = []
        profile, tariffs, channels = env.customer_profile, env.tariffs, env.channels
        if "tariff_plan_code" not in tariffs or "price_tariff" not in tariffs:
            raise ValueError("invalid tariff table")
        tariff_codes = set(tariffs["tariff_plan_code"].dropna())
        if not tariff_codes or tariffs["tariff_plan_code"].duplicated().any():
            raise ValueError("tariff codes must be unique")
        if not profile["current_tariff"].dropna().isin(tariff_codes).all():
            raise ValueError("unknown current tariff")
        if not tariffs["price_tariff"].map(lambda x: isinstance(x, (int, float)) and math.isfinite(x) and x >= 0).all():
            raise ValueError("invalid tariff prices")
        cells = build_cells(profile)
        if not cells:
            raise ValueError("no representable cells")
        self._event("input_validated", profile_size=len(profile), cells=len(cells))
        history, reason = historical_hints()
        if reason:
            self._event("history_unavailable", reason=reason)
        all_candidates = make_candidates(cells, tariffs, channels, history)
        order = exploratory_order(all_candidates)
        if not order:
            raise ValueError("no candidate tariffs or channels")

        observations, tried = [], set()
        tested = {}
        reserve = None
        attempts = 0
        initial_budget = snapshot(env).remaining_budget
        pilot_spend = 0.0
        while attempts < 20:
            before = snapshot(env)
            if before.pilots_left <= 0:
                break

            def pilot_size(candidate):
                return min(200 if candidate.cost_per_contact <= 22 else 50,
                           candidate.cell.audience_count)

            def eligible(candidate):
                n_requested = pilot_size(candidate)
                return (pilot_spend + n_requested * candidate.cost_per_contact <= initial_budget * 0.25 + 1e-7
                        and can_pilot(candidate, n_requested, before, reserve))

            candidate = next_candidate(order, observations, tried, before, eligible)
            if candidate is None:
                break
            n = pilot_size(candidate)
            attempts += 1
            tried.add(candidate.key)
            self._event("pilot_requested", candidate_key=candidate.key, filters=candidate.cell.filters,
                        target=candidate.target_tariff, channel=candidate.channel, requested_n=n,
                        resources_before=before.__dict__)
            try:
                result = env.run_pilot(target_tariff=candidate.target_tariff, channel=candidate.channel,
                                       n_customers=n, **candidate.cell.filters)
            except Exception as exc:
                after = snapshot(env)
                self._event("pilot_failed", candidate_key=candidate.key, reason=type(exc).__name__,
                            resources_after=after.__dict__)
                # No automatic retry: a failed call may have consumed resources.
                break
            after = snapshot(env)
            try:
                reported_n = result["n_customers"]
                actual = int(reported_n)
                cost = float(result["cost"])
                ratio = float(result["observed_lift_ratio"])
                if (isinstance(reported_n, bool) or reported_n != actual or actual != n
                        or not math.isfinite(cost) or not math.isfinite(ratio)
                        or abs(cost - actual * candidate.cost_per_contact) > 1e-6
                        or before.remaining_contacts - after.remaining_contacts != actual
                        or abs(before.remaining_budget - after.remaining_budget - cost) > 1e-5
                        or before.pilots_left - after.pilots_left != 1):
                    raise ValueError("inconsistent pilot feedback or resource debit")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                self._event("pilot_failed", candidate_key=candidate.key, reason=str(exc),
                            resources_after=after.__dict__)
                break
            observations.append(PilotObservation(candidate.key, actual, cost, ratio))
            pilot_spend += cost
            tested[candidate.key] = candidate
            self._event("pilot_observed", candidate_key=candidate.key, actual_n=actual, cost=cost,
                        ratio=ratio, resources_after=after.__dict__)
            ratios = adjusted_ratios(observations)
            feasible = [c for c in tested.values() if c.cell.audience_count <= after.remaining_contacts and
                        c.cell.audience_count * c.cost_per_contact <= after.remaining_budget + 1e-7]
            if feasible:
                reserve = max(feasible, key=lambda c: (campaign_score(c, ratios[c.key]), c.key))
            self._event("selection_updated", tested=len(tested), reserve=reserve.key if reserve else None)
            if reserve is None:
                break

        if not tested:
            self._event("failed", reason="no successful pilot")
            raise RuntimeError("no successful pilot")
        resources = snapshot(env)
        supported, ratios = transfer_channel_evidence(all_candidates, observations, channels)
        selected = select_campaigns(supported, ratios, resources)
        if not selected:
            self._event("failed", reason="no feasible tested campaign")
            raise RuntimeError("no feasible tested campaign")
        validate_plan(selected, profile, tariffs, channels, resources)
        if all(campaign_score(c, ratios[c.key]) <= 0 for c in selected):
            self._event("emergency", reason="no estimated profitable campaign")
        campaigns = []
        for index, candidate in enumerate(selected, 1):
            campaigns.append({"campaign_name": f"campaign_{index:02d}", **candidate.cell.filters,
                              "target_tariff": candidate.target_tariff, "channel": candidate.channel})
            self._event("final_selected", candidate_key=candidate.key,
                        estimated_score=campaign_score(candidate, ratios[candidate.key]),
                        audience_count=candidate.cell.audience_count)
        return campaigns
