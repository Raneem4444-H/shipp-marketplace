"""Fail closed when an AI Search index references a missing backing endpoint."""

from types import SimpleNamespace

import pytest

from rag.index import _is_not_found, ensure_delta_sync_index, endpoint_state, index_status


INDEX = "bootcamp_students.shipp_gold.gold_listing_search_docs_index"
ENDPOINT = "shipp-vs"


class NotFound(Exception):
    pass


class PermissionDenied(Exception):
    pass


class FakeIndexes:
    def __init__(self, *, error=None, existing=None):
        self.error = error
        self.existing = existing
        self.create_calls = 0

    def get_index(self, *, index_name):
        assert index_name == INDEX
        if self.error:
            raise self.error
        return self.existing

    def create_index(self, **kwargs):
        self.create_calls += 1
        raise AssertionError("Unexpected index creation")


class FakeEndpoints:
    def __init__(self, *, error=None, state="ONLINE"):
        self.error = error
        self.state = state

    def get_endpoint(self, *, endpoint_name):
        assert endpoint_name == ENDPOINT
        if self.error:
            raise self.error
        return SimpleNamespace(endpoint_status=SimpleNamespace(state=self.state))


def test_exact_index_not_found_is_recognized():
    err = NotFound(f"AI Search index {INDEX} not found")
    assert _is_not_found(err, resource_type="index", name=INDEX)


def test_exact_endpoint_not_found_is_recognized():
    err = NotFound(f"AI Search endpoint {ENDPOINT} does not exist")
    assert _is_not_found(err, resource_type="endpoint", name=ENDPOINT)


def test_missing_backing_endpoint_is_not_missing_index():
    err = NotFound("AI Search endpoint d147f6c1-465c-4b79-aa75-4cf35e49536a not found")
    assert not _is_not_found(err, resource_type="index", name=INDEX)


@pytest.mark.parametrize(
    "error",
    [
        NotFound("Not Found"),
        NotFound("AI Search index some-other-index not found"),
        PermissionDenied(f"AI Search index {INDEX} not found"),
        RuntimeError(f"AI Search index {INDEX} not found"),
    ],
)
def test_ambiguous_and_unrelated_errors_are_not_missing_index(error):
    assert not _is_not_found(error, resource_type="index", name=INDEX)


def test_index_status_returns_none_for_explicitly_missing_index():
    w = SimpleNamespace(vector_search_indexes=FakeIndexes(
        error=NotFound(f"AI Search index {INDEX} does not exist"),
    ))
    assert index_status(w, INDEX) is None


def test_existing_index_can_be_reused():
    w = SimpleNamespace(vector_search_indexes=FakeIndexes(
        existing=SimpleNamespace(
            status=SimpleNamespace(ready=True, indexed_row_count=7, message=None)
        )
    ))
    assert index_status(w, INDEX) == {
        "ready": True,
        "indexed_row_count": 7,
        "message": None,
    }
    assert not ensure_delta_sync_index(
        w, INDEX, ENDPOINT, "catalog.schema.docs",
        "listing_id", "search_text", "embedding-model", ["listing_id"],
    )


def test_backing_endpoint_not_found_does_not_trigger_index_creation():
    api = FakeIndexes(error=NotFound(
        "AI Search endpoint d147f6c1-465c-4b79-aa75-4cf35e49536a not found"
    ))
    w = SimpleNamespace(vector_search_indexes=api)
    with pytest.raises(RuntimeError, match="backing"):
        ensure_delta_sync_index(
            w, INDEX, ENDPOINT, "catalog.schema.docs",
            "listing_id", "search_text", "embedding-model", ["listing_id"],
        )
    assert api.create_calls == 0


def test_permission_error_is_not_swallowed():
    w = SimpleNamespace(vector_search_indexes=FakeIndexes(
        error=PermissionDenied(f"AI Search index {INDEX} not found")
    ))
    with pytest.raises(PermissionDenied):
        index_status(w, INDEX)


def test_endpoint_state_handles_only_target_not_found():
    w = SimpleNamespace(vector_search_endpoints=FakeEndpoints(
        error=NotFound(f"AI Search endpoint {ENDPOINT} not found")
    ))
    assert endpoint_state(w, ENDPOINT) is None

    w.vector_search_endpoints = FakeEndpoints(error=NotFound(
        "AI Search endpoint a-different-endpoint not found"
    ))
    with pytest.raises(NotFound):
        endpoint_state(w, ENDPOINT)
