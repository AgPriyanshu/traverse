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
from ..graph import merge, repository
from ..graph.merge import CharacterNotFoundError, MergeValidationError
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
    character_id: UUID,
    limit_book_order: int | None = Query(default=None),
    limit_chapter: int | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> CharacterDetailOut:
    """Return one character: aliases, attributes, appearances and evidence.

    Raises:
        HTTPException: 404 when no such character exists, or it exists but is
            not yet visible at the given reading position — the same
            spoiler gate ``list_characters`` applies, so a deep link cannot
            bypass it.
    """
    character = await repository.get_character(
        session,
        character_id,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )
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
    limit_book_order: int | None = Query(default=None),
    limit_chapter: int | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[MentionOut]:
    """Return one character's mentions, page-ordered and paginated.

    Raises:
        HTTPException: 404 when no such character exists.
    """
    mentions = await repository.list_mentions(
        session,
        character_id,
        limit=limit,
        offset=offset,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )
    if mentions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )

    return mentions


@router.get(
    "/characters/{character_id}/appearances", response_model=list[AppearanceOut]
)
async def list_appearances(character_id: UUID) -> list[AppearanceOut]:
    not_implemented(OWNER, "S5.8")


@router.post("/characters/merge", response_model=CharacterOut)
async def merge_characters(
    body: CharacterMergeRequest,
    session: SQLModelAsyncSession = Depends(get_session),
) -> CharacterOut:
    """Merge ``source_ids`` into ``target_id``, one transaction, zero orphans.

    Raises:
        HTTPException: 404 if a source or the target does not exist; 400 if
            the request is otherwise invalid (target in sources, sources
            spanning more than one project, or a colliding canonical name).
    """
    try:
        merged = await merge.merge_characters(
            session,
            source_ids=body.source_ids,
            target_id=body.target_id,
            canonical_name=body.canonical_name,
        )
    except CharacterNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except MergeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return merged


@router.post("/characters/{character_id}/split", response_model=list[CharacterOut])
async def split_character(
    character_id: UUID,
    body: CharacterSplitRequest,
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[CharacterOut]:
    """Split ``mention_ids`` off ``character_id`` into a new character.

    Raises:
        HTTPException: 404 if ``character_id`` does not exist; 400 if the
            request is otherwise invalid (a mention id not on this
            character, every mention named, or a colliding canonical name).
    """
    try:
        split = await merge.split_character(
            session,
            character_id=character_id,
            mention_ids=body.mention_ids,
            new_canonical_name=body.new_canonical_name,
        )
    except CharacterNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except MergeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return split
