"""The agent's tools: JSON schemas for the model plus their implementations.

Security rule: user_id and request_id are never tool arguments. They come from
the authenticated app session (ToolContext). The model can only choose among
listing_ids that are Gold candidates for that request, so it cannot read or act
on anyone else's data, or on a listing it made up.

Every call is written to agent_activity (spec §5.8, §9.5).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from shipp.agent.config import AgentSettings
from shipp.agent.contracts import (
    ActionStatus,
    CandidateMatch,
    ListingState,
    SaveProposal,
    SearchHit,
)
from shipp.agent.rules import check_listing_saveable

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 500
MAX_REASON_CHARS = 300


# --------------------------------------------------------------- dependencies
class GoldPort(Protocol):
    def get_candidate_matches(
        self, request_id: str, *, limit: int, min_score: float
    ) -> list[CandidateMatch]: ...
    def is_candidate(self, request_id: str, listing_id: str) -> bool: ...


class SearchPort(Protocol):
    def search(self, query: str, *, listing_ids: list[str], k: int) -> list[SearchHit]: ...


class LakebasePort(Protocol):
    def get_listing(self, listing_id: str) -> ListingState | None: ...
    def log_activity(
        self, user_id: str, tool_name: str, entity_id: str | None, status: ActionStatus
    ) -> bool: ...


@dataclass(frozen=True)
class ToolContext:
    user_id: str
    request_id: str


# --------------------------------------------------------------- tool schemas
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_candidate_matches",
            "description": (
                "Return the scored candidate listings for the user's current request, "
                "best first. These are the only listings you may recommend."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_listing_context",
            "description": (
                "Semantic search over the candidate listings' descriptions and "
                "photo-derived text. Use for questions about condition, size, material "
                "or appearance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_listing_status",
            "description": "Check whether a candidate listing is still available right now.",
            "parameters": {
                "type": "object",
                "properties": {"listing_id": {"type": "string"}},
                "required": ["listing_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_save",
            "description": (
                "Propose saving a candidate listing for this request. The user must "
                "confirm in the app; this call does not save anything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "listing_id": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": "One sentence on why this item fits the request.",
                    },
                },
                "required": ["listing_id", "reason"],
            },
        },
    },
]


class ToolArgumentError(ValueError):
    pass


# ----------------------------------------------------------------- toolbox
class ToolBox:
    """Tool implementations for one agent turn, bound to one user and request."""

    def __init__(
        self,
        ctx: ToolContext,
        settings: AgentSettings,
        gold: GoldPort,
        search: SearchPort,
        lakebase: LakebasePort,
    ) -> None:
        self._ctx = ctx
        self._settings = settings
        self._gold = gold
        self._search = search
        self._lakebase = lakebase
        self._candidates: dict[str, CandidateMatch] | None = None
        self.pending_save: SaveProposal | None = None
        self._handlers = {
            "get_candidate_matches": self._get_candidate_matches,
            "search_listing_context": self._search_listing_context,
            "get_listing_status": self._get_listing_status,
            "propose_save": self._propose_save,
        }

    # -- entry point used by the agent loop
    def dispatch(self, name: str, raw_arguments: str | None) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool '{name}'."}
        try:
            args = json.loads(raw_arguments or "{}")
            if not isinstance(args, dict):
                raise ToolArgumentError("Arguments must be a JSON object.")
            payload, entity_id, status = handler(**args)
        except (json.JSONDecodeError, ToolArgumentError, TypeError) as exc:
            payload, entity_id, status = (
                {"error": f"Invalid arguments: {exc}"},
                None,
                ActionStatus.REJECTED,
            )
        except Exception:
            logger.exception("Tool %s failed", name)
            payload, entity_id, status = (
                {"error": "This tool failed. Tell the user you could not check this right now."},
                None,
                ActionStatus.FAILED,
            )
        self._lakebase.log_activity(self._ctx.user_id, name, entity_id, status)
        return payload

    # -- helpers
    def candidates(self) -> dict[str, CandidateMatch]:
        if self._candidates is None:
            rows = self._gold.get_candidate_matches(
                self._ctx.request_id,
                limit=self._settings.max_matches,
                min_score=self._settings.min_match_score,
            )
            self._candidates = {m.listing_id: m for m in rows}
        return self._candidates

    def _require_candidate(self, listing_id: Any) -> CandidateMatch:
        if not isinstance(listing_id, str) or listing_id not in self.candidates():
            raise ToolArgumentError(
                "listing_id is not one of the candidate matches for this request."
            )
        return self.candidates()[listing_id]

    # -- tools
    def _get_candidate_matches(self):
        matches = list(self.candidates().values())
        payload: dict[str, Any] = {"matches": [m.to_tool_payload() for m in matches]}
        if not matches:
            payload["note"] = "No eligible listings for this request yet. Recommend nothing."
        return payload, self._ctx.request_id, ActionStatus.SUCCESS

    def _search_listing_context(self, query: Any):
        if not isinstance(query, str) or not query.strip():
            raise ToolArgumentError("query must be a non-empty string.")
        ids = list(self.candidates())
        hits = self._search.search(
            query.strip()[:MAX_QUERY_CHARS],
            listing_ids=ids,
            k=self._settings.max_search_results,
        )
        return (
            {"results": [h.to_tool_payload() for h in hits]},
            self._ctx.request_id,
            ActionStatus.SUCCESS,
        )

    def _get_listing_status(self, listing_id: Any):
        self._require_candidate(listing_id)
        listing = self._lakebase.get_listing(listing_id)
        reason = check_listing_saveable(listing, datetime.now(timezone.utc))
        payload = {
            "listing_id": listing_id,
            "status": listing.status if listing else None,
            "available_until": (
                listing.available_until.isoformat()
                if listing and listing.available_until
                else None
            ),
            "can_be_saved": reason is None,
            "reason": reason,
        }
        return payload, listing_id, ActionStatus.SUCCESS

    def _propose_save(self, listing_id: Any, reason: Any):
        match = self._require_candidate(listing_id)
        if not isinstance(reason, str) or not reason.strip():
            raise ToolArgumentError("reason must be a non-empty string.")
        blocker = check_listing_saveable(
            self._lakebase.get_listing(listing_id), datetime.now(timezone.utc)
        )
        if blocker is not None:
            return (
                {"proposal_created": False, "reason": blocker},
                listing_id,
                ActionStatus.REJECTED,
            )
        self.pending_save = SaveProposal(
            request_id=self._ctx.request_id,
            listing_id=listing_id,
            title=match.title,
            reason=reason.strip()[:MAX_REASON_CHARS],
        )
        return (
            {
                "proposal_created": True,
                "message": "The app will ask the user to confirm. It is not saved yet.",
            },
            listing_id,
            ActionStatus.SUCCESS,
        )
