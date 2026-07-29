"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";

/**
 * Kept for old bookmarks only. Provider callbacks are completed by the backend,
 * which establishes HttpOnly session cookies before returning to the app.
 */
export default function LegacyGitHubCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/login");
  }, [router]);

  return (
    <main
      id="main-content"
      className="flex min-h-dvh items-center justify-center bg-background p-5"
    >
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 text-center shadow-sm">
        <BrandMark href="/login" className="justify-center" />
        <Loader2
          size={24}
          className="mx-auto mt-6 animate-spin text-primary"
          aria-hidden="true"
        />
        <p role="status" className="mt-3 text-sm text-foreground-muted">
          Returning to sign in…
        </p>
        <Link href="/login" className="ops-secondary mt-5">
          Continue to sign in
        </Link>
      </div>
    </main>
  );
}
