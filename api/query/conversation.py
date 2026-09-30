from dataclasses import dataclass, field
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models.conversation_model import Conversation, ConversationTurn
from . import repository

# A character id (~36 chars) plus punctuation, budgeted generously — this
# caps *how many turns* contribute resolved characters to the next question's
# name resolution, not the tokens sent to the answer model itself.
_CONTEXT_TOKEN_BUDGET = 800
_CHARS_PER_TOKEN = 4


@dataclass
class ConversationContext:
    """What the previous turns carry into resolving this one."""

    character_ids: list[UUID] = field(default_factory=list)
    scope_book_id: UUID | None = None
    scope_chapter: int | None = None
    summary: str | None = None


async def resolve_conversation(
    session: SQLModelAsyncSession, project_id: UUID, thread_id: UUID | None
) -> Conversation:
    """Return the conversation for ``thread_id``, or start a new one.

    A ``thread_id`` naming a conversation in a *different* project, or one
    that no longer exists, starts a fresh conversation rather than raising —
    a stale client-held id must not fail a question outright.
    """
    if thread_id is not None:
        existing = await repository.get_conversation(session, thread_id)
        if existing is not None and existing.project_id == project_id:
            return existing

    conversation = await repository.create_conversation(session, project_id)

    return conversation


def _within_budget(turns: list[ConversationTurn]) -> list[ConversationTurn]:
    """Keep the most recent turns that fit the token budget, oldest first."""
    kept: list[ConversationTurn] = []
    used = 0
    for turn in reversed(turns):
        cost = (len(turn.question) + len(turn.answer or "")) // _CHARS_PER_TOKEN
        if kept and used + cost > _CONTEXT_TOKEN_BUDGET:
            break
        kept.append(turn)
        used += cost

    kept.reverse()

    return kept


def _summarize_dropped(
    turns: list[ConversationTurn], kept: list[ConversationTurn]
) -> str | None:
    """Name the characters an over-budget prefix discussed, cheaply.

    No second LLM call: the characters a dropped turn resolved are already on
    its own row (``resolved_character_ids``), so naming them is a lookup, not
    a generation. Names, not ids — this reads as ordinary context to the
    router and to a human glancing at the log, not as an internal reference.
    """
    dropped = turns[: len(turns) - len(kept)]
    if not dropped:
        return None

    names: list[str] = []
    for turn in dropped:
        names.extend(turn.context.get("resolved_names", []))

    unique = sorted(set(names))
    if not unique:
        return None

    return f"Earlier in this conversation, also discussed: {', '.join(unique)}."


async def carry_context(
    session: SQLModelAsyncSession, conversation_id: UUID
) -> ConversationContext:
    """Return the character/chapter scope this conversation carries forward.

    Args:
        session: An open database session.
        conversation_id: The conversation whose history to read.

    Returns:
        The most recent turn's resolved characters (oldest first, so "her" in
        a compound question resolves against the latest one — see
        ``api.extraction.resolution._resolve_relative``), the conversation's
        reading-position scope, and a summary of anything the token budget
        pushed out.
    """
    conversation = await repository.get_conversation(session, conversation_id)
    turns = await repository.list_turns(session, conversation_id)
    kept = _within_budget(turns)

    character_ids: list[UUID] = []
    seen: set[UUID] = set()
    for turn in kept:
        for raw_id in turn.resolved_character_ids:
            character_id = UUID(raw_id)
            if character_id not in seen:
                seen.add(character_id)
                character_ids.append(character_id)

    context = ConversationContext(
        character_ids=character_ids,
        scope_book_id=conversation.scope_book_id if conversation else None,
        scope_chapter=conversation.scope_chapter if conversation else None,
        summary=_summarize_dropped(turns, kept),
    )

    return context


async def record_turn(
    session: SQLModelAsyncSession,
    *,
    conversation_id: UUID,
    question: str,
    answer: str | None,
    resolved_character_ids: list[UUID],
    resolved_names: list[str],
    query_log_id: UUID | None,
) -> ConversationTurn:
    """Persist one turn, with enough context to summarise it once it ages out."""
    turn = await repository.append_turn(
        session,
        conversation_id=conversation_id,
        question=question,
        answer=answer,
        resolved_character_ids=resolved_character_ids,
        context={"resolved_names": resolved_names},
        query_log_id=query_log_id,
    )

    return turn


async def set_scope(
    session: SQLModelAsyncSession,
    conversation: Conversation,
    *,
    limit_book_order: int | None,
    limit_chapter: int | None,
    project_id: UUID | None = None,
) -> None:
    """Record this turn's reading position as the conversation's carried scope.

    ``project_id`` should be passed by a caller that may have already
    committed on this session since ``conversation`` was loaded (the request-
    scoped session ``api/routes/query.py`` hands in defaults to
    ``expire_on_commit=True``). Reading ``conversation.project_id`` after an
    intervening commit hits an expired attribute and SQLAlchemy's async
    session cannot refresh it outside an awaited call, raising
    ``greenlet_spawn has not been called`` — a real bug this dodges rather
    than fixes at the root, since expiring the whole session after every
    commit is the documented convention (``api/tests/conftest.py``). Defaults
    to reading it off ``conversation`` for a caller that knows its session
    has not committed since the object was loaded.
    """
    if limit_book_order is None:
        return

    resolved_project_id = (
        project_id if project_id is not None else conversation.project_id
    )
    book_id = await repository.book_id_for_series_order(
        session, resolved_project_id, limit_book_order
    )
    conversation.scope_book_id = book_id
    conversation.scope_chapter = limit_chapter
    session.add(conversation)
    await session.commit()
