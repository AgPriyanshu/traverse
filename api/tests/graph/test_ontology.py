import textwrap
from pathlib import Path

import pytest

from api.contracts.enums import RelationFamily
from api.graph import ontology
from api.graph.ontology import build_predicate_enum, load


def _load(tmp_path: Path, body: str):
    """Load a throwaway ontology file.

    Args:
        tmp_path: Directory to write the file into.
        body: YAML content.

    Returns:
        The parsed ``Ontology``.
    """
    path = tmp_path / "ontology.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")

    return load(path)


MINIMAL = """\
version: 1
families:
  kinship:
    predicates:
      parent_of: {inverse: child_of, symmetric: false}
      child_of: {inverse: parent_of, symmetric: false}
transitions: []
"""

EXTRA_FAMILY = """\
  social:
    predicates:
      drinking_companion_of: {inverse: drinking_companion_of, symmetric: true}
"""


def test_every_prd_family_is_declared():
    assert set(ontology.families()) == set(RelationFamily)


def test_prd_f31_predicates_are_all_present():
    """The predicate table in PRD F3.1, verbatim."""
    required = {
        RelationFamily.KINSHIP: {
            "parent_of",
            "child_of",
            "sibling_of",
            "grandparent_of",
            "in_law_of",
            "guardian_of",
            "adopted_by",
        },
        RelationFamily.ROMANTIC: {
            "married_to",
            "engaged_to",
            "lover_of",
            "former_partner_of",
            "unrequited_love_for",
        },
        RelationFamily.SOCIAL: {
            "friend_of",
            "acquaintance_of",
            "neighbour_of",
            "colleague_of",
            "employer_of",
            "mentor_of",
            "customer_of",
        },
        RelationFamily.ADVERSARIAL: {"rival_of", "enemy_of", "betrayed", "deceives"},
        RelationFamily.STRUCTURAL: {"co_occurs_with"},
    }
    for family, names in required.items():
        assert names <= set(ontology.predicates_in(family)), family


def test_enum_matches_the_yaml():
    assert {member.value for member in ontology.Predicate} == set(ontology.PREDICATES)


def test_symmetry_and_inverses():
    assert ontology.is_symmetric("sibling_of")
    assert ontology.inverse_of("sibling_of") == "sibling_of"
    assert ontology.inverse_of("parent_of") == "child_of"
    assert ontology.inverse_of("child_of") == "parent_of"
    assert ontology.family_of("parent_of") is RelationFamily.KINSHIP

    # Asymmetric by definition — the point is that it is not returned.
    assert ontology.inverse_of("unrequited_love_for") is None
    assert not ontology.is_symmetric("unrequited_love_for")


def test_co_occurs_with_is_derived_not_extracted():
    assert not ontology.is_extracted("co_occurs_with")
    assert "co_occurs_with" not in ontology.prompt_fragment()
    assert "co_occurs_with" in ontology.prompt_fragment(include_derived=True)


def test_legal_transitions_are_directional():
    assert ontology.is_legal_transition("engaged_to", "married_to")
    assert not ontology.is_legal_transition("married_to", "engaged_to")
    assert ontology.is_legal_transition("friend_of", "enemy_of")
    # Not a temporal transition — a contradiction, which routes to review.
    assert not ontology.is_legal_transition("parent_of", "child_of")


def test_unknown_predicate_raises():
    assert not ontology.is_predicate("best_mates_with")
    with pytest.raises(KeyError):
        ontology.family_of("best_mates_with")


