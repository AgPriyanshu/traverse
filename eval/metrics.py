"""Pure scoring functions for extraction quality (S3.14).

Nothing here touches the database, the API, or a book id -- every function
takes plain data in and returns plain data out, so it is unit-testable
without Postgres and reusable from both the CI runner
(``eval/runners/extraction.py``) and ad-hoc notebooks.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass


def _normalize(surface_form: str) -> str:
    return " ".join(surface_form.strip().lower().split())


@dataclass(frozen=True)
class CharacterCluster:
    """One character's identity for matching purposes: a name plus its aliases.

    Both gold and predicted characters are represented this way so roster
    matching (`match_rosters`) can compare them uniformly.
    """

    id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    importance_tier: str | None = None

    def surface_forms(self) -> frozenset[str]:
        forms = {_normalize(self.canonical_name)}
        forms.update(_normalize(a) for a in self.aliases)

        return frozenset(forms)


@dataclass(frozen=True)
class RosterMatch:
    gold_id: str
    predicted_id: str
    shared_surface_forms: frozenset[str]


@dataclass(frozen=True)
class RosterMatchResult:
    matches: tuple[RosterMatch, ...]
    unmatched_gold: tuple[str, ...]
    unmatched_predicted: tuple[str, ...]

    @property
    def true_positives(self) -> int:
        return len(self.matches)

    @property
    def false_negatives(self) -> int:
        return len(self.unmatched_gold)

    @property
    def false_positives(self) -> int:
        return len(self.unmatched_predicted)


def match_rosters(
    gold: list[CharacterCluster], predicted: list[CharacterCluster]
) -> RosterMatchResult:
    """Match predicted characters to gold characters by shared surface form.

    Two characters "are" the same person for roster P/R/F1 purposes if they
    share at least one normalised surface form (canonical name or alias) --
    matching on canonical-name string equality alone would wrongly count a
    predicted "Elizabeth" against a gold "Elizabeth Bennet" as a miss.

    Matching is greedy by descending overlap size, one-to-one: once a gold or
    predicted character is claimed it cannot match again, so a system that
    splits one gold character into five predicted rows gets one true positive
    and four false positives, not five true positives.
    """
    candidates: list[tuple[int, str, str, frozenset[str]]] = []
    for g in gold:
        g_forms = g.surface_forms()
        for p in predicted:
            shared = g_forms & p.surface_forms()
            if shared:
                candidates.append((len(shared), g.id, p.id, shared))

    candidates.sort(key=lambda c: c[0], reverse=True)

    matched_gold: set[str] = set()
    matched_predicted: set[str] = set()
    matches: list[RosterMatch] = []
    for _, gold_id, predicted_id, shared in candidates:
        if gold_id in matched_gold or predicted_id in matched_predicted:
            continue
        matched_gold.add(gold_id)
        matched_predicted.add(predicted_id)
        matches.append(RosterMatch(gold_id, predicted_id, shared))

    unmatched_gold = tuple(g.id for g in gold if g.id not in matched_gold)
    unmatched_predicted = tuple(
        p.id for p in predicted if p.id not in matched_predicted
    )

    return RosterMatchResult(tuple(matches), unmatched_gold, unmatched_predicted)


@dataclass(frozen=True)
class PrecisionRecallF1:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def precision_recall_f1(tp: int, fp: int, fn: int) -> PrecisionRecallF1:
    """Compute precision/recall/F1 from raw counts, with 0/0 defined as 0.0."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    )

    return PrecisionRecallF1(precision, recall, f1, tp, fp, fn)


def roster_precision_recall_f1(
    gold: list[CharacterCluster], predicted: list[CharacterCluster]
) -> PrecisionRecallF1:
    """F2.1's headline number: is the roster the right set of people?"""
    result = match_rosters(gold, predicted)

    return precision_recall_f1(
        result.true_positives, result.false_positives, result.false_negatives
    )


NAMED_TIERS = ("protagonist", "major", "minor")


def roster_precision_recall_f1_for_tiers(
    gold: list[CharacterCluster],
    predicted: list[CharacterCluster],
    tiers: tuple[str, ...] = NAMED_TIERS,
) -> PrecisionRecallF1:
    """Roster P/R/F1 restricted to characters above the ``mentioned`` tail.

    The tail of one-line characters is where a gold roster is least complete
    and where reasonable labellers disagree, so an overall precision that
    counts every predicted tail character as right or wrong mostly measures
    the gold's completeness. This scores the part of the cast the product
    depends on, without changing how anything is matched:

    * Matching is the same full-roster ``match_rosters`` used overall.
    * Gold in scope: gold characters whose gold tier is in ``tiers``. An
      unmatched one is a false negative.
    * Predicted in scope: a predicted character matched to a gold character is
      in scope by that gold character's tier (matched to a ``mentioned`` gold
      character, it is dropped, neither right nor wrong). An unmatched one is in
      scope by its own predicted tier, and counts as a false positive: claiming
      someone is a minor-or-above character who is in no gold roster is exactly
      the error this measures. Unmatched predictions tiered ``mentioned`` are
      the unjudged tail and are dropped.

    Unlike the overall number this can be gamed only by tiering, not by the
    gold's size, and both are reported together so neither hides the other.
    """
    result = match_rosters(gold, predicted)
    gold_tier = {g.id: g.importance_tier for g in gold}
    predicted_tier = {p.id: p.importance_tier for p in predicted}

    true_positives = sum(1 for m in result.matches if gold_tier[m.gold_id] in tiers)
    false_negatives = sum(1 for gid in result.unmatched_gold if gold_tier[gid] in tiers)
    false_positives = sum(
        1 for pid in result.unmatched_predicted if predicted_tier[pid] in tiers
    )

    return precision_recall_f1(true_positives, false_positives, false_negatives)


