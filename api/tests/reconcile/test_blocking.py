import uuid

from api.contracts.enums import ImportanceTier, RelationFamily
from api.db.models import Character, CharacterDeath, Relation
from api.reconcile import blocking


def _character(name: str, *, tier: ImportanceTier = ImportanceTier.MINOR) -> Character:
    return Character(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        canonical_name=name,
        importance_tier=tier,
    )


def _ctx(page: int, text: str) -> dict:
    return {"page": page, "context": text, "chapter_number": None}


class TestDeathBlock:
    def test_blocks_an_appearance_in_a_later_book(self) -> None:
        death = CharacterDeath(
            id=uuid.uuid4(), character_id=uuid.uuid4(), book_id=uuid.uuid4(), chapter=12
        )

        reason = blocking.death_block([(death, 2)], candidate_book_order=5)

        assert reason is not None
        assert "book 2" in reason

    def test_does_not_block_an_appearance_in_or_before_the_death_book(self) -> None:
        death = CharacterDeath(
            id=uuid.uuid4(), character_id=uuid.uuid4(), book_id=uuid.uuid4(), chapter=12
        )

        assert blocking.death_block([(death, 2)], candidate_book_order=2) is None
        assert blocking.death_block([(death, 2)], candidate_book_order=1) is None

    def test_no_deaths_never_blocks(self) -> None:
        assert blocking.death_block([], candidate_book_order=5) is None


class TestKinshipContradiction:
    def test_blocks_a_contradicting_kinship_phrase(self) -> None:
        target_id = uuid.uuid4()
        other_id = uuid.uuid4()
        other = _character("Marilla Cuthbert")
        other.id = other_id
        relation = Relation(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            subject_character_id=target_id,
            object_character_id=other_id,
            predicate="mother_of",
            family=RelationFamily.KINSHIP,
        )

        reason = blocking.kinship_contradiction(
            [relation],
            target_id=target_id,
            other_characters={other_id: other},
            candidate_contexts=[
                _ctx(4, "She was the daughter of Marilla Cuthbert, everyone knew.")
            ],
        )

        assert reason is not None
        assert "mother_of" in reason

    def test_no_contradiction_when_text_agrees(self) -> None:
        target_id = uuid.uuid4()
        other_id = uuid.uuid4()
        other = _character("Marilla Cuthbert")
        other.id = other_id
        relation = Relation(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            subject_character_id=target_id,
            object_character_id=other_id,
            predicate="mother_of",
            family=RelationFamily.KINSHIP,
        )

        reason = blocking.kinship_contradiction(
            [relation],
            target_id=target_id,
            other_characters={other_id: other},
            candidate_contexts=[_ctx(4, "She raised Marilla Cuthbert as her own.")],
        )

        assert reason is None


class TestGenerationalNamesake:
    def test_blocks_on_a_generational_marker(self) -> None:
        target = _character("Anne Shirley")
        candidate_name = "Anne Shirley"

        reason = blocking.generational_namesake(
            target,
            candidate_name,
            [_ctx(10, "the elder Anne Shirley had long since left Avonlea")],
            [_ctx(400, "young Anne Shirley toddled after her mother")],
        )

        assert reason is not None

    def test_no_marker_no_block(self) -> None:
        target = _character("Anne Shirley")

        reason = blocking.generational_namesake(
            target,
            "Anne Shirley",
            [_ctx(10, "Anne Shirley walked to school")],
            [_ctx(400, "Anne Shirley taught the class")],
        )

        assert reason is None


class TestTierImplausible:
    def test_blocks_a_weak_signal_promoting_a_minor_character_to_protagonist(
        self,
    ) -> None:
        target = _character("Anne Shirley", tier=ImportanceTier.PROTAGONIST)

        reason = blocking.tier_implausible(
            target, candidate_tier=ImportanceTier.MENTIONED, is_weak_signal=True
        )

        assert reason is not None

    def test_does_not_block_a_deterministic_match(self) -> None:
        target = _character("Anne Shirley", tier=ImportanceTier.PROTAGONIST)

        reason = blocking.tier_implausible(
            target, candidate_tier=ImportanceTier.MENTIONED, is_weak_signal=False
        )

        assert reason is None

    def test_does_not_block_a_plausible_tier_jump(self) -> None:
        target = _character("Anne Shirley", tier=ImportanceTier.MAJOR)

        reason = blocking.tier_implausible(
            target, candidate_tier=ImportanceTier.MINOR, is_weak_signal=True
        )

        assert reason is None
