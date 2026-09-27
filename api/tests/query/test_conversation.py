import uuid

import pytest

from api.query import conversation as conversation_mod


@pytest.mark.asyncio
async def test_resolve_conversation_creates_when_thread_id_is_none(session, project):
    conversation = await conversation_mod.resolve_conversation(
        session, project.id, None
    )
    assert conversation.project_id == project.id


@pytest.mark.asyncio
async def test_resolve_conversation_reuses_existing_thread(session, project):
    first = await conversation_mod.resolve_conversation(session, project.id, None)
    again = await conversation_mod.resolve_conversation(session, project.id, first.id)
    assert again.id == first.id


@pytest.mark.asyncio
async def test_resolve_conversation_starts_fresh_for_a_stale_or_foreign_thread(
    session, project
):
    conversation = await conversation_mod.resolve_conversation(
        session, project.id, uuid.uuid4()
    )
    assert conversation.project_id == project.id


@pytest.mark.asyncio
async def test_carry_context_orders_characters_oldest_first(session, project):
    conversation = await conversation_mod.resolve_conversation(
        session, project.id, None
    )
    first_id, second_id = uuid.uuid4(), uuid.uuid4()

    await conversation_mod.record_turn(
        session,
        conversation_id=conversation.id,
        question="Who is Elizabeth?",
        answer="A character.",
        resolved_character_ids=[first_id],
        resolved_names=["Elizabeth Bennet"],
        query_log_id=None,
    )
    await conversation_mod.record_turn(
        session,
        conversation_id=conversation.id,
        question="And her sister?",
        answer="Jane.",
        resolved_character_ids=[second_id],
        resolved_names=["Jane Bennet"],
        query_log_id=None,
    )

    context = await conversation_mod.carry_context(session, conversation.id)

    assert context.character_ids == [first_id, second_id]


@pytest.mark.asyncio
async def test_carry_context_drops_turns_beyond_the_token_budget_and_summarises(
    session, project, monkeypatch
):
    monkeypatch.setattr(conversation_mod, "_CONTEXT_TOKEN_BUDGET", 10)
    conversation = await conversation_mod.resolve_conversation(
        session, project.id, None
    )
    old_id, new_id = uuid.uuid4(), uuid.uuid4()

    await conversation_mod.record_turn(
        session,
        conversation_id=conversation.id,
        question="Who is Elizabeth Bennet, the second daughter of the family?",
        answer=(
            "A very long answer about Elizabeth that easily blows a ten token budget."
        ),
        resolved_character_ids=[old_id],
        resolved_names=["Elizabeth Bennet"],
        query_log_id=None,
    )
    await conversation_mod.record_turn(
        session,
        conversation_id=conversation.id,
        question="And Jane?",
        answer="Jane.",
        resolved_character_ids=[new_id],
        resolved_names=["Jane Bennet"],
        query_log_id=None,
    )

    context = await conversation_mod.carry_context(session, conversation.id)

    assert new_id in context.character_ids
    assert old_id not in context.character_ids
    assert context.summary is not None
    assert "Elizabeth Bennet" in context.summary


@pytest.mark.asyncio
async def test_set_scope_records_book_and_chapter(session, project, book):
    book.series_order = 1
    session.add(book)
    await session.commit()

    conversation = await conversation_mod.resolve_conversation(
        session, project.id, None
    )
    await conversation_mod.set_scope(
        session, conversation, limit_book_order=1, limit_chapter=5
    )

    refreshed = await conversation_mod.resolve_conversation(
        session, project.id, conversation.id
    )
    assert refreshed.scope_book_id == book.id
    assert refreshed.scope_chapter == 5
