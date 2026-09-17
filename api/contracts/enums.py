"""Enumerations shared by the database models, the API contracts and the workers.

This module has no dependencies inside ``api`` so every other layer may import
it. Values are stored in the database as strings, so renaming one is a
migration, not a refactor.
"""

from enum import StrEnum


class ProjectKind(StrEnum):
    STANDALONE = "standalone"
    SERIES = "series"


class BookStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class StageName(StrEnum):
    """The frozen ingestion stages. These strings are also the Celery task names.

    Changing one renames a Celery task and orphans anything already queued.
    """

    PARSE_AND_CHUNK = "pipeline.parse_and_chunk"
    SEGMENT_CHAPTERS = "pipeline.segment_chapters"
    EMBED_CHUNKS = "pipeline.embed_chunks"
    EXTRACT_CHARACTERS = "pipeline.extract_characters"
    RESOLVE_ALIASES = "pipeline.resolve_aliases"
    RECONCILE_CHARACTERS = "pipeline.reconcile_characters"
    EXTRACT_RELATIONS = "relations.extract"
    AGGREGATE_RELATIONS = "relations.aggregate"
    UPSERT_GRAPH = "graph.upsert"


class StageState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DetectionMethod(StrEnum):
    REGEX = "regex"
    LLM = "llm"
    MANUAL = "manual"


class ImportanceTier(StrEnum):
    PROTAGONIST = "protagonist"
    MAJOR = "major"
    MINOR = "minor"
    MENTIONED = "mentioned"


class CandidateKind(StrEnum):
    PERSON = "person"
    PLACE = "place"
    ORGANISATION = "organisation"
    UNKNOWN = "unknown"


class ResolutionMethod(StrEnum):
    """How a mention ended up in its cluster, or a book roster in a project one."""

    EXACT = "exact"
    NORMALISED = "normalised"
    HONORIFIC = "honorific"
    NICKNAME = "nickname"
    EMBEDDING = "embedding"
    LLM = "llm"
    HUMAN = "human"


class RelationFamily(StrEnum):
    KINSHIP = "kinship"
    ROMANTIC = "romantic"
    SOCIAL = "social"
    ADVERSARIAL = "adversarial"
    STRUCTURAL = "structural"


class AssertionType(StrEnum):
    """How a relationship is known. ``DIALOGUE`` is not the same as fact."""

    NARRATED = "narrated"
    DIALOGUE = "dialogue"
    INFERRED = "inferred"


class RelationStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"
    SUPERSEDED = "superseded"


class ReviewTaskType(StrEnum):
    MERGE_CHARACTERS = "merge_characters"
    MERGE_ACROSS_BOOKS = "merge_across_books"
    CONFIRM_RELATION = "confirm_relation"
    RESOLVE_CONFLICT = "resolve_conflict"
    CLASSIFY_CANDIDATE = "classify_candidate"
    CONFIRM_CHAPTER_SPLIT = "confirm_chapter_split"


class ReviewStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class LLMPurpose(StrEnum):
    """Routing is by purpose, never by call site."""

    CHAPTER_CLASSIFY = "chapter_classify"
    CHARACTER_EXTRACT = "character_extract"
    RELATION_EXTRACT = "relation_extract"
    ADJUDICATE = "adjudicate"
    ANSWER = "answer"
    JUDGE = "judge"


class QueryRoute(StrEnum):
    CHARACTER_LOOKUP = "character_lookup"
    RELATIONSHIP_LOOKUP = "relationship_lookup"
    PATH = "path"
    AGGREGATION = "aggregation"
    SERIES_ARC = "series_arc"
    NARRATIVE = "narrative"
    AMBIGUOUS = "ambiguous"


class InferenceMode(StrEnum):
    LOCAL = "local"
    API = "api"
    ROUTED = "routed"
