"""Stage 10 READ tool — search_listing_context(): semantic Listing context from AI Search.

This is the function the Agent calls. It has no side effects, returns only listings that exist in
the index (each with its listing_id for traceability), and returns [] rather than guessing.
The Agent must still call get_listing_status() in Lakebase before recommending or saving.
"""

import json
from typing import Dict, List, Optional

from config.settings import (
    SEARCH_DEFAULT_K,
    SEARCH_MAX_K,
    SEARCH_MAX_QUERY_CHARS,
    SEARCH_RETURN_COLUMNS,
    SEARCH_SNIPPET_CHARS,
)
from config.tables import VS_INDEX_NAME
from rag.text import clean_text


def validate_query(query: str, k: int) -> str:
    cleaned = clean_text(query, SEARCH_MAX_QUERY_CHARS)
    if not cleaned:
        raise ValueError("query must be a non-empty string")
    if not isinstance(k, int) or not 1 <= k <= SEARCH_MAX_K:
        raise ValueError(f"k must be an integer between 1 and {SEARCH_MAX_K}")
    return cleaned


def rows_from_query_response(resp: Dict) -> List[Dict]:
    """Vector Search query response (as_dict) -> list of {column: value}, score included."""
    columns = [c["name"] for c in (resp.get("manifest") or {}).get("columns", [])]
    data = (resp.get("result") or {}).get("data_array") or []
    return [dict(zip(columns, row)) for row in data]


def to_context(rows: List[Dict]) -> List[Dict]:
    out = []
    for r in rows:
        if not r.get("listing_id"):
            continue  # untraceable result: drop, never pass to the Agent
        text = r.get("search_text") or ""
        out.append({
            "listing_id": r["listing_id"],
            "title": r.get("title"),
            "category": r.get("category"),
            "condition": r.get("condition"),
            "status": r.get("status"),
            "snippet": text[:SEARCH_SNIPPET_CHARS],
            "score": float(r["score"]) if r.get("score") is not None else None,
        })
    return sorted(out, key=lambda x: (x["score"] is None, -(x["score"] or 0.0)))


def search_listing_context(query: str, k: int = SEARCH_DEFAULT_K, category: Optional[str] = None,
                           index_name: str = VS_INDEX_NAME, workspace_client=None) -> List[Dict]:
    """Semantic search over AVAILABLE listings.

    Args:
        query: natural-language need, e.g. "small table for a studio kitchen". PII is redacted first.
        k: number of results, 1..SEARCH_MAX_K.
        category: optional exact category filter (UPPER_SNAKE, e.g. "FURNITURE").
    Returns:
        [{listing_id, title, category, condition, status, snippet, score}, ...] best first; [] if none.
    """
    cleaned = validate_query(query, k)
    if workspace_client is None:
        from databricks.sdk import WorkspaceClient

        workspace_client = WorkspaceClient()
    kwargs = {"index_name": index_name, "columns": SEARCH_RETURN_COLUMNS,
              "query_text": cleaned, "num_results": k}
    if category:
        kwargs["filters_json"] = json.dumps({"category": category})
    resp = workspace_client.vector_search_indexes.query_index(**kwargs)
    return to_context(rows_from_query_response(resp.as_dict()))
