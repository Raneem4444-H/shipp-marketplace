"""Account status. Do not mistake profile lookup for production sign-in."""
from __future__ import annotations

import streamlit as st

from services.identity_service import current_profile

st.title("Account")
profile = current_profile()
if profile:
    st.success("Verified user mapped to a SHIPP profile")
    st.write("Name:", profile["name"])
    st.write("Roles:", ", ".join(profile.get("roles", [])))
else:
    st.info("Secure login and signup have not been activated for SHIPP yet.")
    st.write(
        "Databricks authentication is not the same as a SHIPP profile. "
        "Verified identity-to-profile linking must be approved before user dashboards or writes are enabled."
    )
    st.caption("The existing Give / Find pages remain controlled demo journeys until this is implemented.")
