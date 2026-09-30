from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..graph import ontology
from ..graph.client import session as neo_session

# A starting table for the router's free-text ``predicate_hint`` ("daughters",
# "friends") -> a declared ontology predicate. Deliberately small and
# extended as real questions surface gaps, rather than attempting full
# coverage up front. **Known limitation:** the ontology has no gender
# attribute, so "daughters" and "sons" both map to ``child_of`` and an
# aggregation answer to either returns every child, not just the requested
# gender — flagged here rather than silently over-claiming precision.
AGGREGATION_PREDICATE_HINTS: dict[str, str] = {
    "daughter": "child_of",
    "daughters": "child_of",
    "son": "child_of",
    "sons": "child_of",
    "child": "child_of",
    "children": "child_of",
    "kid": "child_of",
    "kids": "child_of",
    "parent": "parent_of",
    "parents": "parent_of",
    "sibling": "sibling_of",
    "siblings": "sibling_of",
    "sister": "sibling_of",
    "sisters": "sibling_of",
    "brother": "sibling_of",
    "brothers": "sibling_of",
    "grandchild": "grandparent_of",
    "grandchildren": "grandparent_of",
    "friend": "friend_of",
    "friends": "friend_of",
    "enemy": "enemy_of",
    "enemies": "enemy_of",
    "rival": "rival_of",
    "rivals": "rival_of",
    "employee": "employer_of",
    "employees": "employer_of",
    "student": "mentor_of",
    "students": "mentor_of",
    "ward": "guardian_of",
    "wards": "guardian_of",
}


# Predicate alone is gender-blind (the ontology tracks no gender attribute),
# so "Mr Bennet's daughters" and "...sons" would otherwise both resolve to
# every ``child_of`` edge and return the same set — the Sprint 6 demo's
# abstention case ("What happens to Elizabeth's brother?", who has none)
# depends on *not* doing that: her sisters must not stand in for a brother.
# Only the hints below carry a gender requirement; `gender.py` applies it as
# a strict filter (exclude non-matches AND unknowns) precisely because an
# under-inclusive answer that abstains is the safe failure here, and an
# over-inclusive one that lists the wrong gender is the hallucination-shaped
# one PRD F4.4 says to remove rather than soften.
AGGREGATION_HINT_GENDER: dict[str, str] = {
    "daughter": "female",
    "daughters": "female",
    "son": "male",
    "sons": "male",
    "sister": "female",
    "sisters": "female",
    "brother": "male",
    "brothers": "male",
}


def required_gender(hint: str | None) -> str | None:
    """Return the gender an aggregation hint implies, if any."""
    if not hint:
        return None

    return AGGREGATION_HINT_GENDER.get(hint.strip().lower())


def resolve_aggregation_predicate(hint: str | None) -> str | None:
    """Map a router-extracted free-text word to a declared ontology predicate.

    Args:
        hint: The router's ``predicate_hint``, verbatim from the question.

    Returns:
        A predicate declared in ``ontology.yaml``, or ``None`` when the hint
        is missing or does not map to one — the caller must abstain rather
        than pass an unmapped string into a template slot.
    """
    if not hint:
        return None

    predicate = AGGREGATION_PREDICATE_HINTS.get(hint.strip().lower())
    if predicate is None or not ontology.is_predicate(predicate):
        return None

    return predicate


# `RELATED` edges are materialised in both directions at upsert time
# (`graph/upsert.py::build_edge_rows`) — a "child_of(child, parent)" fact also
# exists as "parent_of(parent, child)", each carrying the *same* relation id
# in its `id` property. Matching undirected and de-duplicating by that id is
# what lets these templates stay indifferent to which direction extraction
# happened to write; filtering on `inverse: false` (as `graph/queries.py`
# does for whole-graph rendering, to avoid drawing a fact twice) would instead
# hide half of exactly the rows a directional aggregation query needs.

# The visibility clause below mirrors ``graph/queries.py``'s ``_VISIBLE``
# (S8.1, PRD F4.5): a reader mid-book asking about a relationship must not
# get back an edge first asserted after their reading position, even though
# ``graph/repository.py::relations_out`` re-checks the same thing in Postgres
# before the answer is rendered. Written out rather than imported — a shared
# constant across ``api/graph`` and ``api/query`` buys less than the risk of
# the two modules' Cypher dialects drifting apart under one shared string.
_LBO_LCH_VISIBLE = """(
  $lbo IS NULL OR r.first_book_order IS NULL OR r.first_book_order < $lbo
  OR (r.first_book_order = $lbo
      AND (r.first_chapter IS NULL
           OR ($lch IS NOT NULL AND r.first_chapter <= $lch)))
)"""

_RELATIONSHIP_LOOKUP_QUERY = f"""
MATCH (a:Character {{id: $subject_id, project_id: $project_id}})
      -[r:RELATED]-(b:Character {{id: $object_id, project_id: $project_id}})
WHERE {_LBO_LCH_VISIBLE}
RETURN DISTINCT r.id AS relation_id
ORDER BY relation_id
LIMIT 20
"""

# `predicate` and its ontology inverse are both passed in, never derived here
# from untrusted text — the caller (`api/query/pipeline.py`) validates
# `predicate` against `ontology.is_predicate` before it ever reaches this
# template.
_AGGREGATION_QUERY = f"""
MATCH (anchor:Character {{id: $anchor_id, project_id: $project_id}})
      -[r:RELATED]-(other:Character)
WHERE r.predicate IN [$predicate, $inverse_predicate]
  AND {_LBO_LCH_VISIBLE}
RETURN DISTINCT r.id AS relation_id, other.id AS other_id
ORDER BY other_id
LIMIT 500
"""


class TemplateId(StrEnum):
    RELATIONSHIP_LOOKUP = "relationship_lookup"
    AGGREGATION = "aggregation"


@dataclass(frozen=True)
class CypherTemplate:
    """One declared, parameterised statement. Never built from a string join."""

    id: TemplateId
    query: str
    params: frozenset[str]


TEMPLATES: dict[TemplateId, CypherTemplate] = {
    TemplateId.RELATIONSHIP_LOOKUP: CypherTemplate(
        id=TemplateId.RELATIONSHIP_LOOKUP,
        query=_RELATIONSHIP_LOOKUP_QUERY,
        params=frozenset({"subject_id", "object_id", "project_id", "lbo", "lch"}),
    ),
    TemplateId.AGGREGATION: CypherTemplate(
        id=TemplateId.AGGREGATION,
        query=_AGGREGATION_QUERY,
        params=frozenset(
            {"anchor_id", "project_id", "predicate", "inverse_predicate", "lbo", "lch"}
        ),
    ),
}


class TemplateSlotError(ValueError):
    """A caller passed a slot the template does not declare, or omitted one."""


async def run_template(template_id: TemplateId, **slots: Any) -> list[dict]:
    """Execute one declared template with validated slots.

    Args:
        template_id: Which declared template to run.
        **slots: Named parameters. Must match the template's declared
            ``params`` exactly — no more, no less.

    Returns:
        The raw records, as ``dict``s.

    Raises:
        TemplateSlotError: ``slots`` does not match the template's declared
            parameter names exactly.
    """
    template = TEMPLATES[template_id]
    given = set(slots)
    if given != template.params:
        missing = template.params - given
        unknown = given - template.params
        raise TemplateSlotError(
            f"template {template_id.value!r}: missing slots {sorted(missing)}, "
            f"unknown slots {sorted(unknown)}"
        )

    async with neo_session() as neo:
        result = await neo.run(template.query, **slots)
        rows = await result.data()

    return rows
