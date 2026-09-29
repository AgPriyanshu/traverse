# Why two-pass extraction, with numbers

Traverse turns a novel PDF into a character knowledge graph with page-exact
citations on every relationship. The interesting engineering problem isn't
"call an LLM on a chunk of text" — it's that a relationship in fiction is
almost never stated in one place. "Who is Fumiko's fiancé" is assembled
across a hundred pages, not answered by the single most similar-sounding
paragraph. This is the design decision that follows from that, what it cost,
and what didn't work on the way there.

## The problem with one pass

A single-pass extractor reads a chunk and proposes both characters and
relationships from it in one shot. It's the obvious design, and it fails in
a specific, structural way: by the time the extractor is looking at a
120-word chunk deep in chapter 30, it has no way to know that "Darcy" here
is the same person as "Mr. Fitzwilliam Darcy" in chapter 2, or that "he" in
this sentence resolves to the man mentioned three sentences and one page
ago rather than the one two paragraphs before that. Coreference at book
scale is not a per-chunk problem. Solving it per-chunk means solving it
wrong per-chunk, consistently.

## The two-pass design

**Pass 1** reads the whole book and builds a roster: every named or
speaking character, every alias, every honorific and epithet, clustered
into stable identities with a canonical name and an importance tier. This
is entity resolution, not relationship extraction — it produces the
vocabulary the rest of the pipeline gets to assume is fixed.

**Pass 2** re-reads the book with that roster as fixed context and proposes
relationships between roster members, restricted to chunks that mention at
least two of them. Every relationship extraction call gets the same roster
prefix — which turns out to matter for a reason that has nothing to do with
correctness and everything to do with cost (below).

The real, measured payoff of this design shows up as the headline result:
telling two identically-named characters apart. *Wuthering Heights* has two
Catherines, two Lintons, and a Heathcliff who is simultaneously adopted
brother and suitor — the family tree is the plot, and a system that can't
hold two Catherines apart has failed at the one thing worth building this
for. On a fresh, cold, fully-merged re-ingestion of the real text:

| | Pride and Prejudice | Wuthering Heights | Target |
|---|---|---|---|
| Roster precision (protagonist–minor tiers) | 0.900 | 0.789 | 0.90 |
| Roster recall (same tiers) | 1.000 | 1.000 | 0.95 |
| Alias clustering B³ F1 | 0.955 | 0.865 | 0.85 |

Catherine Earnshaw (major, 63 mentions, dies mid-book) and Catherine Linton
(protagonist, 167 mentions) come out as two correct rows, split on the
birth-date cue in the prose — the two-pass design's whole reason to exist,
holding on the book it was built to stress-test.

**Wuthering Heights' precision shortfall is a named, understood category,
not an unfixed bug.** The false positives are further instances of the
married/maiden-name identity problem — the elder Catherine's married name
splitting from her maiden one, the Linton family's bare-surname ambiguity
between father and son. A real counter-example in the *other* novel (Lady
Catherine addressing Elizabeth, not Jane, as "Miss Bennet" in a context
where guessing by convention would get it wrong) already proved that class
of heuristic unsafe project-wide. The honest choice was to leave it rather
than add a rule that would silently break a different book.

## The prefix-caching argument

Two-pass costs more than one-pass on paper — it reads the book twice. The
argument for it is that the *second* pass is cheap in a way a naive
mental model wouldn't predict: every pass-2 call shares the same roster
prefix, and an inference server that supports prefix caching (vLLM does)
reuses the KV cache for that shared prefix across calls instead of
recomputing it every time.

Measured cache hit rate after fixing the first attempt: **75.0%**, against
a structural ceiling of **~69.4%** for this book's actual roster-to-chunk
ratio — meaning the fix landed at effectively the ceiling for this corpus,
not merely "improved." The mechanism only works if the prefix is
byte-identical call to call, which is a real, non-obvious constraint: the
roster serialization has to be deterministic (stable ordering, no
timestamp or UUID leaking into the prompt) or every call invalidates the
cache and the whole argument for two-pass's cost profile evaporates.

## What did not work

Two things are worth naming precisely because they don't fit a tidy
one-paragraph win narrative:

- **A single misconfigured flag was, by a wide margin, the largest cost
  bug in the project.** Qwen3-8B's reasoning ("thinking") mode was on by
  default. A one-sentence probe used 1,800 completion tokens with thinking
  on and 30 with it off — a 60x cost multiplier on every single call,
  silent, until someone ran a probe specifically to find out why full-book
  ingestion was taking unreasonably long. Turning it off
  (`llm_enable_thinking=false`) was the single highest-leverage fix in the
  whole project, and it has nothing to do with two-pass extraction, prefix
  caching, or coreference — it's a reminder that a model's default
  inference mode is a cost decision, not just a quality one, and it's worth
  checking explicitly rather than assuming a default is sane.
- **Relation extraction recall does not clear its target, for a real
  architectural reason the two-pass design does not fix.** Precision runs
  0.71–1.0 across measurement rounds on Pride and Prejudice; recall runs
  0.24–0.33, well under the 0.80 target. The root cause: median chunk
  length in this pipeline is 60 characters — most "chunks" are a single
  clause, not a paragraph — and several gold-labelled relationship types
  (`enemy_of`, `rival_of`, `deceives`) were never proposed by the extractor
  in *any* run. The single-pass-per-chunk relation prompt reaches for
  direct relationship types (`parent_of`, `married_to`) but not indirect or
  adversarial ones, and one gold predicate (`in_law_of`) requires combining
  two separate marriages stated in two different chunks — a multi-hop
  inference no single-chunk call can make regardless of how good the
  roster context is. This is not a bug to be tuned away; it's evidence
  that a second architectural change — a wider context window per
  relation-extraction call, or a second inference pass over the aggregated
  graph rather than the raw text — is the actual next step, and tuning the
  current single-chunk design further would be optimizing against a
  ceiling rather than fixing the real gap. That redesign was scoped as
  future work rather than attempted under this project's timeline; the
  honest number is reported rather than a version tuned to look better on
  one book.

## What this argues, if you're the buyer reading this

The two-pass design's payoff (identity resolution at book scale) is real,
measured, and reproduced on a second novel deliberately chosen to break it.
Its cost profile is real and measured, not assumed. Its known limitation
(relation recall) is diagnosed to an architectural root cause, not
hand-waved, and the fix that root cause implies is named rather than
left as "needs more tuning." That's the difference this piece is trying to
demonstrate, more than any single number in it: an extraction pipeline that
reports its own ceiling honestly is more trustworthy than one that doesn't
have a ceiling to report because nobody measured hard enough to find it.

Full ablation numbers, including what's still blocked pending a frontier
judge key and a second gold-labelled series project: `README.md`'s
auto-generated eval table, and `traverse-prd.md` §1.3 and Appendix A.
