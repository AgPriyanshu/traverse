import uuid

from api.db.models import DocumentChunk
from api.pipeline.scene_repository import SceneRow
from api.relations.scenes import build_reading_chunks

BOOK = uuid.uuid4()
A, B = uuid.uuid4(), uuid.uuid4()


def make_chunk(text: str, page: int) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(),
        book_id=BOOK,
        text=text,
        pages=[page],
        page_start=page,
        page_end=page,
    )


def test_a_pronoun_only_chunk_is_merged_into_a_qualifying_scene_and_kept():
    named = make_chunk("Darcy spoke to Elizabeth.", 10)
    pronoun_only = make_chunk("He had liberality, and he had the means of it.", 10)
    scene = SceneRow(
        id=uuid.uuid4(),
        chapter_id=None,
        page_start=10,
        page_end=10,
        chunk_ids=[named.id, pronoun_only.id],
        participants={A: 1, B: 1},
    )
    chunks = [(named, 5), (pronoun_only, 5)]

    units, mentions, members = build_reading_chunks(chunks, [scene])

    assert len(units) == 1
    unit, chapter = units[0]
    assert unit.id == named.id
    assert chapter == 5
    assert "Darcy spoke to Elizabeth." in unit.text
    assert "He had liberality" in unit.text
    assert mentions[named.id] == 2
    assert set(members[named.id]) == {named.id, pronoun_only.id}


def test_a_single_participant_scene_is_not_promoted_by_merging():
    lone = make_chunk("Lydia was mentioned once.", 205)
    fragment = make_chunk("and he had the means of exercising it.", 205)
    scene = SceneRow(
        id=uuid.uuid4(),
        chapter_id=None,
        page_start=205,
        page_end=205,
        chunk_ids=[lone.id, fragment.id],
        participants={A: 1},
    )
    chunks = [(lone, 47), (fragment, 47)]

    units, mentions, _ = build_reading_chunks(chunks, [scene])

    assert len(units) == 1
    assert mentions[lone.id] == 1


def test_a_chunk_with_no_scene_falls_back_to_a_singleton_with_unknown_mentions():
    orphan = make_chunk("An unassigned chunk.", 1)

    units, mentions, members = build_reading_chunks([(orphan, None)], [])

    assert units == [(orphan, None)]
    assert mentions[orphan.id] == -1
    assert members[orphan.id] == (orphan.id,)


def test_scene_member_order_and_page_span_are_preserved():
    first = make_chunk("Elizabeth walked in.", 10)
    second = make_chunk("Darcy followed her.", 11)
    scene = SceneRow(
        id=uuid.uuid4(),
        chapter_id=None,
        page_start=10,
        page_end=11,
        chunk_ids=[first.id, second.id],
        participants={A: 1, B: 1},
    )

    units, _, _ = build_reading_chunks([(first, 1), (second, 1)], [scene])

    unit, _ = units[0]
    assert unit.text.index("Elizabeth walked in.") < unit.text.index(
        "Darcy followed her."
    )
    assert unit.page_start == 10 and unit.page_end == 11
