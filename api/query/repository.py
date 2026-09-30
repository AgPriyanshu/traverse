from uuid import UUID

from sqlalchemy import or_, true
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.enums import QueryRoute
from ..db.models.character_model import Character
from ..db.models.conversation_model import Conversation, ConversationTurn
from ..db.models.ops_model import QueryLog
from ..db.models.project_model import Book
from ..db.models.relation_model import Relation, RelationEvidence
from .scope import ReadingScope


async def get_conversation(
    session: SQLModelAsyncSession, conversation_id: UUID
) -> Conversation | None:
    """Return a conversation, or ``None`` if it does not exist."""
    return await session.get(Conversation, conversation_id)


async def create_conversation(
    session: SQLModelAsyncSession, project_id: UUID
) -> Conversation:
    """Start a new, empty conversation thread for a project."""
    conversation = Conversation(project_id=project_id)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)

    return conversation


async def list_turns(
    session: SQLModelAsyncSession, conversation_id: UUID
) -> list[ConversationTurn]:
    """Return a conversation's turns, oldest first."""
    result = await session.exec(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.position)
    )

    return list(result.all())


async def append_turn(
    session: SQLModelAsyncSession,
    *,
    conversation_id: UUID,
    question: str,
    answer: str | None,
    resolved_character_ids: list[UUID],
    context: dict,
    query_log_id: UUID | None,
) -> ConversationTurn:
    """Append the next turn to a conversation, in position order.

    Position is computed from the current row count rather than tracked on
    ``Conversation`` itself — one fewer piece of mutable state to keep in
    sync, and a conversation's own turn count is cheap to read (thread depth
    is turns, not chunks).
    """
    existing = await list_turns(session, conversation_id)
    turn = ConversationTurn(
        conversation_id=conversation_id,
        position=len(existing),
        question=question,
        answer=answer,
        resolved_character_ids=[str(cid) for cid in resolved_character_ids],
        context=context,
        query_log_id=query_log_id,
    )
    session.add(turn)
    await session.commit()
    await session.refresh(turn)

    return turn


