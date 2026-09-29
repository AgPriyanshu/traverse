"""The query pipeline (S6.1-S6.6): route, resolve, retrieve, ground, stream.

``answer_question`` is the one entry point ``api/routes/query.py`` calls. It
is an async generator of ``QueryEvent`` — the SSE route wraps it, nothing
else does; this keeps the pipeline itself transport-agnostic and directly
testable without a running HTTP server.
"""

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    CitationEvent,
    DoneEvent,
    ErrorEvent,
    InterruptEvent,
    QueryEvent,
    QueryRequest,
    RouteEvent,
    TokenEvent,
)
from ..contracts.enums import QueryRoute
from ..extraction.resolution import CharacterRef, resolve_names
from ..graph import ontology
from ..graph import queries as graph_queries
from ..graph import repository as graph_repository
from ..llm import routing as llm_routing
from ..pipeline.timing import QueryTimer
from . import conversation as conversation_mod
from . import gender, generation, grounding, repository, retrieval, router
from .scope import ReadingScope
from .templates import (
    TemplateId,
    required_gender,
    resolve_aggregation_predicate,
    run_template,
)

logger = logging.getLogger(__name__)

MAX_PATH_HOPS = 4


class _Resolution:
    __slots__ = ("ref", "ambiguous_options")

    def __init__(
        self, ref: CharacterRef | None, ambiguous_options: list[CharacterRef]
    ) -> None:
        self.ref = ref
        self.ambiguous_options = ambiguous_options


def _resolve_single(refs: list[CharacterRef]) -> _Resolution:
    """Pick the one candidate a phrase resolved to, or flag a genuine tie.

    A tie at the top score is ambiguity, not something to break arbitrarily
    (``api.extraction.resolution``'s own contract) — the caller must turn
    that into a clarifying interrupt rather than silently picking one.
    """
    if not refs:
        return _Resolution(ref=None, ambiguous_options=[])

    top_score = refs[0].score
    tied = [r for r in refs if r.score == top_score]
    if len(tied) > 1:
        return _Resolution(ref=None, ambiguous_options=tied)

    return _Resolution(ref=refs[0], ambiguous_options=[])


async def _resolve_phrase(
    session: SQLModelAsyncSession,
    project_id: UUID,
    phrase: str | None,
    conversation_characters: list[UUID],
    scope: ReadingScope,
) -> _Resolution:
    if not phrase:
        return _Resolution(ref=None, ambiguous_options=[])

    refs = await resolve_names(
        session, project_id, phrase, conversation_characters=conversation_characters
    )
    # A candidate not yet visible at this reading position must not even
    # reach the ambiguity check: a clarifying question listing it ("Which
    # Catherine do you mean?") would itself confirm a future character's
    # existence, the same information leak as resolving to it outright
    # (S8.1, PRD F4.5).
    visible_refs = [
        ref
        for ref in refs
        if await graph_repository.is_character_visible(session, ref.character_id, scope)
    ]

    return _resolve_single(visible_refs)


def _interrupt(thread_id: UUID, question: str, options: list[str]) -> InterruptEvent:
    return InterruptEvent(
        type="interrupt", thread_id=thread_id, question=question, options=options
    )


