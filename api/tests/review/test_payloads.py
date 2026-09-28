import uuid

import pytest

from api.contracts.enums import (
    AssertionType,
    CandidateKind,
    DetectionMethod,
    ImportanceTier,
    RelationFamily,
    ReviewTaskType,
)
from api.db.models import Chapter, Character, Relation, RelationEvidence
from api.db.models.chunk_model import DocumentChunk
from api.db.models.review_model import ReviewTask
from api.review import payloads


async def _character(session, project, *, name, tier=ImportanceTier.MINOR, mentions=0):
    character = Character(
        project_id=project.id,
        canonical_name=name,
        importance_tier=tier,
        mention_count=mentions,
    )
    session.add(character)
    await session.commit()
    await session.refresh(character)

    return character


@pytest.mark.asyncio
async def test_merge_characters_hydrates_two_candidates_by_name(session, project, book):
    """Mirrors ``queue_collision_review``'s lean ``{name_a, name_b, reason}``."""
    earnshaw = await _character(
        session, project, name="Catherine Earnshaw", tier=ImportanceTier.PROTAGONIST
    )
    linton = await _character(
        session, project, name="Catherine Linton", tier=ImportanceTier.MAJOR
    )
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={
            "name_a": earnshaw.canonical_name,
            "name_b": linton.canonical_name,
            "reason": "co-presence and generational marker",
        },
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    payload, score = await payloads.hydrate(session, task)

    ids = {c.id for c in payload.candidates}
    assert ids == {earnshaw.id, linton.id}
    assert payload.task_type == ReviewTaskType.MERGE_CHARACTERS
    # A protagonist is involved -- this must sort far above a minor confirm.
    assert score > 1000


@pytest.mark.asyncio
async def test_merge_across_books_hydrates_target_by_id(session, project, book):
    target = await _character(session, project, name="Anne Shirley")
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_ACROSS_BOOKS,
        payload={
            "candidate_name": "Miss Shirley",
            "target_name": target.canonical_name,
            "target_character_id": str(target.id),
            "reason": "alias overlap",
            "confidence": 0.7,
        },
        priority=2,
    )
    session.add(task)
    await session.commit()

    with pytest.raises(payloads.HydrationError):
        # The candidate-side character was never created in this fixture --
        # a genuinely unresolvable reference must raise, not silently drop
        # to one candidate.
        await payloads.hydrate(session, task)


@pytest.mark.asyncio
async def test_resolve_conflict_hydrates_both_relations_with_evidence(
    session, project, book
):
    alice = await _character(session, project, name="Alice", tier=ImportanceTier.MAJOR)
    bob = await _character(session, project, name="Bob")
    chunk = DocumentChunk(
        book_id=book.id, text="Alice loves Bob.", pages=[5], page_start=5, page_end=5
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)

    friend = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="friend_of",
        family=RelationFamily.SOCIAL,
        confidence=0.6,
        evidence_count=1,
    )
    enemy = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="enemy_of",
        family=RelationFamily.ADVERSARIAL,
        confidence=0.6,
        evidence_count=1,
    )
    session.add_all([friend, enemy])
    await session.commit()
    await session.refresh(friend)
    await session.refresh(enemy)

    session.add(
        RelationEvidence(
            relation_id=friend.id,
            book_id=book.id,
            chunk_id=chunk.id,
            page_start=5,
            page_end=5,
            quote="Alice loves Bob.",
            assertion_type=AssertionType.NARRATED,
        )
    )
    await session.commit()

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.RESOLVE_CONFLICT,
        payload={
            "type": "incompatible_relations",
            "character_ids": [str(alice.id), str(bob.id)],
            "relations": [
                [str(alice.id), "friend_of", str(bob.id)],
                [str(alice.id), "enemy_of", str(bob.id)],
            ],
        },
        priority=10,
    )
    session.add(task)
    await session.commit()

    payload, score = await payloads.hydrate(session, task)

    predicates = {r.predicate for r in payload.conflicting}
    assert predicates == {"friend_of", "enemy_of"}
    assert len(payload.evidence[str(friend.id)]) == 1
    assert score > 0


@pytest.mark.asyncio
async def test_confirm_relation_hydrates_one_relation(session, project, book):
    alice = await _character(session, project, name="Alice")
    bob = await _character(session, project, name="Bob")
    relation = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="rival_of",
        family=RelationFamily.ADVERSARIAL,
        confidence=0.5,
        hearsay=True,
        evidence_count=1,
    )
    session.add(relation)
    await session.commit()
    await session.refresh(relation)

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CONFIRM_RELATION,
        payload={
            "relation_id": str(relation.id),
            "reason": "single dialogue-sourced claim",
        },
        priority=5,
    )
    session.add(task)
    await session.commit()

    payload, _score = await payloads.hydrate(session, task)

    assert payload.relation.id == relation.id
    assert payload.reason == "single dialogue-sourced claim"


@pytest.mark.asyncio
async def test_classify_candidate_is_self_sufficient(session, project, book):
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CLASSIFY_CANDIDATE,
        payload={
            "candidate_id": str(uuid.uuid4()),
            "surface_form": "the Grange",
            "book_id": str(book.id),
            "kind_guess": CandidateKind.PLACE.value,
            "mention_count": 3,
            "contexts": [],
        },
        priority=1,
    )
    session.add(task)
    await session.commit()

    payload, _score = await payloads.hydrate(session, task)

    assert payload.surface_form == "the Grange"
    assert payload.kind_guess is CandidateKind.PLACE


@pytest.mark.asyncio
async def test_confirm_chapter_split_hydrates_live_chapter(session, project, book):
    chapter = Chapter(
        book_id=book.id,
        number=12,
        page_start=100,
        page_end=110,
        detection_method=DetectionMethod.REGEX,
        confidence=0.4,
    )
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT,
        payload={
            "chapter_id": str(chapter.id),
            "preceding_text": "...end of scene.",
            "following_text": "Chapter Thirteen...",
            "confidence": 0.4,
        },
        priority=1,
    )
    session.add(task)
    await session.commit()

    payload, _score = await payloads.hydrate(session, task)

    assert payload.chapter.id == chapter.id
    assert payload.chapter.page_start == 100
