"""Mention-context similarity clustering — stage 4 of be1's alias cascade.

Stages 1-3 (exact/normalised, honorific, nickname — all table-driven) resolve
the easy cases cheaply; what reaches here is the residue they could not fold
together: the same surface form used by more than one person in a book
("Miss Bennet" for both Jane and Elizabeth, context-dependent), or two
spellings the earlier stages missed. Clustering here is unsupervised — it
does not know how many characters there really are, only how similar two
contexts read — so getting the threshold wrong in either direction is
silent: too low over-merges (the "catastrophic and silent" failure mode PRD
§11 names), too high leaves obvious duplicates unresolved and pushes needless
volume onto stage 5's LLM adjudication.

The threshold is measured, not assumed. See
``plans/sprint-3/HANDOFF.md`` (S3.8) for the full precision/recall curve; the
short version is in ``similarity_threshold()``'s docstring.
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from ..config.settings import settings
from ..retrieval.repository import embedding_model

# Pending SCR (plans/sprint-3/SCR.md): `settings.mention_similarity_threshold`
# — `api/config/settings.py` is orchestrator-owned. `getattr` with this
# default (see `similarity_threshold()`) means every call site already does
# the right thing once the field lands, no further change — same pattern as
# `api/retrieval/rerank.py`'s `reranker_enabled()`.
DEFAULT_SIMILARITY_THRESHOLD = 0.65

# `settings.embedding_batch_size` (16) is tuned for the chunk-embedding path,
# which runs on GPU during integration and CPU only for small worktree runs
# (BRANCH.md §9). Clustering contexts are short (a sentence or two) and this
# path is CPU-only by design, so a larger batch is cheap and roughly halves
# wall clock on 2,000 contexts — see plans/sprint-3/HANDOFF.md (S3.8) for the
# measurement.
_CLUSTER_EMBED_BATCH_SIZE = 128


@dataclass(frozen=True)
class MentionContext:
    """One candidate mention: its id, and the text the resolver clusters on.

    ``context`` should be a window around the mention (a sentence or two),
    not the bare surface form — the whole point of this stage is that the
    surface form alone was not enough to disambiguate.
    """

    mention_id: UUID
    context: str


def similarity_threshold() -> float:
    """Return the configured clustering threshold.

    Returns:
        ``settings.mention_similarity_threshold`` if the pending SCR has
        landed, else ``DEFAULT_SIMILARITY_THRESHOLD``.
    """
    return float(
        getattr(settings, "mention_similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
    )


async def cluster_contexts(
    mentions: list[MentionContext], *, threshold: float
) -> list[list[UUID]]:
    """Cluster mention contexts by embedding similarity.

    Embeds every context with the process-wide BGE-M3 handle (reused from
    ``retrieval/repository.py`` — never a second copy, BRANCH.md §9) and runs
    agglomerative clustering with average-link cosine distance. Both the
    embedding and the clustering step are CPU-bound and run in a thread so
    they never block the event loop of whatever called this.

    Args:
        mentions: Contexts to cluster. Order does not matter; the result
            partitions ``mentions`` by ``mention_id``.
        threshold: Minimum cosine similarity for two contexts to join the
            same cluster. Call ``similarity_threshold()`` for the measured
            default rather than hardcoding a number at the call site.

    Returns:
        Mention ids grouped into clusters. A singleton list is a mention
        that did not read as similar enough to any other to cluster.
    """
    if not mentions:
        return []

    if len(mentions) == 1:
        return [[mentions[0].mention_id]]

    model = embedding_model()
    vectors = await asyncio.to_thread(
        model.encode,
        [item.context for item in mentions],
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=_CLUSTER_EMBED_BATCH_SIZE,
    )

    # AgglomerativeClustering's `distance_threshold` is a maximum distance,
    # so a similarity threshold inverts: cosine distance = 1 - similarity.
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1.0 - threshold,
    )
    labels = await asyncio.to_thread(clustering.fit_predict, np.asarray(vectors))

    clusters: dict[int, list[UUID]] = {}
    for mention, label in zip(mentions, labels, strict=True):
        clusters.setdefault(int(label), []).append(mention.mention_id)

    return list(clusters.values())
