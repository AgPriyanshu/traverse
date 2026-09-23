from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import combinations
from uuid import UUID

from ..contracts.enums import AssertionType, RelationFamily, RelationStatus
from ..contracts.graph import QUOTE_MAX_CHARS, AggregatedRelation, EvidenceItem
from ..contracts.pipeline import SeriesPosition
from ..graph import ontology
from .canonical import canonical_direction
from .validator import fold

# Edge confidence is computed from the evidence, never taken from the model's
# self-report (PRD F3, api/AGENTS.md). Sprint 8 calibrates these weights.
#
#   count     saturating in evidence count: 1 item = 0.50, 2 = 0.75, 3 = 0.875.
#             More independent mentions make a fluke less likely, with
#             diminishing returns so 40 mentions do not dwarf 5.
#   agreement the share of this pair's same-family evidence that backs this
#             predicate. A pair with 6 friend_of and 1 enemy_of item is a
#             friend_of edge with a dissenting minority, not a coin flip.
#   item      mean of the per-item model confidence. Kept as a weak input only:
#             the model volunteers plausible-looking numbers unprompted.
WEIGHT_COUNT = 0.5
WEIGHT_AGREEMENT = 0.3
WEIGHT_ITEM = 0.2
CONFIDENCE_CEILING = 0.99
DEFAULT_ITEM_CONFIDENCE = 0.5

_KINSHIP_CORE = frozenset(
    {"parent_of", "child_of", "sibling_of", "grandparent_of", "grandchild_of"}
)
_MAX_PARENTS = 2


@dataclass(frozen=True)
class Fact:
    subject_id: UUID
    predicate: str
    object_id: UUID
    chunk_id: UUID
    book_id: UUID
    book_order: int
    chapter: int | None
    page_start: int
    page_end: int
    quote: str
    assertion_type: AssertionType
    asserted_by_id: UUID | None
    confidence: float | None


@dataclass
class AggregationResult:
    relations: list[AggregatedRelation]
    conflicts: list[dict]


def edge_confidence(
    evidence_count: int, agreement: float, item_confidences: list[float | None]
) -> float:
    """Compute an edge's confidence from its evidence, not a model self-report.

    Args:
        evidence_count: Distinct evidence items backing the edge.
        agreement: Share of the pair's same-family evidence backing this edge.
        item_confidences: Per-item model confidence, ``None`` where absent.
    """
    count_term = 1.0 - 0.5**evidence_count
    values = [
        DEFAULT_ITEM_CONFIDENCE if c is None else c for c in item_confidences
    ] or [DEFAULT_ITEM_CONFIDENCE]
    item_term = sum(values) / len(values)
    score = (
        WEIGHT_COUNT * count_term
        + WEIGHT_AGREEMENT * agreement
        + WEIGHT_ITEM * item_term
    )
    confidence = round(min(score, CONFIDENCE_CEILING), 4)

    return confidence


def _position(fact: Fact) -> tuple[int, int, int]:
    return (fact.book_order, fact.chapter or 0, fact.page_start)


def _canonicalise(facts: list[Fact]) -> list[Fact]:
    out = []
    for fact in facts:
        subject, predicate, obj = canonical_direction(
            fact.subject_id, fact.predicate, fact.object_id
        )
        out.append(
            replace(fact, subject_id=subject, predicate=predicate, object_id=obj)
        )

    return out


