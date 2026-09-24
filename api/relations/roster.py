import re
from dataclasses import dataclass, field
from uuid import UUID

from ..contracts.enums import ImportanceTier
from ..extraction.normalization import normalize, strip_honorifics, token_set_key

_TIER_RANK = {
    ImportanceTier.PROTAGONIST: 0,
    ImportanceTier.MAJOR: 1,
    ImportanceTier.MINOR: 2,
    ImportanceTier.MENTIONED: 3,
}

MAX_PROMPT_ROSTER = 80
_MAX_ALIASES_SHOWN = 6
_DESCRIPTOR_KEYS = ("occupation", "family_role", "description")
_MIN_FORM_CHARS = 3


@dataclass(frozen=True)
class RosterEntry:
    id: UUID
    canonical_name: str
    aliases: tuple[str, ...]
    tier: ImportanceTier
    descriptor: str = ""


@dataclass
class Roster:
    entries: list[RosterEntry]
    strategy: str = "full"
    _keys: dict[str, UUID | None] = field(default_factory=dict, repr=False)
    _forms: dict[UUID, list[re.Pattern[str]]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.entries = sorted(
            self.entries,
            key=lambda e: (_TIER_RANK[e.tier], e.canonical_name.casefold(), str(e.id)),
        )
        for entry in self.entries:
            self._index(entry)

    def _index(self, entry: RosterEntry) -> None:
        forms = {entry.canonical_name, *entry.aliases}
        patterns: dict[str, re.Pattern[str]] = {}
        for form in forms:
            for key in _keys_of(form):
                # A key two characters share resolves to nobody: guessing one
                # of them would attach an edge to the wrong person silently.
                if key in self._keys and self._keys[key] not in (entry.id, None):
                    self._keys[key] = None
                elif key not in self._keys:
                    self._keys[key] = entry.id

            stripped = strip_honorifics(form)
            if len(stripped) >= _MIN_FORM_CHARS:
                patterns[stripped] = re.compile(
                    rf"(?<!\w){re.escape(stripped)}(?!\w)", re.IGNORECASE
                )
        self._forms[entry.id] = [patterns[k] for k in sorted(patterns)]

    def resolve(self, name: str) -> UUID | None:
        """Map a surface form to a roster character, or ``None`` if off-roster.

        Uses the same normalisation as pass 1's alias cascade (``normalize``,
        ``strip_honorifics``, ``token_set_key``), in that order, so a form the
        cascade would have merged is never rejected here.

        Args:
            name: A subject or object name exactly as the model wrote it.
        """
        resolved = None
        for key in _keys_of(name):
            if key in self._keys:
                resolved = self._keys[key]
                break

        return resolved

    def mentions(self, text: str, character_id: UUID) -> bool:
        """Return whether ``text`` names the character by any known form."""
        found = any(p.search(text) for p in self._forms.get(character_id, ()))

        return found

    def mentioned_in(self, text: str) -> set[UUID]:
        """Return every roster character ``text`` names."""
        hits = {cid for cid in self._forms if self.mentions(text, cid)}

        return hits

    def prompt_block(self) -> str:
        """Render the roster deterministically for the stable prompt prefix.

        Names and aliases only. Pass 1 descriptors and tiers were tried and
        removed: the model copied descriptor lines verbatim as "quotes" and
        treated their guesses ("brother to Miss Bingley") as text evidence.
        """
        lines = []
        for entry in self.entries:
            aliases = sorted(
                (a for a in set(entry.aliases) if a != entry.canonical_name),
                key=lambda a: (len(a), a.casefold(), a),
            )[:_MAX_ALIASES_SHOWN]
            aka = f" (aka {'; '.join(aliases)})" if aliases else ""
            lines.append(f"- {entry.canonical_name}{aka}")

        block = "\n".join(lines)

        return block


def _keys_of(form: str) -> list[str]:
    keys: list[str] = []
    for candidate in (
        normalize(form),
        strip_honorifics(form),
        token_set_key(strip_honorifics(form)),
    ):
        if candidate and candidate not in keys:
            keys.append(candidate)

    return keys


def descriptor_from_attributes(attributes: dict) -> str:
    """Build a short descriptor from grounded pass-1 attributes."""
    parts = []
    for key in _DESCRIPTOR_KEYS:
        entry = attributes.get(key)
        value = entry.get("value") if isinstance(entry, dict) else entry
        if isinstance(value, str) and value.strip():
            parts.append(value.strip()[:60])

    descriptor = "; ".join(parts[:2])

    return descriptor


def choose_roster(entries: list[RosterEntry]) -> Roster:
    """Pick the roster strategy: everyone, or tier-filtered when it is too big.

    A roster over ``MAX_PROMPT_ROSTER`` drops the ``mentioned`` tier first,
    then ``minor``. The strategy is recorded on the roster because Sprint 8
    reports it as an ablation row. Dropped characters stay resolvable on the
    output side only if the model names them, which the prompt forbids.
    """
    ordered = sorted(entries, key=lambda e: _TIER_RANK[e.tier])
    strategy = "full"
    kept = ordered
    for cutoff in (ImportanceTier.MENTIONED, ImportanceTier.MINOR):
        if len(kept) <= MAX_PROMPT_ROSTER:
            break
        kept = [e for e in kept if e.tier is not cutoff]
        strategy = "tier_filtered"
    if len(kept) > MAX_PROMPT_ROSTER:
        kept = kept[:MAX_PROMPT_ROSTER]

    return Roster(entries=kept, strategy=strategy)
