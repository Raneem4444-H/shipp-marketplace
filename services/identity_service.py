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


def verified_profile(auth_repo: Any, streamlit_user: Any) -> dict[str, Any] | None:
    """Resolve a verified OIDC email to a SHIPP user (None => deny)."""
    if not bool(getattr(streamlit_user, "is_logged_in", False)):
        return None
    email = str(getattr(streamlit_user, "email", "") or "").strip().casefold()
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


def current_profile() -> dict[str, Any] | None:
    """Resolve identity using the existing Lakebase connection only if OIDC is configured."""
    import streamlit as st

    from app_auth import ShippAuthRepo
    from ui import legacy_core as core

    st_user = getattr(st, "user", None)
    if st_user is None:
        return None
    # MarketplaceRepo's factory is the trusted production connection.
    connect = getattr(core.marketplace, "_connect", None)
    if connect is None:
        return None
    return verified_profile(ShippAuthRepo(connect, os.getenv("SHIPP_LAKEBASE_SCHEMA", "shipp")), st_user)


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
