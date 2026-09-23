"""Prompt templates for the extraction package's structured LLM calls."""

MENTION_SWEEP_PROMPT = """You are reading a novel to build a character roster.

For each numbered passage below, list every distinct referring expression
that could name a character: proper names, honorific forms ("Mr. Darcy"),
epithets ("the old woman in the white dress"), and role labels ("the
housekeeper"). Do NOT list bare pronouns (he, she, they). Do NOT list places,
houses, estates, organisations, ships, or deities invoked in an oath — list
those too if you are unsure, and let a later step decide; do not silently
omit anything referring to an entity.

If the same expression appears more than once in one passage, list it only
once for that passage.

For each expression, give:
- "surface_form": the expression exactly as it appears
- "kind": your best guess — "person", "place", "organisation", or "unknown"
- "context": the sentence the expression appears in, plus the sentence
  immediately before it if there is one

Passages:
{passages}

Reply with one entry per passage number that contains at least one mention,
using "chunk_index" for the passage's number.
"""

REJECTION_PROMPT = """Decide whether "{surface_form}" names a person (a character
in the story) or something else — a place, house, estate, organisation, ship,
or a deity/figure invoked only in an oath or expression ("Providence",
"Heaven").

Some names are ambiguous: a house or estate can share its name with the
family that owns it ("the Bennets of Longbourn"). If the contexts below show
the expression used BOTH ways, classify it as "person" and set
"is_ambiguous" to true — a person mention must never be discarded because the
same word also names a place.

Contexts where "{surface_form}" appears:
{contexts}

Reply with "kind" (one of "person", "place", "organisation", "unknown"),
"reason" (one sentence), and "is_ambiguous".
"""

ADJUDICATION_PROMPT = """Two names were found in the same novel. Decide whether
they refer to the SAME character or two DIFFERENT characters.

Name A: "{name_a}"
Contexts for A:
{contexts_a}

Name B: "{name_b}"
Contexts for B:
{contexts_b}

Watch for evidence that they are different people even though the names look
related: both names appearing as distinct participants in one scene,
generational markers ("young", "the elder", "her mother's name was"),
statements that one is the other's parent/child, or one appearing to die
before the other is introduced. Any of these means DIFFERENT characters.

Reply with "same_person" (true/false), "confidence" (0.0-1.0), and "reason".
"""

ATTRIBUTE_PROMPT = """Extract factual attributes of the character "{name}" from
the passages below — occupation, age, family role (e.g. "eldest daughter",
"housekeeper"), and physical description. Only extract what these passages
state or clearly imply; do not invent anything.

For each attribute, give "key" (a short label), "value", the "page" the
passage is from, and the "quote" that supports it verbatim from that passage.
Skip anything you cannot point to a specific page for.

Passages, each tagged with its page number:
{passages}
"""
