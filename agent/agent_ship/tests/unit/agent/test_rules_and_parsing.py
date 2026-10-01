from datetime import timedelta
from types import SimpleNamespace

import pytest

from agent_fakes import NOW, settings
from shipp.agent.config import validate_identifier
from shipp.agent.contracts import (
    CANDIDATE_MATCH_COLUMNS,
    ContractError,
    ListingState,
    RequestState,
)
from shipp.agent.gold import parse_candidate_rows
from shipp.agent.rules import check_listing_saveable, check_request_usable
from shipp.agent.search import parse_search_response


# ---------------------------------------------------------------- rules
def test_listing_available_and_in_window_passes():
    listing = ListingState("l1", "available", NOW + timedelta(days=1))
    assert check_listing_saveable(listing, NOW) is None


@pytest.mark.parametrize("status", ["withdrawn", "expired", "unavailable", "draft"])
def test_listing_not_available_is_rejected(status):
    assert check_listing_saveable(ListingState("l1", status, None), NOW) is not None


def test_listing_past_window_is_rejected():
    listing = ListingState("l1", "available", NOW - timedelta(minutes=1))
    assert "ended" in check_listing_saveable(listing, NOW)


def test_naive_timestamp_is_treated_as_utc():
    naive_future = (NOW + timedelta(hours=1)).replace(tzinfo=None)
    assert check_listing_saveable(ListingState("l1", "available", naive_future), NOW) is None


def test_missing_listing_is_rejected():
    assert check_listing_saveable(None, NOW) is not None


def test_request_of_another_user_looks_missing():
    other = RequestState("r1", "someone-else", "open")
    assert check_request_usable(other, "user-1") == check_request_usable(None, "user-1")


def test_closed_request_is_rejected():
    assert check_request_usable(RequestState("r1", "user-1", "closed"), "user-1")


def test_open_request_passes():
    assert check_request_usable(RequestState("r1", "user-1", "open"), "user-1") is None


# ---------------------------------------------------------------- gold parsing
def _row(**overrides):
    base = {
        "request_id": "req-1",
        "listing_id": "l1",
        "title": "Desk",
        "category": "furniture",
        "condition": "good",
        "area": "Al Reem Island",
        "match_score": "0.92",
        "distance_km": "6.4",
        "duration_min": "14",
        "available_until": "2026-09-10T00:00:00Z",
        "computed_at": "2026-09-01T00:00:00Z",
    }
    base.update(overrides)
    return [base[c] for c in CANDIDATE_MATCH_COLUMNS]


def test_parse_candidate_rows_casts_numbers():
    (m,) = parse_candidate_rows([_row()])
    assert m.match_score == pytest.approx(0.92)
    assert m.distance_km == pytest.approx(6.4)
    assert m.to_tool_payload()["route_available"] is True


def test_missing_route_stays_null_not_zero():
    (m,) = parse_candidate_rows([_row(distance_km=None, duration_min=None)])
    assert m.distance_km is None
    assert m.to_tool_payload()["route_available"] is False


def test_wrong_column_count_is_a_contract_error():
    with pytest.raises(ContractError):
        parse_candidate_rows([_row()[:-1]])


# ---------------------------------------------------------------- search parsing
def test_parse_search_response_reads_score_column():
    cols = ["listing_id", "title", "category", "condition", "search_text", "score"]
    resp = SimpleNamespace(
        manifest=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in cols]),
        result=SimpleNamespace(data_array=[["l1", "Desk", "furniture", "good", "x" * 900, 0.77]]),
    )
    (hit,) = parse_search_response(resp)
    assert hit.listing_id == "l1"
    assert hit.score == pytest.approx(0.77)
    assert len(hit.snippet) == 400


def test_search_response_without_listing_id_is_a_contract_error():
    resp = SimpleNamespace(
        manifest=SimpleNamespace(columns=[SimpleNamespace(name="title")]),
        result=SimpleNamespace(data_array=[]),
    )
    with pytest.raises(ContractError):
        parse_search_response(resp)


# ---------------------------------------------------------------- config
@pytest.mark.parametrize(
    "bad", ["shipp.gold.t; DROP TABLE x", "shipp.gold", "a.b.c.d", "sch-ema.x.y", ""]
)
def test_unsafe_three_part_names_rejected(bad):
    with pytest.raises(ValueError):
        validate_identifier(bad, three_part=True)


def test_settings_reject_unsafe_schema():
    with pytest.raises(ValueError):
        settings(lakebase_schema="bootcamp_shipp; --")
