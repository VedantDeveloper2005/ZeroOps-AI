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
    <div role="alert" className="mx-auto max-w-xl rounded-xl border border-danger/25 bg-card px-6 py-10 text-center shadow-sm">
      <AlertTriangle size={26} className="mx-auto text-danger" />
      <h1 className="mt-4 text-lg font-semibold text-foreground">Workspace data could not be loaded</h1>
      <p className="mt-2 text-sm leading-6 text-foreground-muted">
        Retry this view. No changes were made while the route was unavailable.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-xs font-semibold text-white hover:bg-primary-hover"
      >
        <RefreshCw size={15} />
        Try again
      </button>
    </div>
  );
}
