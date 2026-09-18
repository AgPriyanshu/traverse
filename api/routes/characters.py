"""Characters, aliases and appearances. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    AppearanceOut,
    CharacterDetailOut,
    CharacterMergeRequest,
    CharacterOut,
    CharacterSplitRequest,
    MentionOut,
)
from ..contracts.enums import ImportanceTier
from ..db.engine import get_session
from ..graph import repository
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
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[CharacterOut]:
    """Return a project's roster, alias-aware and filterable.

    Raises:
        HTTPException: 404 when the project does not exist. An empty list means
            the project has no characters yet, which is not the same thing.
    """
    if not await repository.project_exists(session, project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    characters = await repository.list_characters(
        session,
        project_id,
        tier=tier,
        q=q,
        book_id=book_id,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )

    return characters


@router.get("/characters/{character_id}", response_model=CharacterDetailOut)
async def get_character(
    character_id: UUID, session: SQLModelAsyncSession = Depends(get_session)
) -> CharacterDetailOut:
    """Return one character with its per-book appearances.

    Alias detail, attributes and per-chapter mention counts land in S3.6.

    Raises:
        HTTPException: 404 when no such character exists.
    """
    character = await repository.get_character(session, character_id)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )

    return character


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
