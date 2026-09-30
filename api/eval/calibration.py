import math
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import CalibrationBinOut, CalibrationModelOut
from ..contracts.enums import ReviewTaskType
from ..db.models.ops_model import CalibrationModel
from ..db.models.review_model import CorrectionFeedback

# Below this many labelled samples, a fitted curve is noise, not a
# measurement — report the sample size and stop (S8.3's brief, PRD F2.2).
MIN_SAMPLES_TO_FIT = 10
DEFAULT_BIN_COUNT = 10
OVERALL_TASK_TYPE = "overall"

_CORRECT_BY_DECISION: dict[ReviewTaskType, dict[str, bool]] = {
    ReviewTaskType.MERGE_CHARACTERS: {"merge": True, "keep_separate": False},
    ReviewTaskType.MERGE_ACROSS_BOOKS: {"merge": True, "keep_separate": False},
    ReviewTaskType.CONFIRM_RELATION: {
        "accept": True,
        "reject": False,
        "change_predicate": False,
    },
}


def label_correctness(feedback: CorrectionFeedback) -> bool | None:
    """Whether ``feedback`` shows the model's decision-time belief held up.

    Returns ``None`` when ``feedback.task_type`` has no declared mapping
    above, or its recorded decision isn't in that mapping — both mean
    "cannot say", never "incorrect".
    """
    mapping = _CORRECT_BY_DECISION.get(feedback.task_type)
    if mapping is None:
        return None

    decision = (feedback.human_value or {}).get("decision")

    return mapping.get(decision)


@dataclass(frozen=True)
class LabelledSample:
    confidence: float
    correct: bool


async def load_labelled_feedback(
    session: SQLModelAsyncSession, *, task_type: ReviewTaskType | None = None
) -> list[LabelledSample]:
    """Return every feedback row with both a confidence and a defined label.

    Args:
        session: An open database session.
        task_type: Restrict to one task type. ``None`` pools every type this
            module knows how to label into one number — only meaningful as a
            coarse, whole-project figure; the per-type fit is what most needs
            the careful accounting, since confidence means a different thing
            for each ``task_type``.
    """
    statement = select(CorrectionFeedback).where(
        CorrectionFeedback.model_confidence.is_not(None)
    )
    if task_type is not None:
        statement = statement.where(CorrectionFeedback.task_type == task_type)

    rows = (await session.exec(statement)).all()

    samples: list[LabelledSample] = []
    for row in rows:
        correct = label_correctness(row)
        if correct is None:
            continue
        samples.append(LabelledSample(confidence=row.model_confidence, correct=correct))

    return samples


