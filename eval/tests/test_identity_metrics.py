"""S5.14 acceptance: link P/R, false-merge rate and duplicate rate verified
against hand-computed toy examples, the same discipline as test_b3.py's
worked example.

Toy setup, four gold characters across three books (book_order 1/2/3):

    Anne   appears in 1, 2, 3   (returns every book)
    Diana  appears in 1, 2, 3   (returns every book)
    Marilla appears in 1, 2     (returns book 2, absent book 3)
    Fred   appears in 3 only    (new in book 3)

Gold pairs sharing a cluster (same person, i.e. a "should link"):
    (Anne:1, Anne:2), (Anne:1, Anne:3), (Anne:2, Anne:3)
    (Diana:1, Diana:2), (Diana:1, Diana:3), (Diana:2, Diana:3)
    (Marilla:1, Marilla:2)
  = 7 gold-linked pairs. Every other pair among these 8 appearances is a
    "should NOT link" pair (different people, or Fred who only has one
    appearance and forms no gold pair at all).
"""

from __future__ import annotations

from eval.identity_metrics import (
    Appearance,
    BlockDecision,
    block_precision,
    canonical_graph_checksum,
    score_identity_links,
)

GOLD = [
    Appearance("Anne:1", "Anne"),
    Appearance("Anne:2", "Anne"),
    Appearance("Anne:3", "Anne"),
    Appearance("Diana:1", "Diana"),
    Appearance("Diana:2", "Diana"),
    Appearance("Diana:3", "Diana"),
    Appearance("Marilla:1", "Marilla"),
    Appearance("Marilla:2", "Marilla"),
    Appearance("Fred:3", "Fred"),
]


def test_perfect_prediction_scores_1_0_everywhere() -> None:
    predicted = [Appearance(a.key, a.cluster) for a in GOLD]  # cluster == gold name.

    scores = score_identity_links(GOLD, predicted)

    assert scores.precision == 1.0
    assert scores.recall == 1.0
    assert scores.false_merge_rate == 0.0
    assert scores.duplicate_rate == 0.0
    assert scores.gold_linked_pairs == 7
    assert scores.gold_multi_book_characters == 3  # Anne, Diana, Marilla.


def test_duplicate_anne_does_not_link_book3_to_books_1_and_2() -> None:
    """Anne:3 lands under a fresh character id -- a duplicate, not a merge."""
    predicted = [
        Appearance("Anne:1", "char-A"),
        Appearance("Anne:2", "char-A"),
        Appearance("Anne:3", "char-A2"),  # a second, unlinked row for Anne.
        Appearance("Diana:1", "char-B"),
        Appearance("Diana:2", "char-B"),
        Appearance("Diana:3", "char-B"),
        Appearance("Marilla:1", "char-C"),
        Appearance("Marilla:2", "char-C"),
        Appearance("Fred:3", "char-D"),
    ]

    scores = score_identity_links(GOLD, predicted)

    # Anne:1/Anne:2 still correctly linked; Anne:1/Anne:3 and Anne:2/Anne:3
    # are missed links, not false merges -- a duplicate is a recall loss,
    # never counted as a false merge (devops-1.md S5.14's asymmetry).
    assert scores.false_merge_rate == 0.0
    assert scores.missed_link_pairs == 2
    assert scores.duplicate_characters == 1
    assert scores.duplicate_rate == 1 / 3  # 1 of 3 multi-book gold characters.
    assert scores.recall == 5 / 7


def test_false_merge_of_two_different_people_is_reported_separately() -> None:
    """Marilla:1 and Fred:3 are different gold people merged into one row."""
    predicted = [
        Appearance("Anne:1", "char-A"),
        Appearance("Anne:2", "char-A"),
        Appearance("Anne:3", "char-A"),
        Appearance("Diana:1", "char-B"),
        Appearance("Diana:2", "char-B"),
        Appearance("Diana:3", "char-B"),
        Appearance("Marilla:1", "char-C"),
        Appearance("Marilla:2", "char-C"),
        Appearance("Fred:3", "char-C"),  # wrongly merged into Marilla's row.
    ]

    scores = score_identity_links(GOLD, predicted)

    assert scores.false_merge_pairs == 2  # (Marilla:1,Fred:3), (Marilla:2,Fred:3)
    assert scores.false_merge_rate == 2 / 9  # 2 of 9 total linked pairs.
    assert scores.recall == 1.0  # every real gold link still holds.
    assert scores.duplicate_rate == 0.0  # no gold character was split.


def test_unmatched_gold_appearance_is_dropped_from_pair_scoring() -> None:
    """A gold appearance the system never matched contributes no pairs."""
    predicted = [
        Appearance("Anne:1", "char-A"),
        Appearance("Anne:2", "char-A"),
        # Anne:3 was never extracted at all -- absent, not merely a miss.
        Appearance("Diana:1", "char-B"),
        Appearance("Diana:2", "char-B"),
        Appearance("Diana:3", "char-B"),
        Appearance("Marilla:1", "char-C"),
        Appearance("Marilla:2", "char-C"),
        Appearance("Fred:3", "char-D"),
    ]

    scores = score_identity_links(GOLD, predicted)

    assert scores.precision == 1.0
    assert scores.recall == 1.0  # every pair among the 8 shared appearances holds.
    # Anne:3 is excluded entirely: Anne keeps only (Anne:1,Anne:2) = 1 pair,
    # Diana keeps all 3, Marilla keeps its 1 -> 5 gold-linked pairs remain.
    assert scores.gold_linked_pairs == 5


def test_block_precision_toy_example() -> None:
    gold_by_key = {"Anne:3": "Anne", "Fred:3": "Fred", "Matthew:2": "Matthew"}
    decisions = [
        BlockDecision("Anne:3", "Marilla", "namesake"),  # correct: different people.
        BlockDecision("Fred:3", "Gilbert", "namesake"),  # correct: different people.
        BlockDecision("Matthew:2", "Matthew", "character_death"),  # WRONG: same person.
    ]

    score = block_precision(decisions, gold_by_key)

    assert score.correct_blocks == 2
    assert score.incorrect_blocks == ("Matthew:2",)
    assert score.precision == 2 / 3


def test_block_precision_with_no_decisions_is_vacuously_1() -> None:
    assert block_precision([], {}).precision == 1.0


def test_canonical_graph_checksum_is_order_independent() -> None:
    """The Sprint 5 DoD claim in one line: permuting inputs must not move the hash."""
    characters = [("Anne Shirley", "protagonist"), ("Gilbert Blythe", "major")]
    relations = [("Anne Shirley", "rival_of", "Gilbert Blythe")]

    forward = canonical_graph_checksum(characters, relations)
    reversed_order = canonical_graph_checksum(list(reversed(characters)), relations)

    assert forward == reversed_order


def test_canonical_graph_checksum_changes_with_content() -> None:
    base = canonical_graph_checksum([("Anne Shirley", "protagonist")], [])
    changed = canonical_graph_checksum([("Anne Shirley", "major")], [])

    assert base != changed
