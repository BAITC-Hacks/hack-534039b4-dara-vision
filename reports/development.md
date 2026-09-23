# Local evaluation

Status: **PASS**

The measured net values below come from the official local scorer and its mock effects.
They do not predict judging effects.

Policy commit: `82ec7b32c0516dfb41107c56826b207e586c0667`

| Seed | Agent net | Baseline net | Paired difference | Cost | Contacts | Status |
|---:|---:|---:|---:|---:|---:|---|
| 0 | 3,441,687 | -1,019,431 | 4,461,118 | 90,318 | 10,175 | PASS |
| 1 | 3,424,106 | -576,204 | 4,000,310 | 83,346 | 11,311 | PASS |
| 2 | 3,555,754 | -338,971 | 3,894,725 | 83,466 | 14,840 | PASS |
| 3 | 3,415,023 | -140,281 | 3,555,304 | 83,466 | 10,752 | PASS |
| 4 | 3,089,264 | -1,019,237 | 4,108,501 | 83,118 | 12,746 | PASS |
| 5 | 3,555,579 | -366,964 | 3,922,543 | 83,626 | 14,963 | PASS |
| 6 | 3,514,693 | -320,312 | 3,835,004 | 89,998 | 14,514 | PASS |
| 7 | 3,601,655 | -348,932 | 3,950,587 | 89,838 | 14,781 | PASS |
| 8 | 2,638,913 | -76,493 | 2,715,406 | 56,352 | 14,986 | PASS |
| 9 | 3,192,105 | -601,538 | 3,793,643 | 76,586 | 14,972 | PASS |

Median agent net: **3,432,897**
Median paired difference: **3,908,634**
Minimum agent net: **2,638,913**
Negative share: **0.0%**
Violations: **0**

## One real trace

```json
[
  {
    "schema_version": 1,
    "event": "input_validated",
    "step": 0,
    "profile_size": 23441,
    "cells": 54
  },
  {
    "schema_version": 1,
    "event": "pilot_requested",
    "step": 1,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_13|target=tariff_8|channel=digital_ads",
    "filters": {
      "filter_current_tariff": "tariff_13",
      "filter_arpu_segment": "MID"
    },
    "target": "tariff_8",
    "channel": "digital_ads",
    "requested_n": 200,
    "resources_before": {
      "remaining_budget": 100000.0,
      "remaining_contacts": 15000,
      "pilots_left": 20
    }
  },
  {
    "schema_version": 1,
    "event": "pilot_observed",
    "step": 2,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_13|target=tariff_8|channel=digital_ads",
    "actual_n": 200,
    "cost": 4400.0,
    "ratio": 0.2104333157543401,
    "resources_after": {
      "remaining_budget": 95600.0,
      "remaining_contacts": 14800,
      "pilots_left": 19
    }
  },
  {
    "schema_version": 1,
    "event": "selection_updated",
    "step": 3,
    "tested": 1,
    "reserve": "filter_arpu_segment=MID|filter_current_tariff=tariff_13|target=tariff_8|channel=digital_ads"
  },
  {
    "schema_version": 1,
    "event": "pilot_requested",
    "step": 4,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_13|target=tariff_8|channel=digital_ads",
    "filters": {
      "filter_current_tariff": "tariff_13",
      "filter_arpu_segment": "MID"
    },
    "target": "tariff_8",
    "channel": "digital_ads",
    "requested_n": 200,
    "resources_before": {
      "remaining_budget": 95600.0,
      "remaining_contacts": 14800,
      "pilots_left": 19
    }
  },
  {
    "schema_version": 1,
    "event": "pilot_observed",
    "step": 5,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_13|target=tariff_8|channel=digital_ads",
    "actual_n": 200,
    "cost": 4400.0,
    "ratio": 0.2543525750209787,
    "resources_after": {
      "remaining_budget": 91200.0,
      "remaining_contacts": 14600,
      "pilots_left": 18
    }
  },
  {
    "schema_version": 1,
    "event": "selection_updated",
    "step": 6,
    "tested": 1,
    "reserve": "filter_arpu_segment=MID|filter_current_tariff=tariff_13|target=tariff_8|channel=digital_ads"
  },
  {
    "schema_version": 1,
    "event": "pilot_requested",
    "step": 7,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_4|target=tariff_8|channel=digital_ads",
    "filters": {
      "filter_current_tariff": "tariff_4",
      "filter_arpu_segment": "MID"
    },
    "target": "tariff_8",
    "channel": "digital_ads",
    "requested_n": 200,
    "resources_before": {
      "remaining_budget": 91200.0,
      "remaining_contacts": 14600,
      "pilots_left": 18
    }
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 66,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_11|target=tariff_21|channel=push",
    "estimated_score": 26124.737093176744,
    "audience_count": 387
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 67,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_4|target=tariff_19|channel=push",
    "estimated_score": 16484.82398053761,
    "audience_count": 299
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 68,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_6|target=tariff_13|channel=sms",
    "estimated_score": 10951.473771099432,
    "audience_count": 30
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 69,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_1|target=tariff_4|channel=sms",
    "estimated_score": 7586.144188890362,
    "audience_count": 40
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 70,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_15|target=tariff_20|channel=sms",
    "estimated_score": 3930.2945252101345,
    "audience_count": 80
  }
]
```

## Limits

History is observational and drawn from another population.
Pilot ratio shrinkage is an uncalibrated heuristic. A positive mock score does not establish production ROI.
