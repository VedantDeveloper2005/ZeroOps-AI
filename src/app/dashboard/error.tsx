"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("ZeroOps dashboard route error", error);
  }, [error]);

  return (
    <div role="alert" className="ops-surface mx-auto max-w-xl border-danger/25 px-6 py-12 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl border border-danger/20 bg-danger-subtle">
        <AlertTriangle size={23} className="text-danger" aria-hidden="true" />
      </span>
      <h1 className="mt-4 text-lg font-semibold text-foreground">Workspace data could not be loaded</h1>
      <p className="mt-2 text-sm leading-6 text-foreground-muted">
        Retry this view. No changes were made while the route was unavailable.
      </p>
      <button
        type="button"
        onClick={reset}
        className="ops-primary mt-5"
      >
        <RefreshCw size={15} aria-hidden="true" />
        Try again
      </button>
    </div>
  );
}
