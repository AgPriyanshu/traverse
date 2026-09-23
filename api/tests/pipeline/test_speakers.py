from uuid import UUID, uuid4

from api.pipeline import speakers

ELIZABETH, JANE, DARCY = uuid4(), uuid4(), uuid4()
FORMS = {
    ELIZABETH: ["Elizabeth Bennet", "Elizabeth", "Lizzy"],
    JANE: ["Jane Bennet", "Jane"],
    DARCY: ["Mr. Darcy", "Darcy"],
}


def _attribute(
    text: str, participants: list[UUID], present: list[UUID] | None = None
) -> list[speakers.Line]:
    chunk_id = uuid4()
    cast = present if present is not None else participants
    matcher = speakers.build_matcher({cid: FORMS[cid] for cid in cast})
    scene = speakers.SceneText(
        chunk_ids=[chunk_id],
        chunk_texts={chunk_id: text},
        participants={cid: 1 for cid in participants},
    )
    _, lines = speakers.attribute_scene(scene, {chunk_id: matcher})

    return lines


def test_finds_curly_and_straight_quotes() -> None:
    text = 'She said “Hello there.” And he said "Good day."'

    assert len(speakers.find_quotes(text)) == 2


def test_ignores_a_quote_with_no_words() -> None:
    assert speakers.find_quotes('the sign read "!"') == []


def test_explicit_tag_after_the_quote() -> None:
    lines = _attribute(
        "“I am not.” said Elizabeth, looking at Jane.",
        [ELIZABETH, JANE],
    )

    assert (lines[0].speaker, lines[0].method) == (ELIZABETH, speakers.EXPLICIT_TAG)


def test_explicit_tag_before_the_quote_with_honorific() -> None:
    lines = _attribute('Then replied Mr. Darcy, "You mistake me."', [ELIZABETH, DARCY])

    assert (lines[0].speaker, lines[0].method) == (DARCY, speakers.EXPLICIT_TAG)


def test_a_tag_naming_the_addressee_does_not_pick_the_addressee() -> None:
    lines = _attribute('Elizabeth said to Jane, "It is late."', [ELIZABETH, JANE])

    assert lines[0].speaker == ELIZABETH


def test_address_inside_the_quote_is_not_the_speaker() -> None:
    lines = _attribute(
        '"Come here, Jane," she whispered. Elizabeth waited.', [ELIZABETH, JANE]
    )

    assert lines[0].speaker == ELIZABETH
    assert lines[0].method == speakers.NARRATION


def test_narration_from_the_paragraph_before() -> None:
    lines = _attribute(
        "Darcy turned to the window.\n“It is settled.”",
        [DARCY, JANE],
        present=[DARCY],
    )

    assert (lines[0].speaker, lines[0].method) == (DARCY, speakers.NARRATION)


def test_two_names_in_narration_are_not_guessed() -> None:
    lines = _attribute('"Yes." Jane looked at Elizabeth.', [ELIZABETH, JANE, DARCY])

    assert lines[0].speaker is None


def test_alternation_in_a_two_party_scene() -> None:
    text = '"Do you dance?" said Elizabeth.\n"Never."\n"Why not?"\n"I dislike it."'

    lines = _attribute(text, [ELIZABETH, DARCY], present=[ELIZABETH])

    assert [line.speaker for line in lines] == [ELIZABETH, DARCY, ELIZABETH, DARCY]
    assert lines[1].method == speakers.ALTERNATION


def test_alternation_stops_after_the_run_cap() -> None:
    text = '"Start," said Elizabeth.\n' + "\n".join('"Line."' for _ in range(12))

    lines = _attribute(text, [ELIZABETH, DARCY], present=[ELIZABETH])

    assert lines[-1].speaker is None


def test_no_alternation_when_the_scene_has_three_speakers() -> None:
    text = '"Yes," said Elizabeth.\n"No."'

    lines = _attribute(text, [ELIZABETH, JANE, DARCY], present=[ELIZABETH])

    assert lines[1].speaker is None


def test_two_spans_in_one_paragraph_share_a_speaker() -> None:
    lines = _attribute(
        '"I cannot," said Elizabeth, "and I will not."', [ELIZABETH, JANE]
    )

    assert [line.speaker for line in lines] == [ELIZABETH, ELIZABETH]


def test_ambiguous_form_is_dropped_by_the_matcher() -> None:
    a, b = uuid4(), uuid4()
    matcher = speakers.build_matcher({a: ["Catherine"], b: ["Catherine", "Linton"]})

    mentions = speakers.find_mentions("Catherine met Linton.", matcher)

    assert [m.character_id for m in mentions] == [b]


def test_unresolved_rows_store_a_null_speaker() -> None:
    line = speakers.Line(0, uuid4(), 0, 5)

    (row,) = speakers.to_rows([line])

    assert row.speaker_character_id is None
    assert row.method == speakers.UNRESOLVED
