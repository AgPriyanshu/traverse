import pytest

from api.contracts.api import QueryRequest
from api.contracts.enums import QueryRoute, RelationFamily
from api.graph import projection
from api.query import pipeline, router
from api.query.router import RouterOutput
from api.tests.query.conftest import make_character, make_relation, project_now


def _stub_router(monkeypatch, output: RouterOutput):
    async def fake_classify(_question, *, project_id):
        del project_id

        return output

    monkeypatch.setattr(router, "classify_question", fake_classify)


async def _events(session, request):
    return [event async for event in pipeline.answer_question(session, request)]


@pytest.mark.asyncio
async def test_character_lookup_abstains_for_an_unknown_character(
    session, project, monkeypatch
):
    _stub_router(
        monkeypatch,
        RouterOutput(route=QueryRoute.CHARACTER_LOOKUP, subject_phrase="Nobody"),
    )
    request = QueryRequest(project_id=project.id, question="Who is Nobody?")

    events = await _events(session, request)

    tokens = [e for e in events if e.type == "token"]
    done = [e for e in events if e.type == "done"][0]
    assert tokens and "Not established" in tokens[0].text
    assert done.abstained is True


@pytest.mark.asyncio
async def test_character_lookup_finds_a_real_character(
    session, project, book, monkeypatch
):
    darcy = await make_character(session, project, name="Mr Darcy", aliases=["Darcy"])
    _stub_router(
        monkeypatch,
        RouterOutput(route=QueryRoute.CHARACTER_LOOKUP, subject_phrase="Darcy"),
    )
    request = QueryRequest(project_id=project.id, question="Who is Darcy?")

    events = await _events(session, request)

    tokens = [e for e in events if e.type == "token"]
    done = [e for e in events if e.type == "done"][0]
    assert tokens and darcy.canonical_name in tokens[0].text
    assert done.abstained is False


@pytest.mark.asyncio
async def test_ambiguous_name_interrupts_instead_of_guessing(
    session, project, monkeypatch
):
    await make_character(session, project, name="Fitzwilliam Darcy", aliases=["Darcy"])
    await make_character(session, project, name="Georgiana Darcy", aliases=["Darcy"])
    _stub_router(
        monkeypatch,
        RouterOutput(route=QueryRoute.CHARACTER_LOOKUP, subject_phrase="Darcy"),
    )
    request = QueryRequest(project_id=project.id, question="Who is Darcy?")

    events = await _events(session, request)

    assert events[-1].type == "interrupt"
    assert len(events[-1].options) == 2
    assert not any(e.type == "done" for e in events)


@pytest.mark.asyncio
async def test_missing_subject_phrase_interrupts(session, project, monkeypatch):
    _stub_router(monkeypatch, RouterOutput(route=QueryRoute.CHARACTER_LOOKUP))
    request = QueryRequest(project_id=project.id, question="Who is that?")

    events = await _events(session, request)

    assert events[-1].type == "interrupt"


@pytest.mark.asyncio
async def test_relationship_lookup_cites_the_real_edge(
    session, project, book, monkeypatch
):
    darcy = await make_character(session, project, name="Mr Darcy")
    elizabeth = await make_character(session, project, name="Elizabeth Bennet")
    await make_relation(
        session,
        project,
        book,
        subject=darcy,
        predicate="married_to",
        obj=elizabeth,
        family=RelationFamily.ROMANTIC,
        quote="Darcy married Elizabeth at last.",
    )
    _stub_router(
        monkeypatch,
        RouterOutput(
            route=QueryRoute.RELATIONSHIP_LOOKUP,
            subject_phrase="Darcy",
            object_phrase="Elizabeth",
        ),
    )
    request = QueryRequest(
        project_id=project.id, question="How does Darcy know Elizabeth?"
    )

    try:
        await project_now(session, project.id)
        events = await _events(session, request)
    finally:
        await projection.reset_project(project.id)

    tokens = [e for e in events if e.type == "token"]
    citations = [e for e in events if e.type == "citation"]
    done = [e for e in events if e.type == "done"][0]
    assert "married" in tokens[0].text
    assert len(citations) >= 1
    assert done.abstained is False


@pytest.mark.asyncio
async def test_relationship_lookup_abstains_when_no_edge_exists(
    session, project, book, monkeypatch
):
    await make_character(session, project, name="Mr Darcy")
    await make_character(session, project, name="Elizabeth Bennet")
    _stub_router(
        monkeypatch,
        RouterOutput(
            route=QueryRoute.RELATIONSHIP_LOOKUP,
            subject_phrase="Darcy",
            object_phrase="Elizabeth",
        ),
    )
    request = QueryRequest(
        project_id=project.id, question="How does Darcy know Elizabeth?"
    )

    try:
        await project_now(session, project.id)
        events = await _events(session, request)
    finally:
        await projection.reset_project(project.id)

    tokens = [e for e in events if e.type == "token"]
    done = [e for e in events if e.type == "done"][0]
    assert "Not established" in tokens[0].text
    assert done.abstained is True


