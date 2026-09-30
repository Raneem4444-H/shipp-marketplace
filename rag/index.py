"""Stage 9B — Databricks AI Search (Vector Search) endpoint + Delta Sync index.

Every function takes the WorkspaceClient explicitly (testable, no globals) and is idempotent:
existing endpoints/indexes are reused, never recreated.
"""

import time
from typing import Callable, Dict, List, Optional

from config.settings import INDEX_SYNC_POLL_SECONDS, INDEX_SYNC_TIMEOUT_SECONDS


def _is_not_found(exc: Exception) -> bool:
    return type(exc).__name__ in ("NotFound", "ResourceDoesNotExist") or "does not exist" in str(exc).lower() \
        or "not found" in str(exc).lower()


def endpoint_state(w, name: str) -> Optional[str]:
    """'ONLINE', 'PROVISIONING', ... or None when the endpoint does not exist."""
    try:
        e = w.vector_search_endpoints.get_endpoint(endpoint_name=name)
    except Exception as exc:  # noqa: BLE001 - SDK error classes differ between versions
        if _is_not_found(exc):
            return None
        raise
    state = e.endpoint_status.state if e.endpoint_status else None
    return getattr(state, "value", state)


def ensure_endpoint(w, name: str) -> str:
    state = endpoint_state(w, name)
    if state is None:
        from databricks.sdk.service.vectorsearch import EndpointType

        print(f"Creating Vector Search endpoint {name} (takes several minutes the first time) ...")
        w.vector_search_endpoints.create_endpoint_and_wait(name=name, endpoint_type=EndpointType.STANDARD)
        state = endpoint_state(w, name)
    print(f"Vector Search endpoint {name}: {state}")
    return state


def index_status(w, index_name: str) -> Optional[Dict]:
    """{'ready': bool, 'indexed_row_count': int, 'message': str} or None when the index does not exist."""
    try:
        idx = w.vector_search_indexes.get_index(index_name=index_name)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        raise
    s = idx.status
    return {
        "ready": bool(getattr(s, "ready", False)),
        "indexed_row_count": getattr(s, "indexed_row_count", None),
        "message": getattr(s, "message", None),
    }


def ensure_delta_sync_index(w, index_name: str, endpoint_name: str, source_table: str,
                            primary_key: str, text_column: str, embedding_endpoint: str,
                            columns_to_sync: List[str]) -> bool:
    """Create the TRIGGERED Delta Sync index if missing. Returns True when it was created now."""
    if index_status(w, index_name) is not None:
        print(f"Index {index_name} exists — reusing it.")
        return False
    from databricks.sdk.service.vectorsearch import (
        DeltaSyncVectorIndexSpecRequest,
        EmbeddingSourceColumn,
        PipelineType,
        VectorIndexType,
    )

    w.vector_search_indexes.create_index(
        name=index_name,
        endpoint_name=endpoint_name,
        primary_key=primary_key,
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=source_table,
            pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[EmbeddingSourceColumn(
                name=text_column, embedding_model_endpoint_name=embedding_endpoint)],
            columns_to_sync=columns_to_sync,
        ),
    )
    print(f"Index {index_name} created (the first sync starts automatically).")
    return True


def trigger_sync(w, index_name: str) -> None:
    w.vector_search_indexes.sync_index(index_name=index_name)


def wait_until_synced(w, index_name: str, expected_rows: int,
                      timeout_seconds: float = INDEX_SYNC_TIMEOUT_SECONDS,
                      poll_seconds: float = INDEX_SYNC_POLL_SECONDS,
                      sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.time) -> float:
    """Poll until the index is ready AND holds exactly expected_rows. Returns seconds waited."""
    started = clock()
    last = None
    while clock() - started <= timeout_seconds:
        last = index_status(w, index_name)
        if last and last["ready"] and last["indexed_row_count"] == expected_rows:
            return round(clock() - started, 1)
        sleep(poll_seconds)
    raise TimeoutError(f"Index {index_name} not synced after {timeout_seconds}s "
                       f"(expected {expected_rows} rows, last status {last})")
