from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_db_string: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5431/postgres"
    )
    env: str = "development"


settings = Settings()
