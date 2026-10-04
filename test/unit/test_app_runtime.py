from app_runtime import bootstrap_streamlit_secrets, runtime_config_status


def test_bootstrap_streamlit_secrets_supports_sections(monkeypatch):
    for name in (
        "DATABRICKS_HOST",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
        "PGHOST",
        "PGDATABASE",
        "SHIPP_LAKEBASE_ENDPOINT",
        "SHIPP_LLM_ENDPOINT",
        "SHIPP_SQL_WAREHOUSE_ID",
        "SHIPP_CANDIDATE_MATCHES_TABLE",
        "SHIPP_SEARCH_INDEX",
    ):
        monkeypatch.delenv(name, raising=False)

    secrets = {
        "databricks": {
            "DATABRICKS_HOST": "https://example.databricks.com",
            "DATABRICKS_CLIENT_ID": "client-id",
            "DATABRICKS_CLIENT_SECRET": "client-secret",
        },
        "lakebase": {
            "PGHOST": "db.example",
            "PGDATABASE": "databricks_postgres",
            "SHIPP_LAKEBASE_ENDPOINT": "projects/p/branches/b/endpoints/e",
        },
        "shipp": {
            "SHIPP_LLM_ENDPOINT": "llm",
            "SHIPP_SQL_WAREHOUSE_ID": "warehouse",
            "SHIPP_CANDIDATE_MATCHES_TABLE": (
                "bootcamp_students.shipp_gold.gold_candidate_matches"
            ),
            "SHIPP_SEARCH_INDEX": (
                "bootcamp_students.shipp_gold.gold_listing_search_docs_index"
            ),
        },
    }

    loaded = bootstrap_streamlit_secrets(secrets)

    assert "DATABRICKS_HOST" in loaded
    assert "DATABRICKS_CLIENT_SECRET" in loaded
    status = runtime_config_status()
    assert status["marketplace_ready"] is True
    assert status["agent_ready"] is True


def test_existing_environment_wins(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://existing")
    bootstrap_streamlit_secrets(
        {"databricks": {"DATABRICKS_HOST": "https://replacement"}}
    )
    assert __import__("os").environ["DATABRICKS_HOST"] == "https://existing"
