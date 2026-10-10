
"""SHIPP account — verified user and roles."""

from __future__ import annotations

import streamlit as st

from services.identity_service import current_profile

st.title("My SHIPP Account")

profile = current_profile()

if profile is None:
    st.warning(
        "No approved SHIPP profile is linked "
        "to your signed-in identity."
    )
    st.info(
        "Pilot accounts must be approved and linked "
        "by the SHIPP administrator."
    )
    st.stop()

roles = set(profile.get("roles") or [])

st.success("SHIPP account connected")

st.write("Name:", profile["name"])
st.write("User ID:", profile["user_id"])

st.subheader("Your roles")

if "DONOR" in roles:
    st.success("Donor — You can give items")

if "REQUESTER" in roles:
    st.success("Requester — You can request items")

if not roles.intersection({"DONOR", "REQUESTER"}):
    st.error("No authorized marketplace roles found.")

st.caption(
    "One account can have both roles. "
    "You cannot reserve your own donation."
)
