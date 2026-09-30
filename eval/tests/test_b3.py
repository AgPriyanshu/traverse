import math

import pytest

from eval.metrics import b3_precision_recall_f1

TOY_GOLD = {
    "1": "G1",
    "2": "G1",
    "3": "G1",
    "4": "G2",
    "5": "G2",
    "6": "G2",
}
TOY_PREDICTED = {
    "1": "P1",
    "2": "P1",
    "3": "P2",
    "4": "P1",
    "5": "P2",
    "6": "P2",
}


def test_b3_matches_hand_computed_toy_example():
    result = b3_precision_recall_f1(TOY_PREDICTED, TOY_GOLD)

    assert result.n_items == 6
    assert math.isclose(result.precision, 5 / 9, rel_tol=1e-9)
    assert math.isclose(result.recall, 5 / 9, rel_tol=1e-9)
    assert math.isclose(result.f1, 5 / 9, rel_tol=1e-9)


def test_b3_perfect_clustering_scores_one():
    gold = {"1": "A", "2": "A", "3": "B"}
    predicted = {"1": "X", "2": "X", "3": "Y"}  # different labels, same grouping

    result = b3_precision_recall_f1(predicted, gold)

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_b3_everything_in_one_predicted_cluster_hurts_precision_not_recall():
    # Two real characters (A, B), the system merges every mention into one.
    gold = {"1": "A", "2": "A", "3": "B", "4": "B"}
    predicted = {"1": "X", "2": "X", "3": "X", "4": "X"}

    result = b3_precision_recall_f1(predicted, gold)

    assert result.recall == 1.0  # every gold cluster is fully contained
    assert math.isclose(result.precision, 0.5)  # half of each predicted pair is wrong


def test_b3_everything_split_into_singletons_hurts_recall_not_precision():
    gold = {"1": "A", "2": "A", "3": "B", "4": "B"}
    predicted = {"1": "X", "2": "Y", "3": "Z", "4": "W"}

    result = b3_precision_recall_f1(predicted, gold)

    assert result.precision == 1.0  # every predicted singleton is internally pure
    assert math.isclose(result.recall, 0.5)


def test_b3_raises_on_disjoint_mention_sets():
    with pytest.raises(ValueError, match="no overlapping"):
        b3_precision_recall_f1({"1": "X"}, {"2": "A"})
