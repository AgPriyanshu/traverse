import re
from collections import defaultdict
from dataclasses import replace

from ..contracts.enums import ResolutionMethod
from .normalization import content_tokens

_BIRTH_RE = re.compile(r"\b(?:was born|gave birth|born the|birth of)\b", re.IGNORECASE)


def _given(form: str) -> str | None:
    tokens = content_tokens(form)

    return tokens[0] if tokens else None


def _is_bare(form: str) -> bool:
    bare = len(content_tokens(form)) == 1

    return bare


def _rebuild(cluster, contexts: list[dict]):
    forms: dict[str, ResolutionMethod] = {}
    counts: dict[str, int] = defaultdict(int)

    for context in contexts:
        form = context["surface_form"]
        forms[form] = cluster.surface_forms.get(form, ResolutionMethod.EXACT)
        counts[form] += int(context.get("count", 1))

    rebuilt = replace(
        cluster, surface_forms=forms, contexts=contexts, mention_counts=dict(counts)
    )

    return rebuilt


def _qualified_by_given(clusters: list) -> dict[str, list]:
    """Group clusters whose canonical names share a given name but not a surname."""
    groups: dict[str, list] = defaultdict(list)

    for cluster in clusters:
        tokens = content_tokens(cluster.canonical_name)
        if len(tokens) >= 2:
            groups[tokens[0]].append(cluster)

    distinct = {
        given: members
        for given, members in groups.items()
        if len({content_tokens(m.canonical_name)[-1] for m in members}) >= 2
    }

    return distinct


def split_generations(clusters: list) -> list:
    """Divide a shared given name between two same-named characters by era.

    Two characters who share a given name (a mother and her daughter) leave
    every bare form ("Catherine", "Cathy", "Miss Cathy") indistinguishable by
    string. What separates them is time: the text says when the second was
    born. Every bare mention before that page belongs to the elder, every one
    from it onwards to the younger; a form carrying a surname stays where the
    cascade put it. The younger is the one same-named cluster with qualified
    mentions after the birth, the elder the best-attested one with none. With
    no birth in the contexts, or no such pair, the clusters come back
    untouched, since a split with no evidence is a guess.

    Args:
        clusters: Clusters after the whole cascade.

    Returns:
        Clusters with each qualifying pair's bare-form mentions reassigned.
    """
    result = list(clusters)

    for given, members in _qualified_by_given(clusters).items():
        pool = [
            c
            for c in result
            if any(_given(f) == given and _is_bare(f) for f in c.surface_forms)
        ]
        bare_contexts = [
            context
            for c in pool
            for context in c.contexts
            if _given(context["surface_form"]) == given
            and _is_bare(context["surface_form"])
        ]
        births = [
            context["page"]
            for context in bare_contexts
            if _BIRTH_RE.search(context["context"])
        ]
        if not births:
            continue

        boundary = min(births)

        def has_after(cluster, boundary=boundary, given=given) -> bool:
            return any(
                _given(context["surface_form"]) == given and context["page"] >= boundary
                for context in cluster.contexts
            )

        younger_options = [m for m in members if has_after(m)]
        elder_options = [m for m in members if not has_after(m)]
        if len(younger_options) != 1 or not elder_options:
            continue

        younger = younger_options[0]
        elder = max(elder_options, key=lambda c: c.total_mentions)

        def without_bare(cluster, given=given) -> list[dict]:
            return [
                context
                for context in cluster.contexts
                if not (
                    _given(context["surface_form"]) == given
                    and _is_bare(context["surface_form"])
                )
            ]

        rebuilt = {
            id(elder): _rebuild(
                elder,
                without_bare(elder)
                + [c for c in bare_contexts if c["page"] < boundary],
            ),
            id(younger): _rebuild(
                younger,
                without_bare(younger)
                + [c for c in bare_contexts if c["page"] >= boundary],
            ),
        }
        for other in pool:
            if id(other) in rebuilt:
                continue

            remaining = without_bare(other)
            rebuilt[id(other)] = _rebuild(other, remaining) if remaining else None

        result = [
            rebuilt.get(id(c), c) for c in result if rebuilt.get(id(c), c) is not None
        ]

    return result
