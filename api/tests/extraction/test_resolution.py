import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ImportanceTier, RelationFamily
from api.db.models import Character, Project, Relation
from api.extraction import resolution
from api.extraction.resolution import NameResolutionMethod


async def _character(
    session: SQLModelAsyncSession,
    project: Project,
    canonical_name: str,
    aliases: list[str] | None = None,
    importance_tier: ImportanceTier = ImportanceTier.MAJOR,
) -> Character:
    row = Character(
        project_id=project.id,
        canonical_name=canonical_name,
        aliases=aliases or [],
        importance_tier=importance_tier,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


@pytest_asyncio.fixture
async def elizabeth(session: SQLModelAsyncSession, project: Project) -> Character:
    return await _character(
        session, project, "Elizabeth Bennet", aliases=["Lizzy", "Eliza", "Miss Bennet"]
    )


@pytest_asyncio.fixture
async def mr_darcy(session: SQLModelAsyncSession, project: Project) -> Character:
    return await _character(
        session, project, "Fitzwilliam Darcy", aliases=["Mr. Darcy", "Darcy"]
    )


@pytest_asyncio.fixture
async def georgiana(session: SQLModelAsyncSession, project: Project) -> Character:
    return await _character(session, project, "Georgiana Darcy", aliases=["Miss Darcy"])


class TestExactAndAliasStages:
    async def test_exact_canonical_name_resolves(
        self, session: SQLModelAsyncSession, project: Project, elizabeth: Character
    ) -> None:
        refs = await resolution.resolve_names(session, project.id, "Elizabeth Bennet")

        assert len(refs) == 1
        assert refs[0].character_id == elizabeth.id
        assert refs[0].method == NameResolutionMethod.EXACT

    async def test_a_stored_alias_resolves_exactly(
        self, session: SQLModelAsyncSession, project: Project, elizabeth: Character
    ) -> None:
        refs = await resolution.resolve_names(session, project.id, "Lizzy")

        assert len(refs) == 1
        assert refs[0].character_id == elizabeth.id
        assert refs[0].method == NameResolutionMethod.EXACT


class TestHonorificStage:
    async def test_a_title_variant_resolves(
        self, session: SQLModelAsyncSession, project: Project, elizabeth: Character
    ) -> None:
        refs = await resolution.resolve_names(
            session, project.id, "Miss Elizabeth Bennet"
        )

        assert len(refs) == 1
        assert refs[0].character_id == elizabeth.id
        assert refs[0].method == NameResolutionMethod.HONORIFIC


class TestPartialNameAmbiguity:
    async def test_a_shared_surname_returns_both_ranked_candidates(
        self,
        session: SQLModelAsyncSession,
        project: Project,
        mr_darcy: Character,
        georgiana: Character,
    ) -> None:
        # "Darcy" is a stored alias of Mr Darcy but not of Georgiana, so this
        # is the genuinely partial case: only the surname-token match fires
        # for Georgiana, while Mr Darcy's literal alias resolves exactly.
        refs = await resolution.resolve_names(session, project.id, "Darcy")

        by_id = {ref.character_id: ref for ref in refs}
        assert mr_darcy.id in by_id
        assert georgiana.id in by_id
        assert by_id[mr_darcy.id].method == NameResolutionMethod.EXACT
        assert by_id[georgiana.id].method == NameResolutionMethod.PARTIAL
        # Never a silent pick: both candidates are surfaced with a score,
        # ranked rather than collapsed to one.
        assert by_id[mr_darcy.id].score > by_id[georgiana.id].score

    async def test_a_conflicting_title_is_not_folded_into_a_cross_gender_match(
        self,
        session: SQLModelAsyncSession,
        project: Project,
        mr_darcy: Character,
        georgiana: Character,
    ) -> None:
        # An explicit, conflicting gendered title must not be stripped away
        # and silently confirm the wrong Darcy at title-cascade confidence.
        refs = await resolution.resolve_names(session, project.id, "Miss Darcy")

        by_id = {ref.character_id: ref for ref in refs}
        assert by_id[georgiana.id].method == NameResolutionMethod.EXACT
        assert by_id[georgiana.id].score == 1.0
        if mr_darcy.id in by_id:
            assert by_id[mr_darcy.id].method != NameResolutionMethod.HONORIFIC

    async def test_a_genuine_tie_ranks_equally(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        first = await _character(session, project, "Catherine Earnshaw")
        second = await _character(session, project, "Catherine Linton")

        refs = await resolution.resolve_names(session, project.id, "Catherine")

        assert {ref.character_id for ref in refs} == {first.id, second.id}
        assert refs[0].score == refs[1].score
        assert all(ref.method == NameResolutionMethod.PARTIAL for ref in refs)


class TestFuzzyStage:
    async def test_a_near_miss_typo_still_resolves(
        self, session: SQLModelAsyncSession, project: Project, elizabeth: Character
    ) -> None:
        refs = await resolution.resolve_names(session, project.id, "Elisabeth Bennet")

        assert len(refs) == 1
        assert refs[0].character_id == elizabeth.id
        assert refs[0].method == NameResolutionMethod.FUZZY

    async def test_an_unrelated_name_resolves_to_nothing(
        self, session: SQLModelAsyncSession, project: Project, elizabeth: Character
    ) -> None:
        refs = await resolution.resolve_names(session, project.id, "Zorblatt Quench")

        assert refs == []


class TestRelativeResolution:
    async def test_her_sister_resolves_against_conversation_context(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        jane = await _character(session, project, "Jane Bennet")
        elizabeth = await _character(session, project, "Elizabeth Bennet")
        session.add(
            Relation(
                project_id=project.id,
                subject_character_id=jane.id,
                object_character_id=elizabeth.id,
                predicate="sibling_of",
                family=RelationFamily.KINSHIP,
            )
        )
        await session.commit()

        refs = await resolution.resolve_names(
            session,
            project.id,
            "her sister",
            conversation_characters=[elizabeth.id],
        )

        assert len(refs) == 1
        assert refs[0].character_id == jane.id
        assert refs[0].method == NameResolutionMethod.RELATIVE

    async def test_her_sister_without_context_resolves_to_nothing(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        refs = await resolution.resolve_names(session, project.id, "her sister")

        assert refs == []

    async def test_her_mother_resolves_the_inverse_stored_direction(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        """``parent_of``/``child_of`` are inverses; aggregation may canonicalise
        onto either direction, so the query must match both."""
        mrs_bennet = await _character(session, project, "Mrs Bennet")
        elizabeth = await _character(session, project, "Elizabeth Bennet")
        session.add(
            Relation(
                project_id=project.id,
                subject_character_id=elizabeth.id,
                object_character_id=mrs_bennet.id,
                predicate="child_of",
                family=RelationFamily.KINSHIP,
            )
        )
        await session.commit()

        refs = await resolution.resolve_names(
            session,
            project.id,
            "her mother",
            conversation_characters=[elizabeth.id],
        )

        assert len(refs) == 1
        assert refs[0].character_id == mrs_bennet.id


class TestEmptyRoster:
    async def test_no_characters_resolves_to_nothing(
        self, session: SQLModelAsyncSession, project: Project
    ) -> None:
        refs = await resolution.resolve_names(session, project.id, "Anybody")

        assert refs == []
