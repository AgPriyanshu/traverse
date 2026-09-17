from fastapi import HTTPException, status


def not_implemented(owner: str, story: str) -> None:
    """Placeholder for a frozen endpoint whose handler has not landed yet.

    The route, its path and its response model are frozen at the contract
    freeze so the generated client is correct before any handler exists.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Not implemented yet — owned by {owner}, {story}.",
    )
