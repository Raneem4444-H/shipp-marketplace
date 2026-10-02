"""resolve_pg_target: App-injected variables win; otherwise resolve from the instance."""

from types import SimpleNamespace

import pytest

from agent_fakes import settings
from shipp.agent.clients import resolve_pg_target

PG_VARS = ("PGHOST", "PGUSER", "PGDATABASE", "SHIPP_LAKEBASE_DATABASE")


class FakeWorkspace:
    def __init__(self, dns="ep-test.database.cloud.databricks.com"):
        self.calls = []
        self.database = SimpleNamespace(get_database_instance=self._get)
        self.current_user = SimpleNamespace(me=lambda: SimpleNamespace(user_name="roro@example.com"))
        self._dns = dns

    def _get(self, name):
        self.calls.append(name)
        return SimpleNamespace(read_write_dns=self._dns)


def _clear(monkeypatch):
    for v in PG_VARS:
        monkeypatch.delenv(v, raising=False)


def test_app_injected_variables_win(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PGHOST", "app-host")
    monkeypatch.setenv("PGUSER", "app-sp")
    monkeypatch.setenv("PGDATABASE", "appdb")
    ws = FakeWorkspace()
    assert resolve_pg_target(settings(lakebase_instance="shipp-lb"), ws) == ("app-host", "app-sp", "appdb")
    assert ws.calls == []  # no SDK lookup needed inside an App


def test_notebook_resolves_from_instance(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPP_LAKEBASE_DATABASE", "shippdb")
    ws = FakeWorkspace()
    host, user, db = resolve_pg_target(settings(lakebase_instance="shipp-lb"), ws)
    assert (host, user, db) == ("ep-test.database.cloud.databricks.com", "roro@example.com", "shippdb")
    assert ws.calls == ["shipp-lb"]


def test_default_database_when_not_set(monkeypatch):
    _clear(monkeypatch)
    _, _, db = resolve_pg_target(settings(lakebase_instance="shipp-lb"), FakeWorkspace())
    assert db == "databricks_postgres"


def test_no_host_and_no_instance_fails_clearly(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="SHIPP_LAKEBASE_INSTANCE"):
        resolve_pg_target(settings(), FakeWorkspace())


def test_instance_without_dns_fails_clearly(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="read_write_dns"):
        resolve_pg_target(settings(lakebase_instance="shipp-lb"), FakeWorkspace(dns=None))
