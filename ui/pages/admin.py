"""Engineering diagnostics are restricted to explicitly allowlisted OIDC users."""
from __future__ import annotations

import os

import streamlit as st

from services.identity_service import current_profile
from ui.legacy_core import render_deployment_evidence

st.title("SHIPP engineering")
profile = current_profile()  # Active verified identity-to-profile binding required.
allowlist = {x.strip() for x in os.getenv("SHIPP_ADMIN_PROFILE_IDS", "").split(",") if x.strip()}
if profile is not None and profile["user_id"] in allowlist:
    render_deployment_evidence()
else:
    st.info("Engineering diagnostics are restricted to authorized maintainers.")
