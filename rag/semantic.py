"""Stage 7 v2 input — semantic_score per (request_id, listing_id) from AI Search.

For every open Request, the cleaned request_text is searched inside the Request's own category.
Retrieved listings get semantic_score = the search score clamped to [0, 1]; listings that were
not retrieved in the top K are simply absent (Gold treats absent as 0 — nothing is invented).
"""

from typing import Dict, List, Optional


def clamp01(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def semantic_rows(request_id: str, results: List[Dict]) -> List[tuple]:
    """search_listing_context() output -> (request_id, listing_id, semantic_score, retrieval_rank)."""
    rows, seen = [], set()
    for rank, r in enumerate(results, 1):
        score = clamp01(r.get("score"))
        if score is None or r["listing_id"] in seen:
            continue
        seen.add(r["listing_id"])
        rows.append((request_id, r["listing_id"], round(score, 4), rank))
    return rows
