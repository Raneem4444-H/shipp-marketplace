"""Application-owned Lakebase operations for SHIPP marketplace UX.

This module deliberately keeps application writes separate from the Agent:
- App writes Listings and Requests.
- Agent writes Saved Items and Agent Activity.

It reuses the same Lakebase connection/authentication factory as the validated
Agent path, so no new credentials or database contract are introduced.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import uuid4


class MarketplaceRepo:
    def __init__(self, connect: Callable[[], Any], schema: str) -> None:
        self._connect = connect
        self._schema = schema

    def list_users(self, role_id: str) -> list[dict[str, str]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT u.user_id, u.name
                FROM {self._schema}.users u
                JOIN {self._schema}.user_roles ur
                  ON ur.user_id = u.user_id
                WHERE ur.role_id = %s
                  AND u.is_active = TRUE
                ORDER BY u.name
                """,
                (role_id,),
            )
            rows = cur.fetchall()

        return [{"user_id": row[0], "name": row[1]} for row in rows]

    def create_listing(
        self,
        *,
        donor_id: str,
        title: str,
        description: str,
        category: str,
        condition: str,
        location: str,
        latitude: float,
        longitude: float,
        available_until: date,
    ) -> str:
        listing_id = str(uuid4())
        available_from = datetime.now(timezone.utc)
        available_until_ts = datetime.combine(
            available_until,
            time(23, 59, 59),
            tzinfo=timezone.utc,
        )

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self._schema}.listings (
                    listing_id,
                    donor_id,
                    title,
                    description,
                    category,
                    condition,
                    location,
                    latitude,
                    longitude,
                    available_from,
                    available_until,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'AVAILABLE')
                """,
                (
                    listing_id,
                    donor_id,
                    title.strip(),
                    description.strip(),
                    category,
                    condition,
                    location.strip(),
                    latitude,
                    longitude,
                    available_from,
                    available_until_ts,
                ),
            )
        return listing_id

    def create_request(
        self,
        *,
        requester_id: str,
        request_text: str,
        category: str,
        location: str,
        latitude: float,
        longitude: float,
        need_by_date: date,
    ) -> str:
        request_id = str(uuid4())
        need_by_ts = datetime.combine(
            need_by_date,
            time(18, 0),
            tzinfo=timezone.utc,
        )

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self._schema}.requests (
                    request_id,
                    requester_id,
                    request_text,
                    category,
                    location,
                    latitude,
                    longitude,
                    need_by_date,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'OPEN')
                """,
                (
                    request_id,
                    requester_id,
                    request_text.strip(),
                    category,
                    location.strip(),
                    latitude,
                    longitude,
                    need_by_ts,
                ),
            )
        return request_id

    def list_requests(self, requester_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    request_id,
                    request_text,
                    category,
                    location,
                    need_by_date,
                    status
                FROM {self._schema}.requests
                WHERE requester_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (requester_id, limit),
            )
            rows = cur.fetchall()

        return [
            {
                "request_id": row[0],
                "request_text": row[1],
                "category": row[2],
                "location": row[3],
                "need_by_date": row[4],
                "status": row[5],
            }
            for row in rows
        ]

    def list_saved_items(self, user_id: str, request_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    s.saved_item_id,
                    s.listing_id,
                    l.title,
                    s.saved_at
                FROM {self._schema}.saved_items s
                JOIN {self._schema}.listings l
                  ON l.listing_id = s.listing_id
                WHERE s.user_id = %s
                  AND s.request_id = %s
                ORDER BY s.saved_at DESC
                """,
                (user_id, request_id),
            )
            rows = cur.fetchall()

        return [
            {
                "saved_item_id": row[0],
                "listing_id": row[1],
                "title": row[2],
                "saved_at": row[3],
            }
            for row in rows
        ]
