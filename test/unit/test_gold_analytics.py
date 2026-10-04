from data_pipeline.gold.analytics import build_marketplace_metrics


def test_marketplace_metrics_are_delete_aware_and_idempotent(spark):
    """Reuse the existing analytics test against SHIPP's current status contract."""
    saved = spark.createDataFrame(
        [
            ("save-1", "insert", 1, 1),
            ("save-2", "insert", 2, 1),
            ("save-2", "delete", 3, 1),
        ],
        ["saved_item_id", "_pg_change_type", "_pg_lsn", "_sort_by"],
    )

    activity = spark.createDataFrame(
        [
            ("a-1", "save_item", "SUCCESS", "insert", 10, 1),
            ("a-2", "save_item", "REJECTED_UNAVAILABLE", "insert", 11, 1),
            ("a-3", "save_item", "REJECTED_DUPLICATE", "insert", 12, 1),
            ("a-4", "save_item", "ERROR", "insert", 13, 1),
        ],
        [
            "activity_id",
            "tool_name",
            "action_status",
            "_pg_change_type",
            "_pg_lsn",
            "_sort_by",
        ],
    )

    row1 = build_marketplace_metrics(saved, activity).first()
    row2 = build_marketplace_metrics(saved, activity).first()

    assert row1.metric_key == "marketplace_current"

    # save-2 was deleted, so only save-1 is current.
    assert row1.saved_item_count == 1

    assert row1.agent_action_count == 4
    assert row1.save_item_action_count == 4
    assert row1.agent_success_count == 1
    assert row1.agent_failure_count == 1
    assert row1.agent_rejected_count == 1
    assert row1.agent_duplicate_count == 1

    # Pure transformation: rerunning with the same histories cannot double-count.
    assert row2.saved_item_count == row1.saved_item_count
    assert row2.agent_action_count == row1.agent_action_count
