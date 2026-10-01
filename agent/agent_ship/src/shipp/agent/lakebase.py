"""Lakebase (Postgres) access for the agent.

The agent's write ownership (spec §6.5) is exactly two tables:
saved_items and agent_activity. Everything else here is a read.

`connect` is any zero-argument callable returning a psycopg 3 connection.
psycopg 3 connection context managers commit on clean exit and roll back on
exception, which is what makes save_item atomic.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from shipp.agent.config import validate_identifier
from shipp.agent.contracts import (
    ActionStatus,
    ListingState,
    RequestState,
    SaveResult,
)
from shipp.agent.rules import check_listing_saveable, check_request_usable

logger = logging.getLogger(__name__)

SAVE_TOOL_NAME = "save_item"


class LakebaseRepo:
    def __init__(self, connect: Callable[[], Any], schema: str) -> None:
        self._connect = connect
        self._s = validate_identifier(schema)

    # ------------------------------------------------------------------ reads
    def get_listing(self, listing_id: str) -> ListingState | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT listing_id, status, available_until FROM {self._s}.listings "
                "WHERE listing_id = %s",
                (listing_id,),
            )
            row = cur.fetchone()
        return ListingState(*row) if row else None

    def get_request(self, request_id: str) -> RequestState | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT request_id, requester_id, status FROM {self._s}.requests "
                "WHERE request_id = %s",
                (request_id,),
            )
            row = cur.fetchone()
        return RequestState(*row) if row else None

    # ----------------------------------------------------------------- writes
    def save_item(
        self,
        *,
        user_id: str,
        request_id: str,
        listing_id: str,
        now: datetime | None = None,
    ) -> SaveResult:
        """Validate current state and write the Saved Item in one transaction.

        The listing row is read with FOR SHARE: a concurrent withdraw by the
        donor has to wait for this transaction, so we can't save a listing that
        was withdrawn between our check and our insert.
        """
        now = now or datetime.now(timezone.utc)
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT request_id, requester_id, status FROM {self._s}.requests "
                    "WHERE request_id = %s",
                    (request_id,),
                )
                req_row = cur.fetchone()
                reason = check_request_usable(
                    RequestState(*req_row) if req_row else None, user_id
                )

                if reason is None:
                    cur.execute(
                        f"SELECT listing_id, status, available_until FROM {self._s}.listings "
                        "WHERE listing_id = %s FOR SHARE",
                        (listing_id,),
                    )
                    lst_row = cur.fetchone()
                    reason = check_listing_saveable(
                        ListingState(*lst_row) if lst_row else None, now
                    )

                if reason is not None:
                    self._insert_activity(cur, user_id, listing_id, ActionStatus.REJECTED, now)
                    return SaveResult(ActionStatus.REJECTED, reason)

                saved_item_id = str(uuid4())
                cur.execute(
                    f"INSERT INTO {self._s}.saved_items "
                    "(saved_item_id, user_id, request_id, listing_id, saved_at) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (user_id, request_id, listing_id) DO NOTHING "
                    "RETURNING saved_item_id",
                    (saved_item_id, user_id, request_id, listing_id, now),
                )
                if cur.fetchone() is None:
                    self._insert_activity(cur, user_id, listing_id, ActionStatus.DUPLICATE, now)
                    return SaveResult(
                        ActionStatus.DUPLICATE, "You already saved this item for this request."
                    )

                self._insert_activity(cur, user_id, listing_id, ActionStatus.SUCCESS, now)
                return SaveResult(ActionStatus.SUCCESS, "Item saved.", saved_item_id)

        except Exception:
            logger.exception("save_item failed for listing %s", listing_id)
            # The transaction above rolled back, so record the failure separately.
            self.log_activity(user_id, SAVE_TOOL_NAME, listing_id, ActionStatus.FAILED)
            return SaveResult(
                ActionStatus.FAILED, "The save failed because of a system error. Nothing was saved."
            )

    def log_activity(
        self, user_id: str, tool_name: str, entity_id: str | None, status: ActionStatus
    ) -> bool:
        """Best-effort audit write in its own transaction. Never raises."""
        try:
            with self._connect() as conn, conn.cursor() as cur:
                self._insert_activity(
                    cur, user_id, entity_id, status, datetime.now(timezone.utc), tool_name
                )
            return True
        except Exception:
            logger.exception("agent_activity write failed (%s, %s)", tool_name, status)
            return False

    def _insert_activity(
        self,
        cur: Any,
        user_id: str,
        entity_id: str | None,
        status: ActionStatus,
        now: datetime,
        tool_name: str = SAVE_TOOL_NAME,
    ) -> None:
        cur.execute(
            f"INSERT INTO {self._s}.agent_activity "
            "(activity_id, user_id, tool_name, entity_id, action_status, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (str(uuid4()), user_id, tool_name, entity_id, status.value, now),
        )
