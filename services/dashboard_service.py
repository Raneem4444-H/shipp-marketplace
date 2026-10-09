"""Role-scoped dashboard reads using existing Lakebase repository contracts."""
from __future__ import annotations

from typing import Any


class DashboardService:
    def __init__(self, repo: Any) -> None:
        self._repo = repo

    def donor_listings(self, profile: dict, limit: int = 30) -> list[dict]:
        if "DONOR" not in profile.get("roles", []):
            raise PermissionError("Donor role required")
        return self._repo.list_available_listings(donor_id=profile["user_id"], limit=limit)

    def requester_requests(self, profile: dict, limit: int = 20) -> list[dict]:
        if "REQUESTER" not in profile.get("roles", []):
            raise PermissionError("Requester role required")
        return self._repo.list_requests(profile["user_id"], limit=limit)

    def requester_saves(self, profile: dict, request_id: str) -> list[dict]:
        if "REQUESTER" not in profile.get("roles", []):
            raise PermissionError("Requester role required")
        requests = self._repo.list_requests(profile["user_id"], limit=100)
        if request_id not in {str(row["request_id"]) for row in requests}:
            raise PermissionError("Request not owned by current requester")
        return self._repo.list_saved_items(profile["user_id"], request_id)
