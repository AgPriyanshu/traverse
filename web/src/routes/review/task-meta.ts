import type { CandidateKind, ReviewTask, ReviewTaskType } from "@/lib/api";
import { TIER_ORDER } from "../project/character-labels";
import { predicateLabel } from "../project/graph/relation-style";
import type { SortMode } from "./types";

export const CANDIDATE_KIND_LABEL: Record<CandidateKind, string> = {
  person: "Character",
  place: "Place",
  organisation: "Organisation",
  unknown: "Not an entity",
};

export const TASK_TYPE_LABEL: Record<ReviewTaskType, string> = {
  merge_characters: "Merge characters",
  merge_across_books: "Merge across books",
  confirm_relation: "Confirm relation",
  resolve_conflict: "Resolve conflict",
  classify_candidate: "Classify candidate",
  confirm_chapter_split: "Confirm chapter split",
};

/** Null means "no confidence signal for this task type" — sorts after every known value, never coerced to 0. */
export const taskConfidence = (task: ReviewTask): number | null => {
  const { payload } = task;
  switch (payload.task_type) {
    case "merge_characters":
    case "merge_across_books":
      return payload.similarity_score ?? null;
    case "confirm_relation":
      return payload.relation.confidence;
    case "resolve_conflict": {
      const values = payload.conflicting.map((relation) => relation.confidence);
      return values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null;
    }
    case "classify_candidate":
      return null;
    case "confirm_chapter_split":
      return payload.confidence ?? null;
  }
};

/**
 * Lower is more important (protagonist = 0). Only `merge_*` payloads carry
 * `CharacterOut.importance_tier` on their candidates — `RelationOut` has no
 * tier field, so `confirm_relation`/`resolve_conflict` fall back to `null`
 * (sorted after every ranked task) rather than a fabricated importance.
 */
export const taskImportanceRank = (task: ReviewTask): number | null => {
  const { payload } = task;
  if (payload.task_type === "merge_characters" || payload.task_type === "merge_across_books") {
    const ranks = payload.candidates.map((candidate) => TIER_ORDER.indexOf(candidate.importance_tier));
    return ranks.length > 0 ? Math.min(...ranks) : null;
  }
  return null;
};

export const taskAgeMs = (task: ReviewTask, now: Date = new Date()): number => {
  return now.getTime() - new Date(task.created_at).getTime();
};

/** One line identifying the decision at a glance in the task list. */
export const taskSummary = (task: ReviewTask): string => {
  const { payload } = task;
  switch (payload.task_type) {
    case "merge_characters":
    case "merge_across_books":
      return payload.candidates.map((candidate) => candidate.canonical_name).join(" & ");
    case "confirm_relation":
      return `${payload.relation.subject_name} ${predicateLabel(payload.relation.predicate)} ${payload.relation.object_name}`;
    case "resolve_conflict": {
      const names = `${payload.conflicting[0]?.subject_name ?? "?"} & ${payload.conflicting[0]?.object_name ?? "?"}`;
      const predicates = payload.conflicting.map((relation) => predicateLabel(relation.predicate)).join(" vs. ");
      return `${names}: ${predicates}`;
    }
    case "classify_candidate":
      return payload.surface_form;
    case "confirm_chapter_split":
      return payload.chapter.title
        ? `Ch. ${payload.chapter.number ?? "?"} — ${payload.chapter.title}`
        : `Chapter ${payload.chapter.number ?? "?"}`;
  }
};

/** The page a reviewer would click through to first — what S7.8's prefetch warms. */
export const firstCitation = (task: ReviewTask): { bookId: string; page: number } | null => {
  const { payload } = task;
  switch (payload.task_type) {
    case "merge_characters":
    case "merge_across_books": {
      for (const mentions of Object.values(payload.contexts ?? {})) {
        const first = mentions[0];
        if (first) { return { bookId: first.book_id, page: first.page }; }
      }
      return null;
    }
    case "confirm_relation": {
      const first = (payload.evidence ?? [])[0];
      return first ? { bookId: first.book_id, page: first.page_start } : null;
    }
    case "resolve_conflict": {
      for (const evidence of Object.values(payload.evidence ?? {})) {
        const first = evidence[0];
        if (first) { return { bookId: first.book_id, page: first.page_start }; }
      }
      return null;
    }
    case "classify_candidate": {
      const first = payload.contexts?.[0];
      return first ? { bookId: first.book_id, page: first.page } : null;
    }
    case "confirm_chapter_split":
      return { bookId: payload.chapter.book_id, page: payload.chapter.page_start };
  }
};

export const formatTaskConfidence = (task: ReviewTask): string | null => {
  const confidence = taskConfidence(task);
  return confidence === null ? null : `${Math.round(confidence * 100)}% confidence`;
};

const NO_SIGNAL_SORTS_LAST = 1;
const HAS_SIGNAL_SORTS_FIRST = -1;

export const compareTasks = (mode: SortMode) => (a: ReviewTask, b: ReviewTask): number => {
  switch (mode) {
    case "priority":
      return b.priority - a.priority;
    case "age":
      return taskAgeMs(b) - taskAgeMs(a);
    case "confidence": {
      const ca = taskConfidence(a);
      const cb = taskConfidence(b);
      if (ca === null && cb === null) { return b.priority - a.priority; }
      if (ca === null) { return NO_SIGNAL_SORTS_LAST; }
      if (cb === null) { return HAS_SIGNAL_SORTS_FIRST; }
      return ca - cb;
    }
    case "importance": {
      const ia = taskImportanceRank(a);
      const ib = taskImportanceRank(b);
      if (ia === null && ib === null) { return b.priority - a.priority; }
      if (ia === null) { return NO_SIGNAL_SORTS_LAST; }
      if (ib === null) { return HAS_SIGNAL_SORTS_FIRST; }
      return ia - ib;
    }
  }
};
