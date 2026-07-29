"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Loader2,
  MailCheck,
  Smartphone,
} from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/lib/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

type VerificationPhase = "preparing" | "email" | "phone" | "success" | "missing";

const PENDING_EMAIL_KEY = "zeroops.pendingVerificationEmail";

function VerifyEmailContent() {
  const { verifyEmail, verifyPhone, resendPhoneVerification } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token")?.trim() || "";
  const queryEmail = searchParams.get("email")?.trim() || "";
  const automaticAttempted = useRef(false);
  const [phase, setPhase] = useState<VerificationPhase>(token ? "preparing" : "missing");
  const [email, setEmail] = useState(queryEmail);
  const [phoneHint, setPhoneHint] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [phoneWasRequired, setPhoneWasRequired] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const clearPendingEmail = () => {
    try {
      sessionStorage.removeItem(PENDING_EMAIL_KEY);
    } catch {
      // Storage is optional; verification is already complete.
    }
  };

  const removeTokenFromAddressBar = () => {
    window.history.replaceState(window.history.state, "", "/verify-email");
  };

  const applyEmailVerificationResult = (
    result:
      | { phone_verification_required: true; phone_hint: string }
      | { email_verified: true },
  ) => {
    removeTokenFromAddressBar();
    if ("phone_verification_required" in result) {
      setPhoneHint(result.phone_hint);
      setPhoneWasRequired(true);
      setPhoneCode("");
      setPhase("phone");
    } else {
      clearPendingEmail();
      setPhase("success");
    }
  };

  useEffect(() => {
    if (!token || automaticAttempted.current) return;

    let rememberedEmail = queryEmail;
    if (!rememberedEmail) {
      try {
        rememberedEmail = sessionStorage.getItem(PENDING_EMAIL_KEY) || "";
      } catch {
        rememberedEmail = "";
      }
    }

    if (!rememberedEmail) {
      setPhase("email");
      return;
    }

    automaticAttempted.current = true;
    setEmail(rememberedEmail);
    setPhase("preparing");
    setError(null);

    void verifyEmail(rememberedEmail, token)
      .then((result) => {
        applyEmailVerificationResult(result);
      })
      .catch((verificationError) => {
        setError(
          getErrorMessage(
            verificationError,
            "The verification link is invalid or has expired.",
          ),
        );
        setPhase("email");
      });
    // The provider methods are intentionally read at the time the link is processed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryEmail, token]);

  const submitEmailVerification = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) return;

    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await verifyEmail(email.trim(), token);
      applyEmailVerificationResult(result);
    } catch (verificationError) {
      setError(
        getErrorMessage(
          verificationError,
          "The verification link is invalid or has expired.",
        ),
      );
    } finally {
      setIsBusy(false);
    }
  };

  const requestVerificationLink = async () => {
    setIsResending(true);
    setError(null);
    setNotice(null);
    try {
      await api.resendVerification(email.trim());
      try {
        sessionStorage.setItem(PENDING_EMAIL_KEY, email.trim());
      } catch {
        // The next verification page can ask for the email again.
      }
      setNotice(
        "If this address can be verified, a new verification link has been sent.",
      );
    } catch (resendError) {
      setError(
        getErrorMessage(resendError, "A new verification link could not be requested."),
      );
    } finally {
      setIsResending(false);
    }
  };

  const submitPhoneVerification = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await verifyPhone(phoneCode);
      clearPendingEmail();
      if ("id" in result) {
        router.replace("/dashboard/repositories");
        return;
      }
      setPhase("success");
    } catch (verificationError) {
      setError(
        getErrorMessage(
          verificationError,
          "The phone verification code is invalid or expired.",
        ),
      );
    } finally {
      setIsBusy(false);
    }
  };

  const requestPhoneCode = async () => {
    setIsResending(true);
    setError(null);
    setNotice(null);
    try {
      const result = await resendPhoneVerification();
      setPhoneHint(result.phone_hint);
      setNotice("A new phone verification code was requested.");
    } catch (resendError) {
      setError(getErrorMessage(resendError, "A new phone code could not be requested."));
    } finally {
      setIsResending(false);
    }
  };

  if (phase === "preparing") {
    return (
      <VerificationCard>
        <Loader2 size={28} className="animate-spin text-primary" aria-hidden="true" />
        <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-foreground">
          Verifying your email
        </h1>
        <p role="status" className="mt-2 text-sm leading-6 text-foreground-muted">
          Checking the single-use verification link…
        </p>
      </VerificationCard>
    );
  }

  if (phase === "success") {
    return (
      <VerificationCard>
        <CheckCircle2 size={30} className="text-success" aria-hidden="true" />
        <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-foreground">
          Verification complete
        </h1>
        <p className="mt-2 text-sm leading-6 text-foreground-muted">
          {phoneWasRequired
            ? "Your email and required phone number are verified."
            : "Your email address is verified."}{" "}
          Sign in to continue.
        </p>
        <Link href="/login?verified=true" className="ops-primary mt-6 w-full">
          Continue to sign in
          <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </VerificationCard>
    );
  }

  if (phase === "phone") {
    return (
      <VerificationCard>
        <Smartphone size={28} className="text-primary" aria-hidden="true" />
        <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-foreground">
          Verify your phone
        </h1>
        <p className="mt-2 text-sm leading-6 text-foreground-muted">
          Email verified. Enter the six-digit code sent to {phoneHint || "your phone"}.
        </p>

        <Feedback error={error} notice={notice} />

        <form onSubmit={submitPhoneVerification} className="mt-5 space-y-4 text-left">
          <div>
            <label htmlFor="verify-phone-code" className="text-sm font-medium text-foreground">
              Phone verification code
            </label>
            <input
              id="verify-phone-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={phoneCode}
              onChange={(event) =>
                setPhoneCode(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
              autoFocus
              required
              className="mt-2 min-h-12 w-full rounded-lg border border-border bg-card px-3 text-center font-mono text-lg tracking-[0.2em] text-foreground outline-none transition-colors focus:border-primary"
            />
          </div>
          <button
            type="submit"
            disabled={isBusy || phoneCode.length !== 6}
            className="ops-primary w-full disabled:opacity-60"
          >
            {isBusy ? (
              <>
                <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                Verifying…
              </>
            ) : (
              <>
                Verify phone
                <ArrowRight size={16} aria-hidden="true" />
              </>
            )}
          </button>
        </form>
        <button
          type="button"
          onClick={() => void requestPhoneCode()}
          disabled={isResending}
          className="mt-3 min-h-11 text-sm font-medium text-primary hover:underline disabled:opacity-60"
        >
          {isResending ? "Requesting…" : "Request another code"}
        </button>
      </VerificationCard>
    );
  }

  const hasToken = phase === "email";

  return (
    <VerificationCard>
      <MailCheck size={28} className="text-primary" aria-hidden="true" />
      <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-foreground">
        {hasToken ? "Confirm your email" : "Verification link required"}
      </h1>
      <p className="mt-2 text-sm leading-6 text-foreground-muted">
        {hasToken
          ? "Enter the email address that received this link. The opaque link token will be submitted without being changed."
          : "Open the single-use link from your verification email, or request a new link below."}
      </p>

      <Feedback error={error} notice={notice} />

      <form
        onSubmit={hasToken ? submitEmailVerification : (event) => {
          event.preventDefault();
          void requestVerificationLink();
        }}
        className="mt-5 space-y-4 text-left"
      >
        <div>
          <label htmlFor="verify-email-address" className="text-sm font-medium text-foreground">
            Email address
          </label>
          <input
            id="verify-email-address"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            className="mt-2 min-h-12 w-full rounded-lg border border-border bg-card px-3 text-base text-foreground outline-none transition-colors focus:border-primary sm:text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={isBusy || isResending || !email.trim()}
          className="ops-primary w-full disabled:opacity-60"
        >
          {isBusy || isResending ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              {hasToken ? "Verifying…" : "Requesting…"}
            </>
          ) : (
            <>
              {hasToken ? "Verify email" : "Request new link"}
              <ArrowRight size={16} aria-hidden="true" />
            </>
          )}
        </button>
      </form>

      {hasToken && (
        <button
          type="button"
          onClick={() => void requestVerificationLink()}
          disabled={isResending || !email.trim()}
          className="mt-3 min-h-11 text-sm font-medium text-primary hover:underline disabled:opacity-60"
        >
          {isResending ? "Requesting…" : "Request a replacement link"}
        </button>
      )}

      <Link href="/login" className="ops-secondary mt-4 w-full">
        Back to sign in
      </Link>
    </VerificationCard>
  );
}

