"""A synthetic connected graph in Postgres, for the CI rebuild drill (S4.15).

The integration fixture novel is filler text with no characters, so it yields
an empty graph and an identical projection of nothing proves nothing. This
seeds a small but structured one -- a family, a couple of arcs, dialogue-only
hearsay, several books' worth of page refs -- straight into the relational
tables, so ``graph.upsert`` has something real to project and the drill has
something real to compare.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlmodel import select

from ..contracts.enums import (
    AssertionType,
    BookStatus,
    ImportanceTier,
    ProjectKind,
    RelationFamily,
)
from ..db.engine import db_session
from ..db.models import (
    Book,
    Character,
    CharacterAppearance,
    DocumentChunk,
    Project,
    Relation,
    RelationEvidence,
)

FIXTURE_SLUG = "graph-rebuild-drill"

_NAMES = [
    "Alice Ash", "Bruno Ash", "Clara Ash", "Dmitri Ash", "Edith Birch",
    "Felix Birch", "Greta Cole", "Hugo Cole", "Iris Dunn", "Jonas Dunn",
]  # fmt: skip

# subject index, predicate, object index, family, first chapter, last chapter.
_EDGES = [
    (0, "parent_of", 2, RelationFamily.KINSHIP, 1, None),
    (0, "parent_of", 3, RelationFamily.KINSHIP, 1, None),
    (1, "parent_of", 2, RelationFamily.KINSHIP, 1, None),
    (1, "parent_of", 3, RelationFamily.KINSHIP, 1, None),
    (2, "sibling_of", 3, RelationFamily.KINSHIP, 1, None),
    (0, "married_to", 1, RelationFamily.ROMANTIC, 1, None),
    (4, "engaged_to", 5, RelationFamily.ROMANTIC, 3, 9),
    (4, "married_to", 5, RelationFamily.ROMANTIC, 10, None),
    (6, "friend_of", 4, RelationFamily.SOCIAL, 2, 12),
    (6, "enemy_of", 4, RelationFamily.ADVERSARIAL, 13, None),
    (7, "sibling_of", 6, RelationFamily.KINSHIP, 2, None),
    (8, "employer_of", 9, RelationFamily.SOCIAL, 5, None),
    (2, "friend_of", 8, RelationFamily.SOCIAL, 4, None),
    (3, "rival_of", 9, RelationFamily.ADVERSARIAL, 6, None),
    (5, "deceives", 6, RelationFamily.ADVERSARIAL, 7, 14),
]


async def seed_fixture_graph() -> UUID:
    """Replace the drill's project with a fresh synthetic one; return its book id."""
    async with db_session() as session:
        stale = (
            await session.execute(select(Project).where(Project.slug == FIXTURE_SLUG))  # type: ignore[arg-type]
        ).scalar_one_or_none()
        if stale is not None:
            await session.delete(stale)
            await session.commit()

        project = Project(
            name="Graph Rebuild Drill", slug=FIXTURE_SLUG, kind=ProjectKind.STANDALONE
        )
        session.add(project)
        await session.flush()
        book = Book(
            project_id=project.id,
            series_order=1,
            title="Graph Drill Fixture",
            content_hash=hashlib.sha256(FIXTURE_SLUG.encode()).hexdigest(),
            page_count=40,
            chapter_count=15,
            status=BookStatus.READY,
        )
        session.add(book)
        await session.flush()

        chunks: dict[int, DocumentChunk] = {}
        for page in range(1, 41):
            chunk = DocumentChunk(
                book_id=book.id,
                text=f"Fixture passage on page {page}.",
                pages=[page],
                page_start=page,
                page_end=page,
            )
            session.add(chunk)
            chunks[page] = chunk

        characters: list[Character] = []
        for index, name in enumerate(_NAMES):
            tier = ImportanceTier.MAJOR if index < 6 else ImportanceTier.MINOR
            character = Character(
                project_id=project.id,
                canonical_name=name,
                aliases=[name.split()[0]],
                importance_tier=tier,
                first_book_id=book.id,
                first_chapter=1,
                first_page=index + 1,
                last_book_id=book.id,
                mention_count=20 - index,
            )
            session.add(character)
            characters.append(character)
        await session.flush()

        for index, character in enumerate(characters):
            session.add(
                CharacterAppearance(
                    character_id=character.id,
                    book_id=book.id,
                    first_page=index + 1,
                    first_chapter=1,
                    mention_count=character.mention_count,
                    importance_tier=character.importance_tier,
                    surface_forms=[character.canonical_name, *character.aliases],
                )
            )

        for number, (s, predicate, o, family, first, last) in enumerate(_EDGES):
            dialogue = predicate == "deceives"
            relation = Relation(
                project_id=project.id,
                subject_character_id=characters[s].id,
                object_character_id=characters[o].id,
                predicate=predicate,
                family=family,
                confidence=0.9,
                assertion_type=AssertionType.DIALOGUE
                if dialogue
                else AssertionType.NARRATED,
                hearsay=dialogue,
                first_book_order=1,
                first_chapter=first,
                last_book_order=1 if last else None,
                last_chapter=last,
                evidence_count=2,
            )
            session.add(relation)
            await session.flush()
            for offset in (0, 1):
                page = (number * 2 + offset) % 40 + 1
                session.add(
                    RelationEvidence(
                        relation_id=relation.id,
                        book_id=book.id,
                        chunk_id=chunks[page].id,
                        book_order=1,
                        chapter_no=first,
                        page_start=page,
                        page_end=page,
                        quote=f"{_NAMES[s]} and {_NAMES[o]}, page {page}.",
                        assertion_type=relation.assertion_type,
                        confidence=0.9,
                    )
                )
        await session.commit()

        return book.id
