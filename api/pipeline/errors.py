from ..workers.errors import PermanentError


class DocumentParseError(PermanentError):
    """The file could not be converted. A corrupt PDF is corrupt on every attempt."""


class MissingProvenanceError(PermanentError):
    """A chunk came back with no page provenance.

    Page-exact citation is the product (PRD F1.3), so this is surfaced rather
    than defaulted to page 0 — a chunk that cannot be cited must not be stored.
    """
