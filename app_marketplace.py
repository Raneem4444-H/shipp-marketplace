"""Application-owned Lakebase operations for SHIPP marketplace UX.

This module keeps application writes separate from the Agent:
- App writes Listings and Requests.
- Agent writes Saved Items and Agent Activity.
- Listing images are stored in a Unity Catalog Volume and only their
  references are stored in Lakebase listing_files.

The module reuses the validated Lakebase connection/authentication factory.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4


_SAFE_FILE = re.compile(r"[^A-Za-z0-9._-]+")


class MarketplaceRepo:
    def __init__(
        self,
        connect: Callable[[], Any],
        schema: str,
        *,
        workspace: Any | None = None,
        image_volume_path: str | None = None,
    ) -> None:
        self._connect = connect
        self._schema = schema
        self._workspace = workspace
        self._image_volume_path = (
            image_volume_path.rstrip("/") if image_volume_path else None
        )

    # ------------------------------------------------------------------
    # USERS / PERSONAS
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # DONOR LISTINGS
    # ------------------------------------------------------------------

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

    def save_listing_images(
        self,
        listing_id: str,
        uploads: Sequence[Any],
        *,
        max_files: int = 5,
        max_file_bytes: int = 8 * 1024 * 1024,
    ) -> list[dict[str, Any]]:
        """Persist donor-uploaded images to a UC Volume and listing_files.

        This method deliberately stores only file references in Lakebase.
        """

        if not uploads:
            return []

        if self._workspace is None:
            raise RuntimeError("Workspace client is not available for image upload.")

        if not self._image_volume_path:
            raise RuntimeError(
                "SHIPP_LISTING_IMAGE_VOLUME is not configured for the App."
            )

        selected = list(uploads)[:max_files]
        directory = f"{self._image_volume_path}/{listing_id}"
        self._workspace.files.create_directory(directory)

        uploaded_paths: list[str] = []
        rows: list[tuple[str, str, str, str | None, int]] = []

        try:
            for upload in selected:
                raw = upload.getvalue()
                if not raw:
                    continue

                if len(raw) > max_file_bytes:
                    raise ValueError(
                        f"{getattr(upload, 'name', 'image')} exceeds the "
                        f"{max_file_bytes // (1024 * 1024)} MB limit."
                    )

                mime_type = getattr(upload, "type", None)
                if mime_type and not str(mime_type).startswith("image/"):
                    raise ValueError(
                        f"{getattr(upload, 'name', 'file')} is not an image."
                    )

                original_name = PurePosixPath(
                    str(getattr(upload, "name", "image"))
                ).name
                safe_name = _SAFE_FILE.sub("_", original_name).strip("._")
                safe_name = safe_name or "image"

                listing_file_id = str(uuid4())
                remote_path = (
                    f"{directory}/{listing_file_id}_{safe_name}"
                )

                self._workspace.files.upload(
                    remote_path,
                    io.BytesIO(raw),
                    overwrite=False,
                )
                uploaded_paths.append(remote_path)
                rows.append(
                    (
                        listing_file_id,
                        listing_id,
                        remote_path,
                        mime_type,
                        len(raw),
                    )
                )

            if not rows:
                return []

            with self._connect() as conn, conn.cursor() as cur:
                cur.executemany(
                    f"""
                    INSERT INTO {self._schema}.listing_files (
                        listing_file_id,
                        listing_id,
                        file_path,
                        file_type,
                        file_size
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    rows,
                )

        except Exception:
            for remote_path in uploaded_paths:
                try:
                    self._workspace.files.delete(remote_path)
                except Exception:
                    pass
            raise

        return [
            {
                "listing_file_id": row[0],
                "listing_id": row[1],
                "file_path": row[2],
                "file_type": row[3],
                "file_size": row[4],
            }
            for row in rows
        ]

    def get_primary_listing_image(self, listing_id: str) -> bytes | None:
        """Return the first image bytes for a listing when App access allows it."""

        if self._workspace is None:
            return None

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT file_path
                FROM {self._schema}.listing_files
                WHERE listing_id = %s
                  AND (file_type IS NULL OR file_type LIKE 'image/%')
                ORDER BY uploaded_at ASC
                LIMIT 1
                """,
                (listing_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        try:
            response = self._workspace.files.download(row[0])
            if response.contents is None:
                return None
            return response.contents.read()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # REQUESTER REQUESTS
    # ------------------------------------------------------------------

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

    def list_requests(
        self,
        requester_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
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

    # ------------------------------------------------------------------
    # SAVED STATE
    # ------------------------------------------------------------------

    def list_saved_items(
        self,
        user_id: str,
        request_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    s.saved_item_id,
                    s.listing_id,
                    l.title,
                    l.condition,
                    l.location,
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
                "condition": row[3],
                "location": row[4],
                "saved_at": row[5],
            }
            for row in rows
        ]
