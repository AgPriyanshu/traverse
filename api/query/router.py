"""Query routing (S6.1).

One structured call returns the query class *and* the entity phrases in one
shot — a second entity-extraction pass would double latency on the critical
path (``plans/sprint-6/backend-2.md``). The phrases are literal text lifted
from the question ("Lizzy", "her sister"), never resolved IDs: resolution
happens afterwards, against ``api.extraction.resolution.resolve_names``
(be1, S6.7), which is the only place a name is allowed to turn into a
character id.

``LLMPurpose`` has no dedicated routing entry yet (SCR-2,
``plans/sprint-6/SCR.md``) — ``ADJUDICATE`` is reused as the interim purpose
since both are "pick one of a declared set of discrete outcomes" calls; this
is a stopgap, not a design choice, and should be replaced with a dedicated
purpose at the next contract freeze so routing's cost and latency stop being
folded into adjudication's numbers on the ops dashboard.
"""

from pydantic import BaseModel, Field

from ..contracts.enums import LLMPurpose, QueryRoute
from ..llm import structured_call

# PRD F4.1 names six classes; ``QueryRoute`` (frozen, api/contracts/enums.py)
# adds a seventh, ``series_arc``, for the series-arc work Sprint 5 built
# (``GET /relations/arc``) — the router targets the frozen enum, not the PRD
# table verbatim, since the enum is what every downstream consumer compiles
# against.
_CLASS_GUIDE = """
- character_lookup: asking who someone is, or for a profile/summary of them.
  Example: "Who is Mr Collins?"
- relationship_lookup: asking how two named people are related, directly.
  Example: "How does Elizabeth know Mr Darcy?"
- path: asking how two named people are connected, possibly indirectly, or
  through a chain of relationships.
  Example: "How are Heathcliff and young Cathy connected?"
- aggregation: asking for a complete set of people fitting a relationship to
  one named anchor ("all of", "who are", "list").
  Example: "Who are all of Mr Bennet's daughters?"
- series_arc: asking how a relationship between two named people changed over
  the course of the series/book.
  Example: "How did Anne and Gilbert's relationship change?"
- narrative: asking about events, motives, or "why"/"what happened" questions
  that are not resolved by a direct graph fact.
  Example: "Why did they fall out?"
- ambiguous: the question does not name enough to resolve on its own, or its
  subject depends on a previous turn with nothing to anchor to
  ("What happens to her?" with no antecedent).
""".strip()

_PROMPT_TEMPLATE = """You are a router for a novel question-answering system \
backed by a character relationship graph. Classify the question into exactly \
one of these classes:

{class_guide}

Also extract, verbatim from the question text, whichever of these apply:
- subject_phrase: the first or only named person/reference the question is
  about (a name, nickname, or a relative reference like "her sister").
- object_phrase: the second named person, only for relationship_lookup, path,
  or series_arc questions that name two people.
- predicate_hint: the relationship word the question uses, only for
  aggregation questions (e.g. "daughters", "friends", "enemies").

Leave a field null rather than guessing when the question does not supply it.

Question: {question}
"""


class RouterOutput(BaseModel):
    """The router's one structured call: class plus literal entity phrases."""

    route: QueryRoute
    subject_phrase: str | None = Field(
        default=None, description="Verbatim phrase naming the question's subject."
    )
    object_phrase: str | None = Field(
        default=None, description="Verbatim phrase naming a second person, if any."
    )
    predicate_hint: str | None = Field(
        default=None, description="Verbatim relationship word, for aggregation."
    )


async def classify_question(question: str, *, project_id: str) -> RouterOutput:
    """Classify a question and extract its entity phrases in one LLM call.

    Args:
        question: The user's question, verbatim.
        project_id: Tags the Langfuse trace.

    Returns:
        The predicted route and whichever entity phrases the question named.
    """
    prompt = _PROMPT_TEMPLATE.format(class_guide=_CLASS_GUIDE, question=question)
    result = await structured_call(
        prompt,
        RouterOutput,
        purpose=LLMPurpose.ADJUDICATE,
        book_id=project_id,
        stage="query_route",
    )

    return result
