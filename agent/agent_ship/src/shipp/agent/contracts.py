"""Contracts between the agent and the rest of Shipp.

This file is the agent's side of the Gold DoD. If gold_candidate_matches or
gold_listing_search_docs changes shape, parsing fails here with a clear error
instead of surfacing as a strange LLM answer three layers later.

Grain of gold_candidate_matches: one row = one (request_id, listing_id) pair
that passed eligibility filters, with its score and route enrichment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum

# --- Status vocabulary (spec §7.1 / §7.2) --------------------------------------
# The Lakebase enums must use exactly these values once schema review issues
# #6 and #12 are resolved. If the team picks different spellings, change them
# here and nowhere else.
LISTING_AVAILABLE = "available"
REQUEST_CLOSED = "closed"

# --- Gold: gold_candidate_matches ------------------------------------------------
# Read in this exact order. `area` is the coarse location (neighbourhood/city),
# never an exact address: the privacy boundary in spec §6.4.
CANDIDATE_MATCH_COLUMNS: tuple[str, ...] = (
    "request_id",
    "listing_id",
    "title",
    "category",
    "condition",
    "area",
    "match_score",
    "distance_km",
    "duration_min",
    "available_until",
    "computed_at",
)

# --- Gold: gold_listing_search_docs (AI Search source) ------------------------
SEARCH_DOC_COLUMNS: tuple[str, ...] = (
    "listing_id",
    "title",
    "category",
    "condition",
    "search_text",
)


class ActionStatus(StrEnum):
    """Values written to agent_activity.action_status."""

    SUCCESS = "success"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class ContractError(RuntimeError):
    """Upstream data does not match the shape the agent was built against."""


@dataclass(frozen=True)
class CandidateMatch:
    request_id: str
    listing_id: str
    title: str
    category: str
    condition: str | None
    area: str | None
    match_score: float
    distance_km: float | None
    duration_min: float | None
    available_until: str | None
    computed_at: str | None

    def to_tool_payload(self) -> dict:
        payload = asdict(self)
        payload.pop("request_id")
        payload["route_available"] = self.distance_km is not None
        return payload


@dataclass(frozen=True)
class SearchHit:
    listing_id: str
    title: str | None
    category: str | None
    condition: str | None
    snippet: str
    score: float

    def to_tool_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ListingState:
    listing_id: str
    status: str
    available_until: datetime | None


@dataclass(frozen=True)
class RequestState:
    request_id: str
    requester_id: str
    status: str


@dataclass(frozen=True)
class SaveProposal:
    """A save the agent recommends but has NOT performed. The user confirms it."""

    request_id: str
    listing_id: str
    title: str
    reason: str


@dataclass(frozen=True)
class SaveResult:
    status: ActionStatus
    message: str
    saved_item_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is ActionStatus.SUCCESS
