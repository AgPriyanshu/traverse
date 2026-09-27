"""Best-effort gender inference from honorific aliases, for gendered aggregation.

The ontology (``api/graph/ontology.yaml``) has no gender attribute — it is
about relationships, not demographics — so a gendered aggregation hint
("daughters", "brother") has nothing authoritative to filter against. This
reuses the honorific table Sprint 3's alias cascade already built
(:func:`api.extraction.normalization.gendered_title`, distinguishing "Mr.
Darcy" from "Miss Darcy") as the only gender signal available, rather than
inventing a second one.

**Known limitation:** a character with no honorific-titled alias on record
has no signal and is therefore excluded from a gendered aggregation query
(see ``templates.AGGREGATION_HINT_GENDER``) — an under-inclusive answer that
abstains rather than one that risks stating the wrong gender as fact.
"""

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
