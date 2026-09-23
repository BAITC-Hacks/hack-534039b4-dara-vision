# Local evaluation

Status: **PASS**

The measured net values below come from the official local scorer and its mock effects.
They do not predict judging effects.

Policy commit: `82ec7b32c0516dfb41107c56826b207e586c0667`

| Seed | Agent net | Baseline net | Paired difference | Cost | Contacts | Status |
|---:|---:|---:|---:|---:|---:|---|
| 100 | 3,520,292 | -1,248,998 | 4,769,290 | 83,786 | 11,967 | PASS |
| 101 | 3,342,639 | -73,999 | 3,416,638 | 95,910 | 13,622 | PASS |
| 102 | 2,877,447 | -1,264,595 | 4,142,042 | 76,906 | 6,805 | PASS |
| 103 | 3,139,603 | -404,147 | 3,543,750 | 76,626 | 11,264 | PASS |
| 104 | 3,241,387 | -383,230 | 3,624,617 | 76,906 | 14,973 | PASS |
| 105 | 3,340,523 | -1,249,172 | 4,589,694 | 83,306 | 9,123 | PASS |
| 106 | 3,158,709 | -643,161 | 3,801,870 | 76,586 | 13,485 | PASS |
| 107 | 3,290,902 | -102,423 | 3,393,325 | 65,070 | 10,505 | PASS |
| 108 | 3,560,449 | -1,232,413 | 4,792,862 | 83,186 | 14,985 | PASS |
| 109 | 3,604,283 | -638,054 | 4,242,337 | 90,198 | 14,942 | PASS |
| 110 | 3,453,837 | -1,241,289 | 4,695,126 | 89,718 | 10,726 | PASS |
| 111 | 3,479,604 | -110,374 | 3,589,979 | 83,306 | 14,875 | PASS |
| 112 | 3,249,227 | -355,018 | 3,604,245 | 65,390 | 12,833 | PASS |
| 113 | 3,164,710 | -609,670 | 3,774,381 | 76,746 | 13,525 | PASS |
| 114 | 3,388,636 | -601,256 | 3,989,892 | 83,306 | 10,149 | PASS |
| 115 | 3,528,690 | -143,290 | 3,671,980 | 83,186 | 12,904 | PASS |
| 116 | 3,534,912 | -1,908,609 | 5,443,521 | 83,786 | 14,690 | PASS |
| 117 | 3,453,862 | -344,737 | 3,798,598 | 89,838 | 10,457 | PASS |
| 118 | 3,510,222 | -576,204 | 4,086,426 | 83,666 | 14,806 | PASS |
| 119 | 3,565,821 | -363,827 | 3,929,648 | 89,878 | 12,188 | PASS |

Median agent net: **3,421,236**
Median paired difference: **3,865,759**
Minimum agent net: **2,877,447**
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
    "ratio": 0.23441667895929838,
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
    "ratio": 0.2623362957053652,
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
    "candidate_key": "filter_arpu_segment=HIGH|filter_current_tariff=tariff_4|target=tariff_14|channel=push",
    "estimated_score": 83060.88029619293,
    "audience_count": 2108
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 67,
    "candidate_key": "filter_arpu_segment=MID|filter_current_tariff=tariff_15|target=tariff_20|channel=sms",
    "estimated_score": 33207.59936781738,
    "audience_count": 80
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 68,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_10|target=tariff_21|channel=push",
    "estimated_score": 13147.123725046109,
    "audience_count": 370
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 69,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_1|target=tariff_4|channel=sms",
    "estimated_score": 7011.5222541235025,
    "audience_count": 40
  },
  {
    "schema_version": 1,
    "event": "final_selected",
    "step": 70,
    "candidate_key": "filter_arpu_segment=LOW|filter_current_tariff=tariff_6|target=tariff_13|channel=sms",
    "estimated_score": 3045.858769718928,
    "audience_count": 30
  }
]
```

## Limits

History is observational and drawn from another population.
Pilot ratio shrinkage is an uncalibrated heuristic. A positive mock score does not establish production ROI.
