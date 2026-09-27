import uuid

from api.db.models import Character
from api.query.gender import infer_gender


def _character(canonical_name: str, aliases: list[str] | None = None) -> Character:
    return Character(
        project_id=uuid.uuid4(), canonical_name=canonical_name, aliases=aliases or []
    )


def test_infers_female_from_honorific_alias():
    character = _character("Elizabeth Bennet", aliases=["Miss Bennet", "Lizzy"])
    assert infer_gender(character) == "female"


def test_infers_male_from_honorific_alias():
    character = _character("Mr Bennet", aliases=["Bennet"])
    assert infer_gender(character) == "male"


def test_no_signal_returns_none():
    character = _character("Anne", aliases=["Annie"])
    assert infer_gender(character) is None