def _bin_count_for(n: int) -> int:
    """Fewer bins for fewer samples — an empty bin says nothing an absent
    one didn't, and 10 near-empty bins over 12 samples is noise dressed up
    as a curve."""
    return max(1, min(DEFAULT_BIN_COUNT, n // 3))


def reliability_diagram(
    samples: list[LabelledSample], *, n_bins: int | None = None
) -> tuple[list[CalibrationBinOut], float]:
    """Bin ``samples`` by confidence and return the table plus its ECE.

    Empty bins contribute nothing to either the table or the sum — a bin
    with no samples has no confidence to compare against no accuracy.
    """
    if not samples:
        return [], 0.0

    bins_n = n_bins or _bin_count_for(len(samples))
    buckets: list[list[LabelledSample]] = [[] for _ in range(bins_n)]
    for sample in samples:
        # A confidence of exactly 1.0 would otherwise index one past the
        # last bin.
        index = min(int(sample.confidence * bins_n), bins_n - 1)
        buckets[index].append(sample)

    total = len(samples)
    rows: list[CalibrationBinOut] = []
    ece = 0.0
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        mean_confidence = sum(s.confidence for s in bucket) / len(bucket)
        accuracy = sum(1 for s in bucket if s.correct) / len(bucket)
        rows.append(
            CalibrationBinOut(
                confidence_lower=index / bins_n,
                confidence_upper=(index + 1) / bins_n,
                predicted_confidence=mean_confidence,
                observed_accuracy=accuracy,
                sample_size=len(bucket),
            )
        )
        ece += (len(bucket) / total) * abs(accuracy - mean_confidence)

    return rows, ece


def _sigmoid(x: float) -> float:
    if x < -700:  # guards math.exp overflow on a large negative argument
        return 0.0

    return 1.0 / (1.0 + math.exp(-x))


def fit_platt(
    samples: list[LabelledSample], *, lr: float = 0.1, iters: int = 500
) -> tuple[float, float]:
    """Fit ``P(correct) = sigmoid(a * confidence + b)`` by gradient descent.

    Pure Python, no numpy/scipy — see the module docstring. Plain batch
    gradient descent is enough at this scale: Sprint 7's feedback volume is
    dozens of rows, not millions.
    """
    a, b = 1.0, 0.0
    n = len(samples)
    if n == 0:
        return a, b

    for _ in range(iters):
        grad_a = 0.0
        grad_b = 0.0
        for sample in samples:
            prediction = _sigmoid(a * sample.confidence + b)
            error = prediction - (1.0 if sample.correct else 0.0)
            grad_a += error * sample.confidence
            grad_b += error
        a -= lr * grad_a / n
        b -= lr * grad_b / n

    return a, b


def platt_predict(params: tuple[float, float], confidence: float) -> float:
    a, b = params

    return _sigmoid(a * confidence + b)


def fit_isotonic(samples: list[LabelledSample]) -> list[tuple[float, float, float]]:
    """Fit a monotonic step calibrator by the pool-adjacent-violators algorithm.

    Standard isotonic regression under squared-error loss on the 0/1 outcome,
    sorted by raw confidence. Returns ascending ``(x_min, x_max,
    calibrated_value)`` triples, one per pooled group, covering every input
    confidence exactly once.
    """
    ordered = sorted(samples, key=lambda s: s.confidence)
    values: list[float] = []
    weights: list[int] = []
    groups: list[list[float]] = []

    for sample in ordered:
        values.append(1.0 if sample.correct else 0.0)
        weights.append(1)
        groups.append([sample.confidence])
        while len(values) > 1 and values[-2] > values[-1]:
            v2, w2, g2 = values.pop(), weights.pop(), groups.pop()
            v1, w1, g1 = values.pop(), weights.pop(), groups.pop()
            pooled_value = (v1 * w1 + v2 * w2) / (w1 + w2)
            values.append(pooled_value)
            weights.append(w1 + w2)
            groups.append(g1 + g2)

    return [
        (min(group), max(group), value)
        for group, value in zip(groups, values, strict=True)
    ]


def isotonic_predict(
    thresholds: list[tuple[float, float, float]], confidence: float
) -> float:
    if not thresholds:
        return confidence

    for _lower, upper, value in thresholds:
        if confidence <= upper:
            return value

    return thresholds[-1][2]


@dataclass(frozen=True)
class CalibrationFit:
    """Both calibrators' results, so the caller can report each per S8.3's brief."""

    task_type: str
    fitted_on_n: int
    bins: list[CalibrationBinOut]
    ece_before: float
    ece_after_platt: float
    ece_after_isotonic: float
    platt_params: tuple[float, float]
    isotonic_thresholds: list[tuple[float, float, float]]

    @property
    def ece_after(self) -> float:
        """The better of the two fitted calibrators — reported as the
        headline "after" number; both are still recorded on this dataclass."""
        return min(self.ece_after_platt, self.ece_after_isotonic)


def fit_calibration(
    samples: list[LabelledSample], *, task_type: str
) -> CalibrationFit | None:
    """Fit both calibrators on ``samples`` and score each by ECE.

    Returns:
        ``None`` when there are fewer than ``MIN_SAMPLES_TO_FIT`` samples.
    """
    if len(samples) < MIN_SAMPLES_TO_FIT:
        return None

    bins, ece_before = reliability_diagram(samples)

    platt_params = fit_platt(samples)
    platt_samples = [
        LabelledSample(
            confidence=platt_predict(platt_params, s.confidence), correct=s.correct
        )
        for s in samples
    ]
    _, ece_after_platt = reliability_diagram(platt_samples)

    isotonic_thresholds = fit_isotonic(samples)
    isotonic_samples = [
        LabelledSample(
            confidence=isotonic_predict(isotonic_thresholds, s.confidence),
            correct=s.correct,
        )
        for s in samples
    ]
    _, ece_after_isotonic = reliability_diagram(isotonic_samples)

    return CalibrationFit(
        task_type=task_type,
        fitted_on_n=len(samples),
        bins=bins,
        ece_before=ece_before,
        ece_after_platt=ece_after_platt,
        ece_after_isotonic=ece_after_isotonic,
        platt_params=platt_params,
        isotonic_thresholds=isotonic_thresholds,
    )


async def _next_version(session: SQLModelAsyncSession, task_type: str) -> int:
    result = await session.exec(
        select(func.max(CalibrationModel.version)).where(
            CalibrationModel.task_type == task_type
        )
    )
    current = result.first()

    return (current or 0) + 1


async def fit_and_store(
    session: SQLModelAsyncSession, *, task_type: ReviewTaskType | None = None
) -> CalibrationModelOut | None:
    """Fit a calibrator for ``task_type`` (or every known type pooled) and persist it.

    Args:
        session: An open database session.
        task_type: One review task type, or ``None`` to pool every type
            ``label_correctness`` can label into one number, stored with
            ``task_type="overall"``.

    Returns:
        The persisted model, as its API contract shape, or ``None`` when
        there was not enough labelled feedback to fit — call
        ``load_labelled_feedback`` directly to still report the sample size
        in that case (S8.3's brief: say so, don't fit noise).
    """
    samples = await load_labelled_feedback(session, task_type=task_type)
    label = task_type.value if task_type is not None else OVERALL_TASK_TYPE
    fit = fit_calibration(samples, task_type=label)
    if fit is None:
        return None

    version = await _next_version(session, label)
    row = CalibrationModel(
        task_type=label,
        version=version,
        bins={"rows": [b.model_dump() for b in fit.bins]},
        ece_before=fit.ece_before,
        ece_after=fit.ece_after,
        fitted_on_n=fit.fitted_on_n,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return CalibrationModelOut(
        task_type=row.task_type,
        version=row.version,
        bins=fit.bins,
        ece_before=row.ece_before,
        ece_after=row.ece_after,
        fitted_on_n=row.fitted_on_n,
    )


async def fit_all(
    session: SQLModelAsyncSession,
) -> dict[str, CalibrationModelOut | None]:
    """Fit every task type this module can label, plus an overall pooled fit.

    Returns:
        Mapping from a ``ReviewTaskType`` value (or ``"overall"``) to its
        fitted, persisted model — or ``None`` for a type/pool that did not
        reach ``MIN_SAMPLES_TO_FIT`` labelled rows.
    """
    results: dict[str, CalibrationModelOut | None] = {}
    for task_type in _CORRECT_BY_DECISION:
        results[task_type.value] = await fit_and_store(session, task_type=task_type)
    results[OVERALL_TASK_TYPE] = await fit_and_store(session, task_type=None)

    return results
