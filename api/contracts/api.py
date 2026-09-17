"""HTTP response and request models — the contract the web app is generated from.

Every endpoint declares one of these, so ``/openapi.json`` is complete and
correct on day one and the frontend can generate a typed client before a single
handler is implemented.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import (
    AssertionType,
    BookStatus,
    DetectionMethod,
    ImportanceTier,
    ProjectKind,
    QueryRoute,
    RelationFamily,
    RelationStatus,
    ResolutionMethod,
    ReviewStatus,
    ReviewTaskType,
)
from .pipeline import StageStatus

# ── Projects and books ──────────────────────────────────────────────────────


class BookOut(BaseModel):
    id: UUID
    project_id: UUID
    series_order: int | None = None
    title: str
    author: str | None = None
    page_count: int | None = None
    chapter_count: int | None = None
    character_count: int = 0
    status: BookStatus
    ingested_at: datetime | None = None


class ProjectOut(BaseModel):
    id: UUID
    name: str
    slug: str
    kind: ProjectKind
    book_count: int = 0
    character_count: int = 0
    relation_count: int = 0
    updated_at: datetime | None = None


class ProjectDetailOut(ProjectOut):
    books: list[BookOut] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str
    kind: ProjectKind = ProjectKind.STANDALONE


class BookOrderUpdate(BaseModel):
    """Reordering recomputes derived character fields; it does not re-extract."""

    order: list[UUID]


class BookStatusOut(BaseModel):
    book_id: UUID
    status: BookStatus
    stages: list[StageStatus] = Field(default_factory=list)
    estimated_seconds_remaining: int | None = None
    trace_url: str | None = None


class ChapterOut(BaseModel):
    id: UUID
    book_id: UUID
    number: int | None = None
    title: str | None = None
    page_start: int
    page_end: int
    detection_method: DetectionMethod
    chunk_count: int = 0


class ChunkOut(BaseModel):
    id: UUID
    book_id: UUID
    chapter_id: UUID | None = None
    chapter_number: int | None = None
    text: str
    pages: list[int]
    page_start: int
    page_end: int
    token_count: int | None = None
    dense_score: float | None = None
    lexical_score: float | None = None


class SpanBox(BaseModel):
    """PDF user space, origin top-left, unscaled. Agreed with the frontend once."""

    page: int
    x: float
    y: float
    width: float
    height: float


class PageRenderOut(BaseModel):
    book_id: UUID
    page: int
    image_url: str
    width: float
    height: float
    spans: list[SpanBox] = Field(default_factory=list)


# ── Characters ──────────────────────────────────────────────────────────────


class AliasOut(BaseModel):
    surface_form: str
    count: int
    resolution_method: ResolutionMethod
    ambiguous: bool = False


class AppearanceOut(BaseModel):
    book_id: UUID
    series_order: int | None = None
    book_title: str
    first_page: int | None = None
    first_chapter: int | None = None
    mention_count: int = 0
    importance_tier: ImportanceTier
    surface_forms: list[str] = Field(default_factory=list)


class CharacterOut(BaseModel):
    id: UUID
    project_id: UUID
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    importance_tier: ImportanceTier
    mention_count: int = 0
    first_page: int | None = None
    first_chapter: int | None = None
    first_book_id: UUID | None = None
    appears_in_books: list[int] = Field(default_factory=list)
    collision_suspected: bool = False
    human_verified: bool = False


class MentionOut(BaseModel):
    id: UUID
    chunk_id: UUID
    book_id: UUID
    surface_form: str
    page: int
    context: str | None = None
    resolution_method: ResolutionMethod


class AttributeOut(BaseModel):
    label: str
    value: str
    book_id: UUID | None = None
    page: int


class CharacterDetailOut(CharacterOut):
    alias_detail: list[AliasOut] = Field(default_factory=list)
    attributes: list[AttributeOut] = Field(default_factory=list)
    appearances: list[AppearanceOut] = Field(default_factory=list)
    mentions_per_chapter: dict[str, int] = Field(default_factory=dict)


class CharacterMergeRequest(BaseModel):
    source_ids: list[UUID] = Field(min_length=1)
    target_id: UUID
    canonical_name: str | None = None


class CharacterSplitRequest(BaseModel):
    mention_ids: list[UUID] = Field(min_length=1)
    new_canonical_name: str


# ── Graph ───────────────────────────────────────────────────────────────────


class EvidenceOut(BaseModel):
    id: UUID
    book_id: UUID
    book_title: str | None = None
    series_order: int | None = None
    chapter_no: int | None = None
    page_start: int
    page_end: int
    quote: str
    assertion_type: AssertionType
    asserted_by: str | None = None
    confidence: float | None = None


class RelationOut(BaseModel):
    id: UUID
    subject_character_id: UUID
    subject_name: str
    predicate: str
    object_character_id: UUID
    object_name: str
    family: RelationFamily
    confidence: float
    status: RelationStatus
    assertion_type: AssertionType
    hearsay: bool = False
    evidence_count: int = 0
    first_book_order: int = 1
    first_chapter: int | None = None
    last_book_order: int | None = None
    last_chapter: int | None = None
    page_refs: list[int] = Field(default_factory=list)


class RelationArcOut(BaseModel):
    """The ordered sequence of states for one pair.

    A relationship that never changes is a one-element sequence, so callers
    have a single code path.
    """

    subject_character_id: UUID
    object_character_id: UUID
    states: list[RelationOut] = Field(default_factory=list)


class GraphNodeOut(BaseModel):
    id: UUID
    canonical_name: str
    importance_tier: ImportanceTier
    mention_count: int = 0
    first_book_order: int | None = None
    first_chapter: int | None = None
    appears_in_books: list[int] = Field(default_factory=list)


class GraphEdgeOut(BaseModel):
    id: UUID
    source: UUID
    target: UUID
    predicate: str
    family: RelationFamily
    confidence: float
    evidence_count: int
    hearsay: bool = False
    page_refs: list[int] = Field(default_factory=list)


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)
    truncated: bool = False


class GraphPathOut(BaseModel):
    hops: list[RelationOut] = Field(default_factory=list)
    found: bool = True


class OntologyPredicateOut(BaseModel):
    predicate: str
    family: RelationFamily
    inverse: str | None = None
    symmetric: bool = False


class OntologyOut(BaseModel):
    predicates: list[OntologyPredicateOut] = Field(default_factory=list)
    families: list[RelationFamily] = Field(default_factory=list)


# ── Query ───────────────────────────────────────────────────────────────────


class CitationOut(BaseModel):
    book_id: UUID
    book_title: str | None = None
    series_order: int | None = None
    page_start: int
    page_end: int
    chapter_no: int | None = None
    quote: str | None = None
    chunk_id: UUID | None = None


class QueryRequest(BaseModel):
    project_id: UUID
    question: str
    thread_id: UUID | None = None
    # The reader's position. ``None`` means no limit and must be chosen
    # explicitly by the caller — never defaulted into.
    limit_book_order: int | None = None
    limit_chapter: int | None = None


# Discriminated on ``type`` so the generated TypeScript is a usable union
# rather than ``unknown``.
class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class CitationEvent(BaseModel):
    type: Literal["citation"] = "citation"
    index: int
    citation: CitationOut


class RouteEvent(BaseModel):
    type: Literal["route"] = "route"
    route: QueryRoute
    explanation: str | None = None
    retrieval_tier: str | None = None


class InterruptEvent(BaseModel):
    type: Literal["interrupt"] = "interrupt"
    thread_id: UUID
    question: str
    options: list[str] = Field(default_factory=list)


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    thread_id: UUID
    citation_count: int = 0
    latency_ms: int | None = None
    abstained: bool = False


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool = False


QueryEvent = Annotated[
    TokenEvent | CitationEvent | RouteEvent | InterruptEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]


class QueryEventEnvelope(BaseModel):
    """Documents the SSE stream for the generated client.

    The wire format is ``text/event-stream``; this envelope exists so the
    generated TypeScript carries the discriminated union.
    """

    event: QueryEvent


class ClarifyResponse(BaseModel):
    answer: str


# ── Review ──────────────────────────────────────────────────────────────────


class ReviewTaskOut(BaseModel):
    id: UUID
    project_id: UUID
    book_id: UUID | None = None
    task_type: ReviewTaskType
    status: ReviewStatus
    priority: int
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReviewResolution(BaseModel):
    decision: str
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Search and ops ──────────────────────────────────────────────────────────


class SearchResultOut(BaseModel):
    chunks: list[ChunkOut] = Field(default_factory=list)
    tier: str | None = None


class DependencyHealth(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: list[DependencyHealth] = Field(default_factory=list)


class StageCost(BaseModel):
    stage: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


class MetricsOut(BaseModel):
    book_id: UUID | None = None
    stages: list[StageCost] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    prefix_cache_hit_rate: float | None = None


class RoutingPolicyOut(BaseModel):
    version: int
    purposes: dict[str, str] = Field(default_factory=dict)


class DeadLetterOut(BaseModel):
    book_id: UUID
    book_title: str
    stage: str
    error_class: str | None = None
    error_message: str | None = None
    attempts: int = 0
    trace_url: str | None = None
