from ..db.models import Character
from ..extraction.normalization import gendered_title

_MALE_TITLES = frozenset({"mr", "sir", "lord", "master"})
_FEMALE_TITLES = frozenset({"mrs", "miss", "ms", "lady", "madam"})


def infer_gender(character: Character) -> str | None:
    """Infer a character's gender from any honorific-titled alias on record.

    Returns:
        ``"male"``, ``"female"``, or ``None`` when no alias carries a
        gendered title.
    """
    for form in (character.canonical_name, *character.aliases):
        title = gendered_title(form)
        if title in _MALE_TITLES:
            return "male"
        if title in _FEMALE_TITLES:
            return "female"

    return None
