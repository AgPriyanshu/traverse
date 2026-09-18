from ..workers.errors import PermanentError, TransientError


class DocumentParseError(PermanentError):
    """The file could not be converted. A corrupt PDF is corrupt on every attempt."""


class MissingProvenanceError(PermanentError):
    """A chunk came back with no page provenance.

    Page-exact citation is the product (PRD F1.3), so this is surfaced rather
    than defaulted to page 0 — a chunk that cannot be cited must not be stored.
    """


class PageParseError(TransientError):
    """The backend dropped one or more pages of an otherwise readable document.

    Transient rather than permanent: the Docling PDF backend does this
    non-deterministically, and the same file converted twice in a row can yield
    pages ``[1, 3]`` and then ``[1, 2, 3]``. A silently missing page is a
    citation that can never be made, so it is raised rather than tolerated.
    """
