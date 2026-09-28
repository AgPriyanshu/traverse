import uuid

import pytest

from api.contracts.enums import ReviewTaskType
from api.db.models.review_model import CorrectionFeedback
from api.eval import calibration


def _feedback(
    *,
    project_id,
    task_type: ReviewTaskType,
    decision: str,
    confidence: float | None,
) -> CorrectionFeedback:
    return CorrectionFeedback(
        project_id=project_id,
        task_type=task_type,
        model_value={"confidence": confidence},
        human_value={"decision": decision, "payload": {}},
        model_confidence=confidence,
    )


class TestLabelCorrectness:
    def test_merge_confirms_the_models_flagged_match(self):
        feedback = _feedback(
            project_id=uuid.uuid4(),
            task_type=ReviewTaskType.MERGE_CHARACTERS,
            decision="merge",
            confidence=0.8,
        )

        assert calibration.label_correctness(feedback) is True

    def test_keep_separate_overrides_the_models_flagged_match(self):
        feedback = _feedback(
            project_id=uuid.uuid4(),
            task_type=ReviewTaskType.MERGE_CHARACTERS,
            decision="keep_separate",
            confidence=0.8,
        )

        assert calibration.label_correctness(feedback) is False

    def test_confirm_relation_change_predicate_counts_as_incorrect(self):
        """The specific predicate the model claimed was wrong, even though a
        relation between the pair does hold in some form."""
        feedback = _feedback(
            project_id=uuid.uuid4(),
            task_type=ReviewTaskType.CONFIRM_RELATION,
            decision="change_predicate",
            confidence=0.4,
        )

        assert calibration.label_correctness(feedback) is False

    def test_resolve_conflict_has_no_defined_label(self):
        """Which candidate the human kept isn't "was one specific model
        belief right" -- deliberately excluded, not guessed at."""
        feedback = _feedback(
            project_id=uuid.uuid4(),
            task_type=ReviewTaskType.RESOLVE_CONFLICT,
            decision="accept",
            confidence=0.5,
        )

        assert calibration.label_correctness(feedback) is None

    def test_unrecognised_decision_has_no_defined_label(self):
        feedback = _feedback(
            project_id=uuid.uuid4(),
            task_type=ReviewTaskType.MERGE_CHARACTERS,
            decision="something_new_fe1_invented",
            confidence=0.8,
        )

        assert calibration.label_correctness(feedback) is None


class TestReliabilityDiagram:
    def test_perfectly_calibrated_confidence_has_zero_ece(self):
        samples = [
            calibration.LabelledSample(confidence=0.5, correct=i < 5)
            for i in range(10)
        ] + [
            calibration.LabelledSample(confidence=0.9, correct=i < 9)
            for i in range(10)
        ]

        bins, ece = calibration.reliability_diagram(samples, n_bins=10)

        assert ece == pytest.approx(0.0, abs=1e-9)
        assert sum(b.sample_size for b in bins) == 20

    def test_overconfident_model_has_nonzero_ece_matching_the_gap(self):
        # confidence=0.9 but only 50% actually correct -- a 0.4 gap, over
        # every sample, so ECE is exactly 0.4 regardless of bin count.
        samples = [
            calibration.LabelledSample(confidence=0.9, correct=i < 5)
            for i in range(10)
        ]

        _bins, ece = calibration.reliability_diagram(samples, n_bins=10)

        assert ece == pytest.approx(0.4, abs=1e-9)

    def test_empty_input_is_zero_ece_not_a_crash(self):
        bins, ece = calibration.reliability_diagram([])

        assert bins == []
        assert ece == 0.0


