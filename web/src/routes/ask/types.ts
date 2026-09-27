import type { Citation, QueryRoute } from "@/lib/api";

export type TurnStatus = "streaming" | "interrupt" | "done" | "error";

/**
 * The answer as an ordered sequence of prose runs and citations, in the exact
 * order the SSE stream produced them — not tokens collected into one string
 * with citations appended at the end. That ordering *is* "inline citation
 * chips appearing in place" (frontend-1.md, S6.10): a `CitationEvent` arrives
 * right after the token events for the claim it supports, so splicing it in
 * at that position is enough; no paragraph-boundary guessing needed.
 */
export type AnswerPart =
  | { kind: "text"; id: string; text: string }
  | { kind: "citation"; id: string; index: number; citation: Citation };

export type TurnRoute = {
  route: QueryRoute;
  explanation: string | null;
  retrievalTier: string | null;
};

export type TurnInterrupt = {
  question: string;
  options: string[];
};

/**
 * One question/answer pair, accumulated client-side from the SSE stream.
 * Field names mirror `api/db/models/conversation_model.py`'s `ConversationTurn`
 * (`position`, `question`, an answer) — there is no read contract for that
 * table yet (S6.13 mocks against the model shape, per the sprint brief), so
 * this is built entirely from the stream this session drove, not fetched.
 */
export type Turn = {
  id: string;
  position: number;
  question: string;
  parts: AnswerPart[];
  route?: TurnRoute;
  status: TurnStatus;
  abstained: boolean;
  latencyMs: number | null;
  interrupt?: TurnInterrupt;
  errorMessage?: string;
  errorRecoverable?: boolean;
};

export const plainTextOf = (parts: readonly AnswerPart[]): string =>
  parts
    .map((part) => (part.kind === "text" ? part.text : `[${part.index}]`))
    .join("");

/** What the ask screen scopes its query to — the reading position, not carried character context (see the `use-conversation.ts` gotcha). */
export type AskScope = {
  projectId: string;
  limitBookOrder: number | null;
  limitChapter: number | null;
  /** A short label for the scope banner — "Pride and Prejudice" or "the whole series". */
  label: string;
  /** Present only for a book-scoped ask; lets the banner offer "ask the whole series" instead. */
  clearHref?: string;
};
