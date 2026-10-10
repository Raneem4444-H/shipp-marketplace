"""Multi-photo listing repository regression checks (no external credentials)."""
from __future__ import annotations

import io
from types import SimpleNamespace

from app_marketplace import MarketplaceRepo


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statement = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params):
        self.statement = statement
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_instance


class FakeFiles:
    def __init__(self, files, fail=()):
        self.files = files
        self.fail = set(fail)
        self.downloaded = []

    def download(self, path):
        self.downloaded.append(path)
        if path in self.fail:
            raise OSError("volume unavailable")
        return SimpleNamespace(contents=io.BytesIO(self.files[path]))


def test_three_listing_images_are_loaded_in_order():
    db = FakeConnection([("a", "/p/1"), ("b", "/p/2"), ("c", "/p/3")])
    storage = FakeFiles({"/p/1": b"one", "/p/2": b"two", "/p/3": b"three"})
    repo = MarketplaceRepo(lambda: db, "shipp", workspace=SimpleNamespace(files=storage))

    result = repo.get_listing_images("item-1")
    assert [p["content"] for p in result] == [b"one", b"two", b"three"]
    assert storage.downloaded == ["/p/1", "/p/2", "/p/3"]
    assert "ORDER BY uploaded_at ASC, listing_file_id ASC" in db.cursor_instance.statement
    assert db.cursor_instance.params == ("item-1", "image/%", 5)


def test_one_failed_photo_does_not_hide_other_photos():
    db = FakeConnection([("a", "/p/1"), ("b", "/p/2")])
    storage = FakeFiles({"/p/1": b"one"}, fail=["/p/2"])
    repo = MarketplaceRepo(lambda: db, "shipp", workspace=SimpleNamespace(files=storage))

    result = repo.get_listing_images("item-1")
    assert [p["content"] for p in result] == [b"one", None]


def test_gallery_bound_and_empty_state():
    db = FakeConnection([])
    storage = FakeFiles({})
    repo = MarketplaceRepo(lambda: db, "shipp", workspace=SimpleNamespace(files=storage))
    assert repo.get_listing_images("item-1", limit=100) == []
    assert db.cursor_instance.params == ("item-1", "image/%", 5)


def test_no_volume_client_returns_empty_gallery():
    repo = MarketplaceRepo(lambda: None, "shipp")
    assert repo.get_listing_images("item-1") == []
