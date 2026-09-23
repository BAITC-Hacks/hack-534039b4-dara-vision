from dataclasses import dataclass


FILTER_COLUMNS = ("filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff")
CAMPAIGN_COLUMNS = ("campaign_name", *FILTER_COLUMNS, "target_tariff", "channel")


@dataclass(frozen=True)
class Cell:
    key: str
    filters: dict[str, str]
    audience_count: int
    arpu_sum: float


@dataclass(frozen=True)
class Candidate:
    key: str
    cell: Cell
    target_tariff: str
    channel: str
    cost_per_contact: float
    prior_score: float
    multiplier: float = 1.0


@dataclass(frozen=True)
class PilotObservation:
    candidate_key: str
    n_actual: int
    cost: float
    ratio: float


@dataclass(frozen=True)
class ResourceSnapshot:
    remaining_budget: float
    remaining_contacts: int
    pilots_left: int
