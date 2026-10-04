"""Final-submission contract guards.

These tests protect only the frozen submission wiring. They do not replace
Databricks runtime validation.
"""

from __future__ import annotations

import json
from pathlib import Path

from config.settings import SCORING

ROOT = Path(__file__).resolve().parents[2]


def test_root_databricks_app_is_canonical() -> None:
    """The final App contract must live at repository root."""
    assert (ROOT / "app.py").is_file()
    assert (ROOT / "app.yaml").is_file()
    assert (ROOT / "requirements.txt").is_file()

    manifest = (ROOT / "app.yaml").read_text(encoding="utf-8")
    required_bindings = {
        "SHIPP_LLM_ENDPOINT",
        "SHIPP_SQL_WAREHOUSE_ID",
        "SHIPP_CANDIDATE_MATCHES_TABLE",
        "SHIPP_SEARCH_INDEX",
        "SHIPP_LAKEBASE_SCHEMA",
        "SHIPP_LAKEBASE_ENDPOINT",
    }
    missing = sorted(name for name in required_bindings if name not in manifest)
    assert not missing, f"Root app.yaml is missing managed-resource bindings: {missing}"

    legacy_notice = (ROOT / "app" / "README.md").read_text(encoding="utf-8")
    assert "Do not deploy this directory" in legacy_notice
    assert "repository root" in legacy_notice


def test_pipeline_uses_canonical_notebook_60_analytics_writer() -> None:
    """Pipeline 90 must call Notebook 60, not the competing Python analytics module."""
    notebook_path = ROOT / "notebooks" / "pipeline" / "90_run_pipeline.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "\n".join(
        line
        for cell in notebook["cells"]
        for line in cell.get("source", [])
    )

    assert "../development/60_gold_marketplace_metrics" in source
    assert "data_pipeline.gold.analytics" not in source
    assert "data_pipeline/gold/analytics.py" not in source


def test_gold_v1_scoring_contract_remains_frozen() -> None:
    """Prevent an accidental final-day scoring change without team approval."""
    assert SCORING["version"] == "v1-structured"
    assert SCORING["weights"] == {
        "distance": 0.50,
        "timing": 0.30,
        "condition": 0.20,
    }