@dataclass(frozen=True)
class BCubedResult:
    """B-cubed precision/recall/F1 (Bagga & Baldwin 1998) for alias clustering.

    Unlike cluster accuracy, B-cubed is defined per *item* (mention), not per
    cluster, and averages over items -- a system that splits one gold cluster
    of 10 into two predicted clusters of 5 is penalised proportionally to how
    many items landed in the wrong company, not scored as a single wrong
    cluster out of N. That distinction is F2.2's whole point: alias
    clustering errors are almost always partial splits/merges, not clean
    wrong-cluster misses, and a metric that cannot see "how wrong" collapses
    a near-miss and a total failure into the same score.
    """

    precision: float
    recall: float
    f1: float
    n_items: int


def b3_precision_recall_f1(
    predicted_clusters: dict[str, str], gold_clusters: dict[str, str]
) -> BCubedResult:
    """Score a clustering of mentions into characters against gold clusters.

    Args:
        predicted_clusters: mention id -> predicted cluster id (the
            resolved character id a mention was assigned to).
        gold_clusters: mention id -> gold cluster id (the gold character id
            a mention should have been assigned to).

    Both maps must key by the same mention identifiers; only mentions present
    in both are scored (a mention pass-1 never surfaced can't be clustered
    either way, and belongs in roster/rejection metrics instead).

    Returns:
        Item-averaged precision, recall and F1 over the shared mention set.

    Raises:
        ValueError: If there is no overlap between the two mention sets.
    """
    items = set(predicted_clusters) & set(gold_clusters)
    if not items:
        raise ValueError(
            "no overlapping mention ids between predicted and gold clusterings"
        )

    pred_groups: dict[str, set[str]] = defaultdict(set)
    gold_groups: dict[str, set[str]] = defaultdict(set)
    for item in items:
        pred_groups[predicted_clusters[item]].add(item)
        gold_groups[gold_clusters[item]].add(item)

    precisions: list[float] = []
    recalls: list[float] = []
    for item in items:
        pred_group = pred_groups[predicted_clusters[item]]
        gold_group = gold_groups[gold_clusters[item]]
        correct = len(pred_group & gold_group)
        precisions.append(correct / len(pred_group))
        recalls.append(correct / len(gold_group))

    precision = sum(precisions) / len(precisions)
    recall = sum(recalls) / len(recalls)
    f1 = (
        (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    )

    return BCubedResult(precision, recall, f1, len(items))


def tier_accuracy(
    gold: list[CharacterCluster],
    predicted: list[CharacterCluster],
    match: RosterMatchResult,
) -> float:
    """Fraction of correctly-matched characters whose tier also matches.

    Scored only over true positives -- a character the system never found or
    invented has no tier to be right or wrong about; that failure is already
    counted in `roster_precision_recall_f1`.
    """
    if not match.matches:
        return 0.0

    gold_by_id = {g.id: g for g in gold}
    predicted_by_id = {p.id: p for p in predicted}
    correct = sum(
        1
        for m in match.matches
        if gold_by_id[m.gold_id].importance_tier
        == predicted_by_id[m.predicted_id].importance_tier
    )

    return correct / len(match.matches)


@dataclass(frozen=True)
class RejectionScore:
    precision: float
    correctly_rejected: int
    wrongly_rejected: tuple[str, ...]


def rejection_precision(
    rejected_surface_forms: list[str], gold_character_forms: frozenset[str]
) -> RejectionScore:
    """How many rejected candidates were actually real characters (F2.4).

    A rejection is *wrong* if its surface form matches a gold character's
    canonical name or alias -- the classifier threw away a real person.
    Precision here is "fraction of rejections that were correctly not
    characters"; the wrongly-rejected list is kept alongside it because a
    single number hides which names to look at first.
    """
    if not rejected_surface_forms:
        return RejectionScore(precision=1.0, correctly_rejected=0, wrongly_rejected=())

    wrongly = [
        form
        for form in rejected_surface_forms
        if _normalize(form) in gold_character_forms
    ]
    correct = len(rejected_surface_forms) - len(wrongly)
    precision = correct / len(rejected_surface_forms)

    return RejectionScore(precision, correct, tuple(wrongly))


@dataclass(frozen=True)
class CascadeContribution:
    counts: dict[str, int]
    fractions: dict[str, float]
    total: int


def cascade_stage_contribution(resolution_methods: list[str]) -> CascadeContribution:
    """Tally which alias-cascade stage resolved each cluster (character-graph.md).

    Each cluster records the cheapest stage that resolved it
    (exact/normalised/honorific/nickname/embedding/llm/human). If stage 5
    (llm) is doing most of the work, stages 1-4 are underperforming -- that
    is the finding this metric exists to surface, not a scaling concern.
    """
    counts = Counter(resolution_methods)
    total = sum(counts.values())
    fractions = (
        {stage: count / total for stage, count in counts.items()} if total else {}
    )

    return CascadeContribution(dict(counts), fractions, total)


__all__ = [
    "BCubedResult",
    "CascadeContribution",
    "CharacterCluster",
    "PrecisionRecallF1",
    "RejectionScore",
    "RosterMatch",
    "RosterMatchResult",
    "b3_precision_recall_f1",
    "cascade_stage_contribution",
    "match_rosters",
    "precision_recall_f1",
    "rejection_precision",
    "NAMED_TIERS",
    "roster_precision_recall_f1",
    "roster_precision_recall_f1_for_tiers",
    "tier_accuracy",
]
