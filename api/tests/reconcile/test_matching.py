import uuid

import pytest

from api.contracts.enums import ImportanceTier
from api.db.models import Character
from api.extraction import similarity
from api.extraction.schemas import AdjudicationOutput
from api.reconcile import matching
from api.reconcile.repository import BookCluster


def _character(
    name: str,
    aliases: list[str] | None = None,
    *,
    tier: ImportanceTier = ImportanceTier.MINOR,
    mention_count: int = 10,
) -> Character:
    return Character(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        canonical_name=name,
        aliases=aliases or [],
        importance_tier=tier,
        mention_count=mention_count,
    )


def _ctx(page: int, text: str) -> dict:
    return {"page": page, "context": text, "chapter_number": None}


def _cluster(character: Character, contexts: list[dict]) -> BookCluster:
    return BookCluster(character=character, contexts=contexts, mention_count=10)


@pytest.fixture(autouse=True)
def _no_embedding_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding similarity is not exercised by these tests unless overridden."""

    async def unavailable(text_a: str, text_b: str) -> None:
        return None

    monkeypatch.setattr(similarity, "context_similarity", unavailable)


class TestDeterministicStages:
    async def test_exact_normalised_match_merges(self) -> None:
        target = _character("Anne Shirley")
        cluster = _cluster(
            _character("anne shirley."), [_ctx(1, "anne shirley. walked in.")]
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={},
            deaths={},
            kinship={},
            other_characters={},
            book_order=1,
            book_id=uuid.uuid4(),
        )

        assert result.target is target
        assert result.method == "exact"
        assert result.blocked_by is None

    async def test_honorific_and_name_order_match_merges(self) -> None:
        target = _character("Tokita Kazu")
        cluster = _cluster(_character("Kazu Tokita"), [_ctx(1, "Kazu Tokita bowed.")])

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={},
            deaths={},
            kinship={},
            other_characters={},
            book_order=1,
            book_id=uuid.uuid4(),
        )

        assert result.target is target
        assert result.method == "honorific"

    async def test_alias_overlap_merges_a_renamed_character(self) -> None:
        """Book 3's "Miss Shirley" carries "Anne Shirley" as its own alias."""
        target = _character("Anne Shirley", aliases=["Anne Shirley", "Anne"])
        cluster = _cluster(
            _character("Miss Shirley", aliases=["Anne Shirley", "Miss Shirley"]),
            [_ctx(400, "Miss Shirley took her post at the school.")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={},
            deaths={},
            kinship={},
            other_characters={},
            book_order=3,
            book_id=uuid.uuid4(),
        )

        assert result.target is target
        assert result.method == "exact"

    async def test_no_shared_token_leaves_a_genuinely_new_character(self) -> None:
        target = _character("Gilbert Blythe")
        cluster = _cluster(_character("Diana Barry"), [_ctx(1, "Diana Barry giggled.")])

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={},
            deaths={},
            kinship={},
            other_characters={},
            book_order=1,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is None


class TestBlockingGate:
    async def test_death_blocks_autolink(self) -> None:
        """A character's death in an earlier book blocks a later "reappearance".

        Named to match the acceptance criterion in
        ``plans/sprint-5/backend-1.md`` S5.2.
        """
        target = _character("Matthew Cuthbert")
        cluster = _cluster(
            _character("Matthew Cuthbert"),
            [_ctx(50, "Matthew Cuthbert walked into the kitchen.")],
        )
        from api.db.models import CharacterDeath

        deaths = {
            target.id: [
                (
                    CharacterDeath(
                        id=uuid.uuid4(),
                        character_id=target.id,
                        book_id=uuid.uuid4(),
                        chapter=20,
                    ),
                    2,
                )
            ]
        }

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={},
            deaths=deaths,
            kinship={},
            other_characters={},
            book_order=3,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is not None
        assert "death" in result.blocked_by
        assert result.blocked_target is target

    async def test_generational_namesake_blocks_a_string_perfect_match(self) -> None:
        """Named to match the acceptance criterion in ``backend-1.md`` S5.2."""
        target = _character("Anne Shirley")
        cluster = _cluster(
            _character("Anne Shirley"),
            [_ctx(400, "young Anne Shirley toddled after her mother")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(10, "Anne Shirley walked to school.")]},
            deaths={},
            kinship={},
            other_characters={},
            book_order=4,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is not None
        assert result.blocked_target is target

    async def test_kinship_contradiction_blocks_an_embedding_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api.contracts.enums import RelationFamily
        from api.db.models import Relation

        target = _character("Marilla Cuthbert", aliases=["Marilla Cuthbert"])
        other = _character("Anne Shirley")
        relation = Relation(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            subject_character_id=target.id,
            object_character_id=other.id,
            predicate="mother_of",
            family=RelationFamily.KINSHIP,
        )

        async def similar(text_a: str, text_b: str) -> bool:
            return True

        monkeypatch.setattr(similarity, "context_similarity", similar)

        cluster = _cluster(
            _character("Marilla of Green Gables"),
            [_ctx(5, "She was the daughter of Anne Shirley, the neighbours said.")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(1, "Marilla Cuthbert kept house.")]},
            deaths={},
            kinship={target.id: [relation]},
            other_characters={other.id: other},
            book_order=2,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is not None
        assert "mother_of" in result.blocked_by

    async def test_tier_implausible_blocks_a_weak_signal_promotion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _character(
            "Anne Shirley", aliases=["Anne Shirley"], tier=ImportanceTier.PROTAGONIST
        )

        async def similar(text_a: str, text_b: str) -> bool:
            return True

        monkeypatch.setattr(similarity, "context_similarity", similar)

        cluster = _cluster(
            _character(
                "Miss Shirley", aliases=["Miss Shirley"], tier=ImportanceTier.MENTIONED
            ),
            [_ctx(5, "a Shirley girl was seen near the well")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(1, "Anne Shirley walked to school.")]},
            deaths={},
            kinship={},
            other_characters={},
            book_order=2,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is not None
        assert "tier" in result.blocked_by


class TestEmbeddingAndLLMStages:
    async def test_embedding_similarity_merges_when_names_differ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def similar(text_a: str, text_b: str) -> bool:
            return True

        monkeypatch.setattr(similarity, "context_similarity", similar)

        target = _character("Diana Barry", aliases=["Diana Barry"])
        cluster = _cluster(
            _character("the Barry girl", aliases=["the Barry girl"]),
            [_ctx(300, "the Barry girl poured the tea.")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(1, "Diana Barry laughed.")]},
            deaths={},
            kinship={},
            other_characters={},
            book_order=2,
            book_id=uuid.uuid4(),
        )

        assert result.target is target
        assert result.method == "embedding"

    async def test_llm_high_confidence_merges(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_call(prompt, schema, **kwargs):
            return AdjudicationOutput(same_person=True, confidence=0.95, reason="same")

        monkeypatch.setattr(matching, "structured_call", fake_call)

        target = _character("Rachel Lynde", aliases=["Rachel Lynde"])
        cluster = _cluster(
            _character("Mrs. Rachel", aliases=["Mrs. Rachel"]),
            [_ctx(2, "Mrs. Rachel peered out the window.")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(1, "Rachel Lynde gossiped.")]},
            deaths={},
            kinship={},
            other_characters={},
            book_order=1,
            book_id=uuid.uuid4(),
        )

        assert result.target is target
        assert result.method == "llm"

    async def test_llm_middle_band_routes_to_review_not_auto_merge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_call(prompt, schema, **kwargs):
            return AdjudicationOutput(
                same_person=True, confidence=0.5, reason="uncertain"
            )

        monkeypatch.setattr(matching, "structured_call", fake_call)

        target = _character("Rachel Lynde", aliases=["Rachel Lynde"])
        cluster = _cluster(
            _character("Mrs. Rachel", aliases=["Mrs. Rachel"]),
            [_ctx(2, "Mrs. Rachel peered out the window.")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(1, "Rachel Lynde gossiped.")]},
            deaths={},
            kinship={},
            other_characters={},
            book_order=1,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is not None
        assert result.blocked_target is target

    async def test_llm_says_different_leaves_a_new_character(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_call(prompt, schema, **kwargs):
            return AdjudicationOutput(same_person=False, confidence=0.9, reason="no")

        monkeypatch.setattr(matching, "structured_call", fake_call)

        target = _character("Rachel Lynde", aliases=["Rachel Lynde"])
        cluster = _cluster(
            _character("Rachel White", aliases=["Rachel White"]),
            [_ctx(2, "Rachel White peered out the window.")],
        )

        result = await matching.match_cluster(
            cluster,
            roster=[target],
            context_map={target.id: [_ctx(1, "Rachel Lynde gossiped.")]},
            deaths={},
            kinship={},
            other_characters={},
            book_order=1,
            book_id=uuid.uuid4(),
        )

        assert result.target is None
        assert result.blocked_by is None