def _dedupe(facts: list[Fact]) -> list[Fact]:
    seen: set[tuple] = set()
    unique = []
    for fact in sorted(facts, key=lambda f: (_position(f), str(f.chunk_id), f.quote)):
        key = (
            fact.subject_id,
            fact.predicate,
            fact.object_id,
            fact.chunk_id,
            fold(fact.quote),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(fact)

    return unique


def _legal_between(x: "_State", y: "_State") -> bool:
    """Whether ``y`` legally supersedes ``x``, in either orientation."""
    same_direction = (x.subject_id, x.object_id) == (y.subject_id, y.object_id)
    inv_x = ontology.inverse_of(x.predicate)
    inv_y = ontology.inverse_of(y.predicate)
    if same_direction:
        options = [(x.predicate, y.predicate), (inv_x, inv_y)]
    else:
        options = [(x.predicate, inv_y), (inv_x, y.predicate)]

    legal = any(
        a is not None and b is not None and ontology.is_legal_transition(a, b)
        for a, b in options
    )

    return legal


@dataclass
class _State:
    subject_id: UUID
    predicate: str
    object_id: UUID
    facts: list[Fact]
    last: SeriesPosition | None = None
    closed: bool = False

    @property
    def first(self) -> tuple[int, int, int]:
        return _position(self.facts[0])

    @property
    def family(self) -> RelationFamily:
        return ontology.family_of(self.predicate)


def _detect_conflicts(states: list[_State]) -> list[dict]:
    conflicts: list[dict] = []
    for x, y in combinations(states, 2):
        if _legal_between(x, y) or _legal_between(y, x):
            continue
        reversed_direction = (
            x.predicate == y.predicate
            and not ontology.is_symmetric(x.predicate)
            and (x.subject_id, x.object_id) == (y.object_id, y.subject_id)
        )
        both_core_kinship = (
            x.predicate in _KINSHIP_CORE
            and y.predicate in _KINSHIP_CORE
            and x.predicate != y.predicate
        )
        both_romantic = (
            x.family is RelationFamily.ROMANTIC
            and y.family is RelationFamily.ROMANTIC
            and x.predicate != y.predicate
            and not x.closed
            and not y.closed
        )
        if reversed_direction or both_core_kinship or both_romantic:
            conflicts.append(
                {
                    "type": "incompatible_relations",
                    "character_ids": sorted({str(x.subject_id), str(x.object_id)}),
                    "relations": sorted(
                        [
                            [str(s.subject_id), s.predicate, str(s.object_id)]
                            for s in (x, y)
                        ]
                    ),
                }
            )

    return conflicts


def _detect_parent_conflicts(states: list[_State]) -> list[dict]:
    parents: dict[UUID, set[UUID]] = defaultdict(set)
    for state in states:
        if state.predicate == "parent_of":
            parents[state.object_id].add(state.subject_id)

    conflicts = [
        {
            "type": "multiple_parents",
            "child_id": str(child),
            "parent_ids": sorted(str(p) for p in ids),
        }
        for child, ids in sorted(parents.items(), key=lambda kv: str(kv[0]))
        if len(ids) > _MAX_PARENTS
    ]

    return conflicts


def _apply_transitions(pair_states: list[_State]) -> None:
    ordered = sorted(pair_states, key=lambda s: (s.first, s.predicate))
    for earlier, later in combinations(ordered, 2):
        if earlier.first >= later.first or not _legal_between(earlier, later):
            continue
        position = SeriesPosition(
            book_order=later.first[0], chapter=later.first[1] or None
        )
        if earlier.last is None or position.as_tuple() < earlier.last.as_tuple():
            earlier.last = position
        earlier.closed = True


def aggregate(facts: list[Fact]) -> AggregationResult:
    """Collapse raw assertions into one edge per relation, with history.

    N assertions of one relation become one edge with N evidence items.
    Inverse and symmetric duplicates merge first (see ``canonical_direction``).
    A later relation that legally supersedes an earlier one closes the earlier
    edge (``last_*`` set, ``status='superseded'``) and leaves it in place; a
    pair of edges that cannot both hold is reported as a conflict for a human,
    never resolved by confidence.

    Args:
        facts: Validated assertions from every book of a project.

    Returns:
        The edges, ordered deterministically, and the conflicts found.
    """
    unique = _dedupe(_canonicalise(facts))

    grouped: dict[tuple[UUID, str, UUID], list[Fact]] = defaultdict(list)
    for fact in unique:
        grouped[(fact.subject_id, fact.predicate, fact.object_id)].append(fact)

    states = [
        _State(subject_id=s, predicate=p, object_id=o, facts=group)
        for (s, p, o), group in grouped.items()
    ]

    by_pair: dict[frozenset[UUID], list[_State]] = defaultdict(list)
    for state in states:
        by_pair[frozenset((state.subject_id, state.object_id))].append(state)

    conflicts: list[dict] = []
    for pair_states in by_pair.values():
        _apply_transitions(pair_states)
        conflicts.extend(_detect_conflicts(pair_states))
    conflicts.extend(_detect_parent_conflicts(states))

    relations = [
        _build(state, by_pair[frozenset((state.subject_id, state.object_id))])
        for state in states
    ]
    relations.sort(
        key=lambda r: (
            r.first.as_tuple(),
            str(r.subject_character_id),
            r.predicate,
            str(r.object_character_id),
        )
    )
    unique_conflicts = _dedupe_conflicts(conflicts)

    return AggregationResult(relations=relations, conflicts=unique_conflicts)


def _dedupe_conflicts(conflicts: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for conflict in conflicts:
        key = repr(sorted(conflict.items(), key=lambda kv: kv[0]))
        if key not in seen:
            seen.add(key)
            out.append(conflict)

    return out


def _edge_assertion(kinds: set[AssertionType]) -> AssertionType:
    if AssertionType.NARRATED in kinds:
        chosen = AssertionType.NARRATED
    elif AssertionType.INFERRED in kinds:
        chosen = AssertionType.INFERRED
    else:
        chosen = AssertionType.DIALOGUE

    return chosen


def _build(state: _State, pair_states: list[_State]) -> AggregatedRelation:
    facts = state.facts
    same_family = [s for s in pair_states if s.family is state.family]
    total = sum(len(s.facts) for s in same_family)
    agreement = len(facts) / total if total else 1.0

    evidence = [
        EvidenceItem(
            chunk_id=f.chunk_id,
            book_id=f.book_id,
            book_order=f.book_order,
            chapter_no=f.chapter,
            page_start=f.page_start,
            page_end=f.page_end,
            quote=f.quote[:QUOTE_MAX_CHARS],
            assertion_type=f.assertion_type,
            confidence=f.confidence,
        )
        for f in facts
    ]
    kinds = {f.assertion_type for f in facts}
    hearsay = kinds == {AssertionType.DIALOGUE}

    speaker = None
    if hearsay:
        counts: dict[UUID, int] = defaultdict(int)
        for f in facts:
            if f.asserted_by_id is not None:
                counts[f.asserted_by_id] += 1
        if counts:
            speaker = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]

    first = SeriesPosition(book_order=facts[0].book_order, chapter=facts[0].chapter)
    relation = AggregatedRelation(
        subject_character_id=state.subject_id,
        predicate=state.predicate,
        object_character_id=state.object_id,
        family=state.family,
        confidence=edge_confidence(
            len(facts), agreement, [f.confidence for f in facts]
        ),
        status=RelationStatus.SUPERSEDED if state.closed else RelationStatus.ACTIVE,
        assertion_type=_edge_assertion(kinds),
        asserted_by_character_id=speaker,
        hearsay=hearsay,
        first=first,
        last=state.last,
        evidence=evidence,
    )

    return relation
