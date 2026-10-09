"""Regression tests for SHIPP modular Streamlit application."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PAGES = {
    "home.py": "render_home",
    "marketplace.py": "render_explore",
    "donate.py": "render_donor",
    "ai_advisor.py": "render_requester",
}


def test_top_navigation_contains_four_real_pages():
    entry = (ROOT / "app.py").read_text(encoding="utf-8")
    navbar = (ROOT / "ui/components/navbar.py").read_text(
        encoding="utf-8"
    )

    assert "from ui import legacy_core as core" in entry
    assert "from ui.components.navbar import create_navigation" in entry
    assert "navigation.run()" in entry
    assert 'position="top"' in navbar

    for filename, function_name in PAGES.items():
        path = ROOT / "ui/pages" / filename
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }

        invocations = {
            node.value.func.id
            for node in tree.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        }

        assert function_name in definitions
        assert function_name in invocations
        assert f'st.Page("ui/pages/{filename}"' in navbar

    assert "persona = st.radio(" not in entry


def test_existing_business_paths_remain_in_place():
    required = {
        "ui/pages/donate.py": [
            "marketplace.create_listing(",
            "marketplace.save_listing_images(",
            "render_deployment_evidence()",
        ],
        "ui/pages/ai_advisor.py": [
            "marketplace.create_request(",
            "agent.get_candidate_matches(",
            "agent.confirm_save(",
            "saved_state_refresh",
            "render_deployment_evidence()",
        ],
        "ui/legacy_core.py": [
            "def render_deployment_evidence(",
            "def load_listing_image(",
            "def render_listing_gallery(",
        ],
        "ui/pages/home.py": [
            "catalog.list_available_listings(",
            "render_listing_gallery(",
        ],
        "ui/pages/marketplace.py": [
            "catalog.list_available_listings(",
            "render_listing_gallery(",
        ],
    }

    for filename, markers in required.items():
        source = (ROOT / filename).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in source, (
                f"Missing {marker!r} in {filename}"
            )
