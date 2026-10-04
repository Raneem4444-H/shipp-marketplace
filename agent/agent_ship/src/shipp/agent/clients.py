"""Factories for real platform clients.

Lakebase connection details come from one of two places:

1. Databricks App with a Lakebase Autoscaling database resource attached:
   PGHOST, PGPORT, PGDATABASE and PGUSER are injected automatically, while
   SHIPP_LAKEBASE_ENDPOINT (from valueFrom: postgres) carries the endpoint path
   required to mint short-lived database credentials.
2. Notebook/local fallback:
   SHIPP_LAKEBASE_INSTANCE can still resolve a legacy/provisioned target.

No database password is stored in code. Databricks Apps use the app service
principal through WorkspaceClient unified auth and mint a short-lived Lakebase
OAuth credential for the configured endpoint.
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

    # External Streamlit deployments use OAuth M2M explicitly when all three
    # service-principal settings are present. This avoids ambiguous/default
    # auth discovery in a runtime that has no Databricks CLI profile.
    host = os.getenv("DATABRICKS_HOST")
    client_id = os.getenv("DATABRICKS_CLIENT_ID")
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")

    if host and client_id and client_secret:
        return WorkspaceClient(
            host=host,
            client_id=client_id,
            client_secret=client_secret,
        )

    # Databricks Apps/notebooks continue to use platform-injected unified auth.
    return WorkspaceClient()


def resolve_pg_target(
    settings: AgentSettings,
    workspace_client: Any,
) -> tuple[str, str, str]:
    """Return (host, user, database) for the Lakebase connection.

    Databricks Apps inject PG* variables for an attached Lakebase resource.
    Outside an App, missing values can be resolved from a legacy/provisioned
    Lakebase instance through the SDK.
    """
    host = os.getenv("PGHOST")
    user = os.getenv("PGUSER")
    database = os.getenv("PGDATABASE") or os.getenv("SHIPP_LAKEBASE_DATABASE")

    if not host:
        if not settings.lakebase_instance:
            raise RuntimeError(
                "No PGHOST and no SHIPP_LAKEBASE_INSTANCE. In a Databricks App, "
                "attach the Lakebase database resource. Outside an App, set "
                "SHIPP_LAKEBASE_INSTANCE (and optionally SHIPP_LAKEBASE_DATABASE)."
            )
        instance = workspace_client.database.get_database_instance(
            name=settings.lakebase_instance
        )
        host = instance.read_write_dns
        if not host:
            raise RuntimeError(
                f"Lakebase instance '{settings.lakebase_instance}' returned no "
                "read_write_dns (is it AVAILABLE?)."
            )

    if not user:
        user = workspace_client.current_user.me().user_name

    return host, user, database or _DEFAULT_DATABASE


def _generate_database_token(
    settings: AgentSettings,
    workspace_client: Any,
) -> str:
    """Mint a short-lived Lakebase database credential.

    Autoscaling uses the endpoint path exposed by the Databricks App resource.
    The legacy instance path remains only as a backward-compatible fallback for
    existing notebook/local workflows.
    """
    if settings.lakebase_endpoint:
        credential = workspace_client.postgres.generate_database_credential(
            endpoint=settings.lakebase_endpoint
        )
        return credential.token

    if settings.lakebase_instance:
        credential = workspace_client.database.generate_database_credential(
            request_id=str(uuid4()),
            instance_names=[settings.lakebase_instance],
        )
        return credential.token

    raise RuntimeError(
        "Lakebase OAuth credential cannot be generated: no "
        "SHIPP_LAKEBASE_ENDPOINT or SHIPP_LAKEBASE_INSTANCE is configured. "
        "For Databricks Apps, bind SHIPP_LAKEBASE_ENDPOINT with "
        "valueFrom: postgres."
    )


def build_lakebase_connect(
    settings: AgentSettings,
    workspace_client: Any,
) -> Callable[[], Any]:
    """Return a zero-arg callable that opens a psycopg 3 Lakebase connection."""
    import psycopg

    host, user, database = resolve_pg_target(settings, workspace_client)
    port = int(os.getenv("PGPORT", "5432"))
    lock = threading.Lock()
    cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _password() -> str:
        static = os.getenv("PGPASSWORD")
        if static:
            return static

        with lock:
            if cache["token"] and time.monotonic() < cache["expires_at"]:
                return cache["token"]

            token = _generate_database_token(settings, workspace_client)
            cache.update(
                token=token,
                expires_at=time.monotonic() + _TOKEN_TTL_SECONDS,
            )
            return token

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
