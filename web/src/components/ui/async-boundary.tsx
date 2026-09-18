import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { Component, Suspense } from "react";
import type { ReactNode } from "react";
import { ErrorState } from "./error-state";
import { LoadingSkeleton } from "./loading-skeleton";

type ErrorBoundaryProps = {
  children: ReactNode;
  fallback: (error: unknown, reset: () => void) => ReactNode;
  onReset?: () => void;
};

type ErrorBoundaryState = {
  error: unknown;
};

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { error };
  }

  reset = () => {
    this.setState({ error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.error !== null) {
      return this.props.fallback(this.state.error, this.reset);
    }
    return this.props.children;
  }
}

export type AsyncBoundaryProps = {
  children: ReactNode;
  /** Shaped like the content it replaces, so nothing jumps when data lands. */
  pending?: ReactNode;
  errorTitle?: string;
};

/**
 * Suspense plus an error boundary plus a retry that also clears the failed
 * queries underneath — resetting the boundary without resetting the cache just
 * re-renders the same error.
 */
export const AsyncBoundary = ({
  children,
  pending,
  errorTitle,
}: AsyncBoundaryProps) => {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallback={(error, retry) => (
            <ErrorState error={error} onRetry={retry} title={errorTitle} />
          )}
        >
          <Suspense fallback={pending ?? <LoadingSkeleton />}>
            {children}
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
};
