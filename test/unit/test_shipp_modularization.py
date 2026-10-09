"""Offline checks for the no-push SHIPP migration utility."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = next(p for p in Path(__file__).resolve().parents if (p / "shipp_modularize.py").exists())
sys.path.insert(0, str(HERE))
from shipp_modularize import LayoutError, render_files  # noqa: E402


FAKE_APP = '''# SHIPP — Databricks App
from __future__ import annotations
from pathlib import Path
import streamlit as st
ROOT_DIR = Path(__file__).resolve().parent
st.set_page_config(page_title="SHIPP")
def load_css():
    pass
load_css()
marketplace = object()
agent = object()
def render_listing_gallery(*a, **k):
    pass
def render_deployment_evidence():
    pass
def load_listing_image(*a):
    pass
st.session_state

def render_saved_items(user_id, request_id):
    pass

def location_picker(*a, **k):
    pass

def run_agent_turn(*a, **k):
    pass

def reset_request_session(*a):
    pass

def display_user(row):
    return row["name"]

defaults = {"messages": [], "pending_save": None}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ------------------------------------------------------------
# Shared marketplace brand. Streamlit renders the page navigation in its top bar.
# ------------------------------------------------------------
st.markdown("SHIPP")

# ============================================================
# DONOR JOURNEY
# ============================================================
def render_donor():
    render_deployment_evidence()
    marketplace.create_listing(donor_id="test")
    marketplace.save_listing_images(listing_id="test", uploads=[])

# ============================================================
# REQUESTER JOURNEY
# ============================================================
def render_requester():
    marketplace.create_request(requester_id="test")
    agent.confirm_save(user_id="test", request_id="req", listing_id="item")

CATALOG_PAGE_SIZE = 9

def render_home():
    marketplace.list_available_listings(limit=6)
    st.switch_page(EXPLORE_PAGE)

def render_explore():
    marketplace.list_available_listings(limit=CATALOG_PAGE_SIZE + 1, offset=0)

# ------------------------------------------------------------
# Professional project footer
# ------------------------------------------------------------
st.markdown("Footer")
'''


def test_generated_pages_compile_and_preserve_write_calls():
    out = render_files(FAKE_APP)
    assert "def render_donor()" in out["ui/pages/donate.py"]
    assert 'marketplace.save_listing_images(' in out["ui/pages/donate.py"]
    assert 'agent.confirm_save(' in out["ui/pages/ai_advisor.py"]
    assert 'ui/pages/marketplace.py' in out["ui/pages/home.py"]
    assert 'ROOT_DIR = Path(__file__).resolve().parents[1]' in out["ui/legacy_core.py"]
    assert 'st.set_page_config' not in out["ui/legacy_core.py"]
    for path, contents in out.items():
        compile(contents, path, "exec")


def test_converter_refuses_missing_functions_without_writing():
    with pytest.raises(LayoutError, match="Missing current-app functions"):
        render_files(FAKE_APP.replace("def render_requester():", "def other_name():"))


def test_cli_preview_does_not_change_source(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    original = repo / "app.py"
    original.write_text(FAKE_APP, encoding="utf-8")
    out = tmp_path / "preview"
    p = subprocess.run(
        [sys.executable, str(HERE / "shipp_modularize.py"),
         "--repo", str(repo), "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert p.returncode == 0, p.stderr
    assert "NO GIT ACTIONS" in p.stdout
    assert original.read_text(encoding="utf-8") == FAKE_APP
    assert (out / "app.py").exists()
    assert (out / "ui/pages/donate.py").exists()
    assert (out / "ui/components/footer.py").exists()
    assert (out / "services/identity_service.py").exists()


def test_apply_creates_backup_and_is_explicit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(FAKE_APP, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(HERE / "shipp_modularize.py"),
         "--repo", str(repo), "--apply"],
        capture_output=True, text=True, check=False,
    )
    assert p.returncode == 0, p.stderr
    assert (repo / "app.py").read_text(encoding="utf-8").startswith('"""SHIPP — small')
    backups = list((repo / ".shipp-refactor-backup").glob("app-*.py"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == FAKE_APP
