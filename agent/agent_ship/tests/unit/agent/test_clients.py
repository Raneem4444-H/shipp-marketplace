"""Lakebase connection/auth behavior for Databricks Apps and notebook fallback."""

from types import SimpleNamespace

import pytest

from agent_fakes import settings
from shipp.agent.clients import _generate_database_token, resolve_pg_target

PG_VARS = (
    "PGHOST",
    "PGUSER",
    "PGDATABASE",
    "PGPASSWORD",
    "SHIPP_LAKEBASE_DATABASE",
)


class FakeWorkspace:
    def __init__(self, dns="ep-test.database.cloud.databricks.com"):
        self.calls = []
        self.database = SimpleNamespace(
            get_database_instance=self._get,
            generate_database_credential=self._legacy_credential,
        )
        self.postgres = SimpleNamespace(
            generate_database_credential=self._postgres_credential,
        )
        self.current_user = SimpleNamespace(
            me=lambda: SimpleNamespace(user_name="roro@example.com")
        )
        self._dns = dns

    def _get(self, name):
        self.calls.append(("get_database_instance", name))
        return SimpleNamespace(read_write_dns=self._dns)

    def _postgres_credential(self, *, endpoint):
        self.calls.append(("postgres_credential", endpoint))
        return SimpleNamespace(token="autoscaling-token")

    def _legacy_credential(self, *, request_id, instance_names):
        self.calls.append(("legacy_credential", tuple(instance_names)))
        assert request_id
        return SimpleNamespace(token="legacy-token")


def _clear(monkeypatch):
    for var in PG_VARS:
        monkeypatch.delenv(var, raising=False)


def test_app_injected_variables_win(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PGHOST", "app-host")
    monkeypatch.setenv("PGUSER", "app-sp")
    monkeypatch.setenv("PGDATABASE", "appdb")
    ws = FakeWorkspace()
    assert resolve_pg_target(
        settings(lakebase_endpoint="projects/p/branches/b/endpoints/e"),
        ws,
    ) == ("app-host", "app-sp", "appdb")
    assert ws.calls == []


def test_app_autoscaling_endpoint_mints_token():
    ws = FakeWorkspace()
    token = _generate_database_token(
        settings(lakebase_endpoint="projects/p/branches/b/endpoints/e"),
        ws,
    )
    assert token == "autoscaling-token"
    assert ws.calls == [
        ("postgres_credential", "projects/p/branches/b/endpoints/e")
    ]


def test_notebook_resolves_from_instance(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPP_LAKEBASE_DATABASE", "shippdb")
    ws = FakeWorkspace()
    host, user, db = resolve_pg_target(
        settings(lakebase_instance="shipp-lb"),
        ws,
    )
    assert (host, user, db) == (
        "ep-test.database.cloud.databricks.com",
        "roro@example.com",
        "shippdb",
    )
    assert ws.calls == [("get_database_instance", "shipp-lb")]


def test_legacy_instance_can_still_mint_token():
    ws = FakeWorkspace()
    token = _generate_database_token(
        settings(lakebase_instance="shipp-lb"),
        ws,
    )
    assert token == "legacy-token"
    assert ws.calls == [("legacy_credential", ("shipp-lb",))]


def test_default_database_when_not_set(monkeypatch):
    _clear(monkeypatch)
    _, _, db = resolve_pg_target(
        settings(lakebase_instance="shipp-lb"),
        FakeWorkspace(),
    )
    assert db == "databricks_postgres"


def test_no_host_and_no_instance_fails_clearly(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="SHIPP_LAKEBASE_INSTANCE"):
        resolve_pg_target(settings(), FakeWorkspace())


def test_no_endpoint_or_instance_cannot_mint_token():
    with pytest.raises(RuntimeError, match="SHIPP_LAKEBASE_ENDPOINT"):
        _generate_database_token(settings(), FakeWorkspace())


def test_instance_without_dns_fails_clearly(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="read_write_dns"):
        resolve_pg_target(
            settings(lakebase_instance="shipp-lb"),
            FakeWorkspace(dns=None),
        )