async def write_query_log(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    question: str,
    route: QueryRoute | None,
    cypher_template: str | None,
    retrieved_ids: dict | None,
    answer: str | None,
    citations: dict | None,
    latency_ms: dict | None,
    limit_book_order: int | None,
    limit_chapter: int | None,
    policy_version: int | None = None,
) -> QueryLog:
    """Persist one query for the ops dashboard and the answer-quality harness.

    ``policy_version`` is the live routing policy's version at answer time
    (``api/llm/routing.py::get_live_policy``, S9.6) -- without it, a
    cost/accuracy comparison across a policy flip is uninterpretable, since
    there would be no way to tell which queries ran under which policy
    (backend-2.md's S9.6 DoD).
    """
    row = QueryLog(
        project_id=project_id,
        question=question,
        route=route,
        cypher_template=cypher_template,
        retrieved_ids=retrieved_ids,
        answer=answer,
        citations=citations,
        latency_ms=latency_ms,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
        policy_version=policy_version,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


async def book_id_for_series_order(
    session: SQLModelAsyncSession, project_id: UUID, series_order: int
) -> UUID | None:
    """Resolve a reading-position book order to its book id, within one project."""
    result = await session.exec(
        select(Book.id)
        .where(Book.project_id == project_id)
        .where(Book.series_order == series_order)
    )

    return result.first()


class EvidenceRow:
    """One relation-evidence row with the fields citation-building needs.

    ``graph.repository.EvidenceOut`` (the API contract) deliberately drops
    ``chunk_id`` — the web client never needs it — but the query path needs it
    to run ``locate_quote`` (be1, S6.8), so this reads the ORM row directly
    rather than going through that contract type.
    """

    __slots__ = (
        "chunk_id",
        "book_id",
        "book_title",
        "series_order",
        "chapter_no",
        "page_start",
        "page_end",
        "quote",
        "confidence",
    )

    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


def _evidence_visible_at(statement, *, scope: ReadingScope):
    """Restrict a ``RelationEvidence`` query to a reading position.

    Mirrors ``graph/repository.py::_evidence_reading_position_filter`` — kept
    as a second, smaller copy rather than a cross-package import because this
    module never otherwise reaches into ``api.graph`` (``api/AGENTS.md``'s
    repository-per-package convention). A citation for a relation that is
    itself already visible must still not cite a *later* reassertion of it
    (S8.1, PRD F4.5).
    """
    if scope.book_order is None:
        return statement

    return statement.where(
        or_(
            RelationEvidence.book_order < scope.book_order,
            (RelationEvidence.book_order == scope.book_order)
            & (
                true()
                if scope.chapter is None
                else RelationEvidence.chapter_no <= scope.chapter
            ),
        )
    )


async def top_evidence_for_relation(
    session: SQLModelAsyncSession,
    relation_id: UUID,
    *,
    scope: ReadingScope,
    limit: int = 5,
) -> list[EvidenceRow]:
    """Return a relation's best evidence, chunk id included, for citations.

    Args:
        session: An open database session.
        relation_id: The relation whose evidence to load.
        scope: The reader's position. ``ReadingScope.unlimited()`` for no
            restriction — never a default, an explicit choice at the call
            site (S8.1, PRD F4.5).
        limit: Top-N to return, by confidence.
    """
    statement = (
        select(RelationEvidence, Book.title, Book.series_order)
        .join(Book, Book.id == RelationEvidence.book_id)
        .where(RelationEvidence.relation_id == relation_id)
    )
    statement = _evidence_visible_at(statement, scope=scope)
    statement = statement.order_by(
        RelationEvidence.confidence.desc().nulls_last()
    ).limit(limit)
    rows = (await session.exec(statement)).all()

    return [
        EvidenceRow(
            chunk_id=evidence.chunk_id,
            book_id=evidence.book_id,
            book_title=title,
            series_order=series_order,
            chapter_no=evidence.chapter_no,
            page_start=evidence.page_start,
            page_end=evidence.page_end,
            quote=evidence.quote,
            confidence=evidence.confidence,
        )
        for evidence, title, series_order in rows
    ]


async def characters_by_id(
    session: SQLModelAsyncSession, character_ids: list[UUID]
) -> dict[UUID, Character]:
    """Return full character rows for a set of ids, keyed by id.

    Full rows, not just names: aggregation rendering also needs ``aliases``
    to infer gender for a gendered hint (``gender.infer_gender``).
    """
    if not character_ids:
        return {}

    result = await session.exec(
        select(Character).where(Character.id.in_(character_ids))
    )

    return {character.id: character for character in result.all()}


async def relation_speaker(
    session: SQLModelAsyncSession, relation_id: UUID
) -> str | None:
    """Return the name a hearsay relation is attributed to, or ``None``.

    ``Relation.asserted_by_character_id`` is only ever set for ``dialogue``
    assertions; a narrated fact has nobody to attribute, and rendering must
    not invent an "According to..." prefix for one.
    """
    relation = await session.get(Relation, relation_id)
    if relation is None or relation.asserted_by_character_id is None:
        return None

    result = await session.exec(
        select(Character.canonical_name).where(
            Character.id == relation.asserted_by_character_id
        )
    )

    return result.first()


async def top_relation_ids_for_character(
    session: SQLModelAsyncSession, character_id: UUID, *, limit: int = 12
) -> list[UUID]:
    """Return a character's strongest relation ids, either direction.

    Over-fetches; the caller hydrates through ``relations_out``, which drops
    anything beyond the reader's position, then keeps the first few.

    Args:
        session: An open database session.
        character_id: The character whose relations to list.
        limit: Candidate ids to return, by confidence.
    """
    statement = (
        select(Relation.id)
        .where(
            or_(
                Relation.subject_character_id == character_id,
                Relation.object_character_id == character_id,
            )
        )
        .order_by(Relation.confidence.desc(), Relation.id)
        .limit(limit)
    )
    result = await session.exec(statement)
    relation_ids = list(result.all())

    return relation_ids
