import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { describeError, pageRenderQueryOptions, streamQuery, streamRespond } from "@/lib/api";
import type { QueryEvent } from "@/lib/api";
import type { AskScope, Turn } from "./types";

let nextId = 0;

const makeId = (prefix: string): string => {
  nextId += 1;
  return `${prefix}-${nextId}`;
};

const updateTurn = (
  turns: Turn[],
  turnId: string,
  updater: (turn: Turn) => Turn,
): Turn[] => turns.map((turn) => (turn.id === turnId ? updater(turn) : turn));

export type UseConversationResult = {
  turns: Turn[];
  /** True while a turn is streaming or paused on an interrupt — the composer disables until it resolves. */
  isActive: boolean;
  ask: (question: string) => void;
  respondToInterrupt: (turnId: string, answer: string) => void;
};

/**
 * Drives the SSE conversation for one ask screen. `thread_id` is carried
 * across turns (server-side conversation memory, S6.6) once the first
 * response hands one back — never invented client-side.
 */
export const useConversation = (scope: AskScope): UseConversationResult => {
  // States.
  const [turns, setTurns] = useState<Turn[]>([]);

  // Refs.
  const threadIdRef = useRef<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Hooks.
  const queryClient = useQueryClient();

  // Variables.
  const isActive = turns.some((turn) => turn.status === "streaming" || turn.status === "interrupt");

  // useEffects.
  useEffect(() => {
    // Leaving the screen mid-stream aborts the fetch rather than letting it
    // keep writing to state nobody will read.
    return () => { controllerRef.current?.abort(); };
  }, []);

  // Handlers.
  const applyEvent = useCallback(
    (turnId: string, event: QueryEvent) => {
      switch (event.type) {
        case "token": {
          setTurns((prev) =>
            updateTurn(prev, turnId, (turn) => {
              const last = turn.parts[turn.parts.length - 1];
              if (last && last.kind === "text") {
                const merged = { ...last, text: last.text + event.text };
                return { ...turn, parts: [...turn.parts.slice(0, -1), merged] };
              }
              return {
                ...turn,
                parts: [...turn.parts, { kind: "text", id: makeId("text"), text: event.text }],
              };
            }),
          );
          break;
        }
        case "citation": {
          setTurns((prev) =>
            updateTurn(prev, turnId, (turn) => ({
              ...turn,
              parts: [
                ...turn.parts,
                {
                  kind: "citation",
                  id: makeId("citation"),
                  index: event.index,
                  citation: event.citation,
                },
              ],
            })),
          );
          // Prefetched before the click, not on it — the citation is the
          // product's one interaction and it has to feel instant (S6.11).
          void queryClient.prefetchQuery(
            pageRenderQueryOptions(event.citation.book_id, event.citation.page_start),
          );
          break;
        }
        case "route": {
          setTurns((prev) =>
            updateTurn(prev, turnId, (turn) => ({
              ...turn,
              route: {
                route: event.route,
                explanation: event.explanation ?? null,
                retrievalTier: event.retrieval_tier ?? null,
              },
            })),
          );
          break;
        }
        case "interrupt": {
          threadIdRef.current = event.thread_id;
          setTurns((prev) =>
            updateTurn(prev, turnId, (turn) => ({
              ...turn,
              status: "interrupt",
              interrupt: { question: event.question, options: event.options ?? [] },
            })),
          );
          break;
        }
        case "done": {
          threadIdRef.current = event.thread_id;
          setTurns((prev) =>
            updateTurn(prev, turnId, (turn) => ({
              ...turn,
              status: "done",
              abstained: event.abstained,
              latencyMs: event.latency_ms ?? null,
              interrupt: undefined,
            })),
          );
          break;
        }
        case "error": {
          setTurns((prev) =>
            updateTurn(prev, turnId, (turn) => ({
              ...turn,
              status: "error",
              errorMessage: event.message,
              errorRecoverable: event.recoverable,
            })),
          );
          break;
        }
      }
    },
    [queryClient],
  );

  const consume = useCallback(
    async (turnId: string, events: AsyncGenerator<QueryEvent>) => {
      try {
        for await (const event of events) {
          applyEvent(turnId, event);
        }
      } catch (cause) {
        setTurns((prev) =>
          updateTurn(prev, turnId, (turn) => ({
            ...turn,
            status: "error",
            errorMessage: describeError(cause),
            errorRecoverable: false,
          })),
        );
      }
    },
    [applyEvent],
  );

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (trimmed === "") { return; }

      const id = makeId("turn");
      const controller = new AbortController();
      controllerRef.current = controller;

      setTurns((prev) => [
        ...prev,
        {
          id,
          position: prev.length,
          question: trimmed,
          parts: [],
          status: "streaming",
          abstained: false,
          latencyMs: null,
        },
      ]);

      void consume(
        id,
        streamQuery(
          {
            project_id: scope.projectId,
            question: trimmed,
            thread_id: threadIdRef.current,
            limit_book_order: scope.limitBookOrder,
            limit_chapter: scope.limitChapter,
          },
          { signal: controller.signal },
        ),
      );
    },
    [consume, scope.limitBookOrder, scope.limitChapter, scope.projectId],
  );

  const respondToInterrupt = useCallback(
    (turnId: string, answer: string) => {
      const trimmed = answer.trim();
      const threadId = threadIdRef.current;
      if (trimmed === "" || !threadId) { return; }

      const controller = new AbortController();
      controllerRef.current = controller;

      setTurns((prev) =>
        updateTurn(prev, turnId, (turn) => ({ ...turn, status: "streaming" })),
      );

      void consume(turnId, streamRespond(threadId, { answer: trimmed }, { signal: controller.signal }));
    },
    [consume],
  );

  return { turns, isActive, ask, respondToInterrupt };
};
