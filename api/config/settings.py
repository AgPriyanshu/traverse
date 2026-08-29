from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_db_string: str = "postgresql://user:passwordp@host/db"
    env = "local"


settings = Settings()
