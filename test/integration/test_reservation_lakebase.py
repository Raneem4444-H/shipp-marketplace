"""SHIPP reservation integration tests — isolated Lakebase DEV only.

Repository path: test/integration/test_reservation_lakebase.py

Prerequisites:
* Databricks CLI profile `shipp-raneem-dev` is authenticated.
* Lakebase branch `shipp-reservation-dev` is READY and contains migration 011.
* Python dependencies from the SHIPP requirements are installed.

Default behavior: SKIP with no database access or writes.
Explicit real-DEV execution (from repository root):

    SHIPP_ALLOW_DEV_DB_WRITE=YES python -m pytest -q -s \
        test/integration/test_reservation_lakebase.py

Writes exclusively to the API-verified DEV endpoint, with test-specific user,
request, and listing IDs. Tests are independent and always attempt cleanup.
Hard termination (SIGKILL/power loss) can prevent cleanup: retain the printed
TEST_RUN_PREFIX if manual recovery is required. Never run on production.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest

# Import guard must precede the application import and all database discovery.
if os.environ.get("SHIPP_ALLOW_DEV_DB_WRITE") != "YES":
    pytest.skip(
        "Real Lakebase writes are disabled; set SHIPP_ALLOW_DEV_DB_WRITE=YES explicitly",
        allow_module_level=True,
    )

from services.reservation_service import ReservationError, ReservationService

PROJECT = "projects/shipp-capstone-v1"
DEV_BRANCH = f"{PROJECT}/branches/shipp-reservation-dev"
PROD_BRANCH = f"{PROJECT}/branches/production"
PROFILE = "shipp-raneem-dev"
DATABASE = "databricks_postgres"


def _cli(*args: str) -> Any:
    """Use the named authenticated CLI profile; never parse shell env PGHOST."""
    result = subprocess.run(
        ["databricks", *args, "--profile", PROFILE, "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    )
    return json.loads(result.stdout)


def _read_write_endpoint(branch_name: str) -> tuple[str, str]:
    """Retrieve endpoint and host *from the named branch*, not local env."""
    data = _cli("postgres", "list-endpoints", branch_name)
    endpoints = data if isinstance(data, list) else data.get("endpoints", [])
    matches: list[tuple[str, str]] = []
    for endpoint in endpoints:
        name = endpoint.get("name", "")
        if not isinstance(name, str) or not name.startswith(
            branch_name + "/endpoints/"
        ):
            raise RuntimeError("Endpoint belongs to an unexpected Lakebase branch")
        detail = _cli("postgres", "get-endpoint", name)
        if detail.get("name") != name:
            raise RuntimeError("Endpoint identity changed during discovery")
        status = detail.get("status") or {}
        kind = str(status.get("endpoint_type", ""))
        if kind not in {"ENDPOINT_TYPE_READ_WRITE", "READ_WRITE"}:
            continue
        if status.get("disabled") is True:
            continue
        host = (status.get("hosts") or {}).get("host")
        if not isinstance(host, str) or not host.strip():
            raise RuntimeError("Read-write Lakebase endpoint has no hostname")
        matches.append((name, host))

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one enabled read-write endpoint in {branch_name}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _dev_connection_factory():
    """Refuse all connections unless the expected independent DEV branch is verified."""
    import psycopg
    from databricks.sdk import WorkspaceClient

    branch = _cli("postgres", "get-branch", DEV_BRANCH)
    info = branch.get("status") or {}
    if not (
        branch.get("name") == DEV_BRANCH
        and info.get("current_state") == "READY"
        and info.get("default") is False
        and info.get("is_protected") is False
        and info.get("source_branch") == PROD_BRANCH
    ):
        raise RuntimeError("DEV Lakebase branch check failed: aborting all writes")

    dev_endpoint, dev_host = _read_write_endpoint(DEV_BRANCH)
    _, prod_host = _read_write_endpoint(PROD_BRANCH)
    if dev_host == prod_host:
        raise RuntimeError("DEV and production resolved to the same host: abort")

    client = WorkspaceClient(profile=PROFILE)
    username = client.current_user.me().user_name
    if not username:
        raise RuntimeError("Authenticated Databricks user could not be resolved")

    # Each actual connection obtains a valid short-lived OAuth database token.
    # Refresh safely even when simultaneous test workers open connections.
    token_lock = threading.Lock()
    cache = {"token": None, "refreshed_at": 0.0}

    def _password() -> str:
        with token_lock:
            if cache["token"] and time.monotonic() - cache["refreshed_at"] < 40 * 60:
                return str(cache["token"])
            credential = client.postgres.generate_database_credential(
                endpoint=dev_endpoint
            )
            if not credential.token:
                raise RuntimeError("Unable to generate DEV database credential")
            cache["token"] = credential.token
            cache["refreshed_at"] = time.monotonic()
            return str(credential.token)

    def connect():
        # Intentionally DO NOT read PGHOST, PGUSER, PGPASSWORD or the
        # production-oriented ~/.shipp/start_local.py values.
        return psycopg.connect(
            host=dev_host,
            port=5432,
            dbname=DATABASE,
            user=username,
            password=_password(),
            sslmode="require",
            connect_timeout=15,
            application_name="shipp_reservation_dev_test",
        )

    print(f"\nVERIFIED_DEV_ENDPOINT={dev_endpoint}")
    return connect


def _check_schema(connect) -> None:
    """Read-only contract check before constructing *any* test data."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT current_database(),
                      to_regclass('shipp.reservations'),
                      to_regclass('shipp.reservation_events'),
                      to_regclass('shipp.delivery_quotes'),
                      to_regclass('shipp.ux_shipp_one_active_reservation_per_listing')"""
        )
        database, *objects = cur.fetchone()
        if database != DATABASE or any(item is None for item in objects):
            raise RuntimeError("DEV database or reservation migration 011 mismatch")
        cur.execute(
            "SELECT role_id FROM shipp.roles WHERE role_id IN ('DONOR', 'REQUESTER')"
        )
        if {row[0] for row in cur.fetchall()} != {"DONOR", "REQUESTER"}:
            raise RuntimeError("DEV database is missing a required test role")
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='shipp' AND table_name='reservations'
                 AND column_name IN ('created_at', 'hold_expires_at', 'status')"""
        )
        if len(cur.fetchall()) != 3:
            raise RuntimeError("Expected current reservation schema not found")


