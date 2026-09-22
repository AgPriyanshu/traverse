from eval.runners.extraction import render_markdown


def test_render_markdown_skips_cleanly_when_no_gold_roster():
    report = render_markdown({"gold_available": False}, baseline=None)

    assert "Skipped" in report
    assert "no gold roster" in report


def test_render_markdown_reports_error_reason_when_present():
    report = render_markdown(
        {"gold_available": False, "error": "corpus checksum mismatch"}, baseline=None
    )

    assert "corpus checksum mismatch" in report


def test_render_markdown_renders_a_table_with_no_baseline():
    current = {
        "gold_available": True,
        "book_key": "pride-and-prejudice",
        "roster_precision": 0.9,
        "roster_recall": 0.95,
        "roster_f1": 0.924,
        "roster_true_positives": 19,
        "roster_false_positives": 2,
        "roster_false_negatives": 1,
    }

    report = render_markdown(current, baseline=None)

    assert "pride-and-prejudice" in report
    assert "0.900" in report
    assert "19 matched, 2 extra, 1 missed" in report


def test_render_markdown_shows_a_signed_delta_against_a_baseline():
    current = {"gold_available": True, "book_key": "wuthering-heights", "b3_f1": 0.90}
    baseline = {"b3_f1": 0.85}

    report = render_markdown(current, baseline)

    assert "0.900" in report
    assert "0.850 (+0.050)" in report


def test_render_markdown_shows_a_negative_delta_as_a_regression():
    current = {
        "gold_available": True,
        "book_key": "wuthering-heights",
        "tier_accuracy": 0.70,
    }
    baseline = {"tier_accuracy": 0.80}

    report = render_markdown(current, baseline)

    assert "0.800 (-0.100)" in report


def test_render_markdown_surfaces_wrongly_rejected_names():
    current = {
        "gold_available": True,
        "book_key": "pride-and-prejudice",
        "wrongly_rejected": ["Darcy", "Wickham"],
    }

    report = render_markdown(current, baseline=None)

    assert "Darcy, Wickham" in report


def test_render_markdown_surfaces_cascade_contribution():
    current = {
        "gold_available": True,
        "book_key": "pride-and-prejudice",
        "cascade_contribution": {"exact": 40, "llm": 3},
    }

    report = render_markdown(current, baseline=None)

    assert "exact=40" in report
    assert "llm=3" in report
