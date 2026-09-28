from eval.ablation import (
    BLOCKED_CONFIG_SWITCH,
    build_matrix,
    cache_key,
    matrix_summary,
    metrics_from_answer_quality,
    metrics_from_extraction_quality,
    metrics_from_relation_quality,
)


def test_matrix_has_recommended_extraction_cell():
    matrix = build_matrix()
    recommended = [c for c in matrix if c.axis == "extraction" and c.recommended]

    assert len(recommended) == 1
    assert recommended[0].config == {
        "extraction_mode": "two_pass",
        "alias_mode": "full_cascade",
        "with_human_review": False,
    }
    assert recommended[0].blocked_reason is None


def test_every_axis_has_exactly_one_recommended_cell():
    matrix = build_matrix()
    for axis in ("extraction", "retrieval", "model"):
        recommended = [c for c in matrix if c.axis == axis and c.recommended]
        assert len(recommended) == 1, axis


def test_non_recommended_extraction_cells_are_blocked_on_config_switch():
    matrix = build_matrix()
    for cell in matrix:
        if cell.axis == "extraction" and not cell.recommended:
            assert cell.blocked_reason == BLOCKED_CONFIG_SWITCH


def test_model_and_retrieval_axis_non_recommended_cells_are_not_statically_blocked():
    # S8.2 landed a real runtime switch for these two axes (api/eval/ablation.py
    # ::resolve()) -- scripts/run_ablation.py decides at run time whether a
    # cell can actually be measured (e.g. a missing frontier key), not
    # build_matrix() up front.
    matrix = build_matrix()
    for cell in matrix:
        if cell.axis in ("model", "retrieval"):
            assert cell.blocked_reason is None, cell.label


def test_matrix_is_a_partial_matrix_not_the_full_cross_product():
    # 5 extraction rows x 6 retrieval rows x 3 model rows would be 90 cells.
    # This sprint holds two axes fixed at their recommended value per cell.
    matrix = build_matrix()
    assert len(matrix) < 20
    summary = matrix_summary(matrix)
    assert summary["total"] == len(matrix)
    assert summary["blocked"] > 0
    assert summary["runnable"] > 0
    assert summary["blocked"] + summary["runnable"] == summary["total"]


def test_cache_key_is_deterministic_and_sensitive_to_config():
    matrix = build_matrix()
    a, b = matrix[0], matrix[1]
    key_a1 = cache_key(a, book_key="pride-and-prejudice", corpus_checksum="x", git_sha="sha1")
    key_a2 = cache_key(a, book_key="pride-and-prejudice", corpus_checksum="x", git_sha="sha1")
    key_b = cache_key(b, book_key="pride-and-prejudice", corpus_checksum="x", git_sha="sha1")

    assert key_a1 == key_a2
    assert key_a1 != key_b


def test_cache_key_changes_with_corpus_checksum():
    matrix = build_matrix()
    cell = matrix[3]
    key1 = cache_key(cell, book_key="pride-and-prejudice", corpus_checksum="aaa", git_sha="sha1")
    key2 = cache_key(cell, book_key="pride-and-prejudice", corpus_checksum="bbb", git_sha="sha1")

    assert key1 != key2


def test_metrics_from_extraction_quality_maps_roster_fields():
    payload = {
        "roster_precision": 0.7555555555555555,
        "roster_recall": 0.6538461538461539,
        "roster_f1": 0.7010309278350516,
        "roster_true_positives": 34,
        "roster_false_negatives": 18,
    }
    metrics = metrics_from_extraction_quality(payload)

    assert metrics["precision"] == payload["roster_precision"]
    assert metrics["recall"] == payload["roster_recall"]
    assert metrics["f1"] == payload["roster_f1"]
    assert metrics["sample_size"] == 52


def test_metrics_from_relation_quality_maps_precision_recall_f1():
    payload = {"precision": 0.6666, "recall": 0.303, "f1": 0.4166, "scored_edges": 15}
    metrics = metrics_from_relation_quality(payload)

    assert metrics == {
        "precision": 0.6666,
        "recall": 0.303,
        "f1": 0.4166,
        "sample_size": 15,
    }


def test_metrics_from_answer_quality_is_none_when_unjudged():
    payload = {
        "answered": 19,
        "accuracy": {"hit": 0, "total": 0, "rate": None},
        "citation_precision": {"hit": 0, "total": 0, "rate": None},
    }
    metrics = metrics_from_answer_quality(payload)

    assert metrics["accuracy"] is None
    assert metrics["precision"] is None
    assert metrics["sample_size"] == 19


def test_metrics_from_answer_quality_reads_judged_rate():
    payload = {
        "answered": 30,
        "accuracy": {"hit": 27, "total": 30, "rate": 0.9},
        "citation_precision": {"hit": 28, "total": 30, "rate": 0.9333},
    }
    metrics = metrics_from_answer_quality(payload)

    assert metrics["accuracy"] == 0.9
    assert metrics["precision"] == 0.9333
    assert metrics["sample_size"] == 30
