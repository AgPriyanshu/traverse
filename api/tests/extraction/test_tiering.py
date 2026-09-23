import pytest

from api.contracts.enums import ImportanceTier
from api.extraction import tiering


class TestTierByMentionCount:
    def test_multiple_protagonists_survive_relative_thresholding(self) -> None:
        tiers = tiering.tier_by_mention_count(
            {"Elizabeth": 400, "Darcy": 380, "Mrs Reynolds": 20, "A Footman": 1}
        )

        assert tiers["Elizabeth"] is ImportanceTier.PROTAGONIST
        assert tiers["Darcy"] is ImportanceTier.PROTAGONIST
        assert tiers["Mrs Reynolds"] is ImportanceTier.MINOR
        assert tiers["A Footman"] is ImportanceTier.MENTIONED

    def test_empty_input(self) -> None:
        assert tiering.tier_by_mention_count({}) == {}


class TestTierByParticipation:
    def test_scores_breadth_of_appearance(self) -> None:
        tiers = tiering.tier_by_participation(
            chapter_counts={"Elizabeth": 20, "A Footman": 1},
            chunk_counts={"Elizabeth": 80, "A Footman": 1},
        )

        assert tiers["Elizabeth"] is ImportanceTier.PROTAGONIST
        assert tiers["A Footman"] is ImportanceTier.MENTIONED


class TestActiveMethod:
    def test_defaults_to_mention_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TIERING_METHOD", raising=False)

        assert tiering.active_method() == "mention_count"

    def test_reads_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIERING_METHOD", "participation")

        assert tiering.active_method() == "participation"

    def test_falls_back_on_an_unknown_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TIERING_METHOD", "nonsense")

        assert tiering.active_method() == "mention_count"
