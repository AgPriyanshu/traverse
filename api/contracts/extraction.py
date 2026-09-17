"""Contracts for character discovery, alias resolution and reconciliation."""

from uuid import UUID

from pydantic import BaseModel, Field

from .enums import CandidateKind, ImportanceTier, ResolutionMethod


class CharacterCandidate(BaseModel):
    """A pass-1 mention. ``context`` is mandatory: the resolver runs on it."""

    surface_form: str
    chunk_id: UUID
    page: int = Field(ge=1)
    chapter_number: int | None = None
    context: str
    kind: CandidateKind = CandidateKind.UNKNOWN


class ResolvedCharacter(BaseModel):
    """A book-local cluster, before it is reconciled against the project roster."""

    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    mention_ids: list[UUID] = Field(default_factory=list)
    importance_tier: ImportanceTier = ImportanceTier.MENTIONED
    first_page: int
    first_chapter: int | None = None
    mention_count: int = 0
    resolution_method: ResolutionMethod = ResolutionMethod.EXACT
    collision_suspected: bool = False


class ReconcileCandidate(BaseModel):
    book_cluster: ResolvedCharacter
    project_character_id: UUID | None = None
    score: float = 0.0
    method: ResolutionMethod = ResolutionMethod.EXACT


class ReconcileDecision(BaseModel):
    """Every link, every new character, every block — with its reason.

    An unaudited merge cannot be reviewed or measured.
    """

    book_id: UUID
    cluster_key: str
    character_id: UUID | None = None
    created_new: bool = False
    method: ResolutionMethod = ResolutionMethod.EXACT
    confidence: float = 0.0
    blocked_by: str | None = None
