"""SHIPP account — verified user and roles."""

from __future__ import annotations

import json

import streamlit as st

from services.identity_service import current_profile, signed_in_identity

st.title("My SHIPP Account")

profile = current_profile()

if profile is None:
    identity = signed_in_identity()
    platform_user = identity.get("platform_user", "")
    email = identity.get("email", "")

    if not email:
        st.warning("SHIPP could not read a signed-in identity for this session.")
        st.info(
            "Open SHIPP through its Databricks App link while signed in to the "
            "workspace. If you already are, ask the SHIPP administrator to "
            "check the app's sign-in configuration."
        )
        st.stop()

    st.info(
        "You're signed in, but your sign-in isn't linked to a SHIPP profile "
        "yet. Pilot accounts are approved and linked by the SHIPP "
        "administrator."
    )
    st.markdown("**Send these details to the administrator:**")
    st.code(
        f"email         = {email}\nplatform_user = {platform_user or '(not provided)'}",
        language=None,
    )
    with st.expander("For the administrator: identity map entry", expanded=False):
        st.caption(
            "Add this entry to SHIPP_DATABRICKS_IDENTITY_MAP, replacing the "
            "user_id with the approved row in shipp.users, then redeploy."
        )
        st.code(
            json.dumps(
                {platform_user or "<x-forwarded-user>": {
                    "email": email,
                    "user_id": "<shipp.users.user_id>",
                }},
                indent=2,
            ),
            language="json",
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