async def answer_question(
    session: SQLModelAsyncSession, request: QueryRequest
) -> AsyncIterator[QueryEvent]:
    """Answer one question, yielding the SSE event stream as it is produced.

    Every branch below yields exactly one of ``interrupt`` or ``done`` as its
    terminal event — the route contract fe1 builds against
    (``plans/sprint-6/HANDOFF.md``).
    """
    timer = QueryTimer()
    # The one place a ``QueryRequest``'s optional, HTTP-boundary
    # ``limit_book_order``/``limit_chapter`` become the required internal
    # scope object every graph/retrieval/generation call below takes — no
    # other function in this package accepts the bare optional pair (S8.1,
    # PRD F4.5). ``None``/``None`` here is still an explicit choice: the
    # frozen ``QueryRequest`` contract (``api/contracts/api.py``) documents
    # it as one, made by whoever built the request.
    scope = ReadingScope(
        book_order=request.limit_book_order, chapter=request.limit_chapter
    )
    conversation = await conversation_mod.resolve_conversation(
        session, request.project_id, request.thread_id
    )

    try:
        with timer.stage("route"):
            router_out = await router.classify_question(
                request.question, project_id=str(request.project_id)
            )
    except Exception:
        logger.exception("query %s: router call failed", request.project_id)
        yield ErrorEvent(
            type="error", message="Could not route this question.", recoverable=True
        )

        return

    yield RouteEvent(type="route", route=router_out.route, explanation=None)

    with timer.stage("resolve"):
        context = await conversation_mod.carry_context(session, conversation.id)
        subject = await _resolve_phrase(
            session,
            request.project_id,
            router_out.subject_phrase,
            context.character_ids,
            scope,
        )
        object_ = await _resolve_phrase(
            session,
            request.project_id,
            router_out.object_phrase,
            context.character_ids,
            scope,
        )

    route = router_out.route
    needs_subject = route in {
        QueryRoute.CHARACTER_LOOKUP,
        QueryRoute.RELATIONSHIP_LOOKUP,
        QueryRoute.PATH,
        QueryRoute.AGGREGATION,
        QueryRoute.SERIES_ARC,
    }
    needs_object = route in {
        QueryRoute.RELATIONSHIP_LOOKUP,
        QueryRoute.PATH,
        QueryRoute.SERIES_ARC,
    }

    missing_required_phrase = (needs_subject and not router_out.subject_phrase) or (
        needs_object and not router_out.object_phrase
    )
    if route is QueryRoute.AMBIGUOUS or missing_required_phrase:
        async for event in _finish_interrupt(
            conversation.id, question="Which character do you mean?", options=[]
        ):
            yield event

        return

    if subject.ambiguous_options:
        options = [ref.canonical_name for ref in subject.ambiguous_options]
        question = f"Which {router_out.subject_phrase!r} do you mean?"
        async for event in _finish_interrupt(conversation.id, question, options):
            yield event

        return

    if needs_object and object_.ambiguous_options:
        options = [ref.canonical_name for ref in object_.ambiguous_options]
        question = f"Which {router_out.object_phrase!r} do you mean?"
        async for event in _finish_interrupt(conversation.id, question, options):
            yield event

        return

    if needs_subject and subject.ref is None:
        result = grounding.abstain("No such character is established in this project.")
        async for event in _finish(
            session,
            request,
            conversation,
            router_out,
            timer,
            resolved=[],
            answer=result,
        ):
            yield event

        return

    if needs_object and object_.ref is None:
        result = grounding.abstain("No such character is established in this project.")
        async for event in _finish(
            session,
            request,
            conversation,
            router_out,
            timer,
            resolved=[subject.ref] if subject.ref else [],
            answer=result,
        ):
            yield event

        return

    resolved_refs = [r for r in (subject.ref, object_.ref) if r is not None]

    with timer.stage("graph"):
        if route is QueryRoute.CHARACTER_LOOKUP:
            character = await graph_repository.get_character(
                session, subject.ref.character_id, scope=scope
            )
            mentions = (
                await graph_repository.list_mentions(
                    session, subject.ref.character_id, limit=5, scope=scope
                )
                or []
            )
            answer = await generation.render_character_lookup(character, mentions)

        elif route is QueryRoute.RELATIONSHIP_LOOKUP:
            rows = await run_template(
                TemplateId.RELATIONSHIP_LOOKUP,
                subject_id=str(subject.ref.character_id),
                object_id=str(object_.ref.character_id),
                project_id=str(request.project_id),
                lbo=scope.book_order,
                lch=scope.chapter,
            )
            relation_ids = [UUID(row["relation_id"]) for row in rows]
            relations = await graph_repository.relations_out(
                session, relation_ids, scope=scope
            )
            answer = await generation.render_relationship_lookup(
                session, relations, scope=scope
            )

        elif route is QueryRoute.PATH:
            path = await graph_queries.shortest_path(
                session,
                subject.ref.character_id,
                object_.ref.character_id,
                MAX_PATH_HOPS,
                scope=scope,
            )
            answer = await generation.render_path(session, path.hops, scope=scope)

        elif route is QueryRoute.AGGREGATION:
            answer = await _run_aggregation(
                session, request, subject.ref, router_out, scope
            )

        elif route is QueryRoute.SERIES_ARC:
            arc = await graph_repository.relation_arc(
                session, subject.ref.character_id, object_.ref.character_id, scope=scope
            )
            answer = await generation.render_series_arc(session, arc, scope=scope)

        else:
            answer = None  # narrative — handled below, outside the graph stage.

    if route is QueryRoute.NARRATIVE:
        async for event in _answer_narrative(
            session, request, conversation, router_out, timer, resolved_refs, scope
        ):
            yield event

        return

    async for event in _finish(
        session,
        request,
        conversation,
        router_out,
        timer,
        resolved=resolved_refs,
        answer=answer,
    ):
        yield event


