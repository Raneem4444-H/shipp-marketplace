"""Runtime settings for the Shipp agent.

Values come from environment variables:
- local dev: `.env`, loaded by python-dotenv before the agent is built
- Databricks App: the `env:` block in app.yaml plus injected app resources

No secret lives in this module. Credentials are resolved by the Databricks SDK
(unified auth) or by the Lakebase credential API, never read from code.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_THREE_PART = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$"
)


def validate_identifier(value: str, *, three_part: bool = False) -> str:
    """Reject anything that is not a plain SQL identifier.

    Table and schema names cannot be bound as query parameters, so they are
    interpolated into SQL. This check is what makes that interpolation safe.
    """
    pattern = _THREE_PART if three_part else _IDENT
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class AgentSettings:
    llm_endpoint: str
    sql_warehouse_id: str
    candidate_matches_table: str
    search_index: str
    lakebase_schema: str
    # Lakebase Autoscaling endpoint resource path, for example:
    # projects/<project>/branches/<branch>/endpoints/<endpoint>.
    lakebase_endpoint: str | None = None
    # Legacy/Provisioned Lakebase instance name. Kept for notebook/local fallback.
    lakebase_instance: str | None = None
    max_matches: int = 5
    max_search_results: int = 5
    max_tool_rounds: int = 6
    min_match_score: float = 0.0

    def __post_init__(self) -> None:
        validate_identifier(self.candidate_matches_table, three_part=True)
        validate_identifier(self.search_index, three_part=True)
        validate_identifier(self.lakebase_schema)
        if not 1 <= self.max_matches <= 10:
            raise ValueError("max_matches must be between 1 and 10")
        if not 1 <= self.max_search_results <= 20:
            raise ValueError("max_search_results must be between 1 and 20")
        if not 1 <= self.max_tool_rounds <= 10:
            raise ValueError("max_tool_rounds must be between 1 and 10")
        if not 0.0 <= self.min_match_score <= 1.0:
            raise ValueError("min_match_score must be between 0 and 1")

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            llm_endpoint=_require("SHIPP_LLM_ENDPOINT"),
            sql_warehouse_id=_require("SHIPP_SQL_WAREHOUSE_ID"),
            candidate_matches_table=os.getenv(
                "SHIPP_CANDIDATE_MATCHES_TABLE", "shipp.gold.gold_candidate_matches"
            ),
            search_index=os.getenv(
                "SHIPP_SEARCH_INDEX", "shipp.gold.gold_listing_search_docs_index"
            ),
            lakebase_schema=os.getenv("SHIPP_LAKEBASE_SCHEMA", "bootcamp_shipp"),
            lakebase_endpoint=(
                os.getenv("SHIPP_LAKEBASE_ENDPOINT")
                or os.getenv("ENDPOINT_NAME")
            ),
            lakebase_instance=os.getenv("SHIPP_LAKEBASE_INSTANCE"),
            max_matches=int(os.getenv("SHIPP_AGENT_MAX_MATCHES", "5")),
            max_search_results=int(os.getenv("SHIPP_AGENT_MAX_SEARCH_RESULTS", "5")),
            max_tool_rounds=int(os.getenv("SHIPP_AGENT_MAX_TOOL_ROUNDS", "6")),
            min_match_score=float(os.getenv("SHIPP_AGENT_MIN_MATCH_SCORE", "0.0")),
        )