function Feedback({ error, notice }: { error: string | null; notice: string | null }) {
  return (
    <>
      {error && (
        <div
          role="alert"
          className="mt-5 rounded-lg border border-danger/25 bg-danger-subtle p-3 text-left text-sm leading-5 text-danger"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="mt-5 rounded-lg border border-success/25 bg-success-subtle p-3 text-left text-sm leading-5 text-foreground"
        >
          {notice}
        </div>
      )}
    </>
  );
}

function VerificationCard({ children }: { children: React.ReactNode }) {
  return (
    <section className="w-full max-w-md rounded-xl border border-border bg-card p-6 text-center shadow-sm sm:p-8">
      {children}
    </section>
  );
}

function VerifyEmailFallback() {
  return (
    <VerificationCard>
      <Loader2 size={28} className="mx-auto animate-spin text-primary" aria-hidden="true" />
      <p role="status" className="mt-4 text-sm text-foreground-muted">
        Preparing verification…
      </p>
    </VerificationCard>
  );
}

export default function VerifyEmailPage() {
  return (
    <main
      id="main-content"
      className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-background px-4 py-10"
    >
      <div className="pointer-events-none absolute inset-0 ops-page-grid opacity-50" aria-hidden="true" />
      <BrandMark className="relative z-10 mb-7" />
      <div className="relative z-10 flex w-full justify-center">
        <Suspense fallback={<VerifyEmailFallback />}>
          <VerifyEmailContent />
        </Suspense>
      </div>
    </main>
  );
}