async def _run_aggregation(
    session, request, anchor: CharacterRef, router_out, scope: ReadingScope
):
    predicate = resolve_aggregation_predicate(router_out.predicate_hint)
    if predicate is None:
        return grounding.abstain(
            "Could not map that relationship word to a known relationship type."
        )

    inverse_predicate = ontology.inverse_of(predicate) or predicate
    rows = await run_template(
        TemplateId.AGGREGATION,
        anchor_id=str(anchor.character_id),
        project_id=str(request.project_id),
        predicate=predicate,
        inverse_predicate=inverse_predicate,
        lbo=scope.book_order,
        lch=scope.chapter,
    )
    relation_ids = [UUID(row["relation_id"]) for row in rows]
    relations = await graph_repository.relations_out(session, relation_ids, scope=scope)
    # ``other_ids`` is derived from ``relations`` *after* spoiler filtering,
    # never from the raw Cypher rows above: an aggregation answer's own
    # sentence enumerates every id in ``other_names`` regardless of whether
    # its relation to the anchor is still in ``relations`` (see
    # ``generation.render_aggregation``), so naming one from an unfiltered
    # id list would reintroduce exactly the leak filtering ``relations``
    # alone was meant to close (S8.1, PRD F4.5).
    other_ids = list(
        {
            (
                r.object_character_id
                if r.subject_character_id == anchor.character_id
                else r.subject_character_id
            )
            for r in relations
        }
    )
    others = await repository.characters_by_id(session, other_ids)

    wanted_gender = required_gender(router_out.predicate_hint)
    if wanted_gender is not None:
        others = {
            cid: character
            for cid, character in others.items()
            if gender.infer_gender(character) == wanted_gender
        }
        relations = [
            r
            for r in relations
            if r.subject_character_id in others or r.object_character_id in others
        ]

    other_names = {cid: character.canonical_name for cid, character in others.items()}
    answer = await generation.render_aggregation(
        session,
        anchor_name=anchor.canonical_name,
        predicate=predicate,
        relations=relations,
        other_names=other_names,
        scope=scope,
    )

    return answer


