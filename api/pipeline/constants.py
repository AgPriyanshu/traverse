import re

from pydantic import BaseModel

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# Budget for one chunk, counted with BGE-M3's own tokenizer rather than a
# characters/4 estimate — prose with dialogue tokenizes differently enough that
# the error compounds into an overflow.
CHUNK_MAX_TOKENS = 1024


class ChapterInfoStructuredOutput(BaseModel):
    """The shape the heading classifier must return. Sent to the model as schema."""

    is_chapter: bool
    number: int | None = None
    title: str | None = None


class ChapterBatchStructuredOutput(BaseModel):
    """One classification per heading in a batch, in the same order sent."""

    items: list[ChapterInfoStructuredOutput]


CHAPTER_RE = re.compile(
    r"""
    ^\s*
    (?:chapter|chap\.?)
    \s+
    (?P<number>
        [IVXLCDM]+
        |
        \d+(?:\.\d+)*
    )
    (?:\s*[:.\-–—]\s*|\s+)?
    (?P<title>.*?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)
