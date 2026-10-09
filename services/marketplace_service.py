"""Read-only catalog facade around the existing Lakebase MarketplaceRepo.

Do not use the AI Search index as an operational authority for availability.
Agent recommendations and saves continue to use trusted Gold and Lakebase.
"""
from __future__ import annotations

from typing import Any


class MarketplaceService:
    def __init__(self, repo: Any) -> None:
        self._repo = repo

    def list_available_listings(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        query: str | None = None,
        category: str | None = None,
        condition: str | None = None,
        donor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._repo.list_available_listings(
            limit=limit, offset=offset, query=query,
            category=category, condition=condition, donor_id=donor_id,
        )
