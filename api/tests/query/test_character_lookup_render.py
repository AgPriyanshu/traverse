from uuid import uuid4

from api.contracts.api import AttributeOut, CharacterDetailOut
from api.contracts.enums import ImportanceTier
from api.query import generation
from api.query.scope import ReadingScope


def _character(**overrides) -> CharacterDetailOut:
    fields = {
        "id": uuid4(),
        "project_id": uuid4(),
        "canonical_name": "Kazu Tokita",
        "aliases": ["Kazu Tokita", "Kazu", "Miss Tokita"],
        "importance_tier": ImportanceTier.PROTAGONIST,
        "mention_count": 54,
        "first_page": 12,
        "first_chapter": 1,
        "attributes": [
            AttributeOut(label="family_role", value="cousin", page=12),
            AttributeOut(label="occupation", value="waitress", page=13),
        ],
    }
    fields.update(overrides)

    return CharacterDetailOut(**fields)


async def test_character_answer_describes_aliases_first_appearance_and_details():
    answer = await generation.render_character_lookup(
        None,  # type: ignore[arg-type] -- no relations, so no session is used
        _character(),
        [],
        [],
        scope=ReadingScope.unlimited(),
    )

    assert answer.abstained is False
    assert "also called Kazu, Miss Tokita" in answer.text
    assert "first appearing in chapter 1 (page 12)" in answer.text
    assert "family role: cousin" in answer.text
    assert "family_role" not in answer.text


async def test_character_answer_abstains_for_an_unknown_character():
    answer = await generation.render_character_lookup(
        None,  # type: ignore[arg-type]
        None,
        [],
        [],
        scope=ReadingScope.unlimited(),
    )

    assert answer.abstained is True


def test_context_snippet_falls_back_to_the_surface_form_then_the_chunk_opening():
    from api.graph.repository import _context_snippet

    text = "It was late. Kazu poured the coffee before it could go cold."

    located = _context_snippet(text, None, None, surface_form="Kazu", pad=5)
    opening = _context_snippet(text, None, None, surface_form="Nobody", pad=5)
    recorded = _context_snippet(text, 13, 17, surface_form="Kazu", pad=2)

    assert located is not None and "Kazu" in located
    assert opening == text[:10].strip()
    assert recorded == text[11:19]
    assert _context_snippet("", None, None) is None