class TestCalibrators:
    @staticmethod
    def _linearly_miscalibrated_samples() -> list[calibration.LabelledSample]:
        """accuracy = confidence - 0.2 at every level, 10 samples per level --
        systematically overconfident, the textbook calibration failure."""
        samples = []
        for confidence, correct_count in (
            (0.5, 3),
            (0.6, 4),
            (0.7, 5),
            (0.8, 6),
            (0.9, 7),
        ):
            for i in range(10):
                samples.append(
                    calibration.LabelledSample(
                        confidence=confidence, correct=i < correct_count
                    )
                )

        return samples

    def test_both_calibrators_reduce_ece_on_a_systematically_overconfident_model(self):
        samples = self._linearly_miscalibrated_samples()

        fit = calibration.fit_calibration(samples, task_type="merge_characters")

        assert fit is not None
        assert fit.fitted_on_n == 50
        assert fit.ece_before == pytest.approx(0.2, abs=1e-9)
        assert fit.ece_after_platt < fit.ece_before
        assert fit.ece_after_isotonic < fit.ece_before
        assert fit.ece_after == min(fit.ece_after_platt, fit.ece_after_isotonic)

    def test_isotonic_predictions_are_monotonic_in_confidence(self):
        samples = self._linearly_miscalibrated_samples()
        thresholds = calibration.fit_isotonic(samples)

        predictions = [
            calibration.isotonic_predict(thresholds, c)
            for c in (0.5, 0.6, 0.7, 0.8, 0.9)
        ]

        assert predictions == sorted(predictions)

    def test_platt_predictions_are_monotonic_in_confidence(self):
        samples = self._linearly_miscalibrated_samples()
        params = calibration.fit_platt(samples)

        predictions = [
            calibration.platt_predict(params, c) for c in (0.5, 0.6, 0.7, 0.8, 0.9)
        ]

        assert predictions == sorted(predictions)

    def test_below_the_minimum_sample_count_nothing_is_fit(self):
        samples = [
            calibration.LabelledSample(confidence=0.7, correct=True)
            for _ in range(calibration.MIN_SAMPLES_TO_FIT - 1)
        ]

        fit = calibration.fit_calibration(samples, task_type="merge_characters")
        assert fit is None


@pytest.mark.asyncio
class TestFitAndStore:
    async def test_too_few_samples_returns_none_and_writes_nothing(
        self, session, project
    ):
        for _ in range(3):
            session.add(
                _feedback(
                    project_id=project.id,
                    task_type=ReviewTaskType.MERGE_CHARACTERS,
                    decision="merge",
                    confidence=0.8,
                )
            )
        await session.commit()

        result = await calibration.fit_and_store(
            session, task_type=ReviewTaskType.MERGE_CHARACTERS
        )

        assert result is None

    async def test_fits_and_persists_a_calibration_model(self, session, project):
        # 4 samples per confidence level; correct_count of them decide
        # "merge" (confirming the model), the rest "keep_separate"
        # (overriding it) -- a clean, systematically overconfident spread.
        for confidence, correct_count in (
            (0.5, 1),
            (0.6, 2),
            (0.7, 2),
            (0.8, 3),
            (0.9, 3),
        ):
            for i in range(4):
                session.add(
                    _feedback(
                        project_id=project.id,
                        task_type=ReviewTaskType.MERGE_CHARACTERS,
                        decision="merge" if i < correct_count else "keep_separate",
                        confidence=confidence,
                    )
                )
        await session.commit()

        result = await calibration.fit_and_store(
            session, task_type=ReviewTaskType.MERGE_CHARACTERS
        )

        assert result is not None
        assert result.task_type == "merge_characters"
        assert result.version == 1
        assert result.fitted_on_n == 20
        assert result.ece_before is not None
        assert result.ece_after is not None
        assert len(result.bins) > 0

        # A second fit on the same task type is a new version, not an
        # overwrite -- a published number stays reproducible from its row
        # even after the model is refit on more feedback later.
        again = await calibration.fit_and_store(
            session, task_type=ReviewTaskType.MERGE_CHARACTERS
        )
        assert again.version == 2

    async def test_resolve_conflict_feedback_never_contributes_a_sample(
        self, session, project
    ):
        for _ in range(20):
            session.add(
                _feedback(
                    project_id=project.id,
                    task_type=ReviewTaskType.RESOLVE_CONFLICT,
                    decision="accept",
                    confidence=0.8,
                )
            )
        await session.commit()

        samples = await calibration.load_labelled_feedback(
            session, task_type=ReviewTaskType.RESOLVE_CONFLICT
        )

        assert samples == []

    async def test_rows_missing_a_confidence_are_excluded(self, session, project):
        session.add(
            _feedback(
                project_id=project.id,
                task_type=ReviewTaskType.MERGE_CHARACTERS,
                decision="merge",
                confidence=None,
            )
        )
        await session.commit()

        samples = await calibration.load_labelled_feedback(
            session, task_type=ReviewTaskType.MERGE_CHARACTERS
        )

        assert samples == []
