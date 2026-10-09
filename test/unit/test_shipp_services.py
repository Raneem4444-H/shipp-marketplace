"""Fail-closed identity and ownership tests without Databricks credentials."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services.dashboard_service import DashboardService
from services.identity_service import verified_profile
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
