from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    postgres_db_string: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5433/postgres"
    )
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str

    env: str = "development"


settings = Settings()  # pyright: ignore[reportCallIssue]
