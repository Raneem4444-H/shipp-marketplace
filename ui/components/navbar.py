"""Single source of truth for SHIPP top navigation.

Scripts are executable Streamlit pages, not HTML mockups. Access controls
must remain in page/service code and are not delegated to nav visibility.
"""
from __future__ import annotations

import streamlit as st


def create_navigation():
    main_pages = [
        st.Page("ui/pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("ui/pages/marketplace.py", title="Explore", icon=":material/search:"),
        st.Page("ui/pages/donate.py", title="Give an item", icon=":material/volunteer_activism:"),
        st.Page("ui/pages/ai_advisor.py", title="Find an item", icon=":material/smart_toy:"),
    ]
    account_pages = [
        st.Page("ui/pages/auth.py", title="Account", icon=":material/person:"),
        st.Page("ui/pages/donor_dashboard.py", title="Donor dashboard", icon=":material/dashboard:"),
        st.Page("ui/pages/requester_dashboard.py", title="My requests", icon=":material/bookmark:"),
    ]
    admin_pages = [
        st.Page("ui/pages/admin.py", title="Engineering", icon=":material/monitor_heart:"),
    ]
    return st.navigation(
        {"Marketplace": main_pages, "Account": account_pages, "Engineering": admin_pages},
        position="top",
    )
