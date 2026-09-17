from contextlib import asynccontextmanager

from fastapi import FastAPI

from .contracts.api import HealthOut
from .routes import api_router
from .routes.ops import health as _health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dependency clients (Neo4j driver, embedding model, MinIO) are opened here
    # by their owning agents in Sprint 1. Nothing to start at the freeze.
    yield


app = FastAPI(
    title="Traverse",
    version="0.2.0",
    summary="Character knowledge graphs for novels and series.",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health", response_model=HealthOut, tags=["ops"])
async def health() -> HealthOut:
    """Root-level alias so container healthchecks do not depend on the API prefix."""
    return await _health()
