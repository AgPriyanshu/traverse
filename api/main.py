import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from neo4j.exceptions import ServiceUnavailable

from . import graph
from .contracts.api import ErrorOut, HealthOut
from .routes import api_router
from .routes.ops import health as _health

# Applied to every route: the shape FastAPI's own HTTPException and validation
# errors already serialise to, now documented rather than hand-parsed on the
# client (SCR-9).
_ERROR_RESPONSES = {
    404: {"model": ErrorOut},
    422: {"model": ErrorOut},
    501: {"model": ErrorOut},
}

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One Neo4j driver per process, opened here and closed on shutdown. A
    # driver per call opens a fresh connection pool each time and collapses
    # under the Sprint 4 upsert load.
    try:
        await graph.connect()
    except ServiceUnavailable:
        # The API still serves Postgres-backed routes without Neo4j, and
        # /health reports the dependency as down. Refusing to boot would take
        # the whole product out for a rebuildable projection.
        logger.exception("neo4j unavailable at startup; graph routes will degrade")

    try:
        yield
    finally:
        await graph.close()


app = FastAPI(
    title="Traverse",
    version="0.2.0",
    summary="Character knowledge graphs for novels and series.",
    lifespan=lifespan,
    responses=_ERROR_RESPONSES,
)

app.include_router(api_router)


@app.get("/health", response_model=HealthOut, tags=["ops"])
async def health() -> HealthOut:
    """Root-level alias so container healthchecks do not depend on the API prefix."""
    return await _health()
