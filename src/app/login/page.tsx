"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  LockKeyhole,
  MailCheck,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import {
  isEmailVerificationPending,
  isMfaChallenge,
  isPhoneVerificationPending,
  useAuth,
} from "@/lib/AuthContext";
import { getErrorMessage } from "@/lib/api";

type AuthStep = "credentials" | "email" | "phone" | "mfa";
type OAuthProvider = "google" | "github";

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  access_denied: "The provider sign-in was cancelled.",
  invalid_state: "This sign-in request expired or could not be verified. Please try again.",
  token_exchange_failed: "The provider could not complete sign-in. Please try again.",
  no_verified_email: "Your provider account needs a verified email address before it can sign in.",
  github_user_fetch_failed: "We could not retrieve your GitHub profile. Please try again.",
  google_user_fetch_failed: "We could not retrieve your Google profile. Please try again.",
};

export default function LoginPage() {
  const {
    login,
    verifyMfa,
    verifyPhone,
    resendVerification,
    resendMfaOtp,
    resendPhoneVerification,
    loginWithGitHub,
    loginWithGoogle,
  } = useAuth();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [step, setStep] = useState<AuthStep>("credentials");
  const [formData, setFormData] = useState({ email: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [challengeCode, setChallengeCode] = useState("");
  const [mfaMethod, setMfaMethod] = useState("totp");
  const [phoneHint, setPhoneHint] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [oauthProvider, setOauthProvider] = useState<OAuthProvider | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("mfa") === "required") {
      const queryMfaMethod = params.get("mfa_method");
      if (queryMfaMethod === "email" || queryMfaMethod === "totp") {
        setMfaMethod(queryMfaMethod);
      }
      setStep("mfa");
    }

    const oauthError = params.get("oauth_error");
    if (oauthError) {
      setError(
        OAUTH_ERROR_MESSAGES[oauthError] ||
          "The identity provider could not complete sign-in. Please try again.",
      );
    } else if (params.get("verified") === "true") {
      setNotice("Email verified. Sign in to continue.");
    }
  }, []);

  useEffect(() => {
    if (step === "credentials") return;
    const frame = window.requestAnimationFrame(() => headingRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [step]);

  const updateField = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData((current) => ({ ...current, [name]: value }));
  };

  const clearMessages = () => {
    setError(null);
    setNotice(null);
  };

  const resetToCredentials = () => {
    setStep("credentials");
    setChallengeCode("");
    setMfaMethod("totp");
    setPhoneHint("");
    setOauthProvider(null);
    clearMessages();
  };

  const submitCredentials = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    clearMessages();

    try {
      const email = formData.email.trim();
      const result = await login(email, formData.password);

      if (isMfaChallenge(result)) {
        setMfaMethod(result.mfa_method || "totp");
        setChallengeCode("");
        setStep("mfa");
      } else if (isEmailVerificationPending(result)) {
        setFormData({ email: result.email, password: "" });
        setStep("email");
      } else if (isPhoneVerificationPending(result)) {
        setPhoneHint(result.phone_hint);
        setFormData((current) => ({ ...current, password: "" }));
        setChallengeCode("");
        setStep("phone");
      }
    } catch (loginError) {
      setError(getErrorMessage(loginError, "The email or password is incorrect."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitMfa = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    clearMessages();
    try {
      await verifyMfa(challengeCode.trim());
    } catch (verificationError) {
      setError(
        getErrorMessage(
          verificationError,
          "We could not verify that authentication code.",
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitPhone = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    clearMessages();
    try {
      const result = await verifyPhone(challengeCode);
      if ("id" in result) return;

      setStep("credentials");
      setChallengeCode("");
      setNotice("Phone number verified. Sign in to continue.");
    } catch (verificationError) {
      setError(
        getErrorMessage(verificationError, "We could not verify that phone code."),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const resendEmailVerification = async () => {
    setIsResending(true);
    clearMessages();
    try {
      await resendVerification(formData.email.trim());
      setNotice("A new verification link has been requested. Check your inbox.");
    } catch (resendError) {
      setError(
        getErrorMessage(resendError, "A new verification link could not be requested."),
      );
    } finally {
      setIsResending(false);
    }
  };

  const resendMfaCode = async () => {
    setIsResending(true);
    clearMessages();
    try {
      await resendMfaOtp();
      setNotice("A new sign-in code has been sent to your email.");
    } catch (resendError) {
      setError(getErrorMessage(resendError, "A new sign-in code could not be sent."));
    } finally {
      setIsResending(false);
    }
  };

  const resendPhoneCode = async () => {
    setIsResending(true);
    clearMessages();
    try {
      const result = await resendPhoneVerification();
      setPhoneHint(result.phone_hint);
      setNotice("A new phone verification code has been sent.");
    } catch (resendError) {
      setError(
        getErrorMessage(resendError, "A new phone verification code could not be sent."),
      );
    } finally {
      setIsResending(false);
    }
  };

  const beginOAuth = (provider: OAuthProvider) => {
    setOauthProvider(provider);
    clearMessages();
    try {
      if (provider === "google") loginWithGoogle();
      else loginWithGitHub();
    } catch {
      setOauthProvider(null);
      setError("The identity provider could not be opened. Please try again.");
    }
  };

  const pageCopy = getPageCopy(step, formData.email, phoneHint, mfaMethod);

  return (
    <main
      id="main-content"
      className="min-h-dvh bg-background lg:grid lg:grid-cols-[minmax(320px,0.8fr)_minmax(520px,1.2fr)]"
    >
      <AuthAside />

      <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4 py-10 sm:px-8 lg:px-12">
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_72%_18%,var(--primary-glow),transparent_30%)] lg:hidden"
          aria-hidden="true"
        />
        <div className="relative w-full max-w-lg">
          <div className="mb-8 lg:hidden">
            <BrandMark />
          </div>

          <div className="mb-7">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">
              {pageCopy.kicker}
            </p>
            <h1
              ref={headingRef}
              tabIndex={-1}
              className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-foreground focus:outline-none"
            >
              {pageCopy.title}
            </h1>
            <p className="mt-2 break-words text-sm leading-6 text-foreground-muted">
              {pageCopy.description}
            </p>
          </div>

          {error && <MessageBanner id="login-error" tone="error" message={error} />}
          {notice && <MessageBanner id="login-notice" tone="success" message={notice} />}

          {step === "credentials" && (
            <CredentialsStep
              formData={formData}
              showPassword={showPassword}
              isSubmitting={isSubmitting}
              oauthProvider={oauthProvider}
              hasError={Boolean(error)}
              onFieldChange={updateField}
              onTogglePassword={() => setShowPassword((visible) => !visible)}
              onSubmit={submitCredentials}
              onOAuth={beginOAuth}
            />
          )}

          {step === "email" && (
            <EmailVerificationStep
              email={formData.email}
              isResending={isResending}
              onResend={() => void resendEmailVerification()}
              onBack={resetToCredentials}
            />
          )}

          {step === "phone" && (
            <PhoneVerificationStep
              code={challengeCode}
              hasError={Boolean(error)}
              isSubmitting={isSubmitting}
              isResending={isResending}
              onCodeChange={(value) =>
                setChallengeCode(value.replace(/\D/g, "").slice(0, 6))
              }
              onSubmit={submitPhone}
              onResend={() => void resendPhoneCode()}
              onBack={resetToCredentials}
            />
          )}

          {step === "mfa" && (
            <MfaStep
              code={challengeCode}
              method={mfaMethod}
              hasError={Boolean(error)}
              isSubmitting={isSubmitting}
              isResending={isResending}
              onCodeChange={setChallengeCode}
              onSubmit={submitMfa}
              onResend={() => void resendMfaCode()}
              onBack={resetToCredentials}
            />
          )}
        </div>
      </div>
    </main>
  );
}

function CredentialsStep({
  formData,
  showPassword,
  isSubmitting,
  oauthProvider,
  hasError,
  onFieldChange,
  onTogglePassword,
  onSubmit,
  onOAuth,
}: {
  formData: { email: string; password: string };
  showPassword: boolean;
  isSubmitting: boolean;
  oauthProvider: OAuthProvider | null;
  hasError: boolean;
  onFieldChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onTogglePassword: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onOAuth: (provider: OAuthProvider) => void;
}) {
  const isBusy = isSubmitting || oauthProvider !== null;

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        <ProviderButton
          provider="google"
          busy={oauthProvider === "google"}
          disabled={isBusy}
          onClick={() => onOAuth("google")}
        />
        <ProviderButton
          provider="github"
          busy={oauthProvider === "github"}
          disabled={isBusy}
          onClick={() => onOAuth("github")}
        />
      </div>
      <p className="mt-2 text-center text-[11px] leading-5 text-foreground-muted">
        Single sign-on is available when its backend provider is configured.
      </p>

      <div className="my-6 flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-border" />
        <span className="text-[11px] font-medium uppercase tracking-wide text-foreground-subtle">
          or
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <Field
          id="login-email"
          label="Email address"
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          maxLength={320}
          value={formData.email}
          onChange={onFieldChange}
          aria-invalid={hasError || undefined}
          aria-describedby={hasError ? "login-error" : undefined}
          required
        />
        <Field
          id="login-password"
          label="Password"
          name="password"
          type={showPassword ? "text" : "password"}
          autoComplete="current-password"
          maxLength={128}
          value={formData.password}
          onChange={onFieldChange}
          aria-invalid={hasError || undefined}
          aria-describedby={hasError ? "login-error" : undefined}
          required
          trailing={
            <button
              type="button"
              onClick={onTogglePassword}
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

        <button
          type="submit"
          disabled={isBusy}
          aria-busy={isSubmitting}
          className="ops-primary w-full disabled:opacity-60"
        >
          {isSubmitting ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Signing in...
            </>
          ) : (
            <>
              Sign in securely
              <ArrowRight size={16} aria-hidden="true" />
            </>
          )}
        </button>
      </form>

      <p className="mt-7 text-center text-sm text-foreground-muted">
        New to ZeroOps AI?{" "}
        <Link href="/signup" className="font-semibold text-primary hover:underline">
          Create an account
        </Link>
      </p>
    </>
  );
}

function EmailVerificationStep({
  email,
  isResending,
  onResend,
  onBack,
}: {
  email: string;
  isResending: boolean;
  onResend: () => void;
  onBack: () => void;
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <MailCheck size={27} className="text-primary" aria-hidden="true" />
      <h2 className="mt-3 text-sm font-semibold text-foreground">Verify before signing in</h2>
      <p className="mt-1.5 break-words text-xs leading-5 text-foreground-muted">
        Open the single-use verification link sent to{" "}
        <span className="font-semibold text-foreground">{email}</span>. The link expires and can
        only be used once.
      </p>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={onResend}
          disabled={isResending}
          aria-busy={isResending}
          className="ops-primary flex-1 disabled:opacity-60"
        >
          {isResending && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
          Request new link
        </button>
        <button type="button" onClick={onBack} className="ops-secondary flex-1">
          Use another account
        </button>
      </div>
    </section>
  );
}

function PhoneVerificationStep({
  code,
  hasError,
  isSubmitting,
  isResending,
  onCodeChange,
  onSubmit,
  onResend,
  onBack,
}: {
  code: string;
  hasError: boolean;
  isSubmitting: boolean;
  isResending: boolean;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onResend: () => void;
  onBack: () => void;
}) {
  return (
    <ChallengeCard icon={<Smartphone size={19} aria-hidden="true" />} title="Phone verification">
      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <Field
          id="login-phone-code"
          label="Six-digit verification code"
          type="text"
          autoComplete="one-time-code"
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          value={code}
          onChange={(event) => onCodeChange(event.target.value)}
          aria-invalid={hasError || undefined}
          aria-describedby={hasError ? "login-error" : undefined}
          autoFocus
          required
          helper="The code expires quickly and can only be used once."
        />
        <button
          type="submit"
          disabled={isSubmitting || code.length !== 6}
          aria-busy={isSubmitting}
          className="ops-primary w-full disabled:opacity-60"
        >
          {isSubmitting ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Verifying...
            </>
          ) : (
            <>
              Verify and continue
              <ArrowRight size={16} aria-hidden="true" />
            </>
          )}
        </button>
      </form>
      <ChallengeActions
        isResending={isResending}
        onResend={onResend}
        onBack={onBack}
        resendLabel="Resend phone code"
      />
    </ChallengeCard>
  );
}

function MfaStep({
  code,
  method,
  hasError,
  isSubmitting,
  isResending,
  onCodeChange,
  onSubmit,
  onResend,
  onBack,
}: {
  code: string;
  method: string;
  hasError: boolean;
  isSubmitting: boolean;
  isResending: boolean;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onResend: () => void;
  onBack: () => void;
}) {
  const usesEmail = method === "email";

  return (
    <ChallengeCard icon={<KeyRound size={19} aria-hidden="true" />} title="Multi-factor authentication">
      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <Field
          id="login-mfa-code"
          label={usesEmail ? "Six-digit sign-in code" : "Authentication or recovery code"}
          type="text"
          autoComplete="one-time-code"
          inputMode={usesEmail ? "numeric" : "text"}
          maxLength={32}
          value={code}
          onChange={(event) => onCodeChange(event.target.value)}
          aria-invalid={hasError || undefined}
          aria-describedby={hasError ? "login-error" : undefined}
          autoFocus
          required
          helper={
            usesEmail
              ? "Use the latest code sent to your registered email address."
              : "Use your authenticator code, or an unused recovery code in the format XXXX-XXXX."
          }
        />
        <button
          type="submit"
          disabled={isSubmitting || !code.trim()}
          aria-busy={isSubmitting}
          className="ops-primary w-full disabled:opacity-60"
        >
          {isSubmitting ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Verifying...
            </>
          ) : (
            <>
              Verify and continue
              <ArrowRight size={16} aria-hidden="true" />
            </>
          )}
        </button>
      </form>
      <ChallengeActions
        isResending={isResending}
        onResend={onResend}
        onBack={onBack}
        resendLabel="Resend email code"
        hideResend={!usesEmail}
      />
    </ChallengeCard>
  );
}

function ChallengeCard({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-primary-subtle text-primary">
          {icon}
        </span>
        {title}
      </div>
      {children}
    </section>
  );
}

function ChallengeActions({
  isResending,
  onResend,
  onBack,
  resendLabel,
  hideResend = false,
}: {
  isResending: boolean;
  onResend: () => void;
  onBack: () => void;
  resendLabel: string;
  hideResend?: boolean;
}) {
  return (
    <div className="mt-4 flex flex-col-reverse items-stretch justify-between gap-2 sm:flex-row sm:items-center">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-2 text-sm font-medium text-foreground-muted transition-colors hover:text-foreground"
      >
        <ArrowLeft size={15} aria-hidden="true" />
        Back to sign in
      </button>
      {!hideResend && (
        <button
          type="button"
          onClick={onResend}
          disabled={isResending}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-2 text-sm font-semibold text-primary hover:underline disabled:opacity-60"
        >
          {isResending && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
          {resendLabel}
        </button>
      )}
    </div>
  );
}

function ProviderButton({
  provider,
  busy,
  disabled,
  onClick,
}: {
  provider: OAuthProvider;
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const label = provider === "google" ? "Google" : "GitHub";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-busy={busy}
      className="ops-secondary w-full disabled:opacity-60"
    >
      {busy ? (
        <Loader2 size={16} className="animate-spin" aria-hidden="true" />
      ) : provider === "google" ? (
        <GoogleIcon />
      ) : (
        <GitHubIcon />
      )}
      {busy ? `Opening ${label}...` : `Continue with ${label}`}
    </button>
  );
}

function MessageBanner({
  id,
  tone,
  message,
}: {
  id: string;
  tone: "error" | "success";
  message: string;
}) {
  const isError = tone === "error";
  return (
    <div
      id={id}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
      className={`mb-4 flex gap-2 rounded-lg border p-3 text-sm leading-5 ${
        isError
          ? "border-danger/25 bg-danger-subtle text-danger"
          : "border-success/25 bg-success-subtle text-foreground"
      }`}
    >
      {isError ? (
        <LockKeyhole size={17} className="mt-0.5 shrink-0" aria-hidden="true" />
      ) : (
        <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
      )}
      <span>{message}</span>
    </div>
  );
}

function AuthAside() {
  return (
    <aside className="relative hidden overflow-hidden border-r border-border bg-sidebar p-10 lg:flex lg:flex-col lg:justify-between xl:p-14">
      <div className="pointer-events-none absolute inset-0 ops-page-grid opacity-55" aria-hidden="true" />
      <div
        className="pointer-events-none absolute -left-24 top-1/3 h-72 w-72 rounded-full bg-primary-glow blur-3xl"
        aria-hidden="true"
      />
      <BrandMark className="relative z-10 w-fit" />

      <div className="relative z-10 max-w-md">
        <p className="ops-kicker">Secure workspace access</p>
        <h2 className="mt-4 text-4xl font-semibold tracking-[-0.05em] text-foreground xl:text-5xl">
          Return to reviewed infrastructure.
        </h2>
        <p className="mt-5 text-sm leading-6 text-foreground-muted">
          Resume repository analysis, inspect generated infrastructure, and keep every deployment
          behind an explicit approval.
        </p>

        <div className="mt-8 space-y-3 rounded-xl border border-border bg-card/80 p-4 shadow-sm">
          <SecurityPoint icon={<LockKeyhole size={16} />} label="Session-backed authentication" />
          <SecurityPoint icon={<ShieldCheck size={16} />} label="Verification checks when required" />
          <SecurityPoint icon={<KeyRound size={16} />} label="Approval-gated infrastructure plans" />
        </div>
      </div>

      <p className="relative z-10 max-w-sm text-xs leading-5 text-foreground-subtle">
        Identity-provider sign-in depends on your ZeroOps backend configuration.
      </p>
    </aside>
  );
}

function SecurityPoint({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-3 text-xs font-medium text-foreground-muted">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary" aria-hidden="true">
        {icon}
      </span>
      <span>{label}</span>
    </div>
  );
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  helper?: string;
  trailing?: ReactNode;
};

function Field({ id, label, helper, trailing, ...props }: FieldProps) {
  const helperId = helper ? `${id}-helper` : undefined;
  const describedBy = [props["aria-describedby"], helperId].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      <div className="relative mt-2">
        <input
          {...props}
          id={id}
          aria-describedby={describedBy}
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

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.87h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.35Z" />
      <path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.63-2.42l-3.24-2.51c-.9.6-2.05.95-3.39.95-2.61 0-4.82-1.76-5.61-4.13H3.04v2.59A10 10 0 0 0 12 22Z" />
      <path fill="#FBBC05" d="M6.39 13.89A6 6 0 0 1 6.08 12c0-.66.11-1.3.31-1.89V7.52H3.04A10 10 0 0 0 2 12c0 1.61.39 3.14 1.04 4.48l3.35-2.59Z" />
      <path fill="#EA4335" d="M12 5.98c1.47 0 2.79.51 3.82 1.49l2.88-2.88A9.67 9.67 0 0 0 12 2a10 10 0 0 0-8.96 5.52l3.35 2.59C7.18 7.74 9.39 5.98 12 5.98Z" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.4c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.04 1.77 2.71 1.26 3.38.96.1-.75.4-1.26.74-1.55-2.57-.3-5.27-1.29-5.27-5.69 0-1.26.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.16 1.18a10.98 10.98 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.62 1.58.23 2.75.11 3.04.74.8 1.18 1.82 1.18 3.08 0 4.42-2.7 5.39-5.28 5.68.42.36.79 1.06.79 2.13v3.28c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
    </svg>
  );
}

function getPageCopy(step: AuthStep, email: string, phoneHint: string, mfaMethod: string) {
  if (step === "email") {
    return {
      kicker: "Email verification",
      title: "Check your email",
      description: `Open the single-use verification link sent to ${email || "your inbox"}.`,
    };
  }
  if (step === "phone") {
    return {
      kicker: "Phone verification",
      title: "Verify your phone",
      description: `Enter the six-digit code sent to ${phoneHint || "your registered phone"}.`,
    };
  }
  if (step === "mfa") {
    return {
      kicker: "Identity verification",
      title: "Complete sign-in",
      description:
        mfaMethod === "email"
          ? "Enter the latest one-time code sent to your registered email address."
          : "Use your authenticator app or an unused recovery code.",
    };
  }
  return {
    kicker: "Welcome back",
    title: "Sign in to ZeroOps AI",
    description: "Use your local account or a configured identity provider to return to your workspace.",
  };
}
