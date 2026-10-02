"""Factories for real platform clients. Imports are lazy so unit tests and CI
don't need databricks-sdk, psycopg, or openai installed.

Lakebase connection details come from one of two places:

1. Databricks App with a Lakebase database resource attached:
   PGHOST, PGPORT, PGDATABASE and PGUSER are injected automatically.
2. Anywhere else (notebooks, jobs, local dev): those variables do NOT exist.
   They are resolved from the instance through the SDK instead:
     host     <- database instance read_write_dns
     user     <- the current Databricks identity
     database <- SHIPP_LAKEBASE_DATABASE (default databricks_postgres)

In both cases the password is a short-lived OAuth token, unless PGPASSWORD is
set explicitly for local development.
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
_DEFAULT_DATABASE = "databricks_postgres"


def build_workspace_client() -> Any:
    from databricks.sdk import WorkspaceClient

    # Unified auth: notebook identity, `databricks configure` locally, the app's service principal in Apps.
    return WorkspaceClient()


def resolve_pg_target(settings: AgentSettings, workspace_client: Any) -> tuple[str, str, str]:
    """Return (host, user, database) for the Lakebase connection.

    Uses the App-injected PG* variables when present; otherwise resolves each
    missing value from the Lakebase instance and the current identity.
    """
    host = os.getenv("PGHOST")
    user = os.getenv("PGUSER")
    database = os.getenv("PGDATABASE") or os.getenv("SHIPP_LAKEBASE_DATABASE")

    if not host:
        if not settings.lakebase_instance:
            raise RuntimeError(
                "No PGHOST and no SHIPP_LAKEBASE_INSTANCE. Outside a Databricks App, set "
                "SHIPP_LAKEBASE_INSTANCE (and SHIPP_LAKEBASE_DATABASE) so the host can be resolved."
            )
        instance = workspace_client.database.get_database_instance(name=settings.lakebase_instance)
        host = instance.read_write_dns
        if not host:
            raise RuntimeError(
                f"Lakebase instance '{settings.lakebase_instance}' returned no read_write_dns "
                "(is it AVAILABLE?)."
            )

    if not user:
        user = workspace_client.current_user.me().user_name

    return host, user, database or _DEFAULT_DATABASE


def build_lakebase_connect(settings: AgentSettings, workspace_client: Any) -> Callable[[], Any]:
    """Return a zero-arg callable that opens a psycopg 3 connection to Lakebase."""
    import psycopg

    host, user, database = resolve_pg_target(settings, workspace_client)
    port = int(os.getenv("PGPORT", "5432"))
    lock = threading.Lock()
    cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _password() -> str:
        static = os.getenv("PGPASSWORD")
        if static:
            return static
        if not settings.lakebase_instance:
            raise RuntimeError(
                "No PGPASSWORD and no SHIPP_LAKEBASE_INSTANCE: cannot generate a Lakebase OAuth token."
            )
        with lock:
            if cache["token"] and time.monotonic() < cache["expires_at"]:
                return cache["token"]
            cred = workspace_client.database.generate_database_credential(
                request_id=str(uuid4()),
                instance_names=[settings.lakebase_instance],
            )
            cache.update(token=cred.token, expires_at=time.monotonic() + _TOKEN_TTL_SECONDS)
            return cred.token

    def connect() -> Any:
        return psycopg.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=_password(),
            sslmode=os.getenv("PGSSLMODE", "require"),
            connect_timeout=10,
        )

    return connect
