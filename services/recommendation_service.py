"""Narrow read/write facade over the existing SHIPP Agent.

Security-sensitive user IDs must come from a verified server-side profile,
never a client-submitted arbitrary ID. This service is for future integration;
original requester flow is preserved without behavior change.
"""
from __future__ import annotations

from typing import Any


class RecommendationService:
    def __init__(self, agent: Any) -> None:
        self._agent = agent

    def candidates(self, profile: dict, request_id: str):
        if "REQUESTER" not in profile.get("roles", []):
            raise PermissionError("Requester role required")
        return self._agent.get_candidate_matches(user_id=profile["user_id"], request_id=request_id)

    def confirm_save(self, profile: dict, request_id: str, listing_id: str):
        if "REQUESTER" not in profile.get("roles", []):
            raise PermissionError("Requester role required")
        return self._agent.confirm_save(
            user_id=profile["user_id"], request_id=request_id, listing_id=listing_id,
        )
