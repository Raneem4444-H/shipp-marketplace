"""Retrieval parsing, the READ tool contract, semantic rows and eval metrics — no network, no Spark."""

import json

import pytest

from rag.evaluation import hit_at_k, reciprocal_rank, summarize
from rag.retrieval import rows_from_query_response, search_listing_context, to_context, validate_query
from rag.semantic import clamp01, semantic_rows

RESP = {
    "manifest": {"columns": [{"name": c} for c in
                             ["listing_id", "title", "category", "condition", "status", "search_text", "score"]]},
    "result": {"data_array": [
        ["demo-listing-002", "Four-Seater", "FURNITURE", "GOOD", "AVAILABLE", "Compact table", 0.61],
        ["demo-listing-001", "Wooden Dining Table", "FURNITURE", "GOOD", "AVAILABLE", "Solid table", 0.83],
        [None, "ghost", None, None, None, "x", 0.99],
    ]},
}


class FakeResult:
    def __init__(self, d):
        self._d = d

    def as_dict(self):
        return self._d


class FakeIndexes:
    def __init__(self):
        self.kwargs = None

    def query_index(self, **kwargs):
        self.kwargs = kwargs
        return FakeResult(RESP)


class FakeWorkspace:
    def __init__(self):
        self.vector_search_indexes = FakeIndexes()


def test_rows_and_context_are_traceable_and_sorted():
    ctx = to_context(rows_from_query_response(RESP))
    assert [c["listing_id"] for c in ctx] == ["demo-listing-001", "demo-listing-002"]  # ghost row dropped
    assert ctx[0]["score"] == 0.83 and ctx[0]["snippet"] == "Solid table"
    assert rows_from_query_response({}) == []


def test_search_redacts_query_and_applies_filter():
    w = FakeWorkspace()
    out = search_listing_context("table, call +971 50 123 4567", k=2, category="FURNITURE", workspace_client=w)
    sent = w.vector_search_indexes.kwargs
    assert "971" not in sent["query_text"] and sent["num_results"] == 2
    assert json.loads(sent["filters_json"]) == {"category": "FURNITURE"}
    assert out[0]["listing_id"] == "demo-listing-001"


def test_validate_query_rejects_bad_input():
    with pytest.raises(ValueError):
        validate_query("   ", 3)
    with pytest.raises(ValueError):
        validate_query("desk", 0)
    with pytest.raises(ValueError):
        validate_query("desk", 11)


def test_semantic_rows():
    assert clamp01(1.4) == 1.0 and clamp01(-0.2) == 0.0 and clamp01(None) is None
    rows = semantic_rows("r1", [{"listing_id": "a", "score": 0.9}, {"listing_id": "a", "score": 0.5},
                                {"listing_id": "b", "score": None}, {"listing_id": "c", "score": 0.3}])
    assert rows == [("r1", "a", 0.9, 1), ("r1", "c", 0.3, 4)]


def test_eval_metrics():
    assert hit_at_k(["x", "a"], ["a"], 2) == 1 and hit_at_k(["x", "a"], ["a"], 1) == 0
    assert reciprocal_rank(["x", "a"], ["a"]) == 0.5 and reciprocal_rank([], ["a"]) == 0.0
    s = summarize([{"hit": 1, "rr": 1.0, "latency_ms": 10, "positive": True},
                   {"hit": 0, "rr": 0.0, "latency_ms": 30, "positive": True},
                   {"hit": 0, "rr": 0.0, "latency_ms": 20, "positive": False}])
    assert s["positive_cases"] == 2 and s["hit_rate"] == 0.5 and s["mrr"] == 0.5 and s["max_latency_ms"] == 30
