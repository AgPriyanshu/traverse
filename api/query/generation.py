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
from ..contracts.enums import InferenceMode, LLMPurpose
from ..llm import get_llm, semaphore
from ..llm.tracing import trace_generation
from . import citations, repository
from .grounding import GroundedAnswer, abstain
from .scope import ReadingScope

_MAX_MENTION_CITATIONS = 5
_MAX_CHARACTER_RELATIONS = 5
_MAX_AGGREGATION_RESULTS = 200


def _humanize(predicate: str) -> str:
    return predicate.replace("_", " ")


async def _relation_sentence(
    session: SQLModelAsyncSession,
    relation: RelationOut,
    *,
    scope: ReadingScope,
    top_n: int = 2,
) -> tuple[str, list[CitationOut]]:
    """One cited sentence for a relation, hearsay-attributed when it applies."""
    evidence_rows = await repository.top_evidence_for_relation(
        session, relation.id, scope=scope, limit=top_n
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
    session: SQLModelAsyncSession,
    character: CharacterDetailOut | None,
    mentions: list[MentionOut],
    relations: list[RelationOut],
    *,
    scope: ReadingScope,
) -> GroundedAnswer:
    """Render a descriptive character answer, every claim from the record.

    Assembled, never free-generated: aliases, first appearance, attributes and
    the strongest visible relationships all come straight from stored rows, so
    grounding is true by construction; relationship sentences carry their own
    evidence citations, the rest cite top mention passages.

    Args:
        session: An open database session, for relationship evidence.
        character: The resolved character, or ``None`` when resolution found
            nobody by that name in this project — the abstention case.
        mentions: Top evidence passages for the character, page-ordered.
        relations: Visible relations touching the character, strongest first.
        scope: The reader's position, so each relation's cited evidence stays
            inside it.
    """
    if character is None:
        return abstain("No character by that name is established in this project.")

    name = character.canonical_name
    other_names = [a for a in character.aliases if a != name][:4]
    opening = f"{name}"
    if other_names:
        opening += f" (also called {', '.join(other_names)})"
    opening += (
        f" is a {character.importance_tier.value} character, mentioned "
        f"{character.mention_count} times"
    )
    if character.first_chapter is not None and character.first_page is not None:
        opening += (
            f", first appearing in chapter {character.first_chapter} "
            f"(page {character.first_page})"
        )
    parts = [opening + "."]

    facts = [
        f"{_humanize(a.label)}: {a.value}" for a in character.attributes[:4] if a.value
    ]
    if facts:
        parts.append("Recorded details: " + "; ".join(facts) + ".")

    citation_list: list[CitationOut] = []
    relation_sentences: list[str] = []
    for relation in relations[:_MAX_CHARACTER_RELATIONS]:
        sentence, relation_citations = await _relation_sentence(
            session, relation, scope=scope, top_n=1
        )
        relation_sentences.append(sentence)
        citation_list.extend(relation_citations)
    if relation_sentences:
        parts.append("Relationships: " + " ".join(relation_sentences))

    seen_chunks = {c.chunk_id for c in citation_list if c.chunk_id}
    for mention in mentions[:_MAX_MENTION_CITATIONS]:
        if not mention.context or mention.chunk_id in seen_chunks:
            continue
        seen_chunks.add(mention.chunk_id)
        citation = CitationOut(
            book_id=mention.book_id,
            page_start=mention.page,
            page_end=mention.page,
            quote=mention.context,
            chunk_id=mention.chunk_id,
        )
        citation_list.append(citation)

    return GroundedAnswer(
        text=" ".join(parts), citations=citation_list, abstained=False
    )


async def render_relationship_lookup(
    session: SQLModelAsyncSession, relations: list[RelationOut], *, scope: ReadingScope
) -> GroundedAnswer:
    """Render the direct edge(s) between two characters, or abstain.

    ``relations`` is assumed already spoiler-filtered by ``scope``
    (``graph.repository.relations_out``); ``scope`` is still needed here to
    keep each cited sentence's *own* evidence from reaching past it too (a
    visible edge can carry evidence from a later reassertion — S8.1).
    """
    if not relations:
        return abstain("No established relationship between them in this project.")

    sentences: list[str] = []
    citation_list: list[CitationOut] = []
    for relation in relations:
        sentence, relation_citations = await _relation_sentence(
            session, relation, scope=scope
        )
        sentences.append(sentence)
        citation_list.extend(relation_citations)

    return GroundedAnswer(
        text=" ".join(sentences), citations=citation_list, abstained=False
    )


async def render_path(
    session: SQLModelAsyncSession, hops: list[RelationOut], *, scope: ReadingScope
) -> GroundedAnswer:
    """Render a shortest-path chain, one cited sentence per hop, or abstain."""
    if not hops:
        return abstain("No path connects them in this project's graph.")

    sentences: list[str] = []
    citation_list: list[CitationOut] = []
    for hop in hops:
        sentence, hop_citations = await _relation_sentence(session, hop, scope=scope)
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
    scope: ReadingScope,
) -> GroundedAnswer:
    """Render an exhaustive set answer, every member cited, or abstain.

    Args:
        session: An open database session.
        anchor_name: The subject of the aggregation ("Mr Bennet").
        predicate: The ontology predicate the question was mapped to.
        relations: Every matching relation, already deduplicated by id and
            already spoiler-filtered by ``scope``
            (``graph.repository.relations_out``).
        other_names: The other endpoint's canonical name, by character id —
            needed because a relation's ``subject``/``object`` naming depends
            on which direction it happened to be stored in, not on which side
            the anchor is. Callers must derive this from the same filtered
            ``relations``, never from an unfiltered id list — the sentence
            below names every id in ``other_names`` regardless of whether
            it appears in ``relations``, so an unfiltered caller would name a
            character whose edge to the anchor was just spoiler-filtered out.
        scope: The reader's position, applied again to each cited sentence's
            own evidence (see ``render_relationship_lookup``).
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
            session, relation, scope=scope, top_n=1
        )
        citation_list.extend(relation_citations)

    return GroundedAnswer(text=sentence, citations=citation_list, abstained=False)


async def render_series_arc(
    session: SQLModelAsyncSession, arc: RelationArcOut, *, scope: ReadingScope
) -> GroundedAnswer:
    """Render a relationship's states over series position, in order, or abstain.

    ``arc.states`` is assumed already trimmed to ``scope`` by
    ``graph.repository.relation_arc`` — a later state must be absent
    entirely, not appended and then hidden, or "how did their relationship
    change?" would still betray that it *does* change (S8.1).
    """
    if not arc.states:
        return abstain("No established relationship between them in this project.")

    sentences: list[str] = []
    citation_list: list[CitationOut] = []
    for state in arc.states:
        sentence, state_citations = await _relation_sentence(
            session, state, scope=scope, top_n=1
        )
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
    question: str,
    chunks: list,
    *,
    project_id: str,
    mode: InferenceMode | None = None,
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
        mode: The Sprint 8 "model" ablation axis override for this call
            (PRD Appendix A). ``None`` (every caller before S8.2) is local,
            unchanged (``llm.routing.route_for``).

    Yields:
        Text deltas as they arrive from the model.
    """
    if not chunks:
        return

    prompt = _build_narrative_prompt(question, chunks)
    model = get_llm(LLMPurpose.ANSWER, mode=mode)

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
