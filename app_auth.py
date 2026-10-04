"""SHIPP profile registration and sign-in logic.

This module intentionally reuses the existing Lakebase identity model:

    shipp.users
    shipp.roles
    shipp.user_roles

It does NOT create duplicate donor/requester tables.

Important:
The current SHIPP schema has no password/email credential columns. Therefore
"sign in" here means selecting/validating an existing active SHIPP profile.
For production credential authentication, use an identity provider or add a
separate approved authentication design rather than storing plaintext passwords.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from uuid import uuid4


ALLOWED_APP_ROLES = {"DONOR", "REQUESTER"}


class AuthError(RuntimeError):
    """Base error for SHIPP profile/authentication operations."""


class ProfileNotFound(AuthError):
    """Raised when the requested active SHIPP profile does not exist."""


class InvalidRole(AuthError):
    """Raised when an unsupported role is requested."""


class ShippAuthRepo:
    """Lakebase-backed profile registration and sign-in helper."""

    def __init__(
        self,
        connect: Callable[[], Any],
        schema: str = "shipp",
    ) -> None:
        self._connect = connect
        self._schema = schema

    def _normalize_roles(self, roles: Iterable[str]) -> list[str]:
        normalized = sorted(
            {
                str(role).strip().upper()
                for role in roles
                if str(role).strip()
            }
        )

        if not normalized:
            raise InvalidRole("Choose at least one role: DONOR or REQUESTER.")

        invalid = set(normalized) - ALLOWED_APP_ROLES
        if invalid:
            raise InvalidRole(
                "Unsupported role(s): "
                + ", ".join(sorted(invalid))
                + ". Allowed app roles are DONOR and REQUESTER."
            )

        return normalized

    def register_profile(
        self,
        *,
        name: str,
        current_city: str | None,
        roles: Iterable[str],
    ) -> dict[str, Any]:
        """Create one user and assign one or more existing SHIPP roles.

        The inserts occur in one transaction. If any role assignment fails,
        the user insert is rolled back as well.
        """

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Name is required.")

        clean_city = current_city.strip() if current_city else None
        normalized_roles = self._normalize_roles(roles)
        user_id = str(uuid4())

        with self._connect() as conn:
            with conn.cursor() as cur:
                # Verify the reference roles exist before creating the profile.
                cur.execute(
                    f"""
                    SELECT role_id
                    FROM {self._schema}.roles
                    WHERE role_id = ANY(%s)
                    """,
                    (normalized_roles,),
                )
                existing_roles = {row[0] for row in cur.fetchall()}
                missing_roles = set(normalized_roles) - existing_roles
                if missing_roles:
                    raise InvalidRole(
                        "Lakebase is missing required role(s): "
                        + ", ".join(sorted(missing_roles))
                    )

                cur.execute(
                    f"""
                    INSERT INTO {self._schema}.users (
                        user_id,
                        name,
                        current_city,
                        is_active
                    )
                    VALUES (%s, %s, %s, TRUE)
                    """,
                    (user_id, clean_name, clean_city),
                )

                cur.executemany(
                    f"""
                    INSERT INTO {self._schema}.user_roles (
                        user_id,
                        role_id,
                        assigned_by
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, role_id) DO NOTHING
                    """,
                    [
                        (user_id, role_id, user_id)
                        for role_id in normalized_roles
                    ],
                )

            # psycopg context managers normally commit automatically on success.
            # Explicit commit keeps the transaction boundary obvious.
            conn.commit()

        return self.get_profile(user_id)

    def get_profile(self, user_id: str) -> dict[str, Any]:
        """Return one active profile and all assigned roles."""

        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ProfileNotFound("User ID is required.")

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    u.user_id,
                    u.name,
                    u.current_city,
                    u.created_at,
                    u.updated_at,
                    ARRAY_AGG(ur.role_id ORDER BY ur.role_id) AS roles
                FROM {self._schema}.users u
                JOIN {self._schema}.user_roles ur
                  ON ur.user_id = u.user_id
                WHERE u.user_id = %s
                  AND u.is_active = TRUE
                GROUP BY
                    u.user_id,
                    u.name,
                    u.current_city,
                    u.created_at,
                    u.updated_at
                """,
                (clean_user_id,),
            )
            row = cur.fetchone()

        if not row:
            raise ProfileNotFound("Active SHIPP profile was not found.")

        return {
            "user_id": row[0],
            "name": row[1],
            "current_city": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "roles": list(row[5] or []),
        }

    def sign_in(self, user_id: str) -> dict[str, Any]:
        """Validate and return an existing active SHIPP profile.

        This is profile sign-in, not password authentication.
        """

        return self.get_profile(user_id)

    def list_profiles(self, role_id: str | None = None) -> list[dict[str, Any]]:
        """List active profiles, optionally restricted to DONOR/REQUESTER."""

        params: tuple[Any, ...] = ()
        role_filter = ""

        if role_id is not None:
            normalized = role_id.strip().upper()
            if normalized not in ALLOWED_APP_ROLES:
                raise InvalidRole(
                    f"Unsupported role: {role_id}. "
                    "Expected DONOR or REQUESTER."
                )
            role_filter = """
              AND EXISTS (
                    SELECT 1
                    FROM {schema}.user_roles role_filter
                    WHERE role_filter.user_id = u.user_id
                      AND role_filter.role_id = %s
              )
            """.format(schema=self._schema)
            params = (normalized,)

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    u.user_id,
                    u.name,
                    u.current_city,
                    ARRAY_AGG(ur.role_id ORDER BY ur.role_id) AS roles
                FROM {self._schema}.users u
                JOIN {self._schema}.user_roles ur
                  ON ur.user_id = u.user_id
                WHERE u.is_active = TRUE
                {role_filter}
                GROUP BY u.user_id, u.name, u.current_city
                ORDER BY u.name, u.user_id
                """,
                params,
            )
            rows = cur.fetchall()

        return [
            {
                "user_id": row[0],
                "name": row[1],
                "current_city": row[2],
                "roles": list(row[3] or []),
            }
            for row in rows
        ]

    def add_role(self, *, user_id: str, role_id: str) -> dict[str, Any]:
        """Assign an additional DONOR/REQUESTER role to an active profile."""

        normalized_role = self._normalize_roles([role_id])[0]

        # Prove the user exists and is active before assigning.
        self.get_profile(user_id)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self._schema}.user_roles (
                        user_id,
                        role_id,
                        assigned_by
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, role_id) DO NOTHING
                    """,
                    (user_id, normalized_role, user_id),
                )
            conn.commit()

        return self.get_profile(user_id)

    def deactivate_profile(self, user_id: str) -> None:
        """Soft-disable a profile without deleting operational history."""

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {self._schema}.users
                    SET
                        is_active = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                      AND is_active = TRUE
                    """,
                    (user_id,),
                )
                if cur.rowcount != 1:
                    raise ProfileNotFound("Active SHIPP profile was not found.")
            conn.commit()
