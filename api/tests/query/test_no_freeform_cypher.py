import ast
from pathlib import Path

import pytest

QUERY_PACKAGE = Path(__file__).resolve().parents[2] / "query"
ROUTES_FILE = Path(__file__).resolve().parents[2] / "routes" / "query.py"

_CYPHER_RUNNING_METHODS = {"run", "execute_query"}

# A query argument is safe when it is a bare reference (a module constant, or
# an attribute of one, like ``template.query``) or a literal string written
# inline. It is a violation when it is visibly *built* at call time: an
# f-string, a concatenation, or a ``.format()``/``%`` call — those are exactly
# the shapes a router- or model-authored value could smuggle text into.
_SAFE_ARG_TYPES = (ast.Name, ast.Attribute, ast.Constant)


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):  # an f-string
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add):
        return True

    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


class _CypherCallVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast visitor API
        # ``asyncio.run(...)`` is a real, unrelated stdlib call that happens to
        # share the method name ``run`` — narrow to calls whose receiver looks
        # like a Neo4j session/driver, never the ``asyncio`` module itself.
        receiver_is_asyncio = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
        )
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _CYPHER_RUNNING_METHODS
            and node.args
            and not receiver_is_asyncio
        ):
            first = node.args[0]
            if _is_dynamic_string(first) or not isinstance(first, _SAFE_ARG_TYPES):
                self.violations.append(
                    f"{self.path}:{node.lineno}: {node.func.attr}() called with a "
                    f"dynamically-built query ({ast.dump(first)[:60]}...)"
                )

        self.generic_visit(node)


def _check_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _CypherCallVisitor(path)
    visitor.visit(tree)

    return visitor.violations


def test_no_freeform_cypher_in_query_package():
    violations: list[str] = []
    for path in sorted(QUERY_PACKAGE.rglob("*.py")):
        violations.extend(_check_file(path))

    assert not violations, "\n".join(violations)


def test_no_freeform_cypher_in_query_route():
    assert not _check_file(ROUTES_FILE)


def test_templates_use_named_parameters_not_string_formatting():
    """Every declared template's ``query`` uses Cypher ``$params``, not ``.format()``.

    A doubled brace (``{{``) or a ``%s`` in a Cypher string is the fingerprint
    of a query built with string formatting rather than passed straight to
    the driver's own parameter binding.
    """
    from api.query.templates import TEMPLATES

    for template_id, template in TEMPLATES.items():
        assert isinstance(template.query, str), template_id
        assert "{{" not in template.query, template_id
        assert "%s" not in template.query, template_id
        assert "$" in template.query, f"{template_id}: no bound parameter at all"


@pytest.mark.asyncio
async def test_run_template_rejects_undeclared_slots():
    from api.query.templates import TemplateId, TemplateSlotError, run_template

    with pytest.raises(TemplateSlotError):
        await run_template(TemplateId.RELATIONSHIP_LOOKUP, not_a_real_slot="x")
