"""Semantic listing context from Databricks AI Search (Vector Search).

Search is always filtered to the listing_ids that are already Gold candidates
for the active request. AI Search adds *context* (condition details, image-
derived attributes); it never introduces listings that failed eligibility.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from shipp.agent.config import validate_identifier
from shipp.agent.contracts import SEARCH_DOC_COLUMNS, ContractError, SearchHit

SNIPPET_CHARS = 400


def parse_search_response(resp: Any) -> list[SearchHit]:
    """Parse a databricks-sdk QueryVectorIndexResponse.

    The service appends a similarity `score` column after the requested columns.
    """
    manifest = getattr(resp, "manifest", None)
    columns = [c.name for c in (getattr(manifest, "columns", None) or [])]
    if "listing_id" not in columns:
        raise ContractError("AI Search response has no listing_id column")
    result = getattr(resp, "result", None)
    rows = getattr(result, "data_array", None) or []

    hits: list[SearchHit] = []
    for row in rows:
        rec = dict(zip(columns, row, strict=False))
        text = str(rec.get("search_text") or "")
        hits.append(
            SearchHit(
                listing_id=str(rec["listing_id"]),
                title=rec.get("title"),
                category=rec.get("category"),
                condition=rec.get("condition"),
                snippet=text[:SNIPPET_CHARS],
                score=float(rec.get("score") or 0.0),
            )
        )
    return hits


class ListingSearch:
    def __init__(self, workspace_client: Any, index_name: str) -> None:
        self._w = workspace_client
        self._index = validate_identifier(index_name, three_part=True)

    def search(self, query: str, *, listing_ids: Sequence[str], k: int) -> list[SearchHit]:
        if not listing_ids:
            return []
        resp = self._w.vector_search_indexes.query_index(
            index_name=self._index,
            columns=list(SEARCH_DOC_COLUMNS),
            query_text=query,
            filters_json=json.dumps({"listing_id": list(listing_ids)}),
            num_results=int(k),
        )
        return parse_search_response(resp)
