import re

from pydantic import BaseModel


class ChapterDetails(BaseModel):
    number: int | None = None
    title: str | None = None


class ChapterInfo(ChapterDetails):
    is_chapter: bool
    text: str | None = None


class ChapterInfoStructuredOutput(ChapterDetails):
    is_chapter: bool


class Chunk(BaseModel):
    text_embedding: list[float]
    text: str
    pages: list[int]
    page_start: int
    page_end: int
    chapter: ChapterDetails


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
