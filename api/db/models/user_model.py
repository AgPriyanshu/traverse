from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    first_name: str
    last_name: str
    email: str = Field(unique=True)

    @property
    def name(self):
        return self.first_name + " " + self.last_name
