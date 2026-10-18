"""Fail-closed identity and ownership tests without Databricks credentials."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services.dashboard_service import DashboardService
from services.identity_service import (
    verified_profile,
    verified_databricks_profile,
)
from services.marketplace_service import MarketplaceService
from services.recommendation_service import RecommendationService


class FakeAuth:
    def get_profile(self, user_id):
        if user_id == "owner":
            return {"user_id": "owner", "name": "Owner", "roles": ["DONOR", "REQUESTER"]}
        raise RuntimeError("not found")


class FakeRepo:
    def list_available_listings(self, **kwargs):
        self.last_query = kwargs
        return []
    def list_requests(self, user_id, limit=20):
        return [{"request_id": "owned-request", "category": "FURNITURE",
                 "request_text": "Chair"}] if user_id == "owner" else []
    def list_saved_items(self, user_id, request_id):
        assert (user_id, request_id) == ("owner", "owned-request")
        return [{"saved_item_id": "item-1"}]


def test_identity_fail_closed_without_verified_oidc(monkeypatch):
    monkeypatch.setenv("SHIPP_VERIFIED_PROFILE_MAP", json.dumps({"me@example.com": "owner"}))
    assert verified_profile(FakeAuth(), SimpleNamespace(is_logged_in=False, email="me@example.com")) is None
    assert verified_profile(FakeAuth(), SimpleNamespace(is_logged_in=True, email="other@example.com")) is None
    assert verified_profile(FakeAuth(), SimpleNamespace(is_logged_in=True, email="me@example.com"))["user_id"] == "owner"


def test_dashboard_scopes_requests_and_saved_items():
    service = DashboardService(FakeRepo())
    profile = {"user_id": "owner", "roles": ["REQUESTER"]}
    assert service.requester_saves(profile, "owned-request")[0]["saved_item_id"] == "item-1"
    with pytest.raises(PermissionError):
        service.requester_saves(profile, "other-request")
    with pytest.raises(PermissionError):
        service.donor_listings(profile)


def test_marketplace_service_delegates_server_side_filters():
    repo = FakeRepo()
    service = MarketplaceService(repo)
    service.list_available_listings(query="table", category="FURNITURE", offset=9, limit=9)
    assert repo.last_query == {
        "query": "table", "category": "FURNITURE", "condition": None,
        "donor_id": None, "offset": 9, "limit": 9,
    }


def test_recommendation_requires_requester_role():
    class FakeAgent:
        def confirm_save(self, **kwargs):
            return kwargs
    service = RecommendationService(FakeAgent())
    with pytest.raises(PermissionError):
        service.confirm_save({"user_id": "owner", "roles": ["DONOR"]}, "req", "item")
    out = service.confirm_save({"user_id": "owner", "roles": ["REQUESTER"]}, "req", "item")
    assert out == {"user_id": "owner", "request_id": "req", "listing_id": "item"}



def test_databricks_dual_role_identity(monkeypatch):
    monkeypatch.setenv(
        "SHIPP_DATABRICKS_IDENTITY_MAP",
        json.dumps({
            "platform-user-123": {
                "email": "me@example.com",
                "user_id": "owner",
            }
        }),
    )

    headers = {
        "x-forwarded-user": "platform-user-123",
        "x-forwarded-email": "me@example.com",
    }

    # External deployments must reject Databricks headers.
    monkeypatch.setenv(
        "SHIPP_DEPLOYMENT_TARGET", "external_streamlit"
    )
    assert verified_databricks_profile(
        FakeAuth(), headers
    ) is None

    # Test the configured Databricks App path.
    monkeypatch.setenv(
        "SHIPP_DEPLOYMENT_TARGET", "databricks_app"
    )

    profile = verified_databricks_profile(
        FakeAuth(), headers
    )

    assert profile is not None
    assert profile["user_id"] == "owner"
    assert set(profile["roles"]) == {
        "DONOR", "REQUESTER"
    }

    # Reject a missing platform user identifier.
    assert verified_databricks_profile(
        FakeAuth(),
        {"x-forwarded-email": "me@example.com"},
    ) is None

    # Reject an unknown platform user.
    assert verified_databricks_profile(
        FakeAuth(),
        {
            "x-forwarded-user": "unknown-user",
            "x-forwarded-email": "unknown@example.com",
        },
    ) is None

    # Reject a different user attempting the same email.
    assert verified_databricks_profile(
        FakeAuth(),
        {
            "x-forwarded-user": "different-platform-user",
            "x-forwarded-email": "me@example.com",
        },
    ) is None

    # Reject an email mismatch.
    assert verified_databricks_profile(
        FakeAuth(),
        {
            "x-forwarded-user": "platform-user-123",
            "x-forwarded-email": "different@example.com",
        },
    ) is None

    # Reject a missing approved mapping.
    monkeypatch.delenv(
        "SHIPP_DATABRICKS_IDENTITY_MAP",
        raising=False,
    )
    assert verified_databricks_profile(
        FakeAuth(), headers
    ) is None


def _fake_streamlit(monkeypatch, headers):
    import sys
    from types import ModuleType

    st = ModuleType("streamlit")
    st.session_state = {}
    st.context = SimpleNamespace(headers=headers)
    monkeypatch.setitem(sys.modules, "streamlit", st)
    return st


def test_profile_cache_is_keyed_by_signed_in_identity(monkeypatch):
    import services.identity_service as identity

    monkeypatch.setenv("SHIPP_DEPLOYMENT_TARGET", "databricks_app")
    headers = {"x-forwarded-user": "u-1", "x-forwarded-email": "one@example.com"}
    st = _fake_streamlit(monkeypatch, headers)
    lookups = []

    def fake_resolve():
        lookups.append(headers["x-forwarded-email"])
        return {"user_id": headers["x-forwarded-user"], "roles": ["DONOR"]}

    monkeypatch.setattr(identity, "_resolve_profile_uncached", fake_resolve)

    first = identity.current_profile()
    second = identity.current_profile()
    assert first == second == {"user_id": "u-1", "roles": ["DONOR"]}
    assert lookups == ["one@example.com"]  # second call served from session cache

    # A different asserted identity in the same session must never reuse it.
    headers.update({"x-forwarded-user": "u-2", "x-forwarded-email": "two@example.com"})
    assert identity.current_profile()["user_id"] == "u-2"
    assert lookups == ["one@example.com", "two@example.com"]

    # Expired entries are resolved again so role changes take effect.
    st.session_state[identity._PROFILE_CACHE_KEY]["at"] -= identity.PROFILE_CACHE_SECONDS + 1
    identity.current_profile()
    assert len(lookups) == 3


def test_admin_profile_detection(monkeypatch):
    from services.identity_service import is_admin_profile

    monkeypatch.setenv("SHIPP_ADMIN_PROFILE_IDS", "admin-1, admin-2")
    assert is_admin_profile({"user_id": "admin-2"})
    assert not is_admin_profile({"user_id": "member"})
    assert not is_admin_profile(None)
