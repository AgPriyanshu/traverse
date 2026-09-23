# Sprint 4 — Schema Change Requests

### SCR-13 · be2 · 2026-09-23

**Need:** nullable `asserted_by_character_id` (FK `character`, on delete set null) on `relation_evidence`, and `evidence_ids: list[UUID]` on `RelationOut`.

**Why:** F3.4 attributes each dialogue quote to a speaker and S4.7 path hops must carry evidence ids. Today the speaker is stored only per edge (`relation.asserted_by_character_id`, the most frequent speaker of a hearsay edge), so `EvidenceOut.asserted_by` repeats the edge speaker on every dialogue item. Hop evidence ids are reachable only via `GET /relations/{id}/evidence`.

**Blocking:** no.

### SCR-14 · be2 · 2026-09-23

**Need:** `first_chapter`/`last_chapter` on `GraphEdgeOut` (same as fe1's SCR-11, be2 will populate from the Neo4j edge properties once it lands), and `EvidenceOut.span` (SCR-10) is out of reach: evidence rows carry no span.

**Blocking:** no.

### SCR-15 · be2 · 2026-09-23

**Need:** Sprint 4 plan says migration `0009` adds `relation`/`relation_evidence`. They exist since `0006` (head is `0007`), so no relation migration is needed. Only be1's SCR-1 tables are outstanding. Please correct the plan text.

**Blocking:** no.
