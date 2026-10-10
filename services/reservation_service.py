"""SHIPP — exclusive, transactional 24-hour item holds.

Database contract:
    lakebase/migrations/011_reservation_quote_foundation_DEV.sql

SECURITY: `verified_profile` MUST come from a trusted server-side identity
resolver (services.identity_service.current_profile), never a demo selector,
form, query parameter, or client-supplied JSON. This service also verifies
active requester role and request ownership in Lakebase.

This module creates HELD reservations and audits them; donor approval,
checkout, shipments, and background expiry are separate workstreams.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any


class ReservationError(ValueError):
    """A hold was rejected by an expected business rule."""


def _utc(value: datetime | None) -> datetime | None:
    """Treat the existing naive SHIPP listing timestamps as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ReservationService:
    """Perform atomic Lakebase reservations using a psycopg connection factory."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def reserve(
        self,
        *,
        listing_id: str,
        request_id: str,
        verified_profile: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Create a HELD reservation or return this requester's existing hold.

        Locks the listing first; concurrent claims for the same listing wait.
        PostgreSQL's unique partial index is the final concurrency backstop.
        Changes to reservations and reservation_events commit together.
        """
        if not isinstance(verified_profile, Mapping):
            raise ReservationError("Verified requester sign-in is required.")
        requester_id = verified_profile.get("user_id")
        roles = verified_profile.get("roles")
        if not isinstance(requester_id, str) or not requester_id.strip():
            raise ReservationError("Verified requester sign-in is required.")
        if not isinstance(roles, (list, tuple, set)) or "REQUESTER" not in roles:
            raise ReservationError("Verified requester role is required.")
        if not all(isinstance(value, str) and value.strip()
                   for value in (listing_id, request_id)):
            raise ReservationError("Listing and request IDs are required.")

        with self._connect() as conn, conn.cursor() as cur:
            # Scope time zone to this transaction; no session-wide change.
            cur.execute("SET LOCAL TIME ZONE 'UTC'")

            # SERIALIZATION: lock one listing before inspecting its holds.
            cur.execute(
                """
                SELECT donor_id, status, category, available_from, available_until
                FROM shipp.listings
                WHERE listing_id = %s
                FOR UPDATE
                """,
                (listing_id,),
            )
            listing = cur.fetchone()
            if listing is None:
                raise ReservationError("Item not found.")
            donor_id, status, category, available_from, available_until = listing

            # Recheck platform role, even with an authenticated profile.
            cur.execute(
                """
                SELECT 1
                FROM shipp.users u
                JOIN shipp.user_roles ur ON ur.user_id = u.user_id
                WHERE u.user_id = %s
                  AND u.is_active IS TRUE
                  AND ur.role_id = 'REQUESTER'
                """,
                (requester_id,),
            )
            if cur.fetchone() is None:
                raise ReservationError("Requester account is not authorized.")
            if str(donor_id) == requester_id:
                raise ReservationError("Cannot reserve your own item.")

            # need_by_date is a PostgreSQL DATE, not a Python datetime.
            cur.execute(
                """
                SELECT category
                FROM shipp.requests
                WHERE request_id = %s
                  AND requester_id = %s
                  AND status IN ('OPEN', 'MATCHES_AVAILABLE', 'ITEM_SAVED')
                  AND (need_by_date IS NULL OR need_by_date >= CURRENT_DATE)
                FOR SHARE
                """,
                (request_id, requester_id),
            )
            request = cur.fetchone()
            if request is None:
                raise ReservationError("No eligible request belongs to this account.")
            request_category = request[0]
            if category and request_category and (
                str(category).casefold() != str(request_category).casefold()
            ):
                raise ReservationError("Item category does not match this request.")

            # Database clock is authoritative, including after lock waits.
            cur.execute("SELECT clock_timestamp()")
            now = _utc(cur.fetchone()[0])
            if status != "AVAILABLE":
                raise ReservationError("Item is not available.")
            if available_from is not None and _utc(available_from) > now:
                raise ReservationError("Item is not available yet.")
            if available_until is not None and _utc(available_until) <= now:
                raise ReservationError("Item availability has expired.")

            # Free elapsed HELD claims; CONFIRMED never auto-expires here.
            cur.execute(
                """
                UPDATE shipp.reservations
                SET status = 'EXPIRED', closed_at = %s, updated_at = %s
                WHERE listing_id = %s
                  AND status = 'HELD'
                  AND hold_expires_at <= %s
                RETURNING reservation_id
                """,
                (now, now, listing_id, now),
            )
            for (expired_id,) in cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO shipp.reservation_events
                        (reservation_id, actor_type, event_type, note)
                    VALUES (%s, 'SYSTEM', 'EXPIRED',
                            'Elapsed hold released during a new claim')
                    """,
                    (expired_id,),
                )

            # A donated/completed item must not be reserved a second time.
            cur.execute(
                """
                SELECT 1
                FROM shipp.reservations
                WHERE listing_id = %s AND status = 'COMPLETED'
                LIMIT 1
                """,
                (listing_id,),
            )
            if cur.fetchone() is not None:
                raise ReservationError("Item has already been delivered.")

            cur.execute(
                """
                SELECT reservation_id, requester_id, request_id, status, hold_expires_at
                FROM shipp.reservations
                WHERE listing_id = %s AND status IN ('HELD', 'CONFIRMED')
                """,
                (listing_id,),
            )
            active = cur.fetchone()
            if active is not None:
                old_id, old_owner, old_request, old_status, old_expiry = active
                if str(old_owner) == requester_id and str(old_request) == request_id:
                    return {
                        "reservation_id": str(old_id),
                        "status": old_status,
                        "hold_expires_at": old_expiry,
                        "already_reserved": True,
                    }
                raise ReservationError("Item is already reserved.")

            expiry = now + timedelta(hours=24)
            if available_until is not None:
                expiry = min(expiry, _utc(available_until))
            if expiry <= now:
                raise ReservationError("Item cannot be reserved.")

            # PostgreSQL generates a UUID; no change to listings.status.
            cur.execute(
                """
                INSERT INTO shipp.reservations
                    (listing_id, request_id, requester_id,
                     status, created_at, hold_expires_at)
                VALUES (%s, %s, %s, 'HELD', %s, %s)
                RETURNING reservation_id, status, hold_expires_at
                """,
                (listing_id, request_id, requester_id, now, expiry),
            )
            inserted = cur.fetchone()
            if inserted is None:
                raise RuntimeError("Reservation insert did not return a row.")
            reservation_id, new_status, held_until = inserted
            cur.execute(
                """
                INSERT INTO shipp.reservation_events
                    (reservation_id, actor_user_id, actor_type, event_type)
                VALUES (%s, %s, 'REQUESTER', 'HELD')
                """,
                (reservation_id, requester_id),
            )

            return {
                "reservation_id": str(reservation_id),
                "status": new_status,
                "hold_expires_at": held_until,
                "already_reserved": False,
            }
