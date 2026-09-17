"""Router registry. Orchestrator-owned — agents add handlers, never includes.

Every route in the product is declared here at the contract freeze, so
``/openapi.json`` is complete and the generated frontend client is correct
before a single handler lands.
"""

from fastapi import APIRouter

from . import books, characters, graph, ops, query, review

api_router = APIRouter(prefix="/api")
api_router.include_router(books.router)
api_router.include_router(characters.router)
api_router.include_router(graph.router)
api_router.include_router(query.router)
api_router.include_router(review.router)
api_router.include_router(ops.router)

__all__ = ["api_router"]