async def _answer_narrative(
    session,
    request,
    conversation,
    router_out,
    timer,
    resolved_refs,
    scope: ReadingScope,
) -> AsyncIterator[QueryEvent]:
    character_ids = [ref.character_id for ref in resolved_refs]
    with timer.stage("retrieve"):
        retrieved = await retrieval.retrieve_for_narrative(
            session,
            project_id=request.project_id,
            question=request.question,
            character_ids=character_ids,
            scope=scope,
        )

    if not retrieved.chunks:
        answer = grounding.abstain()
        async for event in _finish(
            session,
            request,
            conversation,
            router_out,
            timer,
            resolved=resolved_refs,
            answer=answer,
            retrieval_tier=retrieved.tier,
        ):
            yield event

        return

    # Tokens are buffered, not streamed live: a claim that grounding drops a
    # sentence after it was already shown to the user is exactly the
    # "hedge instead of remove" failure F4.4 forbids, just staged over SSE
    # instead of in the text. TTFT is still measured against the raw model
    # stream (NFR-perf cares about generation latency, not about when the
    # verified text reaches the wire), so the metric stays honest even
    # though nothing renders until grounding finishes.
    draft_pieces: list[str] = []
    with timer.stage("generate"):
        first_token = True
        async for delta in generation.stream_narrative_draft(
            request.question, retrieved.chunks, project_id=str(request.project_id)
        ):
            if first_token:
                timer.mark_ttft()
                first_token = False
            draft_pieces.append(delta)

    draft = "".join(draft_pieces)
    with timer.stage("ground"):
        answer = await grounding.ground_narrative_answer(
            session, draft, retrieved.chunks
        )

    async for event in _finish(
        session,
        request,
        conversation,
        router_out,
        timer,
        resolved=resolved_refs,
        answer=answer,
        retrieval_tier=retrieved.tier,
    ):
        yield event


async def _finish(
    session,
    request,
    conversation,
    router_out,
    timer,
    *,
    resolved,
    answer,
    retrieval_tier=None,
) -> AsyncIterator[QueryEvent]:
    """Emit the answer's tokens and citations, persist it, then yield ``done``.

    The one place ``answer.text`` reaches the wire: every terminal branch
    (abstention, a graph-derived answer, a grounded narrative one) funnels
    through here, so there is exactly one code path that can forget to emit
    it — deliberately, after the abstention-without-a-visible-answer bug this
    replaced.
    """
    yield TokenEvent(type="token", text=answer.text)
    for index, citation in enumerate(answer.citations):
        yield CitationEvent(type="citation", index=index, citation=citation)

    # Captured before any commit below: ``write_query_log``/``record_turn``
    # each commit on this same request-scoped session, which (unlike the
    # test session, ``api/tests/conftest.py``) defaults to
    # ``expire_on_commit=True``. Reading ``conversation.id``/``.project_id``
    # synchronously after that expires them mid-generator raised
    # ``greenlet_spawn has not been called`` on every query route — a real,
    # previously-unfixed bug (Sprint 8 retro, do1) — because SQLAlchemy's
    # async session cannot refresh an expired attribute outside an awaited
    # call. Capturing the plain values once, up front, avoids ever touching
    # the ORM object again after it is expired.
    conversation_id = conversation.id
    conversation_project_id = conversation.project_id

    resolved_ids = [ref.character_id for ref in resolved]
    resolved_names = [ref.canonical_name for ref in resolved]

    live_policy = llm_routing.get_live_policy()
    policy_version = live_policy[0] if live_policy is not None else None

    log = await repository.write_query_log(
        session,
        project_id=request.project_id,
        question=request.question,
        route=router_out.route,
        cypher_template=None,
        retrieved_ids={"tier": retrieval_tier} if retrieval_tier else None,
        answer=answer.text,
        citations={"count": len(answer.citations)},
        latency_ms=timer.as_dict(),
        limit_book_order=request.limit_book_order,
        limit_chapter=request.limit_chapter,
        policy_version=policy_version,
    )
    await conversation_mod.record_turn(
        session,
        conversation_id=conversation_id,
        question=request.question,
        answer=answer.text,
        resolved_character_ids=resolved_ids,
        resolved_names=resolved_names,
        query_log_id=log.id,
    )
    await conversation_mod.set_scope(
        session,
        conversation,
        limit_book_order=request.limit_book_order,
        limit_chapter=request.limit_chapter,
        project_id=conversation_project_id,
    )

    yield DoneEvent(
        type="done",
        thread_id=conversation_id,
        citation_count=len(answer.citations),
        latency_ms=timer.as_dict().get("total_ms"),
        abstained=answer.abstained,
    )


async def _finish_interrupt(
    conversation_id: UUID, question: str, options: list[str]
) -> AsyncIterator[QueryEvent]:
    """Yield the interrupt event. No answer was produced, so nothing is logged."""
    yield _interrupt(conversation_id, question, options)
