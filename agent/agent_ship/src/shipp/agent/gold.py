"""Read trusted candidate matches from Gold.

Uses the Databricks SQL Statement Execution API through databricks-sdk, so the
same code runs locally and inside a Databricks App with no Spark session.
Values are bound as named parameters; only the validated table name is
interpolated.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shipp.agent.config import validate_identifier
from shipp.agent.contracts import CANDIDATE_MATCH_COLUMNS, CandidateMatch, ContractError


class GoldReadError(RuntimeError):
    pass


def _to_float(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def parse_candidate_rows(rows: Sequence[Sequence[Any]]) -> list[CandidateMatch]:
    """Turn JSON_ARRAY rows (all values arrive as strings or None) into matches."""
    matches: list[CandidateMatch] = []
    width = len(CANDIDATE_MATCH_COLUMNS)
    for row in rows:
        if len(row) != width:
            raise ContractError(
                f"gold_candidate_matches row has {len(row)} columns, expected {width}"
            )
        rec = dict(zip(CANDIDATE_MATCH_COLUMNS, row, strict=True))
        if rec["listing_id"] is None or rec["match_score"] is None:
            raise ContractError("gold_candidate_matches row missing listing_id or match_score")
        matches.append(
            CandidateMatch(
                request_id=str(rec["request_id"]),
                listing_id=str(rec["listing_id"]),
                title=str(rec["title"] or ""),
                category=str(rec["category"] or ""),
                condition=rec["condition"],
                area=rec["area"],
                match_score=float(rec["match_score"]),
                distance_km=_to_float(rec["distance_km"]),
                duration_min=_to_float(rec["duration_min"]),
                available_until=rec["available_until"],
                computed_at=rec["computed_at"],
            )
        )
    return matches


class GoldReader:
    def __init__(
        self,
        workspace_client: Any,
        warehouse_id: str,
        table: str,
        wait_timeout: str = "30s",
    ) -> None:
        self._w = workspace_client
        self._warehouse_id = warehouse_id
        self._table = validate_identifier(table, three_part=True)
        self._wait_timeout = wait_timeout

    def get_candidate_matches(
        self, request_id: str, *, limit: int, min_score: float
    ) -> list[CandidateMatch]:
        # LIMIT cannot be bound by the Statement Execution API in this query.
        # Convert before interpolation and cap the model/app-controlled value.
        limit = max(1, min(int(limit), 10))
        sql = (
            f"SELECT {', '.join(CANDIDATE_MATCH_COLUMNS)} FROM {self._table} "
            "WHERE request_id = :request_id AND match_score >= :min_score "
            f"ORDER BY match_score DESC, listing_id LIMIT {limit}"
        )
        rows = self._run(
            sql,
            {"request_id": (request_id, "STRING"), "min_score": (str(min_score), "DOUBLE")},
        )
        return parse_candidate_rows(rows)

    def is_candidate(self, request_id: str, listing_id: str) -> bool:
        sql = (
            f"SELECT 1 FROM {self._table} "
            "WHERE request_id = :request_id AND listing_id = :listing_id LIMIT 1"
        )
        rows = self._run(
            sql,
            {"request_id": (request_id, "STRING"), "listing_id": (listing_id, "STRING")},
        )
        return len(rows) > 0

    def _run(self, sql: str, params: dict[str, tuple[str, str]]) -> list[list[Any]]:
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        resp = self._w.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=self._warehouse_id,
            parameters=[
                StatementParameterListItem(name=name, value=value, type=sql_type)
                for name, (value, sql_type) in params.items()
            ],
            wait_timeout=self._wait_timeout,
        )
        state = resp.status.state if resp.status else None
        if state != StatementState.SUCCEEDED:
            detail = (
                resp.status.error.message
                if resp.status and resp.status.error
                else "no error detail (likely still running past wait_timeout)"
            )
            raise GoldReadError(f"Gold query did not succeed (state={state}): {detail}")
        if resp.result is None or resp.result.data_array is None:
            return []
        return resp.result.data_array
