import uuid

import pytest

from api.graph.similarity import MentionContext, cluster_contexts

pytestmark = pytest.mark.models


async def test_empty_input_returns_no_clusters():
    assert await cluster_contexts([], threshold=0.65) == []


async def test_single_mention_is_its_own_cluster():
    mention = MentionContext(uuid.uuid4(), "Elizabeth walked into the room.")
    clusters = await cluster_contexts([mention], threshold=0.65)

    assert clusters == [[mention.mention_id]]


async def test_similar_contexts_cluster_together():
    elizabeth_a = MentionContext(uuid.uuid4(), "Elizabeth laughed at the joke.")
    elizabeth_b = MentionContext(uuid.uuid4(), "Elizabeth smiled and laughed warmly.")
    darcy = MentionContext(uuid.uuid4(), "Darcy stood silently near the window.")

    clusters = await cluster_contexts([elizabeth_a, elizabeth_b, darcy], threshold=0.5)

    by_mention = {mention_id: cluster for cluster in clusters for mention_id in cluster}
    assert by_mention[elizabeth_a.mention_id] == by_mention[elizabeth_b.mention_id]
    assert by_mention[darcy.mention_id] != by_mention[elizabeth_a.mention_id]


async def test_every_mention_id_appears_exactly_once():
    mentions = [
        MentionContext(uuid.uuid4(), f"Some sentence about person number {i}.")
        for i in range(6)
    ]
    clusters = await cluster_contexts(mentions, threshold=0.9)

    seen = [mention_id for cluster in clusters for mention_id in cluster]
    assert sorted(seen) == sorted(m.mention_id for m in mentions)
