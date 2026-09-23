"""S3.9 — Sprint 4 de-risk spike: relation extraction prototype.

THROWAWAY SCRIPT, NOT SHIPPED CODE. Exploratory scratch (this whole directory
is `ruff`-excluded, `pyproject.toml`'s `extend-exclude`). Findings are written
up in ``plans/sprint-3/HANDOFF.md``; this file exists so the numbers there are
reproducible, not just asserted.

What it does, for one chunk of *Pride and Prejudice* (chapter 1, real text
from Project Gutenberg #1342, fetched at run time — nothing here is
committed as corpus data):

1. Renders a roster into the pass-2 stable prefix, using the real
   ``ontology.prompt_fragment()`` plus a mix of real P&P character names and
   synthetic padding characters (to reach a stated roster size, since the
   real P&P cast is ~28 named characters and Sprint 4's worst case is a
   60-character roster).
2. Runs real pass-2-style extraction over the chunk via
   ``api.llm.structured.structured_call`` — real vLLM, real tokenizer, real
   Langfuse trace if configured. No mocks.
3. Repeats the call across several roster sizes and reads vLLM's own
   ``/metrics`` (``vllm:prefix_cache_{queries,hits}_total``) before and after
   to get a real prefix-cache hit rate, not an assumption.
4. Validates every extracted subject/object against the roster.

Run from the worktree root:

    cd api && MODELS_OFFLINE=1 uv run python notebooks/relation_extraction_spike.py
"""

import asyncio
import random
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field
from transformers import AutoTokenizer

from api.config.settings import settings
from api.contracts.enums import AssertionType, LLMPurpose, RelationFamily
from api.graph import ontology
from api.llm.errors import PermanentLLMError
from api.llm.structured import structured_call

GUTENBERG_URL = "https://www.gutenberg.org/files/1342/1342-0.txt"
CACHE_PATH = Path(__file__).with_name(".pride_and_prejudice_cache.txt")

# Real named cast, well past the point in the sprint where be1's own
# extraction exists — hand-picked from the text itself, not invented.
REAL_CHARACTERS: list[tuple[str, list[str], str]] = [
    ("Elizabeth Bennet", ["Elizabeth", "Lizzy", "Eliza"], "second Bennet daughter, sharp-witted"),
    ("Jane Bennet", ["Jane", "Miss Bennet"], "eldest Bennet daughter, gentle and lovely"),
    ("Mary Bennet", ["Mary"], "middle Bennet daughter, bookish"),
    ("Catherine Bennet", ["Kitty"], "fourth Bennet daughter"),
    ("Lydia Bennet", ["Lydia"], "youngest Bennet daughter, headstrong"),
    ("Mr. Bennet", ["Mr. Bennet"], "father of the five Bennet daughters"),
    ("Mrs. Bennet", ["Mrs. Bennet", "his wife", "her mother"], "mother, preoccupied with marrying off her daughters"),
    ("Fitzwilliam Darcy", ["Darcy", "Mr. Darcy"], "wealthy, proud gentleman of Pemberley"),
    ("Charles Bingley", ["Bingley", "Mr. Bingley"], "amiable gentleman who has just let Netherfield"),
    ("Caroline Bingley", ["Miss Bingley"], "Bingley's status-conscious sister"),
    ("Mrs. Long", ["Mrs. Long"], "Bennet family's neighbour and gossip"),
]

_PADDING_FIRST = [
    "Thomas", "Henry", "Charlotte", "Maria", "William", "Anne", "Louisa",
    "George", "Sarah", "Edward", "Frances", "Robert", "Harriet", "John",
    "Margaret", "James", "Emma", "Richard", "Caroline", "Frederick",
]
_PADDING_LAST = [
    "Hurst", "Denny", "King", "Goulding", "Purvis", "Harrington", "Robinson",
    "Forster", "Chamberlayne", "Stone", "Watson", "Pratt", "Long", "Morris",
]


class ExtractedRelation(BaseModel):
    """Pass-2's output shape — a local stand-in for S4's frozen contract.

    Not ``contracts/extraction.py`` — that file is orchestrator-owned and
    this is a spike, not a contract proposal.
    """

    subject: str = Field(description="Canonical name of the subject character.")
    predicate: str = Field(description="One predicate from the roster's ontology block.")
    object: str = Field(description="Canonical name of the object character.")
    assertion_type: AssertionType
    evidence_quote: str = Field(description="A short quote from the chunk supporting this.")
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    relations: list[ExtractedRelation] = Field(default_factory=list)


def fetch_chapter_one() -> str:
    """Return chapter 1's text, fetched once and cached on disk for reruns."""
    if CACHE_PATH.exists():
        text = CACHE_PATH.read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(GUTENBERG_URL, timeout=30) as response:  # noqa: S310
            text = response.read().decode("utf-8")
        CACHE_PATH.write_text(text, encoding="utf-8")

    start = text.find("It is a truth universally acknowledged")
    end = text.find("\n\nII.", start)
    if end == -1:
        end = start + 5500
    chunk = text[start:end].strip()
    chunk = chunk.replace("[Illustration]", "").replace("[Illustration:", "").strip()

    return chunk


def build_roster(size: int) -> list[tuple[str, list[str], str]]:
    """Return a roster of ``size`` characters: the real cast plus synthetic padding.

    Padding characters are clearly synthetic ("Thomas Hurst — minor
    acquaintance #3") so nothing here could be mistaken for a real finding
    about P&P's actual cast; they exist purely to test token budget at a
    stated roster size.
    """
    roster = list(REAL_CHARACTERS)
    rng = random.Random(42)
    seen = {name for name, _aliases, _desc in roster}
    n = 0
    while len(roster) < size:
        name = f"{rng.choice(_PADDING_FIRST)} {rng.choice(_PADDING_LAST)}"
        if name in seen:
            continue
        seen.add(name)
        n += 1
        roster.append((name, [], f"minor acquaintance #{n}"))

    return roster[:size]


