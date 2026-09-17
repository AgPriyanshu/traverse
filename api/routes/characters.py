"""Characters, aliases and appearances. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Query

from ..contracts.api import (
    AppearanceOut,
    CharacterDetailOut,
    CharacterMergeRequest,
    CharacterOut,
    CharacterSplitRequest,
    MentionOut,
)
from ..contracts.enums import ImportanceTier
from ._stub import not_implemented

router = APIRouter(tags=["characters"])
OWNER = "be2"


@router.get("/projects/{project_id}/characters", response_model=list[CharacterOut])
async def list_characters(
    project_id: UUID,
    tier: ImportanceTier | None = Query(default=None),
    q: str | None = Query(default=None, description="Alias-aware search"),
    book_id: UUID | None = Query(default=None),
    limit_book_order: int | None = Query(default=None),
    limit_chapter: int | None = Query(default=None),
) -> list[CharacterOut]:
    not_implemented(OWNER, "S1.7 / S3.6")


@router.get("/characters/{character_id}", response_model=CharacterDetailOut)
async def get_character(character_id: UUID) -> CharacterDetailOut:
    not_implemented(OWNER, "S3.6")


@router.get("/characters/{character_id}/mentions", response_model=list[MentionOut])
async def list_mentions(
    character_id: UUID,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    limit_chapter: int | None = Query(default=None),
) -> list[MentionOut]:
    not_implemented(OWNER, "S3.6")


@router.get(
    "/characters/{character_id}/appearances", response_model=list[AppearanceOut]
)
async def list_appearances(character_id: UUID) -> list[AppearanceOut]:
    not_implemented(OWNER, "S5.8")


@router.post("/characters/merge", response_model=CharacterOut)
async def merge_characters(body: CharacterMergeRequest) -> CharacterOut:
    not_implemented(OWNER, "S3.7")


@router.post("/characters/{character_id}/split", response_model=list[CharacterOut])
async def split_character(
    character_id: UUID, body: CharacterSplitRequest
) -> list[CharacterOut]:
    not_implemented(OWNER, "S3.7")
