from eval.runners.reconciliation import (
    FALSE_MERGE_TARGET,
    hard_failures,
    render_markdown,
)


def test_render_markdown_skips_cleanly_when_no_gold_identity():
    report = render_markdown({"gold_available": False})

    assert "skipped" in report.lower()


def test_render_markdown_reports_error_reason_when_present():
    report = render_markdown(
        {"gold_available": False, "error": "corpus checksum mismatch"}
    )

    assert "corpus checksum mismatch" in report


def test_render_markdown_renders_the_metrics_table():
    quality = {
        "gold_available": True,
        "project_id": "abc",
        "series_key": "anne-of-green-gables",
        "character_count": 13,
        "book_count": 3,
        "link_precision": 0.97,
        "link_recall": 0.92,
        "false_merge_rate": 0.0,
        "duplicate_rate": 0.0,
        "linked_pairs": 30,
        "correctly_linked_pairs": 29,
        "gold_linked_pairs": 32,
        "missed_link_pairs": 3,
        "duplicate_characters": 0,
        "gold_multi_book_characters": 8,
        "graph_checksum": "deadbeef",
    }

    report = render_markdown(quality)

    assert "anne-of-green-gables" in report
    assert "97.0%" in report
    assert "deadbeef" in report


def test_hard_failures_empty_when_false_merge_rate_is_below_target():
    assert hard_failures({"false_merge_rate": 0.0}) == []
    assert hard_failures({"false_merge_rate": FALSE_MERGE_TARGET}) == []


def test_hard_failures_flags_a_false_merge_rate_over_target():
    problems = hard_failures(
        {"false_merge_rate": 0.05, "false_merge_pairs": 5, "linked_pairs": 100}
    )

    assert len(problems) == 1
    assert "false_merge_rate" in problems[0]


def test_render_markdown_includes_order_check_verdict():
    quality = {"gold_available": False, "graph_checksum": "abc123"}
    order_check = {
        "project_id": "p1",
        "compare_project_id": "p2",
        "checksums_identical": False,
    }

    report = render_markdown(quality, order_check)

    assert "FAIL" in report
    assert "p1" in report and "p2" in report
