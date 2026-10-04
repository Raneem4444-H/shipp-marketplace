"""Deployment-runtime helpers for SHIPP.

SHIPP's target capstone deployment remains Databricks Apps. The same Streamlit
frontend can also run on Streamlit Community Cloud for a public/demo surface.

This module only maps configuration names. It never logs or returns secret
values.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

STREAMLIT_SECRET_SECTIONS: dict[str, tuple[str, ...]] = {
    "databricks": (
        "DATABRICKS_HOST",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
        "DATABRICKS_TOKEN",
    ),
    "lakebase": (
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGSSLMODE",
        "SHIPP_LAKEBASE_ENDPOINT",
        "SHIPP_LAKEBASE_INSTANCE",
        "SHIPP_LAKEBASE_DATABASE",
        "SHIPP_LAKEBASE_SCHEMA",
    ),
    "shipp": (
        "SHIPP_LLM_ENDPOINT",
        "SHIPP_SQL_WAREHOUSE_ID",
        "SHIPP_CANDIDATE_MATCHES_TABLE",
        "SHIPP_SEARCH_INDEX",
        "SHIPP_LISTING_IMAGE_VOLUME",
        "SHIPP_DEPLOYMENT_TARGET",
        "SHIPP_SHOW_EVIDENCE",
    ),
}

MARKETPLACE_REQUIRED_EXTERNAL = (
    "DATABRICKS_HOST",
    "PGHOST",
    "PGDATABASE",
    "PGUSER",
    "SHIPP_LAKEBASE_ENDPOINT",
)

AGENT_REQUIRED = (
    "SHIPP_LLM_ENDPOINT",
    "SHIPP_SQL_WAREHOUSE_ID",
    "SHIPP_CANDIDATE_MATCHES_TABLE",
    "SHIPP_SEARCH_INDEX",
)


def _copy_if_missing(name: str, value: Any) -> bool:
    """Copy one non-empty secret into os.environ only when unset."""

    if os.getenv(name):
        return False
    if value is None:
        return False

    text = str(value).strip()
    if not text:
        return False

    os.environ[name] = text
    return True


def bootstrap_streamlit_secrets(secrets: Mapping[str, Any] | Any) -> list[str]:
    """Support root-level and sectioned Streamlit secrets.

    Streamlit already exports root-level secrets as environment variables.
    This helper additionally supports cleaner sections such as:

    [databricks]
    DATABRICKS_HOST = "..."
    DATABRICKS_CLIENT_ID = "..."

    Only known SHIPP configuration names are copied. Secret values are never
    returned; the caller receives names only for diagnostics.
    """

    loaded: list[str] = []

    try:
        root_items = dict(secrets).items()
    except Exception:
        root_items = ()

    allowed = {
        name
        for names in STREAMLIT_SECRET_SECTIONS.values()
        for name in names
    }

    for name, value in root_items:
        if name in allowed and _copy_if_missing(name, value):
            loaded.append(name)

    for section, names in STREAMLIT_SECRET_SECTIONS.items():
        try:
            section_values = secrets[section]
        except Exception:
            continue

        for name in names:
            try:
                value = section_values[name]
            except Exception:
                continue
            if _copy_if_missing(name, value):
                loaded.append(name)

    return sorted(set(loaded))


def deployment_target() -> str:
    """Return a stable deployment label without inferring credentials."""

    explicit = os.getenv("SHIPP_DEPLOYMENT_TARGET", "").strip().lower()
    if explicit:
        return explicit

    # Databricks Apps inject PG* values and app resource bindings. We avoid
    # depending on undocumented environment names and use this only as a label.
    if os.getenv("SHIPP_LAKEBASE_ENDPOINT") and os.getenv("PGHOST") and not os.getenv(
        "DATABRICKS_CLIENT_SECRET"
    ):
        return "databricks_app"

    return "external_streamlit"


def _has_databricks_auth() -> bool:
    if os.getenv("DATABRICKS_TOKEN"):
        return True
    return bool(
        os.getenv("DATABRICKS_CLIENT_ID")
        and os.getenv("DATABRICKS_CLIENT_SECRET")
    )


def runtime_config_status() -> dict[str, Any]:
    """Return names/status only; never secret values."""

    target = deployment_target()

    marketplace_missing: list[str] = []
    if target != "databricks_app":
        marketplace_missing.extend(
            name for name in MARKETPLACE_REQUIRED_EXTERNAL if not os.getenv(name)
        )
        if not _has_databricks_auth():
            marketplace_missing.append(
                "DATABRICKS_CLIENT_ID+DATABRICKS_CLIENT_SECRET"
            )

    agent_missing = [
        name for name in AGENT_REQUIRED if not os.getenv(name)
    ]

    return {
        "deployment_target": target,
        "marketplace_ready": not marketplace_missing,
        "marketplace_missing": marketplace_missing,
        "agent_ready": not agent_missing,
        "agent_missing": agent_missing,
        "volume_path_configured": bool(os.getenv("SHIPP_LISTING_IMAGE_VOLUME")),
        "lakebase_schema": os.getenv("SHIPP_LAKEBASE_SCHEMA", "shipp"),
    }