@pytest.fixture(scope="session")
def dev_connect():
    connect = _dev_connection_factory()
    _check_schema(connect)
    return connect


@pytest.fixture
def test_entities(dev_connect):
    """Fresh committed DEV-only records PER TEST; no order dependence."""
    prefix = "it" + uuid4().hex[:14]
    ids = {
        "donor": prefix + "d",
        "alice": prefix + "a",
        "bob": prefix + "b",
        "alice_request": prefix + "r1",
        "bob_request": prefix + "r2",
        "listing": prefix + "l",
    }
    user_ids = [ids[key] for key in ("donor", "alice", "bob")]
    request_ids = [ids[key] for key in ("alice_request", "bob_request")]
    listing_id = ids["listing"]
    start = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"\nTEST_RUN_PREFIX={prefix} (DEV only)")

    # All fixture creation is one transaction: if any statement fails,
    # previous fixture inserts are rolled back by psycopg automatically.
    with dev_connect() as conn, conn.cursor() as cur:
        for key in ("donor", "alice", "bob"):
            cur.execute(
                "INSERT INTO shipp.users (user_id, name, is_active) "
                "VALUES (%s, %s, TRUE)",
                (ids[key], f"SHIPP INTEGRATION TEST {prefix} {key}"),
            )
        for key, role in (("donor", "DONOR"), ("alice", "REQUESTER"),
                          ("bob", "REQUESTER")):
            cur.execute(
                "INSERT INTO shipp.user_roles (user_id, role_id) VALUES (%s, %s)",
                (ids[key], role),
            )
        for key, owner in (("alice_request", "alice"), ("bob_request", "bob")):
            cur.execute(
                """INSERT INTO shipp.requests
                       (request_id, requester_id, request_text, category,
                        need_by_date, status)
                       VALUES (%s, %s, %s, 'BOOKS', %s, 'OPEN')""",
                (ids[key], ids[owner], f"INTEGRATION TEST {prefix}",
                 (start + timedelta(days=3)).date()),
            )
        cur.execute(
            """INSERT INTO shipp.listings
                   (listing_id, donor_id, title, category,
                    available_from, available_until, status)
                   VALUES (%s, %s, %s, 'BOOKS', %s, %s, 'AVAILABLE')""",
            (listing_id, ids["donor"], f"INTEGRATION TEST {prefix}",
             start - timedelta(hours=1), start + timedelta(days=3)),
        )

    try:
        yield {"connect": dev_connect, "ids": ids}
    finally:
        # Delete ONLY records created by this test, FK child tables first.
        # In a hard process kill, pytest fixture teardown cannot execute.
        try:
            with dev_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """DELETE FROM shipp.delivery_quotes
                       WHERE reservation_id IN
                         (SELECT reservation_id FROM shipp.reservations
                          WHERE listing_id = %s)""",
                    (listing_id,),
                )
                cur.execute(
                    """DELETE FROM shipp.reservation_events
                       WHERE reservation_id IN
                         (SELECT reservation_id FROM shipp.reservations
                          WHERE listing_id = %s)""",
                    (listing_id,),
                )
                cur.execute(
                    "DELETE FROM shipp.reservations WHERE listing_id = %s",
                    (listing_id,),
                )
                cur.execute(
                    "DELETE FROM shipp.listings WHERE listing_id = %s",
                    (listing_id,),
                )
                cur.execute(
                    "DELETE FROM shipp.requests WHERE request_id = ANY(%s)",
                    (request_ids,),
                )
                cur.execute(
                    "DELETE FROM shipp.user_roles WHERE user_id = ANY(%s)",
                    (user_ids,),
                )
                cur.execute(
                    "DELETE FROM shipp.users WHERE user_id = ANY(%s)",
                    (user_ids,),
                )
                cur.execute(
                    "SELECT COUNT(*) FROM shipp.reservations WHERE listing_id = %s",
                    (listing_id,),
                )
                assert cur.fetchone()[0] == 0, "Reservation cleanup incomplete"
                cur.execute(
                    "SELECT COUNT(*) FROM shipp.users WHERE user_id = ANY(%s)",
                    (user_ids,),
                )
                assert cur.fetchone()[0] == 0, "Test user cleanup incomplete"
            print(f"CLEANUP_OK={prefix}")
        except Exception:
            print(
                f"CLEANUP_FAILED={prefix} — inspect only IDs starting with "
                f"this prefix on the DEV branch. Do not clean production."
            )
            raise


