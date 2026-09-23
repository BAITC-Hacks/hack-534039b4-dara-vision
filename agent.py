"""Offline tariff campaign agent using the public environment contract only."""

import math

from contracts import PilotObservation
from planning import build_cells, snapshot, can_pilot, select_campaigns, validate_plan, score
from policy import historical_priors, build_candidates, adjusted_ratios


class Agent:
    def __init__(self):
        self.trace = []

    def _event(self, name, **data):
        self.trace.append({"schema_version": 1, "event": name, "step": len(self.trace), **data})

    def act(self, env):
        self.trace = []
        profile = env.customer_profile
        cells = build_cells(profile)
        if not cells:
            raise ValueError("No representable campaign cells")
        tariffs = set(env.tariffs["tariff_plan_code"])
        if any(c.filters["filter_current_tariff"] not in tariffs for c in cells):
            raise ValueError("Unknown current tariff")
        self._event("input_validated", cell_count=len(cells), audience_count=len(profile))
        history, reason = historical_priors()
        if reason:
            self._event("history_unavailable", reason=reason)
        candidates = build_candidates(cells, env.tariffs, env.channels, history)
        observed = []
        tried = set()
        attempts = 0
        while attempts < 20:
            resources = snapshot(env)
            ratios = adjusted_ratios(observed, candidates)
            tested = [c for c in candidates if c.key in ratios]
            feasible_tested = [c for c in tested if c.cell.audience_count <= resources.remaining_contacts and
                               c.cell.audience_count * c.cost_per_contact <= resources.remaining_budget + 1e-9]
            reserve = select_campaigns(feasible_tested, ratios, resources)[:1] if feasible_tested else []
            if observed and not reserve:
                break
            if len(observed) >= 12:
                break
            # Avoid spending every pilot on one cell; feedback changes the value of further exploration.
            selected = None
            for c in candidates:
                if c.key in tried:
                    continue
                n = min(200, c.cell.audience_count)
                if not can_pilot(c, n, resources, reserve[0] if reserve else c):
                    continue
                same_cell = [x for x in tested if x.cell.key == c.cell.key]
                if same_cell and max(score(x, ratios[x.key]) for x in same_cell) > max(0.0, c.prior_score):
                    continue
                selected = c
                break
            if selected is None:
                break
            attempts += 1
            tried.add(selected.key)
            n = min(200, selected.cell.audience_count)
            before = resources
            self._event("pilot_requested", candidate_key=selected.key, filters=selected.cell.filters,
                        target=selected.target_tariff, channel=selected.channel, requested_n=n,
                        resources_before=vars(before))
            try:
                feedback = env.run_pilot(target_tariff=selected.target_tariff, channel=selected.channel,
                                         n_customers=n, **selected.cell.filters)
                after = snapshot(env)
                actual = int(feedback["n_customers"])
                cost = float(feedback["cost"])
                ratio = float(feedback["observed_lift_ratio"])
                if (not 10 <= actual <= n or not math.isfinite(ratio) or not math.isfinite(cost) or
                    abs(cost - actual * selected.cost_per_contact) > 1e-6 or
                    before.remaining_contacts - after.remaining_contacts != actual or
                    abs(before.remaining_budget - after.remaining_budget - cost) > 1e-6 or
                    before.pilots_left - after.pilots_left != 1):
                    self._event("pilot_failed", candidate_key=selected.key, reason="Invalid or inconsistent feedback")
                    break
                observed.append(PilotObservation(selected.key, actual, cost, ratio))
                self._event("pilot_observed", candidate_key=selected.key, actual_n=actual, cost=cost,
                            ratio=ratio, resources_after=vars(after))
            except Exception as error:
                self._event("pilot_failed", candidate_key=selected.key, reason=type(error).__name__)
                # A failed call may have consumed resources; re-read before deciding whether to continue.
                after = snapshot(env)
                if after != before:
                    break
                continue
            new_ratios = adjusted_ratios(observed, candidates)
            plan = select_campaigns([c for c in candidates if c.key in new_ratios], new_ratios, snapshot(env))
            self._event("selection_updated", candidate_keys=[c.key for c in plan],
                        estimated_scores=[score(c, new_ratios[c.key]) for c in plan])
        resources = snapshot(env)
        ratios = adjusted_ratios(observed, candidates)
        chosen = select_campaigns([c for c in candidates if c.key in ratios], ratios, resources)
        if not chosen:
            self._event("failed", reason="No feasible tested campaign")
            raise RuntimeError("No feasible tested campaign")
        validate_plan(chosen, profile, env.tariffs, env.channels, resources)
        if all(score(c, ratios[c.key]) <= 0 for c in chosen):
            self._event("emergency", reason="No estimated profitable campaign", candidate_key=chosen[0].key)
        campaigns = []
        for i, c in enumerate(chosen, 1):
            campaigns.append({"campaign_name": f"main_{i:02d}", **c.cell.filters,
                              "target_tariff": c.target_tariff, "channel": c.channel})
        self._event("final_selected", candidate_keys=[c.key for c in chosen], campaigns=campaigns,
                    estimated_scores=[score(c, ratios[c.key]) for c in chosen], resources_before=vars(resources))
        return campaigns
