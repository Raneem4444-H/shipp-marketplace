"""Requester location regression tests (no Databricks credentials or API calls)."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_requester_page_uses_confirmed_pin_derived_area():
    source = (ROOT / "ui/pages/ai_advisor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "reverse_geocode_pickup_area(" in source
    assert '"requester_pin_confirmed"' in source
    assert "elif not request_location.strip():" in source
    assert "location=request_location," in source
    assert "latitude=requester_lat," in source
    assert "longitude=requester_lon," in source
    assert 'key="request_location"' not in source
    # Source remains a real Python module; a location field is display-only.
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "text_input"
        and any(
            kw.arg == "disabled"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        )
        for node in ast.walk(tree)
    )


def _load_geocoder(monkeypatch):
    streamlit = ModuleType("streamlit")
    streamlit.cache_data = lambda **kwargs: lambda fn: fn
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    spec = importlib.util.spec_from_file_location(
        "_shipp_location_geocoder_test",
        ROOT / "ui/location_geocoding.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_confirmed_coordinates_resolve_to_area(monkeypatch):
    module = _load_geocoder(monkeypatch)
    calls = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "features": [
                    {"properties": {
                        "neighbourhood": "Al Maryah Island",
                        "localadmin": "Abu Dhabi",
                    }}
                ]
            }

    def fake_get(url, *, params, timeout):
        calls.update(url=url, params=params, timeout=timeout)
        return Response()

    monkeypatch.setattr(module.requests, "get", fake_get)
    assert module.reverse_geocode_pickup_area(24.5014, 54.3872, "fake-key") == (
        "Al Maryah Island, Abu Dhabi"
    )
    assert calls["params"]["point.lat"] == 24.5014
    assert calls["params"]["point.lon"] == 54.3872
    assert calls["timeout"] == 8


def test_missing_credential_blocks_lookup(monkeypatch):
    module = _load_geocoder(monkeypatch)

    def unexpected_call(*args, **kwargs):
        raise AssertionError("No request should be made without an API key")

    monkeypatch.setattr(module.requests, "get", unexpected_call)
    assert module.reverse_geocode_pickup_area(24.5, 54.4, "") is None


def test_empty_geocoding_response_returns_none(monkeypatch):
    module = _load_geocoder(monkeypatch)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": []}

    monkeypatch.setattr(module.requests, "get", lambda *a, **k: Response())
    assert module.reverse_geocode_pickup_area(24.5, 54.4, "fake-key") is None


def test_invalid_coordinates_are_rejected(monkeypatch):
    module = _load_geocoder(monkeypatch)
    with pytest.raises(ValueError, match="latitude"):
        module.reverse_geocode_pickup_area(100, 54.4, "fake-key")
    with pytest.raises(ValueError, match="longitude"):
        module.reverse_geocode_pickup_area(24.5, 200, "fake-key")
