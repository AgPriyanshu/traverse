"""Cross-book identity reconciliation metrics (S5.14).

Pure functions over plain data -- no database, no API -- so they are
unit-testable and reusable from both ``api/ops/reconciliation_quality.py``
and ad-hoc notebooks, the same split as ``eval/metrics.py`` and
``eval/relation_metrics.py``.

Scoring works at the level of one *appearance*: a character in one book. A
gold identity groups a set of appearances (one per book it lists in
``appears_in``) under one canonical name; a prediction groups the same
appearance keys under whatever ``character_id`` the system assigned. The only
decision either side makes is a partition over appearances, so every metric
below is defined on unordered PAIRS of appearances -- a false merge (two
different gold people sharing one predicted row) and a duplicate (one gold
person spread across two-or-more predicted rows) are both properties of a
*pair*, never of a single appearance in isolation.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class Appearance:
    """One character's presence in one book, identified for pair matching.

    ``key`` must be the same string on the gold side and the predicted side
    for the same real appearance -- typically ``f"{gold_canonical}:
    {book_order}"``, assigned once a per-book roster match (``eval.metrics.
    match_rosters``) has aligned a gold character onto a real
    ``CharacterAppearance`` row for that book (the adapter's job, not this
    module's). An appearance gold declares but the system never matched in
    that book has no predicted counterpart and is dropped from pair scoring
    entirely -- that failure belongs to roster recall, not to link scoring.
    """

    key: str
    cluster: str  # gold canonical name, or predicted character id.


def _pairs(appearances: list[Appearance]) -> dict[frozenset[str], bool]:
    """Every unordered pair of appearance keys -> whether they share a cluster."""
    by_key = {a.key: a for a in appearances}
    linked: dict[frozenset[str], bool] = {}
    for a, b in combinations(appearances, 2):
        pair = frozenset((a.key, b.key))
        linked[pair] = by_key[a.key].cluster == by_key[b.key].cluster

    return linked


@dataclass(frozen=True)
class LinkScores:
    precision: float
    recall: float
    false_merge_rate: float
    duplicate_rate: float
    linked_pairs: int
    correctly_linked_pairs: int
    false_merge_pairs: int
    gold_linked_pairs: int
    missed_link_pairs: int
    duplicate_characters: int
    gold_multi_book_characters: int


def score_identity_links(
    gold: list[Appearance], predicted: list[Appearance]
) -> LinkScores:
    """Score a predicted appearance-to-character partition against gold.

    Args:
        gold: One entry per (character, book) the gold set says genuinely
            appears, ``cluster`` set to the gold canonical name.
        predicted: The same appearance keys the adapter could match, ``cluster``
            set to the predicted ``character_id`` (as a string) each landed
            under.

    Returns:
        Pair-level link precision/recall, the false-merge rate (report this
        separately, never folded into an F1 -- devops-1.md S5.14: a
        duplicate is visible and recoverable, a merge is silent and
        destructive) and the duplicate rate (a gold character genuinely
        spread across 2+ predicted character rows).
    """
    gold_by_key = {a.key: a for a in gold}
    predicted_by_key = {a.key: a for a in predicted}
    shared_keys = sorted(set(gold_by_key) & set(predicted_by_key))
    shared_gold = [gold_by_key[k] for k in shared_keys]
    shared_predicted = [predicted_by_key[k] for k in shared_keys]

    gold_pairs = _pairs(shared_gold)
    predicted_pairs = _pairs(shared_predicted)

    linked_pairs = sum(1 for v in predicted_pairs.values() if v)
    gold_linked_pairs = sum(1 for v in gold_pairs.values() if v)
    correctly_linked = sum(
        1 for pair, v in predicted_pairs.items() if v and gold_pairs.get(pair)
    )
    false_merges = sum(
        1 for pair, v in predicted_pairs.items() if v and not gold_pairs.get(pair)
    )
    missed_links = sum(
        1 for pair, v in gold_pairs.items() if v and not predicted_pairs.get(pair)
    )

    precision = correctly_linked / linked_pairs if linked_pairs else 0.0
    recall = correctly_linked / gold_linked_pairs if gold_linked_pairs else 0.0
    false_merge_rate = false_merges / linked_pairs if linked_pairs else 0.0

    gold_clusters: dict[str, set[str]] = defaultdict(set)
    for a in shared_gold:
        gold_clusters[a.cluster].add(a.key)
    multi_book = {name: keys for name, keys in gold_clusters.items() if len(keys) > 1}
    duplicated = sum(
        1
        for keys in multi_book.values()
        if len({predicted_by_key[k].cluster for k in keys}) > 1
    )
    duplicate_rate = duplicated / len(multi_book) if multi_book else 0.0

    return LinkScores(
        precision=precision,
        recall=recall,
        false_merge_rate=false_merge_rate,
        duplicate_rate=duplicate_rate,
        linked_pairs=linked_pairs,
        correctly_linked_pairs=correctly_linked,
        false_merge_pairs=false_merges,
        gold_linked_pairs=gold_linked_pairs,
        missed_link_pairs=missed_links,
        duplicate_characters=duplicated,
        gold_multi_book_characters=len(multi_book),
    )


@dataclass(frozen=True)
class BlockDecision:
    """One ``reconciliation_decision`` row where a candidate was blocked."""

    candidate_key: str  # the gold appearance key this decision was about.
    blocked_against: str  # gold canonical name of the character it was NOT linked to.
    blocked_by: str  # method: character_death, kinship_contradiction, namesake, ...


@dataclass(frozen=True)
class BlockScore:
    precision: float
    correct_blocks: int
    incorrect_blocks: tuple[str, ...]


def block_precision(
    decisions: list[BlockDecision], gold_by_key: dict[str, str]
) -> BlockScore:
    """Fraction of blocks that were correct to block (devops-1.md S5.14).

    A block is *correct* if the candidate's gold canonical name differs from
    the character it was blocked against -- blocking correctly kept two
    different people apart. It is *incorrect* if gold says they are the same
    person: the block cost a real link (a recall loss, surfaced here so it is
    visible which blocking rule caused it, rather than only showing up as an
    unexplained drop in link recall).
    """
    if not decisions:
        return BlockScore(precision=1.0, correct_blocks=0, incorrect_blocks=())

    incorrect = tuple(
        d.candidate_key
        for d in decisions
        if gold_by_key.get(d.candidate_key) == d.blocked_against
    )
    correct = len(decisions) - len(incorrect)
    precision = correct / len(decisions)

    return BlockScore(precision, correct, incorrect)


def canonical_graph_checksum(
    characters: list[tuple[str, str]],
    relations: list[tuple[str, str, str]],
) -> str:
    """A deterministic, order-independent checksum of a project's graph shape.

    Args:
        characters: ``(canonical_name, importance_tier)`` pairs.
        relations: ``(subject, predicate, object)`` triples, already
            canonicalised for direction/symmetry the way
            ``eval.relation_metrics.OntologyView.canonical`` does -- this
            function only sorts and hashes, it does not know the ontology.

    Sorting before hashing is the whole point: two ingestion orders that
    produce the same set of characters and relations must hash identically
    regardless of insertion order, row ids or timestamps -- the Sprint 5 DoD's
    "reverse-order upload produces a checksum-identical graph" is exactly a
    claim about this function's output being stable under a permutation of
    its inputs.
    """
    payload = {"characters": sorted(characters), "relations": sorted(relations)}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()

    return digest


__all__ = [
    "Appearance",
    "BlockDecision",
    "BlockScore",
    "LinkScores",
    "block_precision",
    "canonical_graph_checksum",
    "score_identity_links",
]
