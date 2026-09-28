from api.contracts.enums import ImportanceTier, ReviewTaskType
from api.review import priority


def test_protagonist_merge_outranks_forty_minor_confirmations():
    """S7.3 DoD: a merge on a protagonist must surface above a pile of
    lower-leverage confirmations, whatever their combined cascade count."""
    protagonist_merge = priority.blast_radius(
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        max_tier=ImportanceTier.PROTAGONIST,
        cascade=12,
    )
    minor_confirm = priority.blast_radius(
        task_type=ReviewTaskType.CONFIRM_RELATION,
        max_tier=ImportanceTier.MINOR,
        cascade=1,
    )

    assert protagonist_merge > minor_confirm * 40


def test_tier_dominates_task_type_within_merges():
    protagonist = priority.blast_radius(
        task_type=ReviewTaskType.MERGE_ACROSS_BOOKS,
        max_tier=ImportanceTier.PROTAGONIST,
        cascade=0,
    )
    mentioned = priority.blast_radius(
        task_type=ReviewTaskType.MERGE_CHARACTERS,
        max_tier=ImportanceTier.MENTIONED,
        cascade=100,
    )

    assert protagonist > mentioned


def test_highest_tier_picks_the_most_prominent():
    assert (
        priority.highest_tier([ImportanceTier.MENTIONED, ImportanceTier.PROTAGONIST])
        is ImportanceTier.PROTAGONIST
    )


def test_highest_tier_of_empty_is_none():
    assert priority.highest_tier([]) is None


def test_classify_and_chapter_split_are_low_priority_by_default():
    classify = priority.blast_radius(
        task_type=ReviewTaskType.CLASSIFY_CANDIDATE, max_tier=None, cascade=1
    )
    chapter = priority.blast_radius(
        task_type=ReviewTaskType.CONFIRM_CHAPTER_SPLIT, max_tier=None
    )
    conflict = priority.blast_radius(
        task_type=ReviewTaskType.RESOLVE_CONFLICT,
        max_tier=ImportanceTier.MAJOR,
        cascade=2,
    )

    assert classify < conflict
    assert chapter < conflict
