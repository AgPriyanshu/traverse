from collections import Counter
from uuid import UUID, uuid4

from api.pipeline.scenes import SceneChunk, segment_scenes

ELIZABETH, JANE, DARCY, BINGLEY = (uuid4() for _ in range(4))


def _chunk(text: str, cast: list[UUID], chapter: UUID | None = None) -> SceneChunk:
    return SceneChunk(
        chunk_id=uuid4(),
        chapter_id=chapter,
        page_start=1,
        page_end=1,
        text=text,
        characters=Counter(cast),
    )


def test_every_chunk_lands_in_exactly_one_scene() -> None:
    chunks = [_chunk("a", [ELIZABETH]) for _ in range(7)]

    scenes = segment_scenes(chunks)

    covered = [chunk_id for scene in scenes for chunk_id in scene.chunk_ids]
    assert covered == [chunk.chunk_id for chunk in chunks]


def test_a_dinkus_opens_a_new_scene() -> None:
    chunks = [
        _chunk("one", [ELIZABETH]),
        _chunk("two", [ELIZABETH]),
        _chunk("* * *\nthree", [ELIZABETH]),
    ]

    scenes = segment_scenes(chunks)

    assert [len(scene.chunk_ids) for scene in scenes] == [2, 1]


def test_a_chapter_change_always_cuts() -> None:
    first, second = uuid4(), uuid4()
    chunks = [_chunk("a", [ELIZABETH], first), _chunk("b", [ELIZABETH], second)]

    assert len(segment_scenes(chunks)) == 2


def test_a_wholly_new_cast_cuts_after_the_minimum_run() -> None:
    chunks = [
        _chunk("a", [ELIZABETH, JANE]),
        _chunk("b", [ELIZABETH]),
        _chunk("c", [DARCY, BINGLEY]),
    ]

    scenes = segment_scenes(chunks)

    assert [len(scene.chunk_ids) for scene in scenes] == [2, 1]
    assert set(scenes[1].participants) == {DARCY, BINGLEY}


def test_a_shared_character_keeps_the_scene_together() -> None:
    chunks = [
        _chunk("a", [ELIZABETH]),
        _chunk("b", [ELIZABETH]),
        _chunk("c", [ELIZABETH, DARCY]),
    ]

    assert len(segment_scenes(chunks)) == 1


def test_the_size_cap_cuts_a_long_run() -> None:
    chunks = [_chunk("a", [ELIZABETH]) for _ in range(30)]

    scenes = segment_scenes(chunks)

    assert max(len(scene.chunk_ids) for scene in scenes) <= 12


def test_participants_sum_mentions_across_the_scene() -> None:
    chunks = [_chunk("a", [ELIZABETH, ELIZABETH]), _chunk("b", [ELIZABETH])]

    (scene,) = segment_scenes(chunks)

    assert scene.participants[ELIZABETH] == 3


def test_empty_book_has_no_scenes() -> None:
    assert segment_scenes([]) == []
