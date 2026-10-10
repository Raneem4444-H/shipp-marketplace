"""SHIPP reservation unit tests (mock DB; does not prove actual concurrency)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from services.reservation_service import ReservationError, ReservationService

NOW = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
PROFILE = {"user_id": "requester-1", "roles": ["REQUESTER"]}
LISTING = ("donor-1", "AVAILABLE", "FURNITURE", None, None)
REQUEST = ("FURNITURE",)
NEW_ID = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
OLD_ID = UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")


def mock_db(fetchone_rows, *, expired_ids=()):
    connect = MagicMock()
    conn = connect.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = fetchone_rows
    cur.fetchall.return_value = [(item,) for item in expired_ids]
    return connect, cur


def invoke(connect, *, profile=PROFILE, listing_id="listing-1", request_id="request-1"):
    return ReservationService(connect).reserve(
        listing_id=listing_id, request_id=request_id,
        verified_profile=profile,
    )


def executed(cur, fragment):
    return [call for call in cur.execute.call_args_list if fragment in call.args[0]]


def ok_rows(*, listing=LISTING, expiry=None):
    return [listing, (1,), REQUEST, (NOW,), None, None,
            (NEW_ID, "HELD", expiry or NOW + timedelta(hours=24))]


def test_success_creates_hold_and_audit_in_same_transaction():
    connect, cur = mock_db(ok_rows())
    result = invoke(connect)
    assert result == {
        "reservation_id": str(NEW_ID), "status": "HELD",
        "hold_expires_at": NOW + timedelta(hours=24),
        "already_reserved": False,
    }
    assert executed(cur, "FOR UPDATE")
    assert executed(cur, "INSERT INTO shipp.reservations")
    assert executed(cur, "INSERT INTO shipp.reservation_events")
    assert not executed(cur, "UPDATE shipp.listings")


def test_rejected_unverified_identity_does_not_access_database():
    connect, cur = mock_db([])
    with pytest.raises(ReservationError, match="Verified requester sign-in"):
        invoke(connect, profile=None)
    assert not cur.execute.called


def test_rejected_missing_user_id_does_not_access_database():
    connect, cur = mock_db([])
    with pytest.raises(ReservationError, match="Verified requester sign-in"):
        invoke(connect, profile={"roles": ["REQUESTER"]})
    assert not cur.execute.called


def test_non_requester_role_rejected():
    connect, cur = mock_db([])
    with pytest.raises(ReservationError, match="Verified requester role"):
        invoke(connect, profile={"user_id": "requester-1", "roles": ["DONOR"]})
    assert not cur.execute.called


def test_missing_listing_or_request_id_rejected():
    connect, cur = mock_db([])
    with pytest.raises(ReservationError, match="Listing and request IDs"):
        invoke(connect, listing_id="")
    with pytest.raises(ReservationError, match="Listing and request IDs"):
        invoke(connect, request_id=" ")
    assert not cur.execute.called


def test_listing_not_found():
    connect, cur = mock_db([None])
    with pytest.raises(ReservationError, match="Item not found"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_inactive_or_missing_role_rejected():
    connect, cur = mock_db([LISTING, None])
    with pytest.raises(ReservationError, match="not authorized"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_donor_cannot_claim_own_listing():
    listing = ("requester-1", "AVAILABLE", "FURNITURE", None, None)
    connect, cur = mock_db([listing, (1,)])
    with pytest.raises(ReservationError, match="own item"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_requester_cannot_use_another_users_request():
    connect, cur = mock_db([LISTING, (1,), None])
    with pytest.raises(ReservationError, match="No eligible request"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_mismatched_category_rejected():
    connect, cur = mock_db([LISTING, (1,), ("BOOKS",)])
    with pytest.raises(ReservationError, match="category does not match"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_unavailable_listing_rejected():
    listing = ("donor-1", "UNAVAILABLE", "FURNITURE", None, None)
    connect, cur = mock_db([listing, (1,), REQUEST, (NOW,)])
    with pytest.raises(ReservationError, match="not available"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_listing_availability_has_expired():
    listing = ("donor-1", "AVAILABLE", "FURNITURE", None, NOW)
    connect, cur = mock_db([listing, (1,), REQUEST, (NOW,)])
    with pytest.raises(ReservationError, match="availability has expired"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_future_listing_not_yet_available():
    listing = ("donor-1", "AVAILABLE", "FURNITURE", NOW + timedelta(hours=1), None)
    connect, cur = mock_db([listing, (1,), REQUEST, (NOW,)])
    with pytest.raises(ReservationError, match="not available yet"):
        invoke(connect)


def test_competing_reservation_rejected():
    connect, cur = mock_db([
        LISTING, (1,), REQUEST, (NOW,), None,
        (OLD_ID, "requester-2", "request-2", "HELD", NOW + timedelta(hours=2)),
    ])
    with pytest.raises(ReservationError, match="already reserved"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_idempotent_retry_returns_existing_hold():
    expires = NOW + timedelta(hours=2)
    connect, cur = mock_db([
        LISTING, (1,), REQUEST, (NOW,), None,
        (OLD_ID, "requester-1", "request-1", "HELD", expires),
    ])
    assert invoke(connect) == {
        "reservation_id": str(OLD_ID), "status": "HELD",
        "hold_expires_at": expires, "already_reserved": True,
    }
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_confirmed_retry_returns_existing_confirmation():
    expires = NOW + timedelta(hours=2)
    connect, cur = mock_db([
        LISTING, (1,), REQUEST, (NOW,), None,
        (OLD_ID, "requester-1", "request-1", "CONFIRMED", expires),
    ])
    result = invoke(connect)
    assert result["status"] == "CONFIRMED"
    assert result["already_reserved"] is True


def test_expired_hold_is_audited_and_replaced():
    connect, cur = mock_db(ok_rows(), expired_ids=[OLD_ID])
    result = invoke(connect)
    assert result["status"] == "HELD"
    assert executed(cur, "status = 'EXPIRED'")
    event_calls = executed(cur, "INSERT INTO shipp.reservation_events")
    assert len(event_calls) == 2
    assert event_calls[0].args[1] == (OLD_ID,)


def test_completed_reservation_is_not_claimable():
    connect, cur = mock_db([LISTING, (1,), REQUEST, (NOW,), (1,)])
    with pytest.raises(ReservationError, match="already been delivered"):
        invoke(connect)
    assert not executed(cur, "INSERT INTO shipp.reservations")


def test_hold_expiry_capped_by_donor_availability():
    cutoff = NOW + timedelta(hours=3)
    listing = ("donor-1", "AVAILABLE", "FURNITURE", None, cutoff)
    connect, cur = mock_db(ok_rows(listing=listing, expiry=cutoff))
    result = invoke(connect)
    assert result["hold_expires_at"] == cutoff
    call = executed(cur, "INSERT INTO shipp.reservations")[0]
    assert call.args[1][-1] == cutoff


def test_request_filter_checks_postgres_date_and_valid_states():
    connect, _ = mock_db(ok_rows())
    invoke(connect)
    cur = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    sql = executed(cur, "FROM shipp.requests")[0].args[0]
    assert "need_by_date >= CURRENT_DATE" in sql
    assert "MATCHES_AVAILABLE" in sql and "ITEM_SAVED" in sql


def test_audit_insert_exception_causes_transaction_rollback():
    connect, cur = mock_db(ok_rows())
    def fail_audit(sql, params=None):
        if "INSERT INTO shipp.reservation_events" in sql:
            raise RuntimeError("Audit failed")
        return None

    cur.execute.side_effect = fail_audit
    with pytest.raises(RuntimeError, match="Audit failed"):
        invoke(connect)
    assert executed(cur, "INSERT INTO shipp.reservations")
    # A real psycopg connection manager rolls the transaction back on exception.
    manager = connect.return_value
    assert manager.__exit__.called
    assert manager.__exit__.call_args.args[0] is RuntimeError
