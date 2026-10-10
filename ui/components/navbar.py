
"""SHIPP top navigation with verified account greeting."""

from __future__ import annotations

import streamlit as st

from services.identity_service import current_profile


def create_navigation():
    # Resolve the current approved SHIPP user.
    profile = current_profile()

    if profile is not None:
        full_name = str(
            profile.get("name") or "Member"
        ).strip()

        first_name = (
            full_name.split()[0]
            if full_name
            else "Member"
        )

        account_menu_title = (
            f"Welcome, {first_name[:20]}"
        )
        account_page_title = "My Account"

    else:
        account_menu_title = "Sign up / Login"
        account_page_title = "Account setup"

    main_pages = [
        st.Page("ui/pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("ui/pages/marketplace.py", title="Explore", icon=":material/search:"),
        st.Page("ui/pages/donate.py", title="Give an item", icon=":material/volunteer_activism:"),
        st.Page("ui/pages/ai_advisor.py", title="Find an item", icon=":material/smart_toy:"),
    ]

    account_pages = [
        st.Page(
            "ui/pages/auth.py",
            title=account_page_title,
            icon=":material/person:",
        ),
        st.Page("ui/pages/donor_dashboard.py", title="My Donations", icon=":material/dashboard:"),
        st.Page("ui/pages/requester_dashboard.py", title="My Requests", icon=":material/bookmark:"),
    ]

    admin_pages = [
        st.Page("ui/pages/admin.py", title="Engineering", icon=":material/monitor_heart:"),
    ]

    return st.navigation(
        {
            "Marketplace": main_pages,
            account_menu_title: account_pages,
            "Engineering": admin_pages,
        },
        position="top",
    )