@pytest.mark.asyncio
async def test_aggregation_lists_every_daughter_exhaustively(
    session, project, book, monkeypatch
):
    bennet = await make_character(
        session, project, name="Mr Bennet", aliases=["Mr. Bennet"]
    )
    names = [
        "Jane Bennet",
        "Elizabeth Bennet",
        "Mary Bennet",
        "Kitty Bennet",
        "Lydia Bennet",
    ]
    daughters = []
    for name in names:
        daughter = await make_character(
            session, project, name=name, aliases=[f"Miss {name.split()[0]}"]
        )
        daughters.append(daughter)
        await make_relation(
            session,
            project,
            book,
            subject=daughter,
            predicate="child_of",
            obj=bennet,
            family=RelationFamily.KINSHIP,
            quote=f"{name} is Mr Bennet's daughter.",
        )
    _stub_router(
        monkeypatch,
        RouterOutput(
            route=QueryRoute.AGGREGATION,
            subject_phrase="Mr Bennet",
            predicate_hint="daughters",
        ),
    )
    request = QueryRequest(
        project_id=project.id, question="Who are all of Mr Bennet's daughters?"
    )

    try:
        await project_now(session, project.id)
        events = await _events(session, request)
    finally:
        await projection.reset_project(project.id)

    tokens = [e for e in events if e.type == "token"]
    done = [e for e in events if e.type == "done"][0]
    for daughter in daughters:
        assert daughter.canonical_name in tokens[0].text
    assert done.abstained is False


@pytest.mark.asyncio
async def test_aggregation_abstains_for_a_gendered_hint_with_no_matching_gender(
    session, project, book, monkeypatch
):
    """The Sprint 6 demo's critical case: Elizabeth has sisters, not a brother.

    A gender-blind predicate match (``child_of``/``sibling_of``) would
    otherwise hand back her sisters as though they answered "brother" — this
    pins that they must not.
    """
    elizabeth = await make_character(
        session, project, name="Elizabeth Bennet", aliases=["Miss Elizabeth"]
    )
    jane = await make_character(
        session, project, name="Jane Bennet", aliases=["Miss Jane"]
    )
    await make_relation(
        session,
        project,
        book,
        subject=elizabeth,
        predicate="sibling_of",
        obj=jane,
        family=RelationFamily.KINSHIP,
        quote="Elizabeth and Jane are sisters.",
    )
    _stub_router(
        monkeypatch,
        RouterOutput(
            route=QueryRoute.AGGREGATION,
            subject_phrase="Elizabeth",
            predicate_hint="brother",
        ),
    )
    request = QueryRequest(
        project_id=project.id, question="What happens to Elizabeth's brother?"
    )

    try:
        await project_now(session, project.id)
        events = await _events(session, request)
    finally:
        await projection.reset_project(project.id)

    tokens = [e for e in events if e.type == "token"]
    done = [e for e in events if e.type == "done"][0]
    assert "Not established" in tokens[0].text
    assert "Jane" not in tokens[0].text
    assert done.abstained is True


@pytest.mark.asyncio
async def test_narrative_abstains_when_nothing_is_retrieved(
    session, project, monkeypatch
):
    _stub_router(monkeypatch, RouterOutput(route=QueryRoute.NARRATIVE))

    async def empty_retrieval(*_args, **_kwargs):
        from api.query.retrieval import RetrievalResult

        return RetrievalResult(tier="none", chunks=[])

    monkeypatch.setattr(pipeline.retrieval, "retrieve_for_narrative", empty_retrieval)
    request = QueryRequest(
        project_id=project.id, question="What is the meaning of life?"
    )

    events = await _events(session, request)

    tokens = [e for e in events if e.type == "token"]
    done = [e for e in events if e.type == "done"][0]
    assert "Not established" in tokens[0].text
    assert done.abstained is True


@pytest.mark.asyncio
async def test_conversation_carries_resolved_character_into_the_next_turn(
    session, project, book, monkeypatch
):
    elizabeth = await make_character(
        session, project, name="Elizabeth Bennet", aliases=["Miss Elizabeth"]
    )
    jane = await make_character(
        session, project, name="Jane Bennet", aliases=["Miss Jane"]
    )
    # Postgres-only: "her sister" resolves via `kinship_candidates`, which
    # reads the `Relation` table directly — no Neo4j projection needed here.
    await make_relation(
        session,
        project,
        book,
        subject=elizabeth,
        predicate="sibling_of",
        obj=jane,
        family=RelationFamily.KINSHIP,
        quote="Elizabeth and Jane are sisters.",
    )

    _stub_router(
        monkeypatch,
        RouterOutput(route=QueryRoute.CHARACTER_LOOKUP, subject_phrase="Elizabeth"),
    )
    first = QueryRequest(project_id=project.id, question="Who is Elizabeth?")
    first_events = await _events(session, first)
    thread_id = [e for e in first_events if e.type == "done"][0].thread_id

    _stub_router(
        monkeypatch,
        RouterOutput(route=QueryRoute.CHARACTER_LOOKUP, subject_phrase="her sister"),
    )
    second = QueryRequest(
        project_id=project.id, question="And her sister?", thread_id=thread_id
    )
    events = await _events(session, second)

    tokens = [e for e in events if e.type == "token"]
    assert tokens and jane.canonical_name in tokens[0].text
