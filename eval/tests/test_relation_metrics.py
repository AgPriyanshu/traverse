from eval.loaders import load_gold_relations
from eval.relation_metrics import (
    GoldRelation,
    OntologyView,
    PredictedEdge,
    citation_page_accuracy,
    gold_relations,
    score_relations,
)

VIEW = OntologyView(
    inverse={
        "parent_of": "child_of",
        "child_of": "parent_of",
        "sibling_of": "sibling_of",
        "engaged_to": "engaged_to",
        "married_to": "married_to",
        "enemy_of": "enemy_of",
        "rival_of": "rival_of",
    },
    symmetric=frozenset(
        {"sibling_of", "engaged_to", "married_to", "enemy_of", "rival_of"}
    ),
)


def test_inverse_and_symmetric_forms_match_the_same_fact():
    gold = [
        GoldRelation("A", "parent_of", "B", (1, 9)),
        GoldRelation("C", "sibling_of", "D", (1, 9)),
    ]
    predicted = [
        PredictedEdge("B", "child_of", "A"),
        PredictedEdge("D", "sibling_of", "C"),
    ]
    scores = score_relations(gold, predicted, VIEW)

    assert scores.overall.f1 == 1.0
    assert scores.direction_accuracy == 1.0


def test_reversed_parent_is_a_direction_error_and_a_miss():
    gold = [GoldRelation("A", "parent_of", "B", (1, 9))]
    scores = score_relations(gold, [PredictedEdge("B", "parent_of", "A")], VIEW)

    assert scores.direction_accuracy == 0.0
    assert scores.overall.recall == 0.0
    assert len(scores.direction_errors) == 1


def test_edge_between_unrelated_pair_is_spurious():
    gold = [GoldRelation("A", "sibling_of", "B", (1, 9))]
    edges = [PredictedEdge("A", "sibling_of", "B"), PredictedEdge("A", "enemy_of", "C")]
    scores = score_relations(gold, edges, VIEW)

    assert scores.spurious_edge_rate == 0.5
    assert scores.overall.precision == 0.5


def test_ignored_predicates_are_not_scored():
    scores = score_relations(
        [GoldRelation("A", "sibling_of", "B", (1, 9))],
        [
            PredictedEdge("A", "sibling_of", "B"),
            PredictedEdge("A", "acquaintance_of", "C"),
        ],
        VIEW,
        ignored_predicates=["acquaintance_of"],
    )

    assert scores.spurious_edge_rate == 0.0


def test_alt_predicate_is_accepted():
    gold = [GoldRelation("A", "enemy_of", "B", (1, 9), alt_predicates=("rival_of",))]
    scores = score_relations(gold, [PredictedEdge("A", "rival_of", "B")], VIEW)

    assert scores.overall.recall == 1.0


def test_temporal_transition_is_scored_by_chapter_within_tolerance():
    gold = [
        GoldRelation("A", "engaged_to", "B", (5, 9), arc="x"),
        GoldRelation("A", "married_to", "B", (10, 20), arc="x"),
    ]
    near = [
        PredictedEdge("A", "engaged_to", "B", 5),
        PredictedEdge("A", "married_to", "B", 12),
    ]
    far = [
        PredictedEdge("A", "engaged_to", "B", 5),
        PredictedEdge("A", "married_to", "B", 30),
    ]

    assert (
        score_relations(gold, near, VIEW, chapter_tolerance=3).temporal_arc_accuracy
        == 1.0
    )
    assert (
        score_relations(gold, far, VIEW, chapter_tolerance=3).temporal_arc_accuracy
        == 0.0
    )


def test_citation_accuracy_needs_fifty_judgements_to_meet_the_target():
    few = citation_page_accuracy([{"supported": True}] * 10)
    enough = citation_page_accuracy(
        [{"supported": True}] * 49 + [{"supported": None}] * 5 + [{"supported": True}]
    )

    assert few.accuracy == 1.0 and not few.meets_target
    assert enough.judged == 50 and enough.meets_target


def test_pride_and_prejudice_gold_relations_load_and_are_pinned():
    document = load_gold_relations("pride-and-prejudice")

    assert len(gold_relations(document)) >= 30
