"""Business rules for the save workflow, kept free of I/O so they are testable.

Each function returns a rejection reason (str) or None when the check passes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from shipp.agent.contracts import (
    LISTING_AVAILABLE,
    REQUEST_CLOSED,
    ListingState,
    RequestState,
)


def _as_utc(value: datetime) -> datetime:
    # Lakebase `timestamp` (without time zone) comes back naive. We store UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def check_request_usable(request: RequestState | None, user_id: str) -> str | None:
    if request is None:
        return "This request does not exist."
    if request.requester_id != user_id:
        # Same message as "missing" on purpose: don't confirm other users' IDs.
        return "This request does not exist."
    if request.status.lower() == REQUEST_CLOSED:
        return "This request is closed."
    return None


def check_listing_saveable(listing: ListingState | None, now: datetime) -> str | None:
    if listing is None:
        return "This listing does not exist."
    if listing.status.lower() != LISTING_AVAILABLE:
        return f"This listing is no longer available (status: {listing.status})."
    if listing.available_until is not None and _as_utc(listing.available_until) < _as_utc(now):
        return "This listing's availability window has ended."
    return None
