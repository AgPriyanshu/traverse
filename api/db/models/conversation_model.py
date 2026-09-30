import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from .base import TimestampMixin


class Conversation(TimestampMixin, table=True):
    __table_args__ = (Index("ix_conversation_project", "project_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    title: str | None = Field(default=None)
    scope_book_id: UUID | None = Field(
        default=None, foreign_key="book.id", ondelete="SET NULL"
    )
    scope_chapter: int | None = Field(default=None)


class ConversationTurn(TimestampMixin, table=True):
    __table_args__ = (Index("ix_conversation_turn_conversation", "conversation_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: UUID = Field(foreign_key="conversation.id", ondelete="CASCADE")
    query_log_id: UUID | None = Field(
        default=None, foreign_key="querylog.id", ondelete="SET NULL"
    )
    position: int
    question: str
    answer: str | None = Field(default=None)
    resolved_character_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
