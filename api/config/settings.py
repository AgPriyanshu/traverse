from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..contracts.enums import InferenceMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "development"
    api_port: int = 8000

    # Postgres — source of truth.
    postgres_db_string: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5433/postgres"
    )

    # Neo4j — a rebuildable projection of the above.
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("very_safe_password")
    neo4j_database: str = "neo4j"

    # Broker.
    rabbitmq_url: str = "pyamqp://guest:guest@localhost:5672//"
    celery_result_backend: str = "rpc://"

    # Object storage.
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "traverse-int"
    minio_secure: bool = False

    # Inference.
    inference_mode: InferenceMode = InferenceMode.LOCAL
    vllm_base_url: str = "http://localhost:8080/v1/"
    llm_model: str = "Qwen/Qwen3-8B-AWQ"
    llm_max_context: int = 16384
    llm_output_reserve: int = 2048
    llm_max_output_tokens: int = 6144
    llm_enable_thinking: bool = False
    llm_max_concurrency: int = 8
    frontier_model: str | None = None
    frontier_api_key: SecretStr | None = None

    # Reranker, mention clustering and tiering (Sprint 2/3 SCRs).
    reranker_enabled: bool = False
    reranker_model_id: str = "BAAI/bge-reranker-v2-m3"
    mention_similarity_threshold: float = 0.65
    tiering_method: str = "mention_count"

    # Embeddings.
    embedding_model_id: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16

    # Model caches. Never a host-specific absolute path in code — set these
    # from the environment; the container mounts a shared volume at /models.
    models_cache_dir: Path = Path("/models")
    docling_artifacts_dir: Path | None = None
    models_offline: bool = False

    # Observability.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://localhost:3000"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


settings = Settings()