def _profile(ids: dict[str, str], user_key: str):
    # Synthetic profiles are ONLY for backend DB transaction tests.
    # This does not validate OIDC sign-in or the real UI security boundary.
    return {"user_id": ids[user_key], "roles": ["REQUESTER"]}


def _reservation_and_audit(connect, listing_id: str):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT r.reservation_id, r.status, e.event_type
               FROM shipp.reservations r
               JOIN shipp.reservation_events e
                 ON e.reservation_id = r.reservation_id
               WHERE r.listing_id = %s
               ORDER BY e.occurred_at, e.event_id""",
            (listing_id,),
        )
        return cur.fetchall()


def test_real_hold_inserts_matching_audit(test_entities):
    connect, ids = test_entities["connect"], test_entities["ids"]
    result = ReservationService(connect).reserve(
        listing_id=ids["listing"],
        request_id=ids["alice_request"],
        verified_profile=_profile(ids, "alice"),
    )
    assert result["status"] == "HELD"
    assert result["already_reserved"] is False
    assert result["reservation_id"]
    remaining = (result["hold_expires_at"] - datetime.now(timezone.utc)).total_seconds()
    assert 0 < remaining <= 86400
    audit = _reservation_and_audit(connect, ids["listing"])
    assert len(audit) == 1
    assert str(audit[0][0]) == result["reservation_id"]
    assert audit[0][1:] == ("HELD", "HELD")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM shipp.listings WHERE listing_id = %s",
            (ids["listing"],),
        )
        assert cur.fetchone()[0] == "AVAILABLE"  # donor-controlled status


def test_idempotent_retry_and_competitor_rejected(test_entities):
    """Independent test: creates its OWN initial reservation."""
    connect, ids = test_entities["connect"], test_entities["ids"]
    service = ReservationService(connect)
    first = service.reserve(
        listing_id=ids["listing"],
        request_id=ids["alice_request"],
        verified_profile=_profile(ids, "alice"),
    )
    again = service.reserve(
        listing_id=ids["listing"],
        request_id=ids["alice_request"],
        verified_profile=_profile(ids, "alice"),
    )
    assert again["already_reserved"] is True
    assert again["reservation_id"] == first["reservation_id"]
    with pytest.raises(ReservationError, match="already reserved"):
        service.reserve(
            listing_id=ids["listing"],
            request_id=ids["bob_request"],
            verified_profile=_profile(ids, "bob"),
        )
    assert len(_reservation_and_audit(connect, ids["listing"])) == 1


def test_two_requesters_race_only_one_wins(test_entities):
    connect, ids = test_entities["connect"], test_entities["ids"]
    barrier = Barrier(2)

    def attempt(user_key: str, request_key: str):
        barrier.wait(timeout=30)
        try:
            result = ReservationService(connect).reserve(
                listing_id=ids["listing"],
                request_id=ids[request_key],
                verified_profile=_profile(ids, user_key),
            )
            return "HELD" if result["status"] == "HELD" else "UNEXPECTED"
        except ReservationError as exc:
            if "already reserved" not in str(exc):
                raise
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(attempt, "alice", "alice_request")
        b = pool.submit(attempt, "bob", "bob_request")
        outcomes = [a.result(timeout=75), b.result(timeout=75)]
    assert sorted(outcomes) == ["HELD", "REJECTED"], outcomes
    assert len(_reservation_and_audit(connect, ids["listing"])) == 1


class _FailOnAuditCursor:
    """Inject an audit failure; preserve real psycopg INSERT + transaction."""

    def __init__(self, real_cursor):
        self._real = real_cursor

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)

    def execute(self, sql, params=None):
        if "INSERT INTO shipp.reservation_events" in str(sql):
            raise RuntimeError("INJECTED_AUDIT_FAILURE")
        return self._real.execute(sql, params)

    def __getattr__(self, attr):
        return getattr(self._real, attr)


class _FailOnAuditConnection:
    def __init__(self, real_connection):
        self._real = real_connection

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)

    def cursor(self):
        return _FailOnAuditCursor(self._real.cursor())


def test_audit_write_failure_rolls_back_reservation(test_entities):
    connect, ids = test_entities["connect"], test_entities["ids"]
    failed_connect = lambda: _FailOnAuditConnection(connect())
    with pytest.raises(RuntimeError, match="INJECTED_AUDIT_FAILURE"):
        ReservationService(failed_connect).reserve(
            listing_id=ids["listing"],
            request_id=ids["alice_request"],
            verified_profile=_profile(ids, "alice"),
        )
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM shipp.reservations WHERE listing_id = %s",
            (ids["listing"],),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            """SELECT COUNT(*) FROM shipp.reservation_events e
               JOIN shipp.reservations r
                 ON r.reservation_id = e.reservation_id
               WHERE r.listing_id = %s""",
            (ids["listing"],),
        )
        assert cur.fetchone()[0] == 0
