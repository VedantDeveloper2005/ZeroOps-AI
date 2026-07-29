import Link from "next/link";
import { SearchX } from "lucide-react";

export default function NotFound() {
  return (
    <main id="main-content" className="grid min-h-dvh place-items-center bg-background px-6 py-16">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card p-6 text-center shadow-sm">
        <SearchX size={28} className="mx-auto text-foreground-subtle" />
        <p className="mt-4 text-xs font-semibold uppercase tracking-[0.1em] text-primary">404</p>
        <h1 className="mt-2 text-xl font-semibold text-foreground">Page not found</h1>
        <p className="mt-2 text-sm leading-6 text-foreground-muted">
          The route may have moved, or the resource is not available to this account.
        </p>
        <Link
          href="/"
          className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-primary px-4 text-xs font-semibold text-white hover:bg-primary-hover"
        >
          Return home
        </Link>
      </div>
    </main>
  );
}
