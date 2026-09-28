import pytest
from sqlmodel import select

from api.contracts.api import ReviewResolution
from api.contracts.enums import (
    CandidateKind,
    DetectionMethod,
    ImportanceTier,
    ReviewStatus,
    ReviewTaskType,
)
from api.db.models import BookCharacterCandidate, Chapter, Character, Relation
from api.db.models.review_model import CorrectionFeedback, ReviewTask
from api.review import resolution


async def _character(session, project, *, name, tier=ImportanceTier.MINOR):
    character = Character(
        project_id=project.id, canonical_name=name, importance_tier=tier
    )
    session.add(character)
    await session.commit()
    await session.refresh(character)

    return character


@pytest.mark.asyncio
async def test_merge_decision_merges_and_marks_resolved(session, project, book):
    target = await _character(session, project, name="Catherine Earnshaw")
    source = await _character(session, project, name="Catherine (dup)")
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": target.canonical_name, "name_b": source.canonical_name},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    body = ReviewResolution(
        decision="merge",
        payload={"primary_id": str(target.id), "merge_ids": [str(source.id)]},
    )
    resolved = await resolution.resolve(session, task, body)

    assert resolved.status == ReviewStatus.RESOLVED
    assert await session.get(Character, source.id) is None
    survivor = await session.get(Character, target.id)
    assert survivor.human_verified is True

    feedback = (
        await session.exec(
            select(CorrectionFeedback).where(
                CorrectionFeedback.review_task_id == task.id
            )
        )
    ).first()
    assert feedback is not None
    assert feedback.human_value["decision"] == "merge"


@pytest.mark.asyncio
async def test_keep_separate_resolves_without_merging(session, project, book):
    a = await _character(session, project, name="Catherine Earnshaw")
    b = await _character(session, project, name="Catherine Linton")
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": a.canonical_name, "name_b": b.canonical_name},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resolved = await resolution.resolve(
        session, task, ReviewResolution(decision="keep_separate")
    )

    assert resolved.status == ReviewStatus.RESOLVED
    assert await session.get(Character, a.id) is not None
    assert await session.get(Character, b.id) is not None


@pytest.mark.asyncio
async def test_confirm_relation_reject_deletes_the_edge(session, project, book):
    from api.contracts.enums import RelationFamily

    alice = await _character(session, project, name="Alice")
    bob = await _character(session, project, name="Bob")
    relation = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="rival_of",
        family=RelationFamily.ADVERSARIAL,
        hearsay=True,
    )
    session.add(relation)
    await session.commit()
    await session.refresh(relation)

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CONFIRM_RELATION,
        payload={"relation_id": str(relation.id), "reason": "single source"},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resolved = await resolution.resolve(
        session, task, ReviewResolution(decision="reject")
    )

    assert resolved.status == ReviewStatus.RESOLVED
    assert await session.get(Relation, relation.id) is None


@pytest.mark.asyncio
async def test_confirm_relation_accept_marks_verified(session, project, book):
    from api.contracts.enums import RelationFamily

    alice = await _character(session, project, name="Alice")
    bob = await _character(session, project, name="Bob")
    relation = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="friend_of",
        family=RelationFamily.SOCIAL,
    )
    session.add(relation)
    await session.commit()
    await session.refresh(relation)

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CONFIRM_RELATION,
        payload={"relation_id": str(relation.id), "reason": "single source"},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    await resolution.resolve(session, task, ReviewResolution(decision="accept"))

    refreshed = await session.get(Relation, relation.id)
    assert refreshed.human_verified is True
    assert refreshed.predicate == "friend_of"


@pytest.mark.asyncio
async def test_confirm_relation_change_predicate_updates_edge(session, project, book):
    from api.contracts.enums import RelationFamily

    alice = await _character(session, project, name="Alice")
    bob = await _character(session, project, name="Bob")
    relation = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="friend_of",
        family=RelationFamily.SOCIAL,
    )
    session.add(relation)
    await session.commit()
    await session.refresh(relation)

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CONFIRM_RELATION,
        payload={"relation_id": str(relation.id), "reason": "single source"},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    await resolution.resolve(
        session,
        task,
        ReviewResolution(
            decision="change_predicate", payload={"predicate": "enemy_of"}
        ),
    )

    refreshed = await session.get(Relation, relation.id)
    assert refreshed.predicate == "enemy_of"
    assert refreshed.family == RelationFamily.ADVERSARIAL
    assert refreshed.human_verified is True


