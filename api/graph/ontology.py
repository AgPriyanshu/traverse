from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from ..contracts.api import OntologyOut, OntologyPredicateOut
from ..contracts.enums import RelationFamily

ONTOLOGY_PATH = Path(__file__).with_name("ontology.yaml")


class OntologyError(ValueError):
    """Raised when the ontology file is malformed.

    It is raised at import, not at first query: a typo in an inverse must not
    surface as a missing edge three stages into an ingestion run.
    """


@dataclass(frozen=True)
class PredicateSpec:
    name: str
    family: RelationFamily
    inverse: str | None
    symmetric: bool
    extracted: bool


@dataclass(frozen=True)
class Ontology:
    version: int
    predicates: dict[str, PredicateSpec]
    transitions: frozenset[tuple[str, str]]

    def spec_of(self, predicate: str) -> PredicateSpec:
        """Return the full declaration for one predicate.

        Args:
            predicate: A declared predicate name.

        Raises:
            KeyError: If the predicate is not declared. An off-ontology
                predicate is invention and must not reach the graph.
        """
        try:
            spec = self.predicates[predicate]
        except KeyError as exc:
            raise KeyError(f"unknown predicate: {predicate!r}") from exc

        return spec

    def families(self) -> list[RelationFamily]:
        """Return every family declaring at least one predicate, in PRD order."""
        declared = {spec.family for spec in self.predicates.values()}
        ordered = [family for family in RelationFamily if family in declared]

        return ordered

    def predicates_in(self, family: RelationFamily) -> list[str]:
        """Return one family's declared predicates, sorted.

        Args:
            family: The family to list.
        """
        names = sorted(
            name for name, spec in self.predicates.items() if spec.family is family
        )

        return names

    def is_legal_transition(self, a: str, b: str) -> bool:
        """Return whether ``a`` superseded by ``b`` is a temporal change.

        Args:
            a: The earlier predicate.
            b: The later predicate.
        """
        legal = (a, b) in self.transitions

        return legal

    def prompt_fragment(self, *, include_derived: bool = False) -> str:
        """Render the predicate list for the pass-2 extraction prompt.

        The prompt is generated from the declaration the validator reads, so a
        predicate the prompt offers but the validator rejects cannot exist.

        This text is part of the vLLM prefix-cached stable prefix, so it must
        be byte-identical across every call for a book: it is sorted, never
        built from set or dict iteration order.

        Args:
            include_derived: Include predicates marked ``extracted: false``.
                Off by default — pass 2 must not be invited to guess at
                ``co_occurs_with``, which is computed from scene participation.

        Returns:
            A newline-delimited block: one family heading per line, then its
            predicates with direction and symmetry annotated.
        """
        lines: list[str] = []
        for family in self.families():
            names = [
                name
                for name in self.predicates_in(family)
                if include_derived or self.predicates[name].extracted
            ]
            if not names:
                continue

            lines.append(f"{family.value}:")
            for name in names:
                spec = self.predicates[name]
                if spec.symmetric:
                    note = "symmetric"
                elif spec.inverse:
                    note = f"inverse: {spec.inverse}"
                else:
                    note = "one-way, no inverse"
                lines.append(f"  - {name} ({note})")

        fragment = "\n".join(lines)

        return fragment

    def to_contract(self) -> OntologyOut:
        """Return the ontology in the shape the API and web client consume."""
        payload = OntologyOut(
            predicates=[
                OntologyPredicateOut(
                    predicate=spec.name,
                    family=spec.family,
                    inverse=spec.inverse,
                    symmetric=spec.symmetric,
                )
                for spec in self.predicates.values()
            ],
            families=self.families(),
        )

        return payload


def _fail(path: Path, message: str) -> OntologyError:
    return OntologyError(f"{path.name}: {message}")


