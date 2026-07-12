"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

/**
 * Legacy callback route retained only for old bookmarks. OAuth callbacks now
 * establish HttpOnly cookies on the backend and navigate directly to the app;
 * this route intentionally never accepts or stores tokens from the URL.
 */
export default function LegacyOAuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/login");
  }, [router]);

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background p-4">
      <div className="text-center">
        <Loader2 size={28} className="mx-auto animate-spin text-primary" aria-hidden="true" />
        <p className="mt-3 text-sm text-foreground-muted">Returning to secure sign-in…</p>
      </div>
    </main>
  );
}
