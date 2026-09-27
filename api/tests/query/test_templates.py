import pytest

from api.contracts.enums import RelationFamily
from api.graph import projection
from api.query.templates import (
    TemplateId,
    required_gender,
    resolve_aggregation_predicate,
    run_template,
)
from api.tests.query.conftest import make_character, make_relation, project_now


def test_resolve_aggregation_predicate_maps_known_hints():
    assert resolve_aggregation_predicate("daughters") == "child_of"
    assert resolve_aggregation_predicate("sons") == "child_of"
    assert resolve_aggregation_predicate("friends") == "friend_of"


def test_resolve_aggregation_predicate_rejects_unknown_hint():
    assert resolve_aggregation_predicate("nemeses") is None
    assert resolve_aggregation_predicate(None) is None
    assert resolve_aggregation_predicate("") is None


def test_resolve_aggregation_predicate_never_returns_an_undeclared_predicate():
    """Every mapped value must be a real ontology predicate, not a made-up string."""
    from api.graph import ontology
    from api.query.templates import AGGREGATION_PREDICATE_HINTS

    for hint, predicate in AGGREGATION_PREDICATE_HINTS.items():
        assert ontology.is_predicate(predicate), (hint, predicate)


def test_required_gender_only_flags_gendered_hints():
    assert required_gender("daughters") == "female"
    assert required_gender("sons") == "male"
    assert required_gender("children") is None
    assert required_gender("friends") is None


@pytest.mark.asyncio
async def test_relationship_lookup_template_finds_edge_either_direction(
    session, project, book
):
    bennet = await make_character(session, project, name="Mr Bennet")
    jane = await make_character(session, project, name="Jane Bennet")
    await make_relation(
        session,
        project,
        book,
        subject=jane,
        predicate="child_of",
        obj=bennet,
        family=RelationFamily.KINSHIP,
        quote="Jane is Mr Bennet's daughter.",
    )

    try:
        await project_now(session, project.id)

        rows = await run_template(
            TemplateId.RELATIONSHIP_LOOKUP,
            subject_id=str(bennet.id),
            object_id=str(jane.id),
            project_id=str(project.id),
        )
        assert len(rows) >= 1

        reversed_rows = await run_template(
            TemplateId.RELATIONSHIP_LOOKUP,
            subject_id=str(jane.id),
            object_id=str(bennet.id),
            project_id=str(project.id),
        )
        assert {r["relation_id"] for r in rows} == {
            r["relation_id"] for r in reversed_rows
        }
    finally:
        await projection.reset_project(project.id)


@pytest.mark.asyncio
async def test_aggregation_template_is_exhaustive_and_predicate_scoped(
    session, project, book
):
    bennet = await make_character(session, project, name="Mr Bennet")
    daughters = [
        await make_character(session, project, name=n)
        for n in (
            "Jane Bennet",
            "Elizabeth Bennet",
            "Mary Bennet",
            "Kitty Bennet",
            "Lydia Bennet",
        )
    ]
    for daughter in daughters:
        await make_relation(
            session,
            project,
            book,
            subject=daughter,
            predicate="child_of",
            obj=bennet,
            family=RelationFamily.KINSHIP,
            quote=f"{daughter.canonical_name} is Mr Bennet's daughter.",
        )
    # A friendship that must NOT show up in a child_of aggregation.
    friend = await make_character(session, project, name="Charlotte Lucas")
    await make_relation(
        session,
        project,
        book,
        subject=bennet,
        predicate="friend_of",
        obj=friend,
        family=RelationFamily.SOCIAL,
        quote="Mr Bennet and Charlotte's father were old friends.",
    )

    try:
        await project_now(session, project.id)

        rows = await run_template(
            TemplateId.AGGREGATION,
            anchor_id=str(bennet.id),
            project_id=str(project.id),
            predicate="parent_of",
            inverse_predicate="child_of",
        )
        other_ids = {r["other_id"] for r in rows}
        assert other_ids == {str(d.id) for d in daughters}
        assert str(friend.id) not in other_ids
    finally:
        await projection.reset_project(project.id)
