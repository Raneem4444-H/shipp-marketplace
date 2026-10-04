# ============================================================
# SHIPP — Databricks App
# P0 Marketplace + Agent Integration
# ============================================================

from __future__ import annotations

import html
from pathlib import Path
import sys

import streamlit as st


# ------------------------------------------------------------
# Paths / existing SHIPP Agent package
# ------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
AGENT_SRC = ROOT_DIR / "agent" / "agent_ship" / "src"
CSS_PATH = ROOT_DIR / "assets" / "shipp.css"

if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from shipp.agent.agent import ShippAgent


# ------------------------------------------------------------
# Page + SHIPP visual system
# ------------------------------------------------------------

st.set_page_config(
    page_title="SHIPP",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def load_css() -> None:
    """Load the checked-in SHIPP stylesheet.

    Failing to load CSS must never prevent the functional App from starting.
    """
    if not CSS_PATH.exists():
        return

    css = CSS_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css()

st.markdown(
    """
    <div class="shipp-header">
      <div class="shipp-brand">
        <span class="shipp-logo">◇</span>
        <span class="shipp-brand-name">SHIPP</span>
      </div>
      <div class="shipp-header-status">
        <span class="shipp-status-dot"></span>
        Gold + AI Search + Lakebase
      </div>
    </div>

    <section class="shipp-hero">
      <div class="shipp-eyebrow">AI-assisted household marketplace</div>
      <h1 class="shipp-hero-title">Find useful items before they go to waste.</h1>
      <p class="shipp-hero-copy">
        Select a request, ask SHIPP for the best available match, review the
        evidence, and save the item only after you approve it.
      </p>
    </section>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Existing SHIPP Agent
# ------------------------------------------------------------

@st.cache_resource
def load_agent() -> ShippAgent:
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

st.markdown('<div class="shipp-section-title">1. Select Request</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="shipp-section-copy">'
    "Use an existing SHIPP requester and request. The Agent will only recommend "
    "listings that are valid candidates for that request."
    "</div>",
    unsafe_allow_html=True,
)

with st.container(border=True):
    left, right = st.columns(2)

    with left:
        user_id = st.text_input(
            "User ID",
            placeholder="Example: demo-requester-001",
            key="app_user_id",
        )

    with right:
        request_id = st.text_input(
            "Request ID",
            placeholder="Example: demo-request-001",
            key="app_request_id",
        )

st.markdown(
    """
    <div class="shipp-ai-banner">
      <span class="shipp-ai-icon">✦</span>
      <span>
        SHIPP grounds recommendations in Gold candidate matches, AI Search
        context, and the current Lakebase listing state.
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Agent conversation
# ------------------------------------------------------------

st.markdown('<div class="shipp-section-title">2. Ask SHIPP Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="shipp-section-copy">'
    "Ask for the best available item. SHIPP will compare candidates, enrich the "
    "answer with listing context, and verify availability before recommending."
    "</div>",
    unsafe_allow_html=True,
)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Recommend the best available item for this request")

if prompt:
    if not user_id:
        st.warning("Enter User ID.")
        st.stop()

    if not request_id:
        st.warning("Enter Request ID.")
        st.stop()

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
    with st.expander("Agent tool trace — Gold → AI Search → Lakebase"):
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
    st.markdown('<div class="shipp-section-title">3. Confirm Save</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="shipp-section-copy">'
        "The Agent has prepared a recommendation. Saving is a separate, explicit "
        "user-approved action and rechecks current Lakebase state."
        "</div>",
        unsafe_allow_html=True,
    )

    pending_title = html.escape(str(pending.title))
    pending_listing_id = html.escape(str(pending.listing_id))
    pending_reason = html.escape(str(pending.reason))

    st.markdown(
        f"""
        <div class="shipp-recommendation">
          <span class="shipp-recommendation-label">Recommended match</span>
          <div class="shipp-recommendation-title">{pending_title}</div>
          <div class="shipp-recommendation-id">{pending_listing_id}</div>
          <div class="shipp-reason">
            <strong>Why it matches:</strong> {pending_reason}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "♡  Save Match",
        type="primary",
        use_container_width=True,
    ):
        try:
            with st.spinner("Checking current Lakebase state..."):
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
# Architecture / trust statement
# ------------------------------------------------------------

st.markdown(
    """
    <div class="shipp-footer">
      Gold Candidate Matches → AI Search → SHIPP Agent →
      User Confirmation → Lakebase
    </div>
    """,
    unsafe_allow_html=True,
)