def render_roster_block(roster: list[tuple[str, list[str], str]]) -> str:
    """Render the roster, sorted deterministically — the prefix-cache invariant."""
    lines = []
    for name, aliases, descriptor in sorted(roster, key=lambda item: item[0]):
        alias_part = f" (aka {', '.join(aliases)})" if aliases else ""
        lines.append(f"- {name}{alias_part}: {descriptor}")

    return "\n".join(lines)


def build_stable_prefix(roster: list[tuple[str, list[str], str]]) -> str:
    return (
        "You are extracting character relationships from a novel chunk.\n\n"
        "ONTOLOGY — use only these predicates, exactly as spelled:\n"
        f"{ontology.prompt_fragment()}\n\n"
        "ROSTER — every subject and object MUST be one of these canonical "
        "names, exactly as spelled. Never invent a name not on this list. "
        "If a relationship involves someone not on the roster, omit it.\n"
        f"{render_roster_block(roster)}\n\n"
        "Extract every stated or clearly implied relationship between two "
        "roster members in the chunk below. For each: subject, predicate, "
        "object, whether it is narrated fact or something a character said "
        "in dialogue, a short supporting quote, and your confidence.\n"
    )


def count_tokens(text: str) -> int:
    tokenizer = AutoTokenizer.from_pretrained(settings.llm_model)

    return len(tokenizer.encode(text))


def read_prefix_cache_counters() -> tuple[float, float]:
    """Return ``(queries, hits)`` in cached tokens, from vLLM's own /metrics."""
    url = settings.vllm_base_url.replace("/v1/", "/metrics")
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        body = response.read().decode("utf-8")

    queries = hits = 0.0
    for line in body.splitlines():
        if line.startswith("vllm:prefix_cache_queries_total"):
            queries = float(line.rsplit(" ", 1)[1])
        elif line.startswith("vllm:prefix_cache_hits_total"):
            hits = float(line.rsplit(" ", 1)[1])

    return queries, hits


async def run_extraction(prefix: str, chunk: str) -> ExtractionResult:
    prompt = f"{prefix}\nCHUNK:\n{chunk}\n"
    try:
        result = await structured_call(
            prompt,
            ExtractionResult,
            purpose=LLMPurpose.RELATION_EXTRACT,
            book_id="spike-pride-and-prejudice",
            stage="s3.9-spike",
        )
    except PermanentLLMError as exc:
        print(f"  extraction failed: {exc}")

        return ExtractionResult(relations=[])

    return result


async def main() -> None:
    chunk = fetch_chapter_one()
    print(f"chunk: {len(chunk)} chars\n")

    print("=" * 70)
    print("Q1 — how many characters fit?")
    print("=" * 70)
    for size in (11, 20, 30, 45, 60):
        roster = build_roster(size)
        prefix = build_stable_prefix(roster)
        prefix_tokens = count_tokens(prefix)
        chunk_tokens = count_tokens(chunk)
        total = prefix_tokens + chunk_tokens + settings.llm_output_reserve
        fits = total <= settings.llm_max_context
        print(
            f"  roster={size:>3}  prefix={prefix_tokens:>5} tok  "
            f"+chunk={chunk_tokens:>4} +reserve={settings.llm_output_reserve} "
            f"= {total:>5} tok  max={settings.llm_max_context}  "
            f"{'FITS' if fits else 'OVERFLOWS'}"
        )

    print()
    print("=" * 70)
    print("Q2 — does prefix caching engage? (roster=45, 4 calls, same prefix)")
    print("=" * 70)
    roster = build_roster(45)
    prefix = build_stable_prefix(roster)
    before_q, before_h = read_prefix_cache_counters()
    timings = []
    for i in range(4):
        start = time.monotonic()
        result = await run_extraction(prefix, chunk)
        elapsed = time.monotonic() - start
        timings.append(elapsed)
        print(f"  call {i + 1}: {elapsed:.2f}s, {len(result.relations)} relations")
    after_q, after_h = read_prefix_cache_counters()
    queried = after_q - before_q
    hit = after_h - before_h
    hit_rate = (hit / queried) if queried else float("nan")
    print(
        f"  prefix cache: queried={queried:.0f} tok, hit={hit:.0f} tok, "
        f"hit_rate={hit_rate:.1%}"
    )
    print(f"  call latency: first={timings[0]:.2f}s, "
          f"subsequent avg={sum(timings[1:]) / len(timings[1:]):.2f}s")

    print()
    print("=" * 70)
    print("Q3/Q4 — precision (eyeball) and off-roster invention, roster=20")
    print("=" * 70)
    roster20 = build_roster(20)
    prefix20 = build_stable_prefix(roster20)
    result = await run_extraction(prefix20, chunk)
    roster_names = {name for name, _a, _d in roster20}
    off_roster = 0
    for relation in result.relations:
        subject_ok = relation.subject in roster_names
        object_ok = relation.object in roster_names
        if not subject_ok or not object_ok:
            off_roster += 1
        flag = "" if (subject_ok and object_ok) else "  <-- OFF-ROSTER"
        print(
            f"  {relation.subject} --{relation.predicate}--> {relation.object} "
            f"[{relation.assertion_type.value}, conf={relation.confidence:.2f}] "
            f"quote={relation.evidence_quote!r}{flag}"
        )
    print(f"\n  total relations: {len(result.relations)}, off-roster: {off_roster}")


if __name__ == "__main__":
    asyncio.run(main())
