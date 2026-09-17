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

  const stepCopy: Record<AuthStep, { title: string; description: string }> = {
    credentials: {
      title: "Sign in to your control plane",
      description: "Access your pipelines, deployments, infrastructure gates, and telemetry.",
    },
    email: {
      title: "Verify your email address",
      description: "Enter the verification code sent to your email to continue.",
    },
    phone: {
      title: "Verify your phone number",
      description: "Enter the SMS verification code sent to your mobile device.",
    },
    mfa: {
      title: "Multi-factor authentication",
      description: "Enter the one-time authentication code from your authenticator app.",
    },
  };
  const pageCopy = stepCopy[step];

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

  return (
    <div className="min-h-screen flex flex-col justify-between bg-[#0a0e17] text-[#dfe2ef]">
      {/* Header Brand Bar */}
      <header className="w-full h-16 px-6 lg:px-12 flex items-center justify-between border-b border-[#1e293b] bg-[#0a0e17]/85 backdrop-blur-md sticky top-0 z-50">
        <BrandMark />
        <div className="flex items-center gap-4">
          <Link
            href="/docs"
            className="text-xs font-semibold text-slate-400 hover:text-[#f8fafc] transition-colors flex items-center gap-1"
          >
            Docs
            <ArrowRight size={13} aria-hidden="true" />
          </Link>
        </div>
      </header>

      {/* Main Split-Screen Container */}
      <main id="main-content" className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 lg:py-12 flex items-center justify-center">
        <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">
          {/* Left Column: Authentication Form Card */}
          <div className="w-full lg:col-span-6 flex flex-col justify-center max-w-xl mx-auto lg:max-w-none">
            <div className="bg-[#0f131c] rounded-xl border border-[#1e293b] p-6 sm:p-10 shadow-2xl shadow-black/50 relative overflow-hidden">
              <div className="absolute -top-10 right-0 w-44 h-44 bg-blue-500/5 rounded-full blur-2xl pointer-events-none" />

              <div className="mb-8">
                <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-500/30 mb-3.5">
                  <LockKeyhole size={13} className="text-blue-400" aria-hidden="true" />
                  <span className="text-xs text-blue-400 font-semibold tracking-wide">Secure Access</span>
                </div>
                <h1
                  ref={headingRef}
                  tabIndex={-1}
                  className="text-2xl sm:text-3xl font-bold tracking-tight text-[#f8fafc] focus:outline-none"
                >
                  {pageCopy.title}
                </h1>
                <p className="text-sm text-slate-400 mt-2">
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

          {/* Right Column: Platform Features */}
          <div className="w-full lg:col-span-6 flex flex-col space-y-5">
            <div className="relative bg-[#0f131c] rounded-xl border border-[#1e293b] p-6 lg:p-7 shadow-2xl shadow-black/50 overflow-hidden">
              <div className="absolute -top-16 -right-16 w-64 h-64 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />
              <div className="absolute -bottom-16 -left-16 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

              <div className="mb-6 relative z-10">
                <span className="text-xs font-semibold uppercase tracking-wider text-blue-400">Deployment Platform</span>
                <h3 className="text-xl font-bold text-[#f8fafc] mt-1">From repository evidence to live Azure workloads</h3>
                <p className="text-xs text-slate-400 mt-1">Every release gate is recorded, verified, and audited with real evidence.</p>
              </div>

              <div className="space-y-3.5 relative z-10">
                <div className="bg-[#141926] rounded-lg p-3.5 border border-[#1e293b] flex items-start gap-3">
                  <span className="w-7 h-7 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center shrink-0 text-xs font-bold">1</span>
                  <div>
                    <h4 className="text-xs font-semibold text-[#f8fafc]">Deep Repository & Stack Analysis</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Detects frameworks, package managers, port configs, and generates declarative Terraform definitions.</p>
                  </div>
                </div>

                <div className="bg-[#141926] rounded-lg p-3.5 border border-[#1e293b] flex items-start gap-3">
                  <span className="w-7 h-7 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 text-xs font-bold">2</span>
                  <div>
                    <h4 className="text-xs font-semibold text-[#f8fafc]">Real-Time Security Scanning</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Automated scans with Gitleaks, Semgrep, and Trivy running directly in isolated environments.</p>
                  </div>
                </div>

                <div className="bg-[#141926] rounded-lg p-3.5 border border-[#1e293b] flex items-start gap-3">
                  <span className="w-7 h-7 rounded-md bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center shrink-0 text-xs font-bold">3</span>
                  <div>
                    <h4 className="text-xs font-semibold text-[#f8fafc]">Evidence-Based Approvals</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Commit-pinned release records with gated approvals. Missing checks block — never pass silently.</p>
                  </div>
                </div>

                <div className="bg-[#141926] rounded-lg p-3.5 border border-[#1e293b] flex items-start gap-3">
                  <span className="w-7 h-7 rounded-md bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center shrink-0 text-xs font-bold">4</span>
                  <div>
                    <h4 className="text-xs font-semibold text-[#f8fafc]">Live Azure App Service Deployment</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Direct provisioning with HTTP health probes, smoke tests, and Azure Monitor integration.</p>
                  </div>
                </div>
              </div>

              {/* Pipeline Preview */}
              <div className="mt-5 bg-[#050810] rounded-lg p-4 border border-slate-800/80 font-mono text-xs text-slate-300 shadow-inner relative z-10">
                <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-slate-800">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                    <span className="text-xs text-slate-400 ml-2">deployment-pipeline</span>
                  </div>
                </div>
                <div className="space-y-1.5 text-[11px] leading-relaxed">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500">[stage 1]</span>
                    <span className="text-emerald-400 font-semibold">PASS</span>
                    <span className="text-slate-300">Repository analysis completed</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500">[stage 2]</span>
                    <span className="text-emerald-400 font-semibold">PASS</span>
                    <span className="text-slate-300">Security scan — 0 critical findings</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500">[stage 3]</span>
                    <span className="text-amber-400 font-semibold">PENDING</span>
                    <span className="text-slate-200">Awaiting deployment approval</span>
                  </div>
                </div>
              </div>

              {/* Security Strip */}
              <div className="mt-5 pt-4 border-t border-[#1e293b] flex items-center justify-between text-xs text-slate-400 relative z-10">
                <span className="flex items-center gap-1.5 font-medium text-[#f8fafc]">
                  <span className="text-emerald-400 font-bold">✓</span> No synthetic telemetry
                </span>
                <span className="flex items-center gap-1.5 font-medium text-[#f8fafc]">
                  <span className="text-emerald-400 font-bold">✓</span> Credential isolation
                </span>
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="w-full py-4 border-t border-[#1e293b] text-center text-xs text-slate-500">
        &copy; {new Date().getFullYear()} ZeroOps AI. All rights reserved.
      </footer>
    </div>
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
        <span className="h-px flex-1 bg-[#1e293b]" />
        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
          or continue with email
        </span>
        <span className="h-px flex-1 bg-[#1e293b]" />
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <Field
          id="login-email"
          label="Work Email"
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          maxLength={320}
          value={formData.email}
          onChange={onFieldChange}
          aria-invalid={hasError || undefined}
          aria-describedby={hasError ? "login-error" : undefined}
          placeholder="name@company.com"
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
          placeholder="Enter your credentials"
          required
          trailing={
            <button
              type="button"
              onClick={onTogglePassword}
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              className="grid h-10 w-10 place-items-center rounded-md text-slate-400 transition-colors hover:text-[#f8fafc]"
            >
              {showPassword ? (
                <EyeOff size={17} aria-hidden="true" />
              ) : (
                <Eye size={17} aria-hidden="true" />
              )}
            </button>
          }
        />

        <div className="flex items-center pt-1 pb-1">
          <input
            id="remember-me"
            type="checkbox"
            defaultChecked
            className="h-4 w-4 bg-[#0a0e17] border-[#1e293b] rounded text-blue-600 focus:ring-blue-500 focus:ring-offset-slate-900 cursor-pointer"
          />
          <label htmlFor="remember-me" className="ml-2.5 block text-xs text-slate-400 select-none cursor-pointer">
            Remember this device for 30 days
          </label>
        </div>

        <button
          type="submit"
          disabled={isBusy}
          aria-busy={isSubmitting}
          className="w-full mt-2 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white py-2.5 px-4 rounded-lg text-sm font-semibold transition-all duration-150 shadow-lg shadow-blue-600/20 active:scale-[0.99] disabled:opacity-60"
        >
          {isSubmitting ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Signing in...
            </>
          ) : (
            <>
              <span>Sign In</span>
              <ArrowRight size={16} aria-hidden="true" />
            </>
          )}
        </button>
      </form>

      <p className="mt-7 text-center text-sm text-slate-400">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="font-semibold text-blue-400 hover:text-blue-300 transition-colors inline-flex items-center gap-1">
          Sign up free
          <ArrowRight size={13} aria-hidden="true" />
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
      className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border border-[#1e293b] bg-[#141926] hover:bg-[#1e293b] text-[#f8fafc] text-sm font-medium transition-all duration-150 shadow-sm hover:border-slate-600 disabled:opacity-60"
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
          ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
          : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
      }`}
    >
      {isError ? (
        <LockKeyhole size={17} className="mt-0.5 shrink-0 text-rose-400" aria-hidden="true" />
      ) : (
        <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-400" aria-hidden="true" />
      )}
      <span>{message}</span>
    </div>
  );
}

function AuthAside() {
  return null;
}

function SecurityPoint({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-3 text-xs font-medium text-slate-400">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-blue-500/10 text-blue-400" aria-hidden="true">
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
      <label htmlFor={id} className="block text-xs font-medium text-[#e2e8f0] mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          {...props}
          id={id}
          aria-describedby={describedBy}
          className={`block w-full rounded-lg border border-[#1e293b] bg-[#0a0e17] px-3.5 py-2.5 text-sm text-[#f8fafc] placeholder:text-slate-600 outline-none transition-all focus:border-blue-500 focus:ring-1 focus:ring-blue-500 ${
            trailing ? "pr-12" : ""
          }`}
        />
        {trailing && <div className="absolute right-1 top-1/2 -translate-y-1/2">{trailing}</div>}
      </div>
      {helper && (
        <p id={helperId} className="mt-1 text-xs text-slate-500">
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
