from sqlmodel import SQLModel, create_engine

from ..config import settings
from . import models  # noqa

echo_engine = settings.env in ["local"]
engine = create_engine(
    settings.postgres_db_string, connect_args={"sslmode": "require"}, echo=echo_engine
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
