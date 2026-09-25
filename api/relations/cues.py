import re

_KINSHIP_CORE = (
    r"mother|father|daughter|son\b|child|children|parent|papa|mamma|mama|"
    r"grand|born|offspring|heir"
)
_MARRIAGE = r"wife|husband|married|marry|marriage|wedding|wedded|bride|spouse|widow"

# A quote that carries none of a predicate's cue words cannot establish it.
# Qwen3-8B attaches high-stakes predicates (parent_of, married_to) to pairs
# that merely share a sentence, and one such edge is a false family fact in the
# graph; the cue check trades some recall on unusual phrasings for precision.
_CUES: dict[str, str] = {
    "parent_of": _KINSHIP_CORE,
    "child_of": _KINSHIP_CORE,
    "grandparent_of": r"grand",
    "grandchild_of": r"grand",
    "sibling_of": r"sister|brother|sibling|twin",
    "in_law_of": r"in-law|sister|brother|mother|father|son\b|daughter",
    "guardian_of": r"guardian|ward\b|charge|protector|trustee",
    "ward_of": r"guardian|ward\b|charge|protector|trustee",
    "adopted_by": r"adopt",
    "adoptive_parent_of": r"adopt",
    "married_to": _MARRIAGE,
    "engaged_to": r"engage|betroth|proposal|proposed|accept|offer|marry|marriage",
    "lover_of": r"love|loved|affection|attach|passion|devot|fond|admir|adore",
    "former_partner_of": r"former|formerly|once|widow|separated|divorc|jilt",
    "unrequited_love_for": r"love|loved|affection|admir|passion|attract|adore|fond",
    "friend_of": r"friend|intima|companion|confid|esteem",
    "acquaintance_of": r"acquaint|introduc|known|met\b|meeting|visit|call",
    "neighbour_of": r"neighbo|near|resid|live|lives|estate",
    "enemy_of": r"enem|hate|hatred|detest|hostil|quarrel|revenge|malice|dislike",
    "rival_of": r"rival|compet|contest|jealous|dislike|prefer",
    "betrayed": r"betray|deceiv|treacher|false|desert",
    "betrayed_by": r"betray|deceiv|treacher|false|desert",
    "deceives": r"deceiv|lie\b|lied|false|trick|impos|cheat",
    "deceived_by": r"deceiv|lie\b|lied|false|trick|impos|cheat",
    "customer_of": r"customer|shop|buy|bought|purchas|trade|custom\b|patron",
    "serves": r"serve|servant|attend|waited on|butler|maid|footman",
    "employer_of": r"employ|hire|servant|steward|master|mistress|patron|living",
    "employee_of": r"employ|hire|servant|steward|master|mistress|patron|living",
    "mentor_of": r"teach|tutor|mentor|master|instruct|govern|educat",
    "student_of": r"teach|tutor|mentor|master|instruct|govern|educat|pupil",
}

_COMPILED = {
    name: re.compile(rf"(?<!\w)(?:{pattern})", re.IGNORECASE)
    for name, pattern in _CUES.items()
}


def has_cue(predicate: str, quote: str) -> bool:
    """Return whether ``quote`` contains a cue word for ``predicate``.

    Predicates without a cue list are unconstrained.
    """
    pattern = _COMPILED.get(predicate)
    present = pattern is None or bool(pattern.search(quote))

    return present
