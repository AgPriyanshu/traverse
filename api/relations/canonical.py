from uuid import UUID

from ..graph import ontology

# Which side of an inverse pair is stored. Everything else falls back to
# alphabetical order, so exactly one of every pair is canonical.
_PREFERRED = frozenset(
    {
        "parent_of",
        "grandparent_of",
        "guardian_of",
        "adoptive_parent_of",
        "employer_of",
        "mentor_of",
        "betrayed",
        "deceives",
        "customer_of",
    }
)


def is_canonical_predicate(predicate: str) -> bool:
    """Return whether a predicate is the stored side of its inverse pair."""
    inverse = ontology.inverse_of(predicate)
    if inverse is None or inverse == predicate:
        return True
    if predicate in _PREFERRED:
        return True
    if inverse in _PREFERRED:
        return False

    return predicate < inverse


def canonical_direction(
    subject_id: UUID, predicate: str, object_id: UUID
) -> tuple[UUID, str, UUID]:
    """Return the one stored form of a relation.

    ``child_of(A, B)`` and ``parent_of(B, A)`` are the same fact and collapse
    to ``parent_of(B, A)``. A symmetric predicate stores its pair sorted by
    character id, so ``sibling_of(A, B)`` and ``sibling_of(B, A)`` never both
    exist. One-way predicates are unchanged.

    Args:
        subject_id: Extracted subject.
        predicate: An ontology predicate.
        object_id: Extracted object.
    """
    spec = ontology.spec_of(predicate)
    if spec.symmetric:
        first, second = sorted((subject_id, object_id), key=str)
        form = (first, predicate, second)
    elif spec.inverse is None or is_canonical_predicate(predicate):
        form = (subject_id, predicate, object_id)
    else:
        form = (object_id, spec.inverse, subject_id)

    return form
