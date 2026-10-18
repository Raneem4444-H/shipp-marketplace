"""Flat top navigation for the Databricks SSO SHIPP pilot.

All end-user destinations use the existing Streamlit page registry. Donor and
requester detail dashboards remain linkable but do not crowd the top header.
"""
from __future__ import annotations

import os

import streamlit as st

from services.identity_service import current_profile


def create_navigation():
    profile = current_profile()
    name = (
        str(profile.get("name") or "Member").strip().split()[0][:20]
        if profile else ""
    )
    account_label = f"Welcome, {name}" if profile else "Account"

    pages = [
        st.Page("ui/pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("ui/pages/marketplace.py", title="Explore", icon=":material/search:"),
        st.Page("ui/pages/donate.py", title="Give an item", icon=":material/volunteer_activism:"),
        st.Page("ui/pages/ai_advisor.py", title="Find an item", icon=":material/smart_toy:"),
        st.Page("ui/pages/dashboard.py", title="My Dashboard", icon=":material/dashboard:"),
        st.Page("ui/pages/auth.py", title=account_label, icon=":material/person:"),
        # Registered URLs stay reachable through st.page_link in Dashboard/Account.
        st.Page("ui/pages/donor_dashboard.py", title="My Donations", visibility="hidden"),
        st.Page("ui/pages/requester_dashboard.py", title="My Requests", visibility="hidden"),
    ]

    # Preserve the existing admin-only rule; never display Engineering to a
    # visitor whose identity is not already linked to an approved SHIPP user.
    admins = {
        identifier.strip()
        for identifier in os.getenv("SHIPP_ADMIN_PROFILE_IDS", "").split(",")
        if identifier.strip()
    }
    if profile is not None and profile.get("user_id") in admins:
        pages.append(
            st.Page("ui/pages/admin.py", title="Engineering", icon=":material/monitor_heart:")
        )

    # A LIST (not a group dict) produces separate visible links in the top bar.
    return st.navigation(pages, position="top")
