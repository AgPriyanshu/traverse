import type { AskScope, Turn } from "./types";

type StoredConversation = {
  turns: Turn[];
  threadId: string | null;
};

/**
 * Conversation state keyed by scope, held outside React. `<AskScreen>`
 * unmounts every time a citation navigates to the page viewer (a sibling
 * route, not a modal) and remounts on browser back — a plain `useState`
 * would lose the whole thread right when S6.11 promises the opposite
 * ("a reader following four citations must be able to get back to the
 * answer without losing it"). This module survives that unmount/remount
 * because it is not part of the component tree; it does not survive a full
 * page reload, which is outside that promise.
 */
const conversations = new Map<string, StoredConversation>();

export const conversationKey = (scope: Pick<AskScope, "projectId" | "limitBookOrder" | "limitChapter">): string =>
  `${scope.projectId}:${scope.limitBookOrder ?? "-"}:${scope.limitChapter ?? "-"}`;

export const loadConversation = (key: string): StoredConversation | undefined => conversations.get(key);

export const saveConversation = (key: string, state: StoredConversation): void => {
  conversations.set(key, state);
};

/** Test-only: the module singleton would otherwise leak a conversation from one test's `/books/:id/ask` into the next's. */
export const resetConversations = (): void => {
  conversations.clear();
};
