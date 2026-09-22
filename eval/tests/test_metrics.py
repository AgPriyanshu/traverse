import math

from eval.metrics import (
    CharacterCluster,
    cascade_stage_contribution,
    match_rosters,
    precision_recall_f1,
    rejection_precision,
    roster_precision_recall_f1,
    tier_accuracy,
)


def test_precision_recall_f1_basic():
    result = precision_recall_f1(tp=8, fp=1, fn=2)

    assert math.isclose(result.precision, 8 / 9)
    assert math.isclose(result.recall, 0.8)
    assert result.f1 > 0


def test_precision_recall_f1_all_zero_is_defined_as_zero_not_nan():
    result = precision_recall_f1(tp=0, fp=0, fn=0)

    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0


def test_match_rosters_matches_on_shared_alias_not_canonical_name_equality():
    gold = [
        CharacterCluster("g1", "Elizabeth Bennet", ("Lizzy", "Eliza"), "protagonist")
    ]
    predicted = [CharacterCluster("p1", "Elizabeth", ("Lizzy",), "protagonist")]

    result = match_rosters(gold, predicted)

    assert result.true_positives == 1
    assert result.false_positives == 0
    assert result.false_negatives == 0


def test_match_rosters_penalises_a_split_character_as_one_tp_and_rest_fp():
    # The two-Catherines case run backwards: one real gold character the
    # system incorrectly split into two predicted rows.
    gold = [CharacterCluster("g1", "Elizabeth Bennet", ("Lizzy", "Eliza"))]
    predicted = [
        CharacterCluster("p1", "Elizabeth", ("Lizzy",)),
        CharacterCluster("p2", "Eliza", ()),
    ]

    result = match_rosters(gold, predicted)

    assert result.true_positives == 1
    assert result.false_positives == 1  # the extra split-off row
    assert result.false_negatives == 0


def test_match_rosters_never_double_matches_a_gold_character():
    # A wrong merge: two distinct gold characters both overlap the same
    # predicted row (e.g. the two Catherines merged into one). Only one may
    # claim the match; the other is a false negative, not a second true
    # positive -- this is the regression this metric exists to catch.
    gold = [
        CharacterCluster("g1", "Catherine Earnshaw", ("Catherine", "Cathy")),
        CharacterCluster("g2", "Catherine Linton", ("Catherine", "Cathy")),
    ]
    predicted = [CharacterCluster("p1", "Catherine", ("Cathy",))]

    result = match_rosters(gold, predicted)

    assert result.true_positives == 1
    assert result.false_negatives == 1
    assert result.false_positives == 0


def test_roster_precision_recall_f1_end_to_end():
    gold = [
        CharacterCluster("g1", "Elizabeth Bennet", ("Lizzy",)),
        CharacterCluster("g2", "Fitzwilliam Darcy", ("Darcy",)),
    ]
    predicted = [
        CharacterCluster("p1", "Elizabeth Bennet", ("Lizzy",)),
        CharacterCluster("p2", "Netherfield", ()),  # a wrongly-kept place name
    ]

    result = roster_precision_recall_f1(gold, predicted)

    assert result.true_positives == 1
    assert result.false_positives == 1  # Netherfield
    assert result.false_negatives == 1  # Darcy was missed


def test_tier_accuracy_only_scores_matched_characters():
    gold = [
        CharacterCluster("g1", "Elizabeth Bennet", ("Lizzy",), "protagonist"),
        CharacterCluster("g2", "Fitzwilliam Darcy", ("Darcy",), "protagonist"),
    ]
    predicted = [
        CharacterCluster("p1", "Elizabeth Bennet", ("Lizzy",), "major"),  # wrong tier
        CharacterCluster("p2", "Fitzwilliam Darcy", ("Darcy",), "protagonist"),
    ]
    match = match_rosters(gold, predicted)

    assert tier_accuracy(gold, predicted, match) == 0.5


def test_rejection_precision_flags_a_real_character_thrown_away():
    gold_forms = frozenset({"elizabeth bennet", "lizzy", "fitzwilliam darcy", "darcy"})
    rejected = ["Netherfield", "Longbourn", "Darcy"]  # Darcy should never be rejected

    score = rejection_precision(rejected, gold_forms)

    assert score.correctly_rejected == 2
    assert score.wrongly_rejected == ("Darcy",)
    assert math.isclose(score.precision, 2 / 3)


def test_rejection_precision_empty_rejection_list_is_vacuously_perfect():
    score = rejection_precision([], frozenset())

    assert score.precision == 1.0
    assert score.wrongly_rejected == ()


def test_cascade_stage_contribution_tallies_and_normalises():
    methods = ["exact", "exact", "nickname", "llm", "llm", "llm"]

    result = cascade_stage_contribution(methods)

    assert result.total == 6
    assert result.counts == {"exact": 2, "nickname": 1, "llm": 3}
    assert math.isclose(result.fractions["llm"], 0.5)
