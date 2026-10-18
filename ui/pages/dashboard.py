"""Read-only, identity-scoped SHIPP pilot dashboard.

Uses the existing DashboardService and registered dashboard pages. No new SQL,
reservation actions, user selection or account permissions are introduced.
"""
from __future__ import annotations

import streamlit as st

from services.dashboard_service import DashboardService
from services.identity_service import current_profile
from ui.legacy_core import marketplace


def render_dashboard() -> None:
    profile = current_profile()
    if profile is None:
        st.title("My Dashboard")
        st.info("Link your sign-in to an approved SHIPP account to see your donations and requests.")
        st.page_link("ui/pages/auth.py", label="Open Account", icon=":material/person:")
        return

    first_name = str(profile.get("name") or "Member").strip().split()[0]
    roles = set(profile.get("roles") or [])
    st.title(f"{first_name}'s dashboard")
    st.caption("Your own activity, loaded from the SHIPP operational database.")

    dashboard = DashboardService(marketplace)
    donation_col, request_col = st.columns(2, gap="large")

    with donation_col:
        st.subheader("My donations")
        if "DONOR" not in roles:
            st.info("The Donor role is not enabled for this account.")
        else:
            try:
                listings = dashboard.donor_listings(profile, limit=30)
            except Exception:
                st.warning("Donation summary is temporarily unavailable.")
            else:
                st.metric("Available items (up to 30)", len(listings))
            st.page_link("ui/pages/donor_dashboard.py", label="View my donations", icon=":material/inventory_2:")
            st.page_link("ui/pages/donate.py", label="Give an item", icon=":material/add_circle:")

    with request_col:
        st.subheader("My requests")
        if "REQUESTER" not in roles:
            st.info("The Requester role is not enabled for this account.")
        else:
            try:
                requests = dashboard.requester_requests(profile, limit=20)
            except Exception:
                st.warning("Request summary is temporarily unavailable.")
            else:
                st.metric("Recent requests (up to 20)", len(requests))
            st.page_link("ui/pages/requester_dashboard.py", label="View my requests", icon=":material/bookmark:")
            st.page_link("ui/pages/ai_advisor.py", label="Find an item", icon=":material/search:")

    st.divider()
    st.page_link("ui/pages/auth.py", label="Account details", icon=":material/person:")


render_dashboard()
