import uuid

import pytest

from api.contracts.enums import ImportanceTier, ResolutionMethod
from api.extraction import attributes as attribute_extraction
from api.extraction import characters
from api.extraction.aliases import Cluster


def _cluster(
    name: str, contexts: list[dict], forms: dict[str, ResolutionMethod]
) -> Cluster:
    counts: dict[str, int] = {form: 0 for form in forms}
    for context in contexts:
        counts[context["surface_form"]] = counts.get(context["surface_form"], 0) + 1

    return Cluster(
        canonical_name=name,
        surface_forms=forms,
        candidate_ids={uuid.uuid4()},
        contexts=contexts,
        mention_counts=counts,
    )


def _ctx(page: int, chapter: int | None, chunk_id: str, surface_form: str) -> dict:
    return {
        "page": page,
        "chapter_number": chapter,
        "chunk_id": chunk_id,
        "context": "some context",
        "surface_form": surface_form,
    }


class TestBuildCharacterRows:
    async def test_computes_first_last_and_mentions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunk_a, chunk_b = str(uuid.uuid4()), str(uuid.uuid4())
        cluster = _cluster(
            "Elizabeth Bennet",
            [
                _ctx(10, 1, chunk_a, "Elizabeth Bennet"),
                _ctx(90, 5, chunk_b, "Lizzy"),
            ],
            {
                "Elizabeth Bennet": ResolutionMethod.EXACT,
                "Lizzy": ResolutionMethod.NICKNAME,
            },
        )

        async def no_attributes(*a, **k):
            return {}

        monkeypatch.setattr(attribute_extraction, "extract_attributes", no_attributes)

        rows = await characters.build_character_rows([cluster], book_id=uuid.uuid4())

        assert len(rows) == 1
        row = rows[0]
        assert row["canonical_name"] == "Elizabeth Bennet"
        assert set(row["aliases"]) == {"Elizabeth Bennet", "Lizzy"}
        assert row["first_page"] == 10
        assert row["first_chapter"] == 1
        assert row["last_page"] == 90
        assert row["last_chapter"] == 5
        assert row["mention_count"] == 2
        assert row["importance_tier"] is not None
        assert len(row["mentions"]) == 2
        methods = {m["surface_form"]: m["resolution_method"] for m in row["mentions"]}
        assert methods["Lizzy"] == ResolutionMethod.NICKNAME

    async def test_protagonist_and_footman_tier_apart(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def no_attributes(*a, **k):
            return {}

        monkeypatch.setattr(attribute_extraction, "extract_attributes", no_attributes)

        protagonist = _cluster(
            "Elizabeth Bennet",
            [_ctx(p, 1, str(uuid.uuid4()), "Elizabeth") for p in range(1, 101)],
            {"Elizabeth Bennet": ResolutionMethod.EXACT},
        )
        footman = _cluster(
            "A Footman",
            [_ctx(50, 3, str(uuid.uuid4()), "A Footman")],
            {"A Footman": ResolutionMethod.EXACT},
        )

        rows = await characters.build_character_rows(
            [protagonist, footman], book_id=uuid.uuid4()
        )
        tiers = {row["canonical_name"]: row["importance_tier"] for row in rows}

        assert tiers["Elizabeth Bennet"] is ImportanceTier.PROTAGONIST
        assert tiers["A Footman"] is ImportanceTier.MENTIONED
