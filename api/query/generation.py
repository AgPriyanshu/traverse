"""Answer rendering (S6.1-S6.4) and narrative generation/streaming (S6.5).

The five graph-derived classes never free-generate: their answer text is
assembled directly from a retrieved character record or ``RelationOut``, so
grounding is true by construction (``grounding.py``'s module docstring) and
every sentence carries a citation built from real evidence
(``citations.py``). Only ``narrative`` calls the model to compose prose, and
that prose is checked by ``grounding.ground_narrative_answer`` before it
reaches the caller.
"""

from collections.abc import AsyncIterator
from uuid import UUID

from langchain.messages import HumanMessage
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    CharacterDetailOut,
    CitationOut,
    MentionOut,
    RelationArcOut,
    RelationOut,
)
from ..contracts.enums import LLMPurpose
from ..llm import get_llm, semaphore
from ..llm.tracing import trace_generation
from . import citations, repository
from .grounding import GroundedAnswer, abstain

_MAX_MENTION_CITATIONS = 5
_MAX_AGGREGATION_RESULTS = 200


def _humanize(predicate: str) -> str:
    return predicate.replace("_", " ")


async def _relation_sentence(
    session: SQLModelAsyncSession, relation: RelationOut, *, top_n: int = 2
) -> tuple[str, list[CitationOut]]:
    """One cited sentence for a relation, hearsay-attributed when it applies."""
    evidence_rows = await repository.top_evidence_for_relation(
        session, relation.id, limit=top_n
    )
    citation_list: list[CitationOut] = []
    for row in evidence_rows:
        citation = await citations.build_citation_from_evidence(
            session,
            chunk_id=row.chunk_id,
            book_id=row.book_id,
            book_title=row.book_title,
            series_order=row.series_order,
            chapter_no=row.chapter_no,
            page_start=row.page_start,
            page_end=row.page_end,
            quote=row.quote,
        )
        citation_list.append(citation)

    verb = _humanize(relation.predicate)
    sentence = f"{relation.subject_name} is {verb} {relation.object_name}."

    if relation.hearsay:
        speaker = await repository.relation_speaker(session, relation.id)
        if speaker:
            sentence = (
                f"According to {speaker}, {relation.subject_name} is {verb} "
                f"{relation.object_name}."
            )

    return sentence, citation_list


async def render_character_lookup(
    character: CharacterDetailOut | None, mentions: list[MentionOut]
) -> GroundedAnswer:
    """Render a character-record answer with top mention passages cited.

    Args:
        character: The resolved character, or ``None`` when resolution found
            nobody by that name in this project — the abstention case.
        mentions: Top evidence passages for the character, page-ordered.
    """
    if character is None:
        return abstain("No character by that name is established in this project.")

    sentence = (
        f"{character.canonical_name} is a {character.importance_tier.value}-tier "
        f"character, mentioned {character.mention_count} times."
    )
    for attribute in character.attributes[:3]:
        sentence += f" {attribute.label.capitalize()}: {attribute.value}."

    citation_list: list[CitationOut] = []
    for mention in mentions[:_MAX_MENTION_CITATIONS]:
        if not mention.context:
            continue
        citation = CitationOut(
            book_id=mention.book_id,
            page_start=mention.page,
            page_end=mention.page,
            quote=mention.context,
            chunk_id=mention.chunk_id,
        )
        citation_list.append(citation)

    return GroundedAnswer(text=sentence, citations=citation_list, abstained=False)


async def render_relationship_lookup(
    session: SQLModelAsyncSession, relations: list[RelationOut]
) -> GroundedAnswer:
    """Render the direct edge(s) between two characters, or abstain."""
    if not relations:
        return abstain("No established relationship between them in this project.")

    sentences: list[str] = []
    citation_list: list[CitationOut] = []
    for relation in relations:
        sentence, relation_citations = await _relation_sentence(session, relation)
        sentences.append(sentence)
        citation_list.extend(relation_citations)

    return GroundedAnswer(
        text=" ".join(sentences), citations=citation_list, abstained=False
    )


