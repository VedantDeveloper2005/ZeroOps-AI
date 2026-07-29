"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  MailCheck,
} from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { isEmailVerificationPending, useAuth } from "@/lib/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

const PENDING_EMAIL_KEY = "zeroops.pendingVerificationEmail";

export default function SignupPage() {
  const { signup, loginWithGitHub, loginWithGoogle } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [oauthProvider, setOauthProvider] = useState<"github" | "google" | null>(null);
  const [checkEmail, setCheckEmail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phoneNumber: "",
    password: "",
  });

  const updateField = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData((current) => ({ ...current, [name]: value }));
  };

  const rememberPendingEmail = (address: string) => {
    try {
      sessionStorage.setItem(PENDING_EMAIL_KEY, address);
    } catch {
      // The verification page also accepts the email manually.
    }
  };

  const submitSignup = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await signup(
        formData.firstName.trim(),
        formData.lastName.trim(),
        formData.email.trim(),
        formData.phoneNumber.trim(),
        formData.password,
      );
      if (isEmailVerificationPending(result)) {
        setFormData((current) => ({
          ...current,
          email: result.email,
          password: "",
        }));
        rememberPendingEmail(result.email);
        setCheckEmail(true);
      }
    } catch (signupError) {
      setError(getErrorMessage(signupError, "The account could not be created."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const resendVerificationLink = async () => {
    setIsResending(true);
    setError(null);
    setNotice(null);
    try {
      await api.resendVerification(formData.email.trim());
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

  return (
    <main
      id="main-content"
      className="min-h-dvh bg-background lg:grid lg:grid-cols-[minmax(320px,0.8fr)_minmax(520px,1.2fr)]"
    >
      <AuthAside />

      <div className="flex min-h-dvh items-center justify-center px-4 py-10 sm:px-8 lg:px-12">
        <div className="w-full max-w-lg">
          <div className="mb-8 lg:hidden">
            <BrandMark />
          </div>

          <div className="mb-7">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">
              Account setup
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-foreground">
              {checkEmail ? "Check your email" : "Create your account"}
            </h1>
            <p className="mt-2 text-sm leading-6 text-foreground-muted">
              {checkEmail
                ? `Open the single-use verification link sent to ${formData.email}.`
                : "Create a local account, or continue through a configured identity provider."}
            </p>
          </div>

          {error && (
            <div
              role="alert"
              className="mb-4 rounded-lg border border-danger/25 bg-danger-subtle p-3 text-sm leading-5 text-danger"
            >
              {error}
            </div>
          )}
          {notice && (
            <div
              role="status"
              className="mb-4 flex gap-2 rounded-lg border border-success/25 bg-success-subtle p-3 text-sm leading-5 text-foreground"
            >
              <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
              <span>{notice}</span>
            </div>
          )}

          {checkEmail ? (
            <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
              <MailCheck size={26} className="text-primary" aria-hidden="true" />
              <h2 className="mt-3 text-sm font-semibold text-foreground">
                Verify before signing in
              </h2>
              <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
                The verification link expires and can only be used once. Phone verification follows
                only when a phone number was provided and the backend requires that step.
              </p>
              <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => void resendVerificationLink()}
                  disabled={isResending}
                  className="ops-primary flex-1 disabled:opacity-60"
                >
                  {isResending && (
                    <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                  )}
                  Request new link
                </button>
                <Link href="/login" className="ops-secondary flex-1">
                  Go to sign in
                </Link>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCheckEmail(false);
                  setError(null);
                  setNotice(null);
                }}
                className="mt-4 min-h-11 text-sm font-medium text-primary hover:underline"
              >
                Edit account details
              </button>
            </section>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => {
                    setOauthProvider("google");
                    loginWithGoogle();
                  }}
                  disabled={oauthProvider !== null}
                  className="ops-secondary w-full disabled:opacity-60"
                >
                  {oauthProvider === "google" && (
                    <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                  )}
                  Continue with Google
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setOauthProvider("github");
                    loginWithGitHub();
                  }}
                  disabled={oauthProvider !== null}
                  className="ops-secondary w-full disabled:opacity-60"
                >
                  {oauthProvider === "github" && (
                    <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                  )}
                  Continue with GitHub
                </button>
              </div>
              <p className="mt-2 text-center text-[11px] leading-5 text-foreground-muted">
                Provider sign-up is available only when its backend credentials are configured.
              </p>

              <div className="my-6 flex items-center gap-3" aria-hidden="true">
                <span className="h-px flex-1 bg-border" />
                <span className="text-[11px] font-medium uppercase tracking-wide text-foreground-subtle">
                  or
                </span>
                <span className="h-px flex-1 bg-border" />
              </div>

              <form onSubmit={submitSignup} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    id="signup-first-name"
                    label="First name"
                    name="firstName"
                    type="text"
                    autoComplete="given-name"
                    value={formData.firstName}
                    onChange={updateField}
                  />
                  <Field
                    id="signup-last-name"
                    label="Last name"
                    name="lastName"
                    type="text"
                    autoComplete="family-name"
                    value={formData.lastName}
                    onChange={updateField}
                  />
                </div>
                <Field
                  id="signup-email"
                  label="Email address"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={formData.email}
                  onChange={updateField}
                  required
                />
                <Field
                  id="signup-phone"
                  label="Phone number (optional)"
                  name="phoneNumber"
                  type="tel"
                  autoComplete="tel"
                  inputMode="tel"
                  pattern="\+[1-9][0-9]{7,14}"
                  value={formData.phoneNumber}
                  onChange={updateField}
                  helper="If provided, use international format such as +14155552671."
                />
                <Field
                  id="signup-password"
                  label="Password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  value={formData.password}
                  onChange={updateField}
                  required
                  helper="Use at least 12 characters with uppercase, lowercase, a number, and a symbol."
                  trailing={
                    <button
                      type="button"
                      onClick={() => setShowPassword((visible) => !visible)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      aria-pressed={showPassword}
                      className="grid h-10 w-10 place-items-center rounded-md text-foreground-muted transition-colors hover:bg-surface-subtle hover:text-foreground"
                    >
                      {showPassword ? (
                        <EyeOff size={17} aria-hidden="true" />
                      ) : (
                        <Eye size={17} aria-hidden="true" />
                      )}
                    </button>
                  }
                />

                <p className="text-xs leading-5 text-foreground-muted">
                  By creating an account, you agree to the{" "}
                  <Link href="/terms" className="font-medium text-primary hover:underline">
                    Terms
                  </Link>{" "}
                  and acknowledge the{" "}
                  <Link href="/privacy" className="font-medium text-primary hover:underline">
                    Privacy Policy
                  </Link>
                  .
                </p>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="ops-primary w-full disabled:opacity-60"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                      Creating account…
                    </>
                  ) : (
                    <>
                      Create account
                      <ArrowRight size={16} aria-hidden="true" />
                    </>
                  )}
                </button>
              </form>

              <p className="mt-7 text-center text-sm text-foreground-muted">
                Already have an account?{" "}
                <Link href="/login" className="font-semibold text-primary hover:underline">
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

function AuthAside() {
  return (
    <aside className="relative hidden overflow-hidden border-r border-border bg-sidebar p-10 lg:flex lg:flex-col lg:justify-between xl:p-14">
      <div className="pointer-events-none absolute inset-0 ops-page-grid opacity-55" aria-hidden="true" />
      <BrandMark className="relative z-10 w-fit" />
      <div className="relative z-10 max-w-md">
        <p className="ops-kicker">Review-first deployment</p>
        <h2 className="mt-4 text-4xl font-semibold tracking-[-0.05em] text-foreground xl:text-5xl">
          Start from source evidence.
        </h2>
        <p className="mt-5 text-sm leading-6 text-foreground-muted">
          Connect a GitHub repository or upload a ZIP, then inspect and approve the proposed
          Azure App Service plan before deployment.
        </p>
        <div className="mt-8 rounded-xl border border-border bg-card/80 p-4 text-xs leading-5 text-foreground-muted shadow-sm">
          ZeroOps does not deploy until the infrastructure plan is approved.
        </div>
      </div>
      <p className="relative z-10 text-xs text-foreground-subtle">
        Local signup requires working email delivery; optional phone verification depends on backend configuration.
      </p>
    </aside>
  );
}

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  helper?: string;
  trailing?: React.ReactNode;
};

function Field({ id, label, helper, trailing, ...props }: FieldProps) {
  const helperId = helper ? `${id}-helper` : undefined;
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      <div className="relative mt-2">
        <input
          {...props}
          id={id}
          aria-describedby={helperId}
          className={`min-h-12 w-full rounded-lg border border-border bg-card px-3 text-base text-foreground outline-none transition-colors placeholder:text-foreground-subtle focus:border-primary sm:text-sm ${
            trailing ? "pr-12" : ""
          }`}
        />
        {trailing && <div className="absolute right-1 top-1/2 -translate-y-1/2">{trailing}</div>}
      </div>
      {helper && (
        <p id={helperId} className="mt-1.5 text-xs leading-5 text-foreground-muted">
          {helper}
        </p>
      )}
    </div>
  );
}
