"""Verify flat, user-scoped pilot navigation without Databricks credentials."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def _navbar(monkeypatch, profile):
    pages = []
    captured = {}
    st = ModuleType("streamlit")

    def page(path, **options):
        p = SimpleNamespace(path=path, **options)
        pages.append(p)
        return p

    def navigation(items, position):
        captured.update(items=items, position=position)
        return captured

    st.Page = page
    st.navigation = navigation
    identity = ModuleType("services.identity_service")
    identity.current_profile = lambda: profile
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "services.identity_service", identity)
    spec = importlib.util.spec_from_file_location("_shipp_nav_test", ROOT / "ui/components/navbar.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.create_navigation()
    return captured


def test_flat_top_navigation_and_dashboard_links(monkeypatch):
    monkeypatch.delenv("SHIPP_ADMIN_PROFILE_IDS", raising=False)
    nav = _navbar(monkeypatch, None)
    assert nav["position"] == "top"
    assert isinstance(nav["items"], list)
    assert [page.title for page in nav["items"] if getattr(page, "visibility", "visible") != "hidden"] == [
        "Home", "Explore", "Give an item", "Find an item", "My Dashboard", "Account",
    ]
    assert {page.path for page in nav["items"] if getattr(page, "visibility", "visible") == "hidden"} == {
        "ui/pages/donor_dashboard.py", "ui/pages/requester_dashboard.py",
    }


def test_verified_member_first_name_and_admin_visibility(monkeypatch):
    monkeypatch.setenv("SHIPP_ADMIN_PROFILE_IDS", "real-admin")
    member = _navbar(monkeypatch, {"name": "Amina Saleh", "user_id": "member"})
    visible = [p.title for p in member["items"] if getattr(p, "visibility", "visible") != "hidden"]
    assert "Welcome, Amina" in visible
    assert "Engineering" not in visible
    admin = _navbar(monkeypatch, {"name": "Site Admin", "user_id": "real-admin"})
    assert any(p.title == "Engineering" for p in admin["items"])


def test_dashboard_reuses_role_scoped_services_and_existing_pages():
    source = (ROOT / "ui/pages/dashboard.py").read_text(encoding="utf-8")
    assert "current_profile()" in source
    assert "DashboardService(marketplace)" in source
    assert "dashboard.donor_listings(profile, limit=30)" in source
    assert "dashboard.requester_requests(profile, limit=20)" in source
    for filename in ["auth", "donor_dashboard", "requester_dashboard", "donate", "ai_advisor"]:
        assert f'"ui/pages/{filename}.py"' in source
    assert "list_users(" not in source
    assert "st.selectbox(" not in source


def _render_dashboard(monkeypatch, profile):
    """Run the actual dashboard page against mocked Streamlit and read services."""
    import runpy
    from contextlib import nullcontext

    calls = {"links": [], "metrics": [], "queries": []}
    st = ModuleType("streamlit")
    st.title = lambda text: calls.setdefault("titles", []).append(text)
    st.caption = lambda text: None
    st.subheader = lambda text: None
    st.info = lambda text: calls.setdefault("info", []).append(text)
    st.warning = lambda text: calls.setdefault("warnings", []).append(text)
    st.error = lambda text: calls.setdefault("errors", []).append(text)
    st.divider = lambda: None
    st.metric = lambda label, value: calls["metrics"].append((label, value))
    st.page_link = lambda path, **kwargs: calls["links"].append(path)
    st.columns = lambda n, **kwargs: [nullcontext() for _ in range(n)]

    identity = ModuleType("services.identity_service")
    identity.current_profile = lambda: profile
    dashboard_mod = ModuleType("services.dashboard_service")

    class FakeDashboardService:
        def __init__(self, repo):
            assert repo is fake_repo

        def donor_listings(self, profile, limit=30):
            calls["queries"].append(("donor", profile["user_id"], limit))
            return [{"listing_id": "one"}]

        def requester_requests(self, profile, limit=20):
            calls["queries"].append(("requester", profile["user_id"], limit))
            return [{"request_id": "one"}, {"request_id": "two"}]

    dashboard_mod.DashboardService = FakeDashboardService
    fake_repo = object()
    legacy = ModuleType("ui.legacy_core")
    legacy.marketplace = fake_repo
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "services.identity_service", identity)
    monkeypatch.setitem(sys.modules, "services.dashboard_service", dashboard_mod)
    monkeypatch.setitem(sys.modules, "ui.legacy_core", legacy)
    runpy.run_path(str(ROOT / "ui/pages/dashboard.py"), run_name="__main__")
    return calls


def test_dashboard_renders_only_verified_owners_data(monkeypatch):
    profile = {"user_id": "raneem", "name": "Raneem User", "roles": ["DONOR", "REQUESTER"]}
    calls = _render_dashboard(monkeypatch, profile)
    assert calls["titles"] == ["Raneem's dashboard"]
    assert calls["queries"] == [("donor", "raneem", 30), ("requester", "raneem", 20)]
    assert calls["metrics"] == [("Available items (up to 30)", 1), ("Recent requests (up to 20)", 2)]
    assert "ui/pages/donor_dashboard.py" in calls["links"]
    assert "ui/pages/requester_dashboard.py" in calls["links"]


def test_unregistered_dashboard_shows_signup_without_queries(monkeypatch):
    calls = _render_dashboard(monkeypatch, None)
    assert calls["links"] == ["ui/pages/auth.py"]
    assert calls["queries"] == []
