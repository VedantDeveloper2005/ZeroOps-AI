"use client";

import { useState, type InputHTMLAttributes, type ReactNode } from "react";
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

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  helper?: string;
  trailing?: ReactNode;
}

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
          {/* Left Column: Registration Form Card */}
          <div className="w-full lg:col-span-6 flex flex-col justify-center max-w-xl mx-auto lg:max-w-none">
            <div className="bg-[#0f131c] rounded-xl border border-[#1e293b] p-6 sm:p-10 shadow-2xl shadow-black/50 relative overflow-hidden">
              <div className="absolute -top-10 right-0 w-44 h-44 bg-blue-500/5 rounded-full blur-2xl pointer-events-none" />

              <div className="mb-7">
                <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-500/30 mb-3.5">
                  <span className="text-xs text-blue-400 font-semibold tracking-wide">Deployment Platform</span>
                </div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#f8fafc]">
                  {checkEmail ? "Check your email" : "Create your ZeroOps AI workspace"}
                </h1>
                <p className="text-sm text-slate-400 mt-2">
                  {checkEmail
                    ? `Open the single-use verification link sent to ${formData.email}.`
                    : "Create your account to start deploying to Azure with evidence-based approvals."}
                </p>
              </div>

              {error && (
                <div
                  role="alert"
                  className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm leading-5 text-rose-400"
                >
                  {error}
                </div>
              )}
              {notice && (
                <div
                  role="status"
                  className="mb-4 flex gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm leading-5 text-emerald-300"
                >
                  <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-400" aria-hidden="true" />
                  <span>{notice}</span>
                </div>
              )}

              {checkEmail ? (
                <section className="rounded-xl border border-[#1e293b] bg-[#141926] p-5 shadow-sm sm:p-6">
                  <MailCheck size={26} className="text-blue-400" aria-hidden="true" />
                  <h2 className="mt-3 text-sm font-semibold text-[#f8fafc]">
                    Verify before signing in
                  </h2>
                  <p className="mt-1.5 text-xs leading-5 text-slate-400">
                    The verification link expires and can only be used once. Phone verification follows
                    only when a phone number was provided and the backend requires that step.
                  </p>
                  <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => void resendVerificationLink()}
                      disabled={isResending}
                      className="flex-1 py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm shadow-md transition disabled:opacity-60"
                    >
                      {isResending && (
                        <Loader2 size={15} className="animate-spin mr-1 inline" aria-hidden="true" />
                      )}
                      Request new link
                    </button>
                    <Link
                      href="/login"
                      className="flex-1 py-2.5 px-4 rounded-lg border border-[#1e293b] bg-[#0f131c] hover:bg-[#181b25] text-center text-sm font-medium text-[#f8fafc] transition"
                    >
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
                    className="mt-4 min-h-11 text-sm font-medium text-blue-400 hover:text-blue-300 transition"
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
                      className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border border-[#1e293b] bg-[#141926] hover:bg-[#1e293b] text-[#f8fafc] text-sm font-medium transition-all duration-150 shadow-sm hover:border-slate-600 disabled:opacity-60"
                    >
                      {oauthProvider === "google" && (
                        <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                      )}
                      <GoogleIcon />
                      Google
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setOauthProvider("github");
                        loginWithGitHub();
                      }}
                      disabled={oauthProvider !== null}
                      className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border border-[#1e293b] bg-[#141926] hover:bg-[#1e293b] text-[#f8fafc] text-sm font-medium transition-all duration-150 shadow-sm hover:border-slate-600 disabled:opacity-60"
                    >
                      {oauthProvider === "github" && (
                        <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                      )}
                      <GitHubIcon />
                      GitHub
                    </button>
                  </div>
                  <p className="mt-2 text-center text-[11px] leading-5 text-slate-500">
                    Provider sign-up is available only when its backend credentials are configured.
                  </p>

                  <div className="my-6 flex items-center gap-3" aria-hidden="true">
                    <span className="h-px flex-1 bg-[#1e293b]" />
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                      or continue with email
                    </span>
                    <span className="h-px flex-1 bg-[#1e293b]" />
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
                      label="Work Email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      value={formData.email}
                      onChange={updateField}
                      placeholder="name@company.com"
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
                      placeholder="+14155552671"
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
                      placeholder="At least 12 characters"
                      required
                      helper="Use at least 12 characters with uppercase, lowercase, a number, and a symbol."
                      trailing={
                        <button
                          type="button"
                          onClick={() => setShowPassword((visible) => !visible)}
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

                    <p className="text-xs leading-5 text-slate-400">
                      By creating an account, you agree to the{" "}
                      <Link href="/terms" className="font-medium text-blue-400 hover:text-blue-300 transition">
                        Terms
                      </Link>{" "}
                      and acknowledge the{" "}
                      <Link href="/privacy" className="font-medium text-blue-400 hover:text-blue-300 transition">
                        Privacy Policy
                      </Link>
                      .
                    </p>

                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full mt-2 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white py-2.5 px-4 rounded-lg text-sm font-semibold transition-all duration-150 shadow-lg shadow-blue-600/20 active:scale-[0.99] disabled:opacity-60"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                          Creating account…
                        </>
                      ) : (
                        <>
                          <span>Create workspace</span>
                          <ArrowRight size={16} aria-hidden="true" />
                        </>
                      )}
                    </button>
                  </form>

                  <p className="mt-7 text-center text-sm text-slate-400">
                    Already have an account?{" "}
                    <Link href="/login" className="font-semibold text-blue-400 hover:text-blue-300 transition inline-flex items-center gap-1">
                      Sign in
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Right Column: Platform Value Props Bento */}
          <div className="w-full lg:col-span-6 flex flex-col space-y-5">
            <div className="relative bg-[#0f131c] rounded-xl border border-[#1e293b] p-6 lg:p-7 shadow-2xl shadow-black/50 overflow-hidden">
              <div className="absolute -top-16 -right-16 w-64 h-64 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />
              <div className="absolute -bottom-16 -left-16 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

              <div className="mb-6">
                <span className="text-xs font-semibold uppercase tracking-wider text-blue-400">Deployment Platform</span>
                <h3 className="text-xl font-bold text-[#f8fafc] mt-1">From repository evidence to live Azure workloads</h3>
                <p className="text-xs text-slate-400 mt-1">Every release gate is recorded, verified, and audited with zero mock data.</p>
              </div>

              <div className="space-y-3.5">
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
                    <h4 className="text-xs font-semibold text-[#f8fafc]">Real-Time Security & Policy Enforcement</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Automated scans with Gitleaks, Semgrep, and Trivy running directly in isolated environments.</p>
                  </div>
                </div>

                <div className="bg-[#141926] rounded-lg p-3.5 border border-[#1e293b] flex items-start gap-3">
                  <span className="w-7 h-7 rounded-md bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center shrink-0 text-xs font-bold">3</span>
                  <div>
                    <h4 className="text-xs font-semibold text-[#f8fafc]">Live App Service Provisioning & Telemetry</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">Direct deployment to Azure App Service with live HTTP health probes and Azure Monitor metrics.</p>
                  </div>
                </div>
              </div>

              {/* Security Strip */}
              <div className="mt-6 pt-5 border-t border-[#1e293b] flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1.5 font-medium text-[#f8fafc]">
                  <span className="text-emerald-400 font-bold">✓</span> Zero fake runtime progress
                </span>
                <span className="flex items-center gap-1.5 font-medium text-[#f8fafc]">
                  <span className="text-emerald-400 font-bold">✓</span> RBAC isolated tenants
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

function Field({ id, label, helper, trailing, ...props }: FieldProps) {
  const helperId = helper ? `${id}-helper` : undefined;
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-[#e2e8f0] mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          {...props}
          id={id}
          aria-describedby={helperId}
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
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current text-white" aria-hidden="true">
      <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.4c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.04 1.77 2.71 1.26 3.38.96.1-.75.4-1.26.74-1.55-2.57-.3-5.27-1.29-5.27-5.69 0-1.26.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.16 1.18a10.98 10.98 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.62 1.58.23 2.75.11 3.04.74.8 1.18 1.82 1.18 3.08 0 4.42-2.7 5.39-5.28 5.68.42.36.79 1.06.79 2.13v3.28c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
    </svg>
  );
}
