"""Stage 11.3 — retrieval evaluation on a small labeled set (rag/eval/eval_set.json)."""

import json
from typing import Dict, List, Sequence


def load_eval_set(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as fh:
        cases = json.load(fh)
    for c in cases:
        assert {"id", "query", "expected_listing_ids"} <= set(c), f"bad eval case: {c}"
    return cases


def hit_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> int:
    return int(bool(set(retrieved[:k]) & set(expected)))


def reciprocal_rank(retrieved: Sequence[str], expected: Sequence[str]) -> float:
    for i, listing_id in enumerate(retrieved, 1):
        if listing_id in expected:
            return 1.0 / i
    return 0.0


def summarize(results: List[Dict]) -> Dict:
    """results: [{hit, rr, latency_ms, positive}] -> aggregate metrics over positive cases."""
    positives = [r for r in results if r["positive"]]
    n = len(positives)
    latencies = sorted(r["latency_ms"] for r in results)
    return {
        "positive_cases": n,
        "hit_rate": round(sum(r["hit"] for r in positives) / n, 3) if n else None,
        "mrr": round(sum(r["rr"] for r in positives) / n, 3) if n else None,
        "p50_latency_ms": latencies[len(latencies) // 2] if latencies else None,
        "max_latency_ms": latencies[-1] if latencies else None,
    }
