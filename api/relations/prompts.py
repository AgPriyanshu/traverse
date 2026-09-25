# ruff: noqa: E501
from ..graph import ontology

# Everything above the ``CHUNK_TEMPLATE`` marker is the stable prefix. vLLM
# prefix caching only pays off when it is byte-identical across every call for
# a book, so nothing chunk-specific may appear before it.
PREFIX_TEMPLATE = """You extract relationships between named characters from a novel passage.

ALLOWED PREDICATES (use exactly these names, each is written subject -> object):
{ontology}

CHARACTER ROSTER (the only characters that may appear as subject or object):
{roster}

RULES
- Write subject and object using a roster name or alias exactly as listed. Never name anyone who is not on the roster.
- Extract only a relationship the passage states or clearly implies. Two characters talking, meeting or standing in the same room is NOT a relationship.
- Never join two characters with an ellipsis or list every pair of characters who appear together; a quote is one unbroken stretch of the passage.
- Do not extract a relationship from a character's name, title or description alone. Kinship and marriage predicates need the passage to say so (mother, sister, wife, married, and so on).
- Prefer the most specific predicate. Use acquaintance_of only when the passage says they are acquainted.
- Direction matters: parent_of means the subject is the parent of the object.
- "quote" must name at least one of the two characters (by name or alias) and be copied verbatim from the passage, at most 300 characters, and must be the words that establish the relationship.
- assertion_type is "narrated" when the narrator states it, "dialogue" when a character says it inside quotation marks, "inferred" when it is only implied.
- For dialogue, put the speaker's roster name in asserted_by; otherwise leave it null.
- confidence is your certainty from 0 to 1.
- If the passage establishes no relationship, return an empty list.

EXAMPLES
Passage: "Anna Verrin took her daughter Mira by the hand and led her into the hall."
{{"relations": [{{"subject": "Anna Verrin", "predicate": "parent_of", "object": "Mira Verrin", "assertion_type": "narrated", "asserted_by": null, "quote": "Anna Verrin took her daughter Mira by the hand", "confidence": 0.95}}]}}

Passage: "\\"Tobias is no friend of mine,\\" said Mira. \\"He is my father's rival.\\""
{{"relations": [{{"subject": "Tobias Hale", "predicate": "rival_of", "object": "Anna Verrin", "assertion_type": "dialogue", "asserted_by": "Mira Verrin", "quote": "He is my father's rival.", "confidence": 0.6}}]}}

Passage: "The rain kept falling and nobody spoke."
{{"relations": []}}

Respond with JSON only.
"""

CHUNK_TEMPLATE = """
--- PASSAGE ---
Chapter {chapter} - pages {page_start}-{page_end}
{text}
--- END PASSAGE ---
"""


def build_prefix(roster_block: str) -> str:
    """Render the stable prefix from the ontology and a rendered roster.

    Args:
        roster_block: Output of ``Roster.prompt_block``.
    """
    prefix = PREFIX_TEMPLATE.format(
        ontology=ontology.ONTOLOGY.prompt_fragment(), roster=roster_block
    )

    return prefix


def build_prompt(
    prefix: str, *, chapter: int | None, page_start: int, page_end: int, text: str
) -> str:
    """Append the variable, chunk-specific tail to the stable prefix."""
    tail = CHUNK_TEMPLATE.format(
        chapter=chapter if chapter is not None else "?",
        page_start=page_start,
        page_end=page_end,
        text=text,
    )
    prompt = prefix + tail

    return prompt
