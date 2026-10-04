# ============================================================
# SHIPP — Databricks App
# P0 Marketplace + Agent Integration
# ============================================================

from pathlib import Path
import sys

import streamlit as st


# ------------------------------------------------------------
# Load existing SHIPP Agent package
# ------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
AGENT_SRC = ROOT_DIR / "agent" / "agent_ship" / "src"

if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from shipp.agent.agent import ShippAgent


# ------------------------------------------------------------
# Page
# ------------------------------------------------------------

st.set_page_config(
    page_title="SHIPP",
    page_icon="📦",
    layout="wide",
)

st.title("SHIPP")
st.caption("AI-assisted household marketplace")


# ------------------------------------------------------------
# Existing SHIPP Agent
# ------------------------------------------------------------

@st.cache_resource
def load_agent():
    return ShippAgent.from_env()


try:
    agent = load_agent()

except Exception as exc:
    st.error("SHIPP Agent could not start.")
    st.code(str(exc))
    st.stop()


# ------------------------------------------------------------
# Session state
# ------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_save" not in st.session_state:
    st.session_state.pending_save = None

if "tool_trace" not in st.session_state:
    st.session_state.tool_trace = []


# ------------------------------------------------------------
# Request context
# ------------------------------------------------------------

st.subheader("1. Select Request")

left, right = st.columns(2)

with left:
    user_id = st.text_input(
        "User ID",
        placeholder="Example: demo-requester-001",
    )

with right:
    request_id = st.text_input(
        "Request ID",
        placeholder="Example: demo-request-001",
    )


# ------------------------------------------------------------
# Agent conversation
# ------------------------------------------------------------

st.subheader("2. Ask SHIPP Agent")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


prompt = st.chat_input(
    "Recommend the best available item for this request"
)


if prompt:

    if not user_id:
        st.warning("Enter User ID.")
        st.stop()

    if not request_id:
        st.warning("Enter Request ID.")
        st.stop()

    # Display user message
    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.spinner("Checking SHIPP candidate matches..."):

            turn = agent.chat(
                user_id=user_id,
                request_id=request_id,
                user_message=prompt,
                history=st.session_state.messages[:-1],
            )

        reply = turn.reply or "No recommendation was returned."

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

        st.session_state.pending_save = turn.pending_save
        st.session_state.tool_trace = turn.tool_trace

        with st.chat_message("assistant"):
            st.markdown(reply)

    except Exception as exc:
        st.error("Agent request failed.")
        st.code(str(exc))


# ------------------------------------------------------------
# Evidence — Agent tool calls
# ------------------------------------------------------------

if st.session_state.tool_trace:

    with st.expander("Agent tool trace"):

        for number, trace in enumerate(
            st.session_state.tool_trace,
            start=1,
        ):
            st.markdown(
                f"**{number}. {trace.get('tool', 'unknown')}**"
            )
            st.json(trace)


# ------------------------------------------------------------
# Controlled operational write
# ------------------------------------------------------------

pending = st.session_state.pending_save

if pending is not None:

    st.divider()

    st.subheader("3. Confirm Save")

    st.write("**Recommended item:**", pending.title)
    st.write("**Listing ID:**", pending.listing_id)
    st.write("**Reason:**", pending.reason)

    if st.button(
        "Confirm Save",
        type="primary",
        use_container_width=True,
    ):

        try:
            with st.spinner(
                "Checking current Lakebase state..."
            ):

                result = agent.confirm_save(
                    user_id=user_id,
                    request_id=request_id,
                    listing_id=pending.listing_id,
                )

            if result.ok:

                st.success(
                    f"Item saved successfully. "
                    f"Saved Item ID: {result.saved_item_id}"
                )

                st.session_state.pending_save = None

            else:

                st.warning(
                    f"Save rejected: {result.message}"
                )

        except Exception as exc:

            st.error("Save failed.")
            st.code(str(exc))


# ------------------------------------------------------------
# Architecture status
# ------------------------------------------------------------

st.divider()

st.caption(
    "Gold Candidate Matches → AI Search → SHIPP Agent → "
    "User Confirmation → Lakebase"
)