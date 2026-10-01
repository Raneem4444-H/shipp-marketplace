import pytest

from shipp.agent.gold import GoldReader


class _WorkspaceStub:
    pass


def test_gold_reader_rejects_unsafe_table_identifier():
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        GoldReader(
            _WorkspaceStub(),
            "warehouse-id",
            "catalog.schema.matches;DROP_TABLE",
        )


def test_candidate_limit_is_integer_and_capped_at_ten():
    reader = GoldReader(
        _WorkspaceStub(),
        "warehouse-id",
        "catalog.schema.gold_candidate_matches",
    )
    captured = {}

    def fake_run(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    reader._run = fake_run

    assert reader.get_candidate_matches(
        "request-001",
        limit="999",
        min_score=0.0,
    ) == []

    assert captured["sql"].endswith("LIMIT 10")
    assert ":request_id" in captured["sql"]
    assert ":min_score" in captured["sql"]
    assert captured["params"]["request_id"] == ("request-001", "STRING")