async def render_path(
    session: SQLModelAsyncSession, hops: list[RelationOut]
) -> GroundedAnswer:
    """Render a shortest-path chain, one cited sentence per hop, or abstain."""
    if not hops:
        return abstain("No path connects them in this project's graph.")

    sentences: list[str] = []
    citation_list: list[CitationOut] = []
    for hop in hops:
        sentence, hop_citations = await _relation_sentence(session, hop)
        sentences.append(sentence)
        citation_list.extend(hop_citations)

    return GroundedAnswer(
        text=" ".join(sentences), citations=citation_list, abstained=False
    )


async def render_aggregation(
    session: SQLModelAsyncSession,
    *,
    anchor_name: str,
    predicate: str,
    relations: list[RelationOut],
    other_names: dict[UUID, str],
) -> GroundedAnswer:
    """Render an exhaustive set answer, every member cited, or abstain.

    Args:
        session: An open database session.
        anchor_name: The subject of the aggregation ("Mr Bennet").
        predicate: The ontology predicate the question was mapped to.
        relations: Every matching relation, already deduplicated by id.
        other_names: The other endpoint's canonical name, by character id —
            needed because a relation's ``subject``/``object`` naming depends
            on which direction it happened to be stored in, not on which side
            the anchor is.
    """
    if not relations:
        return abstain(
            f"No {_humanize(predicate)} relationship from {anchor_name} is "
            "established in this project."
        )

    names = sorted(other_names.values())
    sentence = (
        f"{anchor_name} has {len(names)} established "
        f"{_humanize(predicate)} relationship(s): {', '.join(names)}."
    )

    citation_list: list[CitationOut] = []
    for relation in relations[:_MAX_AGGREGATION_RESULTS]:
        _sentence, relation_citations = await _relation_sentence(
            session, relation, top_n=1
        )
        citation_list.extend(relation_citations)

    return GroundedAnswer(text=sentence, citations=citation_list, abstained=False)


async def render_series_arc(
    session: SQLModelAsyncSession, arc: RelationArcOut
) -> GroundedAnswer:
    """Render a relationship's states over series position, in order, or abstain."""
    if not arc.states:
        return abstain("No established relationship between them in this project.")

    sentences: list[str] = []
    citation_list: list[CitationOut] = []
    for state in arc.states:
        sentence, state_citations = await _relation_sentence(session, state, top_n=1)
        book_note = (
            f" (from book {state.first_book_order})" if state.first_book_order else ""
        )
        sentences.append(f"{sentence}{book_note}")
        citation_list.extend(state_citations)

    return GroundedAnswer(
        text=" ".join(sentences), citations=citation_list, abstained=False
    )


_NARRATIVE_PROMPT = """Answer the question using ONLY the passages below. If \
the passages do not establish an answer, say so plainly rather than \
guessing. Write plain prose, no citation markers, no preamble.

Passages:
{passages}

Question: {question}

Answer:"""


def _build_narrative_prompt(question: str, chunks: list) -> str:
    passages = "\n\n".join(f"({i + 1}) {chunk.text}" for i, chunk in enumerate(chunks))
    prompt = _NARRATIVE_PROMPT.format(passages=passages, question=question)

    return prompt


async def stream_narrative_draft(
    question: str, chunks: list, *, project_id: str
) -> AsyncIterator[str]:
    """Stream a free-text draft answer from the retrieved chunks alone.

    The draft is unverified — the caller runs it through
    ``grounding.ground_narrative_answer`` before it reaches the user. Traced
    like ``structured_call`` (purpose, book_id, stage), but not built on it:
    this is plain streaming text, not a schema-validated reply.

    Args:
        question: The user's question.
        chunks: Retrieved chunks to answer from, in ranked order.
        project_id: Tags the Langfuse trace.

    Yields:
        Text deltas as they arrive from the model.
    """
    if not chunks:
        return

    prompt = _build_narrative_prompt(question, chunks)
    model = get_llm(LLMPurpose.ANSWER)

    async with semaphore():
        with trace_generation(
            purpose=LLMPurpose.ANSWER.value,
            model=getattr(model, "model_name", "unknown"),
            book_id=project_id,
            stage="narrative_generate",
        ) as generation:
            pieces: list[str] = []
            async for chunk in model.astream([HumanMessage(prompt)]):
                text = getattr(chunk, "content", "") or ""
                if text:
                    pieces.append(text)
                    yield text

            if generation is not None:
                generation.update(output="".join(pieces))
