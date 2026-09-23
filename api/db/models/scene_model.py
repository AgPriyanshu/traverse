import uuid
from uuid import UUID

from sqlalchemy import ARRAY, Column, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Scene(SQLModel, table=True):
    __tablename__ = "scene"
    __table_args__ = (Index("ix_scene_book_position", "book_id", "position"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    chapter_id: UUID | None = Field(default=None)
    position: int
    page_start: int
    page_end: int
    chunk_ids: list[UUID] = Field(sa_column=Column(ARRAY(PGUUID(as_uuid=True))))


class SceneParticipant(SQLModel, table=True):
    __tablename__ = "scene_participant"

    scene_id: UUID = Field(foreign_key="scene.id", ondelete="CASCADE", primary_key=True)
    character_id: UUID = Field(
        foreign_key="character.id", ondelete="CASCADE", primary_key=True
    )
    mention_count: int = Field(default=0)


class DialogueLine(SQLModel, table=True):
    __tablename__ = "dialogue_line"
    __table_args__ = (Index("ix_dialogue_line_book", "book_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    chunk_id: UUID = Field(foreign_key="documentchunk.id", ondelete="CASCADE")
    char_start: int
    char_end: int
    speaker_character_id: UUID | None = Field(
        default=None, foreign_key="character.id", ondelete="SET NULL"
    )
    method: str
    confidence: float
