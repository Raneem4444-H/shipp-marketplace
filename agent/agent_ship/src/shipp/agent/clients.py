"""Factories for real platform clients. Imports are lazy so unit tests and CI
don't need databricks-sdk, psycopg, or openai installed.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from shipp.agent.config import AgentSettings

# Lakebase OAuth tokens last one hour; refresh with a safety margin.
_TOKEN_TTL_SECONDS = 45 * 60


def build_workspace_client() -> Any:
    from databricks.sdk import WorkspaceClient

    # Unified auth: `databricks configure` locally, the app's service principal in Apps.
    return WorkspaceClient()


def build_lakebase_connect(settings: AgentSettings, workspace_client: Any) -> Callable[[], Any]:
    """Return a zero-arg callable that opens a psycopg 3 connection to Lakebase.

    In a Databricks App with a Lakebase database resource attached, PGHOST,
    PGPORT, PGDATABASE and PGUSER are injected. The password is a short-lived
    OAuth token, generated on demand and cached.
    """
    import psycopg

    lock = threading.Lock()
    cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _password() -> str:
        static = os.getenv("PGPASSWORD")
        if static:
            return static
        if not settings.lakebase_instance:
            raise RuntimeError("Set SHIPP_LAKEBASE_INSTANCE (or PGPASSWORD for local dev).")
        with lock:
            if cache["token"] and time.monotonic() < cache["expires_at"]:
                return cache["token"]
            cred = workspace_client.database.generate_database_credential(
                request_id=str(uuid4()),
                instance_names=[settings.lakebase_instance],
            )
            cache.update(token=cred.token, expires_at=time.monotonic() + _TOKEN_TTL_SECONDS)
            return cred.token

    def _env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value

    def connect() -> Any:
        return psycopg.connect(
            host=_env("PGHOST"),
            port=int(os.getenv("PGPORT", "5432")),
            dbname=_env("PGDATABASE"),
            user=_env("PGUSER"),
            password=_password(),
            sslmode=os.getenv("PGSSLMODE", "require"),
            connect_timeout=10,
        )

    return connect
