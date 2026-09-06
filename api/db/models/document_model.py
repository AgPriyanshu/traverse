import uuid
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String
from sqlmodel import ARRAY, Column, Field, Relationship, SQLModel


class Document(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    uploaded_by: UUID | None = Field(default=None, foreign_key="user.id")

    # Relationships.
    chunks: list["DocumentChunk"] = Relationship(back_populates="document")


class DocumentChunk(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    text_embedding: list[float] = Field(sa_column=Column(Vector(1024)))
    text: str
    headings: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    pages: list[int] = Field(default_factory=list, sa_column=Column(ARRAY(Integer)))
    page_start: int
    page_end: int
    document_id: UUID = Field(foreign_key="document.id")

    # Relationships.
    document: Document = Relationship(back_populates="chunks")
