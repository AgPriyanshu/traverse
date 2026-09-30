from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadingScope:
    """A reading position: ``(book_order, chapter)``, or explicitly unlimited.

    Mirrors the series-position convention used throughout the graph and
    retrieval layers (``character-graph.md``): a standalone book is
    ``(1, chapter)``, one code path, no branch on project kind. ``book_order
    is None`` means unlimited — nothing is filtered — and must only ever be
    reached via :meth:`unlimited`, never a bare ``ReadingScope(None, None)``
    at a call site that meant to pass a real position.
    """

    book_order: int | None
    chapter: int | None

    @classmethod
    def unlimited(cls) -> "ReadingScope":
        """No reading-position restriction — an explicit opt-out, not a default."""
        return cls(book_order=None, chapter=None)
