import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..contracts.enums import QueryRoute
from .router import classify_question


@dataclass
class RoutingExample:
    question: str
    expected_route: QueryRoute


def load_examples(path: Path) -> list[RoutingExample]:
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        examples.append(
            RoutingExample(
                question=row["question"],
                expected_route=QueryRoute(row["expected_route"]),
            )
        )

    return examples


@dataclass
class RoutingEvalResult:
    confusion: Counter  # (expected, predicted) -> count
    errors: list[tuple[str, str]]  # (question, error message)
    total: int

    @property
    def accuracy(self) -> float:
        correct = sum(
            count
            for (expected, predicted), count in self.confusion.items()
            if expected == predicted
        )

        return correct / self.total if self.total else 0.0

    def per_class(self) -> dict[str, dict[str, float]]:
        """Return precision/recall per route class."""
        classes = {expected for expected, _ in self.confusion} | {
            predicted for _, predicted in self.confusion
        }
        metrics = {}
        for route in sorted(classes):
            true_positive = self.confusion.get((route, route), 0)
            predicted_total = sum(
                count for (_, p), count in self.confusion.items() if p == route
            )
            actual_total = sum(
                count for (e, _), count in self.confusion.items() if e == route
            )
            precision = true_positive / predicted_total if predicted_total else 0.0
            recall = true_positive / actual_total if actual_total else 0.0
            metrics[route] = {
                "precision": precision,
                "recall": recall,
                "support": actual_total,
            }

        return metrics

    def render(self) -> str:
        lines = [f"accuracy: {self.accuracy:.1%} ({self.total} questions)"]
        if self.errors:
            lines.append(
                f"errors (call failed, not merely misrouted): {len(self.errors)}"
            )
        lines.append("")
        lines.append(f"{'class':<22}{'precision':>10}{'recall':>10}{'support':>9}")
        for route, metrics in self.per_class().items():
            lines.append(
                f"{route:<22}{metrics['precision']:>10.1%}{metrics['recall']:>10.1%}"
                f"{metrics['support']:>9}"
            )
        lines.append("")
        lines.append("confusion (expected -> predicted): count")
        for (expected, predicted), count in sorted(self.confusion.items()):
            marker = "" if expected == predicted else "  <-- MISROUTE"
            lines.append(f"  {expected} -> {predicted}: {count}{marker}")

        return "\n".join(lines)


async def evaluate(
    examples: list[RoutingExample], *, project_id: str
) -> RoutingEvalResult:
    confusion: Counter = Counter()
    errors: list[tuple[str, str]] = []

    for example in examples:
        try:
            result = await classify_question(example.question, project_id=project_id)
        except Exception as exc:  # noqa: BLE001 - record and continue the sweep
            errors.append((example.question, str(exc)))
            continue

        confusion[(example.expected_route.value, result.route.value)] += 1

    return RoutingEvalResult(confusion=confusion, errors=errors, total=len(examples))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions_path", type=Path)
    parser.add_argument("--project-id", default="eval")
    args = parser.parse_args()

    examples = load_examples(args.questions_path)
    result = asyncio.run(evaluate(examples, project_id=args.project_id))
    print(result.render())

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
