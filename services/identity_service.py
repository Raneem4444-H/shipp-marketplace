"""Fail-closed user-to-profile binding for a future OIDC-backed SHIPP app.

No demo profile dropdown is accepted as an identity proof.
An ID token verified by Streamlit OIDC must be present, and an administrator
must supply a server-side identity-to-SHIPP-user mapping before dashboards
become available. No app-facing password storage is introduced here.
"""
from __future__ import annotations

import json
import os
from typing import Any



def verified_profile(
    auth_repo: Any,
    streamlit_user: Any,
) -> dict[str, Any] | None:
    """Resolve a verified identity to an approved SHIPP profile."""

    if not bool(getattr(streamlit_user, "is_logged_in", False)):
        return None

    email = str(
        getattr(streamlit_user, "email", "") or ""
    ).strip().casefold()

    if not email:
        return None

    raw_mapping = os.getenv("SHIPP_VERIFIED_PROFILE_MAP", "")
    if not raw_mapping:
        return None

    try:
        mapping = json.loads(raw_mapping)
    except (ValueError, TypeError):
        return None

    if not isinstance(mapping, dict):
        return None

    user_id = mapping.get(email)

    if not isinstance(user_id, str) or not user_id.strip():
        return None

    try:
        return auth_repo.get_profile(user_id)
    except Exception:
        return None





def verified_databricks_profile(auth_repo: Any, headers: Any) -> dict[str, Any] | None:
    """Map a Databricks-proxied user to an approved SHIPP profile."""

    if os.getenv("SHIPP_DEPLOYMENT_TARGET") != "databricks_app":
        return None

    if headers is None:
        return None

    platform_user = str(
        headers.get("x-forwarded-user") or ""
    ).strip()

    platform_email = str(
        headers.get("x-forwarded-email") or ""
    ).strip().casefold()

    if not platform_user or not platform_email:
        return None

    raw = os.getenv("SHIPP_DATABRICKS_IDENTITY_MAP", "")
    try:
        mapping = json.loads(raw)
    except (ValueError, TypeError):
        return None

    if not isinstance(mapping, dict):
        return None

    approved = mapping.get(platform_user)
    if not isinstance(approved, dict):
        return None

    expected_email = approved.get("email")
    shipp_user_id = approved.get("user_id")

    if not isinstance(expected_email, str):
        return None

    if not isinstance(shipp_user_id, str) or not shipp_user_id.strip():
        return None

    if expected_email.strip().casefold() != platform_email:
        return None

    try:
        profile = auth_repo.get_profile(shipp_user_id)
    except Exception:
        return None

    if not isinstance(profile, dict):
        return None

    return profile if str(profile.get("user_id")) == shipp_user_id else None






def current_profile() -> dict[str, Any] | None:
    """Resolve the current verified SHIPP user."""

    import streamlit as st
    from app_auth import ShippAuthRepo
    from ui import legacy_core as core

    connect = getattr(core.marketplace, "_connect", None)
    if connect is None:
        return None

    auth_repo = ShippAuthRepo(
        connect,
        os.getenv("SHIPP_LAKEBASE_SCHEMA", "shipp"),
    )

    if os.getenv("SHIPP_DEPLOYMENT_TARGET") == "databricks_app":
        try:
            headers = st.context.headers
        except Exception:
            return None

        return verified_databricks_profile(auth_repo, headers)

    # External Streamlit deployments still require
    # separately configured, verified OIDC.
    st_user = getattr(st, "user", None)
    return verified_profile(auth_repo, st_user)



def require_role(role: str) -> dict[str, Any] | None:
    import streamlit as st

    profile = current_profile()
    if profile is None:
        st.warning("Personalized features require verified sign-in and an approved profile mapping.")
        st.caption("A demo-profile selector does not authenticate you. This page is intentionally closed until identity is configured.")
        return None
    if role not in set(profile.get("roles", [])):
        st.error("Your account does not have permission to use this page.")
        return None
    return profile
