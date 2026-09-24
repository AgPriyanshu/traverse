"""Name normalisation shared by the alias cascade (S3.3) and collision guard (S3.4).

Cascade stages 1-3 (exact, honorific, nickname) are pure string operations —
no model call, no I/O — which is what makes them cheap enough to run before
anything expensive.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

_HONORIFICS_PATH = Path(__file__).parent / "honorifics.yaml"
_NICKNAMES_PATH = Path(__file__).parent / "nicknames.yaml"

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[.,;:!?'’‘\"()\[\]_*]")
_POSSESSIVE_RE = re.compile(r"['’]s\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _honorifics() -> tuple[frozenset[str], frozenset[str]]:
    data = yaml.safe_load(_HONORIFICS_PATH.read_text())
    prefixes = frozenset(str(p).lower() for p in data.get("prefixes", []))
    suffixes = frozenset(str(s).lower() for s in data.get("suffixes", []))

    return prefixes, suffixes


@lru_cache(maxsize=1)
def _nickname_lookup() -> dict[str, str]:
    """Return ``lowercase nickname -> lowercase canonical first name``.

    Inverted from the YAML's canonical-keyed shape so a lookup by whatever
    first token a surface form happens to carry is O(1).
    """
    data = yaml.safe_load(_NICKNAMES_PATH.read_text())
    lookup: dict[str, str] = {}

    for canonical, nicknames in data.items():
        canonical_lower = canonical.lower()
        lookup[canonical_lower] = canonical_lower
        for nickname in nicknames:
            lookup[nickname.lower()] = canonical_lower

    return lookup


def normalize(surface_form: str) -> str:
    """Fold case, punctuation and whitespace for exact-match clustering (stage 1)."""
    decomposed = unicodedata.normalize("NFKD", surface_form)
    stripped = _PUNCT_RE.sub("", _POSSESSIVE_RE.sub("", decomposed))
    collapsed = _WHITESPACE_RE.sub(" ", stripped).strip().lower()

    return collapsed


def strip_honorifics(surface_form: str) -> str:
    """Remove a leading title and a trailing suffixed honorific (stage 2).

    ``"Mr. Darcy"`` -> ``"darcy"``, ``"Kazu-san"`` -> ``"kazu"``. Leaves the
    input's token order untouched — order-independence is handled separately
    by :func:`token_set_key`, since collapsing both in one pass would hide
    which signal actually matched a given merge.
    """
    prefixes, suffixes = _honorifics()
    tokens = normalize(surface_form).split(" ")

    if tokens and tokens[0] in prefixes:
        tokens = tokens[1:]

    if tokens:
        last = tokens[-1]
        for suffix in suffixes:
            if last.endswith(f"-{suffix}") or last == suffix:
                head = last[: -(len(suffix) + 1)] if last.endswith(f"-{suffix}") else ""
                tokens[-1:] = [head] if head else []
                break

    return " ".join(t for t in tokens if t)


def token_set_key(surface_form: str) -> str:
    """A name-order-independent key: same tokens, sorted.

    ``"Tokita Kazu"`` and ``"Kazu Tokita"`` produce the same key. Deliberately
    not gated to a detected locale — a generic sorted-token comparison over
    two already-observed candidate surface forms is safe (a false positive
    would require the book to also use the reversed order as a distinct
    surface form, which does not happen by chance) and avoids a locale
    detector nobody has built.
    """
    core = strip_honorifics(surface_form)
    tokens = sorted(t for t in core.split(" ") if t)

    return " ".join(tokens)


@lru_cache(maxsize=1)
def _canonical_given_names() -> frozenset[str]:
    data = yaml.safe_load(_NICKNAMES_PATH.read_text())

    return frozenset(str(canonical).lower() for canonical in data)


def is_canonical_first_token(surface_form: str) -> bool:
    """Whether a surface form's first token is itself a canonical given name.

    Used to prefer "Elizabeth Bennet" over "Lizzy Bennet" as a cluster's
    canonical name when both forms are otherwise equally complete — a
    nickname is a fine alias, a poor canonical label.
    """
    core = strip_honorifics(surface_form)
    first_token = core.split(" ")[0] if core else ""

    return first_token in _canonical_given_names()


def nickname_key(surface_form: str) -> str:
    """A key that collapses a nickname's first token to its canonical form.

    ``"Lizzy Bennet"`` and ``"Elizabeth Bennet"`` produce the same key. Only
    the first token is folded — nicknames observed here are given-name
    diminutives, and folding a surname risks conflating two families.
    """
    core = strip_honorifics(surface_form)
    tokens = core.split(" ") if core else []

    if not tokens:
        return ""

    lookup = _nickname_lookup()
    tokens[0] = lookup.get(tokens[0], tokens[0])

    return " ".join(tokens)


GENDERED_TITLES = frozenset({"mr", "mrs", "miss", "ms", "master", "madam"})


def gendered_title(surface_form: str) -> str | None:
    """Return a leading Mr/Mrs/Miss-style title, which distinguishes people.

    "Mr. Darcy" and "Miss Darcy" are different characters, so the honorific
    stage must not fold them together the way it folds "Sir William" into
    "William".
    """
    tokens = normalize(surface_form).split(" ")
    title = tokens[0] if tokens and tokens[0] in GENDERED_TITLES else None

    return title


def titled_token_set_key(surface_form: str) -> str:
    """Like :func:`token_set_key`, but keeps a gendered title in the key."""
    key = f"{gendered_title(surface_form) or ''}|{token_set_key(surface_form)}"

    return key


def titled_nickname_key(surface_form: str) -> str:
    """Like :func:`nickname_key`, but keeps a gendered title in the key."""
    key = f"{gendered_title(surface_form) or ''}|{nickname_key(surface_form)}"

    return key


def content_tokens(surface_form: str) -> list[str]:
    """Name tokens with honorifics removed and the first token nickname-folded."""
    core = strip_honorifics(surface_form)
    tokens = core.split(" ") if core else []

    if tokens:
        tokens[0] = _nickname_lookup().get(tokens[0], tokens[0])

    return tokens


def honorific_of(surface_form: str) -> str | None:
    """Return a leading honorific of any kind (Mr, Lady, Colonel, Sir, ...)."""
    prefixes, _ = _honorifics()
    tokens = normalize(surface_form).split(" ")
    honorific = tokens[0] if tokens and tokens[0] in prefixes else None

    return honorific