@pytest.mark.asyncio
async def test_resolve_conflict_accept_supersedes_the_others(session, project, book):
    from api.contracts.enums import RelationFamily, RelationStatus

    alice = await _character(session, project, name="Alice")
    bob = await _character(session, project, name="Bob")
    friend = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="friend_of",
        family=RelationFamily.SOCIAL,
    )
    enemy = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="enemy_of",
        family=RelationFamily.ADVERSARIAL,
    )
    session.add_all([friend, enemy])
    await session.commit()
    await session.refresh(friend)
    await session.refresh(enemy)

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
    await session.refresh(task)

    await resolution.resolve(
        session,
        task,
        ReviewResolution(decision="accept", payload={"relation_id": str(friend.id)}),
    )

    winner = await session.get(Relation, friend.id)
    loser = await session.get(Relation, enemy.id)
    assert winner.status == RelationStatus.ACTIVE
    assert winner.human_verified is True
    assert loser.status == RelationStatus.SUPERSEDED
    assert loser.human_verified is True


@pytest.mark.asyncio
async def test_resolve_conflict_temporal_transition_chains_the_edges(
    session, project, book
):
    from api.contracts.enums import RelationFamily, RelationStatus

    alice = await _character(session, project, name="Alice")
    bob = await _character(session, project, name="Bob")
    friend = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="friend_of",
        family=RelationFamily.SOCIAL,
        first_book_order=1,
        first_chapter=2,
    )
    enemy = Relation(
        project_id=project.id,
        subject_character_id=alice.id,
        object_character_id=bob.id,
        predicate="enemy_of",
        family=RelationFamily.ADVERSARIAL,
        first_book_order=1,
        first_chapter=10,
    )
    session.add_all([friend, enemy])
    await session.commit()
    await session.refresh(friend)
    await session.refresh(enemy)

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
    await session.refresh(task)

    await resolution.resolve(
        session,
        task,
        ReviewResolution(
            decision="temporal_transition",
            payload={"order": [str(friend.id), str(enemy.id)]},
        ),
    )

    earlier = await session.get(Relation, friend.id)
    later = await session.get(Relation, enemy.id)
    assert earlier.status == RelationStatus.SUPERSEDED
    assert earlier.last_chapter == 10
    assert later.status == RelationStatus.ACTIVE
    assert earlier.human_verified is True
    assert later.human_verified is True


@pytest.mark.asyncio
async def test_resolving_an_already_resolved_task_is_a_noop(session, project, book):
    a = await _character(session, project, name="Catherine Earnshaw")
    b = await _character(session, project, name="Catherine Linton")
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": a.canonical_name, "name_b": b.canonical_name},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    first = await resolution.resolve(
        session, task, ReviewResolution(decision="keep_separate")
    )
    second = await resolution.resolve(
        session, task, ReviewResolution(decision="merge", payload={"primary_id": "x"})
    )

    assert first.status == ReviewStatus.RESOLVED
    assert second.status == ReviewStatus.RESOLVED
    # A second, contradictory decision on an already-resolved task must not
    # apply -- both characters survive, and exactly one feedback row exists.
    assert await session.get(Character, a.id) is not None
    assert await session.get(Character, b.id) is not None
    feedback = (
        await session.exec(
            select(CorrectionFeedback).where(
                CorrectionFeedback.review_task_id == task.id
            )
        )
    ).all()
    assert len(feedback) == 1


@pytest.mark.asyncio
async def test_classify_candidate_sets_kind(session, project, book):
    candidate = BookCharacterCandidate(
        book_id=book.id, surface_form="the Grange", kind=CandidateKind.UNKNOWN
    )
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)

    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.CLASSIFY_CANDIDATE,
        payload={
            "candidate_id": str(candidate.id),
            "surface_form": "the Grange",
            "book_id": str(book.id),
            "mention_count": 2,
            "contexts": [],
        },
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    await resolution.resolve(
        session, task, ReviewResolution(decision="classify", payload={"kind": "place"})
    )

    refreshed = await session.get(BookCharacterCandidate, candidate.id)
    assert refreshed.kind == CandidateKind.PLACE


@pytest.mark.asyncio
async def test_confirm_chapter_split_accept_marks_verified(session, project, book):
    chapter = Chapter(
        book_id=book.id,
        number=12,
        page_start=100,
        page_end=110,
        detection_method=DetectionMethod.REGEX,
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
            "preceding_text": "",
            "following_text": "",
        },
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    await resolution.resolve(session, task, ReviewResolution(decision="accept"))

    refreshed = await session.get(Chapter, chapter.id)
    assert refreshed.human_verified is True


@pytest.mark.asyncio
async def test_unknown_decision_raises(session, project, book):
    a = await _character(session, project, name="A")
    b = await _character(session, project, name="B")
    task = ReviewTask(
        project_id=project.id,
        book_id=book.id,
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        payload={"name_a": a.canonical_name, "name_b": b.canonical_name},
        priority=1,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    with pytest.raises(resolution.UnknownDecisionError):
        await resolution.resolve(session, task, ReviewResolution(decision="shrug"))
