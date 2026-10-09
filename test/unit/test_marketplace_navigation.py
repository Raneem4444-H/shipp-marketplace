"""Workstream A: preserve the working donor/requester Agent flow when adding pages."""

import ast
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[2] / "app.py"


def test_top_navigation_contains_four_real_pages():
    source = APP_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    functions = {node.name for node in module.body if isinstance(node, ast.FunctionDef)}
    assert {"render_home", "render_explore", "render_donor", "render_requester"} <= functions
    assert "position=\"top\"" in source
    assert "active_page.run()" in source
    assert "st.Page(render_home" in source
    assert "st.Page(render_explore" in source
    assert "st.Page(render_donor" in source
    assert "st.Page(render_requester" in source
    assert 'persona = st.radio(' not in source


def test_existing_business_paths_remain_in_place():
    source = APP_PATH.read_text(encoding="utf-8")
    for required in (
        "marketplace.create_listing(",
        "marketplace.save_listing_images(",
        "marketplace.create_request(",
        "agent.get_candidate_matches(",
        "agent.confirm_save(",
        "saved_state_refresh",
        "render_deployment_evidence()",
    ):
        assert required in source
