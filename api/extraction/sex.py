from functools import lru_cache
from pathlib import Path

import yaml

from .normalization import content_tokens, normalize

_GIVEN_NAMES_PATH = Path(__file__).parent / "given_names.yaml"
_MALE_TITLES = frozenset({"mr", "sir", "lord", "master", "monsieur", "herr"})
_FEMALE_TITLES = frozenset(
    {"mrs", "miss", "ms", "lady", "madam", "madame", "dame", "mlle", "mme"}
)


@lru_cache(maxsize=1)
def _given_names() -> dict[str, str]:
    data = yaml.safe_load(_GIVEN_NAMES_PATH.read_text())
    lookup = {str(name).lower(): "m" for name in data.get("male", [])}
    lookup.update({str(name).lower(): "f" for name in data.get("female", [])})

    return lookup


def is_given_name(token: str) -> bool:
    """Whether a lowercase token is a known given name."""
    known = token.lower() in _given_names()

    return known


def form_sex(surface_form: str) -> str | None:
    """Infer ``"m"`` or ``"f"`` from a title or a known given name, else ``None``."""
    tokens = normalize(surface_form).split(" ")
    if tokens and tokens[0] in _MALE_TITLES:
        return "m"

    if tokens and tokens[0] in _FEMALE_TITLES:
        return "f"

    core = content_tokens(surface_form)
    inferred = _given_names().get(core[0]) if core else None

    return inferred


def cluster_sexes(forms: list[str]) -> set[str]:
    """Collect the sexes every surface form of a cluster implies."""
    sexes = {form_sex(form) for form in forms}
    sexes.discard(None)

    return sexes  # type: ignore[return-value]


def sex_conflict(forms_a: list[str], forms_b: list[str]) -> bool:
    """Whether two clusters are unambiguously of different sexes.

    Silent when either side is unknown or already internally mixed: the veto
    exists to stop "Mr. Bingley" joining "Caroline Bingley", not to guess.
    """
    sexes_a, sexes_b = cluster_sexes(forms_a), cluster_sexes(forms_b)
    conflict = len(sexes_a) == 1 and len(sexes_b) == 1 and sexes_a != sexes_b

    return conflict
