"""Cover-image batch and thumbnail tests. No live Databricks connection."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from app_marketplace import MarketplaceRepo
from ui.image_utils import make_card_thumbnail


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.executions.append((sql, params))

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
    def __init__(self, sources):
        self.sources = sources
        self.downloaded = []

    def download(self, path):
        self.downloaded.append(path)
        if path not in self.sources:
            raise OSError("Volume file missing")
        return SimpleNamespace(contents=BytesIO(self.sources[path]))


def test_batch_uses_one_parameterized_metadata_query_and_preserves_missing():
    db = FakeConnection([("item-b", "/volume/b"), ("item-a", "/volume/a")])
    files = FakeFiles({"/volume/a": b"cover-a", "/volume/b": b"cover-b"})
    repo = MarketplaceRepo(lambda: db, "shipp", workspace=SimpleNamespace(files=files))

    result = repo.get_primary_listing_images(["item-a", "item-b", "item-c", "item-a"])
    assert result == {"item-a": b"cover-a", "item-b": b"cover-b", "item-c": None}
    assert len(db.cursor_instance.executions) == 1
    sql, params = db.cursor_instance.executions[0]
    assert "SELECT DISTINCT ON (listing_id)" in sql
    assert "ORDER BY listing_id, uploaded_at ASC, listing_file_id ASC" in sql
    assert "IN (%s, %s, %s)" in sql
    assert params == ("item-a", "item-b", "item-c", "image/%")
    assert files.downloaded == ["/volume/b", "/volume/a"]


def test_failed_volume_file_does_not_hide_other_covers():
    db = FakeConnection([("missing", "/volume/missing"), ("good", "/volume/good")])
    files = FakeFiles({"/volume/good": b"good-cover"})
    repo = MarketplaceRepo(lambda: db, "shipp", workspace=SimpleNamespace(files=files))
    assert repo.get_primary_listing_images(["missing", "good"]) == {
        "missing": None, "good": b"good-cover"
    }


def test_no_images_skips_query_and_missing_workspace_returns_none():
    db = FakeConnection([])
    repo = MarketplaceRepo(lambda: db, "shipp")
    assert repo.get_primary_listing_images([]) == {}
    assert repo.get_primary_listing_images(["item"]) == {"item": None}
    assert db.cursor_instance.executions == []


def test_card_thumbnail_is_bounded_and_jpeg():
    original = BytesIO()
    Image.new("RGB", (1400, 900), color="teal").save(original, "PNG")
    cover = make_card_thumbnail(original.getvalue())
    with Image.open(BytesIO(cover)) as image:
        assert image.format == "JPEG"
        assert image.width <= 480
        assert image.height <= 320
    assert len(cover) < len(original.getvalue())


def test_transparent_thumbnail_and_bad_input():
    original = BytesIO()
    Image.new("RGBA", (50, 50), color=(255, 0, 0, 0)).save(original, "PNG")
    with Image.open(BytesIO(make_card_thumbnail(original.getvalue()))) as image:
        assert image.mode == "RGB"
    assert make_card_thumbnail(b"not-an-image") == b"not-an-image"
