import type { ReviewTask } from "@/lib/api";
import type { Decision } from "./types";

/**
 * The one decision each task type can take **without per-task judgment** —
 * what "accept" means in bulk. `merge_*` bulks to "keep separate" rather than
 * merging, since picking a primary is exactly the judgment bulk accept can't
 * make safely; `classify_candidate` only bulks when the model already offered
 * a guess. Anything that needs a human pick returns `null` and is excluded
 * from the batch (S7.10: "guard against accept-all-blind").
 */
export const bulkDecisionFor = (task: ReviewTask): Decision | null => {
  const { payload } = task;
  switch (payload.task_type) {
    case "merge_characters":
    case "merge_across_books":
      return { decision: "keep_separate", payload: {}, label: "Kept separate" };
    case "confirm_relation":
      return { decision: "accept", payload: {}, label: "Accepted relation" };
    case "confirm_chapter_split":
      return { decision: "accept", payload: {}, label: "Confirmed chapter boundary" };
    case "resolve_conflict":
      return {
        decision: "temporal_transition",
        payload: { order: payload.conflicting.map((relation) => relation.id) },
        label: "Marked as a temporal transition",
      };
    case "classify_candidate":
      return payload.kind_guess
        ? { decision: "classify", payload: { kind: payload.kind_guess }, label: `Classified as ${payload.kind_guess}` }
        : null;
  }
};