def _load_document(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _fail(path, f"could not be read: {exc}") from exc
    except yaml.YAMLError as exc:
        raise _fail(path, f"is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise _fail(path, "must be a mapping at the top level")

    return raw


def _parse_predicates(path: Path, document: dict[str, Any]) -> dict[str, PredicateSpec]:
    families = document.get("families")
    if not isinstance(families, dict) or not families:
        raise _fail(path, "needs a non-empty `families` mapping")

    specs: dict[str, PredicateSpec] = {}
    for family_name, family_body in families.items():
        try:
            family = RelationFamily(family_name)
        except ValueError as exc:
            known = ", ".join(sorted(item.value for item in RelationFamily))
            raise _fail(
                path, f"unknown family {family_name!r}; RelationFamily declares {known}"
            ) from exc

        if not isinstance(family_body, dict):
            raise _fail(path, f"family {family_name!r} must be a mapping")

        predicates = family_body.get("predicates")
        if not isinstance(predicates, dict) or not predicates:
            raise _fail(
                path, f"family {family_name!r} needs a non-empty `predicates` mapping"
            )

        for name, raw_body in predicates.items():
            if name in specs:
                raise _fail(
                    path,
                    f"predicate {name!r} is declared twice "
                    f"({specs[name].family.value} and {family_name})",
                )
            body = {} if raw_body is None else raw_body
            if not isinstance(body, dict):
                raise _fail(path, f"predicate {name!r} must be a mapping")

            inverse = body.get("inverse")
            if inverse is not None and not isinstance(inverse, str):
                raise _fail(path, f"predicate {name!r} has a non-string `inverse`")

            specs[name] = PredicateSpec(
                name=name,
                family=family,
                inverse=inverse,
                symmetric=bool(body.get("symmetric", False)),
                extracted=bool(body.get("extracted", True)),
            )

    return specs


def _validate_predicates(path: Path, specs: dict[str, PredicateSpec]) -> None:
    for spec in specs.values():
        if spec.inverse is not None and spec.inverse not in specs:
            raise _fail(
                path,
                f"predicate {spec.name!r} declares inverse {spec.inverse!r}, "
                "which is not declared anywhere in this file",
            )
        if spec.symmetric and spec.inverse != spec.name:
            raise _fail(
                path,
                f"predicate {spec.name!r} is symmetric, so its inverse must be "
                f"itself, not {spec.inverse!r}",
            )
        if spec.inverse is not None and not spec.symmetric:
            back = specs[spec.inverse]
            if back.inverse != spec.name:
                raise _fail(
                    path,
                    f"inverse of {spec.name!r} is {spec.inverse!r}, but the inverse "
                    f"of {spec.inverse!r} is {back.inverse!r} — inverses must pair",
                )
            if back.family is not spec.family:
                raise _fail(
                    path,
                    f"{spec.name!r} ({spec.family.value}) and its inverse "
                    f"{spec.inverse!r} ({back.family.value}) are in different families",
                )


def _parse_transitions(
    path: Path, document: dict[str, Any], specs: dict[str, PredicateSpec]
) -> frozenset[tuple[str, str]]:
    raw = document.get("transitions") or []
    if not isinstance(raw, list):
        raise _fail(path, "`transitions` must be a list")

    pairs: set[tuple[str, str]] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "from" not in entry or "to" not in entry:
            raise _fail(path, f"transition {entry!r} needs both `from` and `to`")
        source, target = entry["from"], entry["to"]
        for side in (source, target):
            if side not in specs:
                raise _fail(path, f"transition names unknown predicate {side!r}")
        if source == target:
            raise _fail(path, f"transition {source!r} -> {target!r} is a no-op")
        pairs.add((source, target))

    return frozenset(pairs)


def load(path: Path | str = ONTOLOGY_PATH) -> Ontology:
    """Parse and validate an ontology file.

    Args:
        path: The YAML file to read. Defaults to the shipped ``ontology.yaml``.

    Returns:
        The validated ontology.

    Raises:
        OntologyError: If the file is unreadable, malformed, or declares an
            inverse, family or transition that does not resolve.
    """
    path = Path(path)
    document = _load_document(path)
    specs = _parse_predicates(path, document)
    _validate_predicates(path, specs)
    transitions = _parse_transitions(path, document, specs)

    version = document.get("version", 1)
    if not isinstance(version, int):
        raise _fail(path, f"`version` must be an integer, not {version!r}")

    return Ontology(
        version=version,
        predicates=dict(sorted(specs.items())),
        transitions=transitions,
    )


def build_predicate_enum(ontology: "Ontology") -> type[StrEnum]:
    """Build the ``Predicate`` enum from a loaded ontology.

    Args:
        ontology: The ontology to derive members from.
    """
    return StrEnum("Predicate", {name.upper(): name for name in ontology.predicates})


ONTOLOGY: Ontology = load()
VERSION: int = ONTOLOGY.version
PREDICATES: dict[str, PredicateSpec] = ONTOLOGY.predicates
TRANSITIONS: frozenset[tuple[str, str]] = ONTOLOGY.transitions

# Built at import from the YAML, so a new predicate is valid in the enum, the
# API and the prompt without touching Python.
Predicate = build_predicate_enum(ONTOLOGY)


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
        KeyError: If the predicate is not declared.
    """
    return ONTOLOGY.spec_of(predicate)


def family_of(predicate: str) -> RelationFamily:
    """Return the family a predicate belongs to.

    Args:
        predicate: A declared predicate name.
    """
    return ONTOLOGY.spec_of(predicate).family


def inverse_of(predicate: str) -> str | None:
    """Return the inverse predicate, or ``None`` when the relation is one-way.

    Args:
        predicate: A declared predicate name.
    """
    return ONTOLOGY.spec_of(predicate).inverse


def is_symmetric(predicate: str) -> bool:
    """Return whether a predicate holds equally in both directions.

    Args:
        predicate: A declared predicate name.
    """
    return ONTOLOGY.spec_of(predicate).symmetric


def is_extracted(predicate: str) -> bool:
    """Return whether pass 2 may emit this predicate.

    ``co_occurs_with`` is derived from scene participation, so a model emitting
    it is guessing at something already computed.

    Args:
        predicate: A declared predicate name.
    """
    return ONTOLOGY.spec_of(predicate).extracted


def is_legal_transition(a: str, b: str) -> bool:
    """Return whether ``a`` superseded by ``b`` is a temporal change.

    A legal transition closes the earlier edge and opens a new one (F3.3).
    Anything else is a contradiction and routes to ``resolve_conflict`` review
    rather than a confidence tiebreak.

    Args:
        a: The earlier predicate.
        b: The later predicate.
    """
    return ONTOLOGY.is_legal_transition(a, b)


def predicates_in(family: RelationFamily) -> list[str]:
    """Return the declared predicates of one family, sorted.

    Args:
        family: The family to list.
    """
    return ONTOLOGY.predicates_in(family)


def families() -> list[RelationFamily]:
    """Return every family that declares at least one predicate, in PRD order."""
    return ONTOLOGY.families()


def prompt_fragment(*, include_derived: bool = False) -> str:
    """Render the predicate list for the pass-2 extraction prompt.

    Args:
        include_derived: Include predicates marked ``extracted: false``.

    Returns:
        A newline-delimited block, stable byte-for-byte across calls.
    """
    return ONTOLOGY.prompt_fragment(include_derived=include_derived)


def to_contract() -> OntologyOut:
    """Return the ontology in the shape the API and the web client consume."""
    return ONTOLOGY.to_contract()
