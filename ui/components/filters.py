"""Shared filter vocabulary and normalization for the SHIPP catalog."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogFilters:
    query: str = ""
    category: str | None = None
    condition: str | None = None

    @classmethod
    def from_controls(cls, query: str, category: str, condition: str):
        return cls(
            query=query.strip(),
            category=None if category == "All categories" else category,
            condition=None if condition == "All conditions" else condition,
        )
