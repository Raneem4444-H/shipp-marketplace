from pathlib import Path
import sys

import streamlit as st


# ============================================================
# SHIPP APP — REUSE EXISTING AGENT PACKAGE
# ============================================================

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent

AGENT_SRC = REPO_ROOT / "agent" / "agent_ship" / "src"

if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from shipp.agent import ShippAgent


# ============================================================
# UI
# ============================================================

st.set_page_config(
    page_title="SHIPP",
    page_icon="📦",
    layout="wide",
)

st.title("SHIPP Marketplace")
st.caption("Request → Recommendation → Save")

st.success("SHIPP App scaffold is running.")

st.write("Agent package import: PASS")
st.code(str(AGENT_SRC))

st.write(
    "Next gate: configure the existing ShippAgent and connect "
    "the App to real candidate matches."
)