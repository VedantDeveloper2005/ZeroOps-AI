"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Building2, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/lib/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

function AcceptWorkspaceInvitation() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, loading } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mfaEnabled, setMfaEnabled] = useState(Boolean(user?.mfa_enabled));
  const token = params.get("token") || "";

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.acceptWorkspaceInvitation(token);
      setMessage(`You joined ${result.workspace_name} as ${result.role}.`);
      const mfa = await api.getMfaStatus().then((value) => value.enabled).catch(() => Boolean(user?.mfa_enabled));
      setMfaEnabled(mfa);
      if (mfa) {
        window.localStorage.setItem("zeroops:active-workspace", result.workspace_id);
        if (user?.id) window.localStorage.setItem("zeroops:active-workspace-owner", user.id);
        router.replace("/dashboard/team");
      }
    } catch (acceptError) {
      setError(getErrorMessage(acceptError, "This invitation could not be accepted."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-dvh place-items-center bg-background px-4 py-10">
      <section className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-lg sm:p-8">
        <BrandMark href="/" className="justify-center" />
        <div className="mx-auto mt-8 grid size-12 place-items-center rounded-xl bg-primary/10 text-primary"><Building2 size={23} aria-hidden="true" /></div>
        <h1 className="mt-4 text-center text-2xl font-semibold tracking-tight text-foreground">Join a company workspace</h1>
        {loading ? <p role="status" className="mt-3 text-center text-sm text-foreground-muted">Checking your sign-in…</p> : !user ? (
          <>
            <p className="mt-3 text-center text-sm leading-6 text-foreground-muted">Sign in or create a verified ZeroOps account with the email address that received this invite, then reopen this invitation link.</p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2"><Link href="/login" className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary-hover">Sign in</Link><Link href="/signup" className="inline-flex min-h-11 items-center justify-center rounded-lg border border-border px-4 text-sm font-semibold text-foreground hover:bg-surface-raised">Create account</Link></div>
          </>
        ) : message ? (
          <>
            <div role="status" className="mt-5 flex items-start gap-3 rounded-xl border border-success/25 bg-success-subtle p-4"><CheckCircle2 size={19} className="mt-0.5 shrink-0 text-success" aria-hidden="true" /><div><p className="text-sm font-semibold text-foreground">Invitation accepted</p><p className="mt-1 text-sm text-foreground-muted">{message}</p></div></div>
            {!mfaEnabled && <div className="mt-4 rounded-xl border border-warning/25 bg-warning-subtle p-4"><div className="flex gap-3"><ShieldCheck size={18} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" /><p className="text-sm leading-6 text-foreground">This workspace requires MFA. Set up MFA in your personal workspace before entering it.</p></div><Link href="/dashboard/profile" className="mt-3 inline-flex min-h-11 items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary-hover">Set up MFA</Link></div>}
            {mfaEnabled && <Link href="/dashboard/team" className="mt-5 inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary-hover">Open team workspace</Link>}
          </>
        ) : (
          <>
            <p className="mt-3 text-center text-sm leading-6 text-foreground-muted">You are signed in as <span className="font-medium text-foreground">{user.email}</span>. Accepting this invite grants access to the company’s projects and deployment activity.</p>
            {error && <p role="alert" className="mt-4 rounded-lg border border-danger/25 bg-danger-subtle px-3 py-2.5 text-sm text-danger">{error}</p>}
            <button type="button" onClick={() => void accept()} disabled={busy || !token} className="mt-6 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60">{busy ? <Loader2 size={17} className="animate-spin" aria-hidden="true" /> : null}{busy ? "Accepting…" : "Accept invitation"}</button>
          </>
        )}
        {!token && !loading && <p role="alert" className="mt-4 text-center text-sm text-danger">Invitation token is missing. Open the full invite link from your email.</p>}
      </section>
    </main>
  );
}

export default function JoinWorkspacePage() {
  return <Suspense fallback={<main className="grid min-h-dvh place-items-center"><p role="status" className="text-sm text-foreground-muted">Loading invitation…</p></main>}><AcceptWorkspaceInvitation /></Suspense>;
}
