"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("ZeroOps route error", error);
  }, [error]);

  return (
    <main id="main-content" className="grid min-h-dvh place-items-center bg-background px-6 py-16">
      <div role="alert" className="w-full max-w-lg rounded-xl border border-danger/25 bg-card p-6 text-center shadow-sm">
        <AlertTriangle size={28} className="mx-auto text-danger" />
        <h1 className="mt-4 text-xl font-semibold text-foreground">This page could not be loaded</h1>
        <p className="mt-2 text-sm leading-6 text-foreground-muted">
          Retry the route. If the problem continues, check the backend connection and application logs.
        </p>
        {error.digest && (
          <p className="mt-2 font-mono text-[11px] text-foreground-subtle">Reference: {error.digest}</p>
        )}
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <button
            type="button"
            onClick={reset}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-xs font-semibold text-white hover:bg-primary-hover"
          >
            <RefreshCw size={15} />
            Try again
          </button>
          <Link
            href="/"
            className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-4 text-xs font-semibold text-foreground hover:bg-surface-raised"
          >
            Return home
          </Link>
        </div>
      </div>
    </main>
  );
}