def test_prompt_fragment_is_byte_stable():
    """The pass-2 stable prefix must be byte-identical across calls.

    A dict-ordering change here silently halves the vLLM prefix cache hit rate
    with no error anywhere.
    """
    fragment = ontology.prompt_fragment()

    assert fragment == ontology.prompt_fragment()
    assert fragment == load().prompt_fragment()

    lines = fragment.splitlines()
    assert lines[0] == "kinship:"

    families_seen = [line.rstrip(":") for line in lines if not line.startswith("  - ")]
    # `structural` is absent: its only predicate is derived, so the prompt must
    # not offer it.
    assert families_seen == ["kinship", "romantic", "social", "adversarial"]

    kinship_names = [
        line.removeprefix("  - ").split(" ")[0]
        for line in lines[1 : 1 + len(ontology.predicates_in(RelationFamily.KINSHIP))]
    ]
    assert kinship_names == sorted(kinship_names)


def test_contract_round_trip_covers_every_predicate():
    payload = ontology.to_contract()

    assert len(payload.predicates) == len(ontology.PREDICATES)
    assert set(payload.families) == set(RelationFamily)
    by_name = {item.predicate: item for item in payload.predicates}
    assert by_name["sibling_of"].symmetric is True
    assert by_name["parent_of"].inverse == "child_of"
    assert by_name["unrequited_love_for"].inverse is None
    assert by_name["co_occurs_with"].family is RelationFamily.STRUCTURAL


def test_adding_a_predicate_needs_no_python_change(tmp_path):
    """S1.5 acceptance: YAML in; enum, API and prompt out, with no code edit."""
    body = MINIMAL.replace("transitions: []\n", EXTRA_FAMILY + "transitions: []\n")
    loaded = _load(tmp_path, body)
    predicate_enum = build_predicate_enum(loaded)

    assert "drinking_companion_of" in loaded.predicates
    assert predicate_enum("drinking_companion_of")
    assert loaded.spec_of("drinking_companion_of").symmetric
    assert loaded.spec_of("drinking_companion_of").family is RelationFamily.SOCIAL
    assert "drinking_companion_of" in loaded.prompt_fragment()
    names = {item.predicate for item in loaded.to_contract().predicates}
    assert "drinking_companion_of" in names


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("families: [not, a, mapping]\n", "non-empty `families` mapping"),
        (
            "families:\n  kinship:\n    predicates:\n"
            "      parent_of: {inverse: nobody_of}\n",
            "not declared anywhere",
        ),
        (
            "families:\n  kinship:\n    predicates:\n"
            "      sibling_of: {inverse: parent_of, symmetric: true}\n"
            "      parent_of: {inverse: sibling_of}\n",
            "its inverse must be",
        ),
        (
            "families:\n  invented_family:\n    predicates:\n      x: {}\n",
            "unknown family",
        ),
        ("families:\n  kinship: {}\n", "non-empty `predicates` mapping"),
        ("just: a string: broken\n   indent\n", "not valid YAML"),
        ("- a\n- list\n", "mapping at the top level"),
    ],
)
def test_malformed_yaml_fails_with_a_clear_message(tmp_path, body, expected):
    with pytest.raises(ontology.OntologyError) as excinfo:
        _load(tmp_path, body)

    assert expected in str(excinfo.value)
    assert "ontology.yaml" in str(excinfo.value)


def test_transition_naming_an_unknown_predicate_is_rejected(tmp_path):
    with pytest.raises(ontology.OntologyError) as excinfo:
        _load(
            tmp_path,
            MINIMAL.replace(
                "transitions: []",
                "transitions:\n  - {from: parent_of, to: not_a_predicate}",
            ),
        )

    assert "unknown predicate" in str(excinfo.value)


def test_inverse_pointing_into_another_family_is_rejected(tmp_path):
    with pytest.raises(ontology.OntologyError) as excinfo:
        _load(
            tmp_path,
            """
            version: 1
            families:
              kinship:
                predicates:
                  parent_of: {inverse: friend_of}
              social:
                predicates:
                  friend_of: {inverse: parent_of}
            """,
        )

    assert "different families" in str(excinfo.value)


def test_the_shipped_file_loads():
    """The module-level load must be the same object the helpers delegate to."""
    reloaded = load()

    assert reloaded.predicates.keys() == ontology.PREDICATES.keys()
    assert reloaded.transitions == ontology.TRANSITIONS
