"""Workstream A: Lakebase marketplace catalog filters stay parameterized and paginated."""

from app_marketplace import MarketplaceRepo


class FakeCursor:
    def __init__(self, rows=()):
        self.rows = rows
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = tuple(params)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_obj


def test_catalog_filters_are_bound_and_paginated():
    connection = FakeConnection()
    repo = MarketplaceRepo(lambda: connection, "shipp")
    bad_input = "' OR 1=1 --"
    assert repo.list_available_listings(
        limit=10, offset=20, category="FURNITURE",
        condition="GOOD", query=bad_input,
    ) == []

    sql, params = connection.cursor_obj.sql, connection.cursor_obj.params
    assert "status = 'AVAILABLE'" in sql
    assert "available_until >= now()" in sql
    assert "category = %s" in sql and "condition = %s" in sql
    assert "title ILIKE %s OR description ILIKE %s" in sql
    assert "ORDER BY created_at DESC, listing_id DESC" in sql
    assert "LIMIT %s OFFSET %s" in sql
    assert bad_input not in sql
    assert params == (
        "FURNITURE", "GOOD", f"%{bad_input}%", f"%{bad_input}%", 10, 20,
    )


def test_legacy_donor_filter_and_default_limit_still_work():
    connection = FakeConnection()
    repo = MarketplaceRepo(lambda: connection, "shipp")
    repo.list_available_listings(donor_id="donor-123")
    assert "donor_id = %s" in connection.cursor_obj.sql
    assert connection.cursor_obj.params == ("donor-123", 30, 0)


def test_limit_and_offset_are_bounded():
    connection = FakeConnection()
    repo = MarketplaceRepo(lambda: connection, "shipp")
    repo.list_available_listings(limit=10000, offset=-1)
    assert connection.cursor_obj.params == (100, 0)
