"""The reader's position: required context on every graph/retrieval/generation call.

S8.1, PRD F4.5. Before this, ``limit_book_order``/``limit_chapter`` were a pair
of independently optional keyword arguments defaulting to ``None`` ("no
limit"), threaded inconsistently: some read paths (``get_character``,
``list_mentions``, the whole-project ``/graph`` endpoint) applied them, others
(``relations_out``, ``relation_arc``, ``shortest_path``, the neighbourhood
graph, evidence hydration, the aggregation answer's own character-name list)
never had the parameter plumbed at all, so a reader mid-book asking "how are X
and Y related" or "what happened to X's arc" got the whole series back,
unfiltered, by construction — not because a caller forgot to pass ``None``,
but because there was nowhere to pass anything.

``ReadingScope`` replaces the pair everywhere in the graph/query/retrieval
layer with one required, defaultless parameter. There is deliberately no
``ReadingScope | None = None`` anywhere in this codebase's function
signatures: a missing scope is a ``TypeError`` at the call site, not a silent
"no limit". ``ReadingScope.unlimited()`` makes "no limit" a named, explicit
choice instead of an omission — the one route that legitimately wants it (the
human review queue, ``api/review/**``, which shows a reviewer full context
regardless of any reader's position) says so in the code.
"""

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
