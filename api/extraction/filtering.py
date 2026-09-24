import re

from .normalization import strip_honorifics

_PRONOUN_WORDS = """
    i me my mine myself we us our ours ourselves you your yours yourself
    yourselves he him his himself she her hers herself it its itself they them
    their theirs themselves one ones someone somebody anyone anybody everyone
    everybody nobody none either neither both each all any some other others
    another who whom whose which what that this these those there here the a an
    and or but madam sir sister brother mother father mamma papa people person
    persons girl girls boy boys man men woman women lady gentleman gentlemen
    ladies servant servants children child family friends friend nephew niece
    uncle aunt cousin husband wife son daughter master mistress
"""
_DETERMINERS = """
    the a an my his her their our your its this that these those some any one
    either both another whose each every
"""
_PARTICLES = "de la le von van der den di du of del da"
PRONOUNS_AND_FUNCTION_WORDS = frozenset(_PRONOUN_WORDS.split())
_LEADING_DETERMINERS = frozenset(_DETERMINERS.split())
_NAME_PARTICLES = frozenset(_PARTICLES.split())
_ALPHA_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def plausible_character_name(surface_form: str) -> bool:
    """Whether a surface form can name one individual rather than a pronoun or role.

    Deterministic and deliberately conservative: it only rejects what can
    never be a proper name ("she", "my brother Gardiner", "the housekeeper",
    "Mr.", "Mr. and Mrs. Gardiner"). Whether a proper name is a *character*
    (an author, a place) is a model call's job.

    Args:
        surface_form: The expression exactly as pass 1 recorded it.

    Returns:
        ``False`` for a pronoun, determiner phrase, bare title, group or
        fragment; ``True`` otherwise.
    """
    cleaned = surface_form.strip().strip("_*'\"‘’“”")
    tokens = cleaned.replace(",", " , ").split()

    if not tokens or "," in tokens or len(cleaned) < 2:
        return False

    lowered = [token.lower().strip("._") for token in tokens]

    if lowered[0] in _LEADING_DETERMINERS or lowered[0] in {"either", "both"}:
        return False

    if "and" in lowered or "or" in lowered:
        return False

    if not _ALPHA_RE.search(cleaned):
        return False

    if not strip_honorifics(cleaned):
        return False

    core = strip_honorifics(cleaned).split()
    if len(core) == 1 and core[0] in PRONOUNS_AND_FUNCTION_WORDS:
        return False

    if len(tokens) == 1:
        return True

    for token in tokens:
        bare = token.strip("._'’")
        if not bare or bare.lower() in _NAME_PARTICLES:
            continue

        if not bare[0].isupper():
            return False

    return True
