from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from ..contracts.api import OntologyOut, OntologyPredicateOut
from ..contracts.enums import RelationFamily

ONTOLOGY_PATH = Path(__file__).with_name("ontology.yaml")


class OntologyError(ValueError):
    """Raised at import when the ontology file is malformed.

    Failing here rather than at first query is the point: a typo in an inverse
    must not surface as a missing edge three stages into an ingestion run.
    """


@dataclass(frozen=True)
class PredicateSpec:
    name: str
    family: RelationFamily
    inverse: str | None
    symmetric: bool
    extracted: bool


def _fail(message: str) -> OntologyError:
    return OntologyError(f"{ONTOLOGY_PATH.name}: {message}")


def _load_document(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise _fail(f"is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise _fail("must be a mapping at the top level")

    return raw


def _parse_predicates(document: dict[str, Any]) -> dict[str, PredicateSpec]:
    families = document.get("families")
    if not isinstance(families, dict) or not families:
        raise _fail("needs a non-empty `families` mapping")

    specs: dict[str, PredicateSpec] = {}
    for family_name, family_body in families.items():
        try:
            family = RelationFamily(family_name)
        except ValueError as exc:
            known = ", ".join(sorted(f.value for f in RelationFamily))
            raise _fail(
                f"unknown family {family_name!r}; RelationFamily declares {known}"
            ) from exc

        if not isinstance(family_body, dict):
            raise _fail(f"family {family_name!r} must be a mapping")

        predicates = family_body.get("predicates")
        if not isinstance(predicates, dict) or not predicates:
            raise _fail(
                f"family {family_name!r} needs a non-empty `predicates` mapping"
            )

        for name, body in predicates.items():
            if name in specs:
                raise _fail(
                    f"predicate {name!r} is declared twice "
                    f"({specs[name].family.value} and {family_name})"
                )
            if body is None:
                body = {}
            if not isinstance(body, dict):
                raise _fail(f"predicate {name!r} must be a mapping")

            symmetric = bool(body.get("symmetric", False))
            inverse = body.get("inverse")
            if inverse is not None and not isinstance(inverse, str):
                raise _fail(f"predicate {name!r} has a non-string `inverse`")

            specs[name] = PredicateSpec(
                name=name,
                family=family,
                inverse=inverse,
                symmetric=symmetric,
                extracted=bool(body.get("extracted", True)),
            )

    return specs


def _validate_predicates(specs: dict[str, PredicateSpec]) -> None:
    for spec in specs.values():
        if spec.inverse is not None and spec.inverse not in specs:
            raise _fail(
                f"predicate {spec.name!r} declares inverse {spec.inverse!r}, "
                "which is not declared anywhere in this file"
            )
        if spec.symmetric and spec.inverse != spec.name:
            raise _fail(
                f"predicate {spec.name!r} is symmetric, so its inverse must be "
                f"itself, not {spec.inverse!r}"
            )
        if spec.inverse is not None and not spec.symmetric:
            back = specs[spec.inverse]
            if back.inverse != spec.name:
                raise _fail(
                    f"inverse of {spec.name!r} is {spec.inverse!r}, but the inverse "
                    f"of {spec.inverse!r} is {back.inverse!r} — inverses must pair"
                )
            if back.family is not spec.family:
                raise _fail(
                    f"{spec.name!r} ({spec.family.value}) and its inverse "
                    f"{spec.inverse!r} ({back.family.value}) are in different families"
                )


def _parse_transitions(
    document: dict[str, Any], specs: dict[str, PredicateSpec]
) -> frozenset[tuple[str, str]]:
    raw = document.get("transitions") or []
    if not isinstance(raw, list):
        raise _fail("`transitions` must be a list")

    pairs: set[tuple[str, str]] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "from" not in entry or "to" not in entry:
            raise _fail(f"transition {entry!r} needs both `from` and `to`")
        source, target = entry["from"], entry["to"]
        for side in (source, target):
            if side not in specs:
                raise _fail(f"transition names unknown predicate {side!r}")
        if source == target:
            raise _fail(f"transition {source!r} -> {target!r} is a no-op")
        pairs.add((source, target))

    return frozenset(pairs)


_document = _load_document(ONTOLOGY_PATH)
_specs = _parse_predicates(_document)
_validate_predicates(_specs)
_transitions = _parse_transitions(_document, _specs)

VERSION: int = int(_document.get("version", 1))
PREDICATES: dict[str, PredicateSpec] = dict(sorted(_specs.items()))
TRANSITIONS: frozenset[tuple[str, str]] = _transitions

# Built at import from the YAML, so a new predicate is valid in the enum, the
# API and the prompt without touching Python.
Predicate = StrEnum("Predicate", {name.upper(): name for name in PREDICATES})


def is_predicate(value: str) -> bool:
    """Return whether ``value`` is a declared predicate.

    Args:
        value: Candidate predicate name, as emitted by extraction.
    """
    known = value in PREDICATES

    return known


def spec_of(predicate: str) -> PredicateSpec:
    """Return the full declaration for one predicate.

    Args:
        predicate: A declared predicate name.

    Raises:
        KeyError: If the predicate is not declared. Off-ontology predicates are
            invention and must not reach the graph.
    """
    try:
        spec = PREDICATES[predicate]
    except KeyError as exc:
        raise KeyError(f"unknown predicate: {predicate!r}") from exc

    return spec


def family_of(predicate: str) -> RelationFamily:
    """Return the family a predicate belongs to.

    Args:
        predicate: A declared predicate name.
    """
    return spec_of(predicate).family


def inverse_of(predicate: str) -> str | None:
    """Return the inverse predicate, or ``None`` when the relation is one-way.

    Args:
        predicate: A declared predicate name.
    """
    return spec_of(predicate).inverse


def is_symmetric(predicate: str) -> bool:
    """Return whether a predicate holds equally in both directions.

    Args:
        predicate: A declared predicate name.
    """
    return spec_of(predicate).symmetric


def is_extracted(predicate: str) -> bool:
    """Return whether pass 2 may emit this predicate.

    ``co_occurs_with`` is derived from scene participation, so a model that
    emits it is guessing at something already computed.

    Args:
        predicate: A declared predicate name.
    """
    return spec_of(predicate).extracted


def is_legal_transition(a: str, b: str) -> bool:
    """Return whether ``a`` superseded by ``b`` is a temporal change.

    A legal transition closes the earlier edge and opens a new one (F3.3).
    Anything else is a contradiction and routes to ``resolve_conflict`` review
    rather than a confidence tiebreak.

    Args:
        a: The earlier predicate.
        b: The later predicate.
    """
    legal = (a, b) in TRANSITIONS

    return legal


def predicates_in(family: RelationFamily) -> list[str]:
    """Return the declared predicates of one family, sorted.

    Args:
        family: The family to list.
    """
    names = sorted(name for name, spec in PREDICATES.items() if spec.family is family)

    return names


def families() -> list[RelationFamily]:
    """Return every family that declares at least one predicate, in PRD order."""
    declared = {spec.family for spec in PREDICATES.values()}
    ordered = [family for family in RelationFamily if family in declared]

    return ordered


def prompt_fragment(*, include_derived: bool = False) -> str:
    """Render the predicate list for the pass-2 extraction prompt.

    The prompt is generated from the same declaration the validator reads, so
    the two cannot drift apart — a predicate the prompt offers but the
    validator rejects is silently dropped evidence.

    This text is part of the vLLM prefix-cached stable prefix, so it must be
    byte-identical across every call for a book: it is sorted, never built from
    a set or dict iteration order.

    Args:
        include_derived: Include predicates marked ``extracted: false``.
            Off by default — pass 2 must not be invited to guess at
            ``co_occurs_with``.

    Returns:
        A newline-delimited block, one family heading per line followed by its
        predicates with direction and symmetry annotated.
    """
    lines: list[str] = []
    for family in families():
        names = [
            name
            for name in predicates_in(family)
            if include_derived or PREDICATES[name].extracted
        ]
        if not names:
            continue

        lines.append(f"{family.value}:")
        for name in names:
            spec = PREDICATES[name]
            if spec.symmetric:
                note = "symmetric"
            elif spec.inverse:
                note = f"inverse: {spec.inverse}"
            else:
                note = "one-way, no inverse"
            lines.append(f"  - {name} ({note})")

    fragment = "\n".join(lines)

    return fragment


def to_contract() -> OntologyOut:
    """Return the ontology in the shape the API and the web client consume.

    Returns:
        Every declared predicate with its family, inverse and symmetry, plus
        the family list the frontend colours edges by.
    """
    payload = OntologyOut(
        predicates=[
            OntologyPredicateOut(
                predicate=spec.name,
                family=spec.family,
                inverse=spec.inverse,
                symmetric=spec.symmetric,
            )
            for spec in PREDICATES.values()
        ],
        families=families(),
    )

    return payload
