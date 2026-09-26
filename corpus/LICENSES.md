# Corpus licenses

Every text below is in the public domain in the United States and is
distributed by [Project Gutenberg](https://www.gutenberg.org) under the
[Project Gutenberg License](https://www.gutenberg.org/policy/license.html):
free to copy and redistribute provided the Gutenberg header/footer travels
with it, or the redistribution is clearly marked as altered. This corpus
strips that header/footer and repaginates the text — this file is that
notice.

Regenerate with `make seed`. `corpus/manifest.json` pins the exact source
URL, SHA-256 of both the source text and the built PDF, page count and
conversion command each entry below was built with — a citation in a
labelled eval answer (Sprint 8) is a page number, and a silently
regenerated corpus with different pagination invalidates it.

| Title | Author | Gutenberg ID | Pages | Source SHA-256 | Why (PRD §7) |
|---|---|---|---|---|---|
| Anna Karenina | Leo Tolstoy | 1399 | 685 | `a3e29e08c15c…` | scale + patronymics/diminutives stress case |
| Frankenstein; or, the Modern Prometheus | Mary Wollstonecraft Shelley | 84 | 124 | `7810cd483cff…` | nested framing -> assertion provenance |
| Pride and Prejudice | Jane Austen | 1342 | 245 | `3f6bb9d6f78e…` | dense, checkable family network; the aggregation test |
| The Great Gatsby | F. Scott Fitzgerald | 64317 | 111 | `ce760ec377ac…` | first-person narrator who is a character |
| Wuthering Heights | Emily Bronte | 768 | 211 | `e533fe750589…` | the name-collision regression case |

### Anne of Green Gables (series)

| Order | Title | Gutenberg ID | Pages | Source SHA-256 |
|---|---|---|---|---|
| 1 | Anne of Green Gables | 45 | 185 | `89a5e9fb2e0b…` |
| 2 | Anne of Avonlea | 47 | 165 | `e9a12333e4e6…` |
| 3 | Anne of the Island | 51 | 152 | `f9c7d035c05a…` |
| 4 | Anne's House of Dreams | 544 | 152 | `f94dac73e940…` |
| 5 | Rainbow Valley | 5343 | 153 | `f056b035e896…` |
| 6 | Rilla of Ingleside | 3796 | 187 | `83d2784b2754…` |

### Sherlock Holmes (series)

| Order | Title | Gutenberg ID | Pages | Source SHA-256 |
|---|---|---|---|---|
| 1 | A Study in Scarlet | 244 | 80 | `8bbec71f9fa9…` |
| 2 | The Sign of the Four | 2097 | 78 | `4cdea89cf6cd…` |
| 3 | The Hound of the Baskervilles | 2852 | 119 | `f7c8c68729d3…` |
| 4 | The Valley of Fear | 3289 | 119 | `380bfdbf3ab3…` |

**Anne of Green Gables ships six of its eight books, not eight.**
"Anne of Windy Poplars" (1936, book 4) and "Anne of Ingleside" (1939, book 6) are still under US copyright (95 years from publication: until 2031 and 2034 respectively) and are not on gutenberg.org — verified directly against the live catalog, not assumed. They exist on gutenberg.net.au (Australian public domain, life+70), a different licence regime this corpus does not mix in. `series_order` therefore runs 1-6 with no gap; each entry's true position in the eight-book series is `manifest.json`'s `canonical_series_number`.

