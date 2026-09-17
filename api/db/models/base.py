from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin(SQLModel):
    """Timestamps for every table.

    Declared with ``sa_type``/``sa_column_kwargs`` rather than ``sa_column``:
    a ``Column`` instance built at class-definition time would be the SAME
    object on every model that inherits this, and SQLAlchemy refuses to attach
    one column to two tables.
    """

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
        nullable=False,
    )
