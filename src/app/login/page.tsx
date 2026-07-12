"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Circle, Eye, EyeOff, ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { isMfaChallenge, useAuth } from "@/lib/AuthContext";
import { getErrorMessage } from "@/lib/api";

export default function LoginPage() {
  const { login, verifyMfa, loginWithGitHub, loginWithGoogle } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [isGitHubRedirecting, setIsGitHubRedirecting] = useState(false);
  const [isGoogleRedirecting, setIsGoogleRedirecting] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requiresMfa, setRequiresMfa] = useState(false);
  const [mfaCode, setMfaCode] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("mfa") === "required") setRequiresMfa(true);

    const oauthError = params.get("oauth_error");
    if (oauthError) {
      const messages: Record<string, string> = {
        access_denied: "The provider sign-in was cancelled.",
        invalid_state: "The sign-in request expired or could not be verified. Please try again.",
        token_exchange_failed: "The provider could not complete sign-in. Please try again.",
        no_verified_email: "Your provider account needs a verified email address before it can sign in.",
        github_user_fetch_failed: "We could not retrieve your GitHub profile. Please try again.",
        google_user_fetch_failed: "We could not retrieve your Google profile. Please try again.",
      };
      setError(messages[oauthError] || "Provider sign-in failed. Please try again.");
    }
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await login(formData.email, formData.password);
      if (isMfaChallenge(result)) {
        setRequiresMfa(true);
        setMfaCode("");
        setIsSubmitting(false);
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Invalid email or password"));
      setIsSubmitting(false);
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      await verifyMfa(mfaCode);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Unable to verify your authentication code"));
      setIsSubmitting(false);
    }
  };

  // Stagger container animation for left column content
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.2,
      },
    },
  };

  // Fade in and slide up animation for children
  const itemVariants = {
    hidden: { opacity: 0, y: 10 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.5, ease: "easeOut" as const },
    },
  };

  return (
    <main id="main-content" className="dark flex min-h-screen w-full bg-background selection:bg-primary/30 p-2 transition-all duration-500 lg:h-screen lg:overflow-hidden lg:p-4 text-foreground">
      {/* Left Column (Hero & Video Background) */}
      <div className="w-[52%] hidden lg:flex relative flex-col items-center justify-end pb-32 px-12 rounded-3xl overflow-hidden shadow-2xl h-full border border-border/10 dark">
        {/* Background Video */}
        <video
          autoPlay
          muted
          loop
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
        >
          <source
            src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260506_081238_406ed0e3-5d83-436e-a512-0bbff7ec5b95.mp4"
            type="video/mp4"
          />
        </video>

        {/* Staggered Animations Content Overlay */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="relative z-10 w-full max-w-xs space-y-8 text-left"
        >
          {/* Brand/Logo */}
          <motion.div variants={itemVariants} className="flex items-center gap-2.5">
            <Circle className="fill-white text-white w-6 h-6" />
            <span className="text-xl font-semibold tracking-tight text-white">
              ZeroOps
            </span>
          </motion.div>

          {/* Heading Block */}
          <motion.div variants={itemVariants} className="space-y-2">
            <h1 className="text-4xl font-medium tracking-tight whitespace-nowrap text-white">
              Welcome Back
            </h1>
            <p className="text-white/60 text-sm leading-relaxed px-4">
              Verify your credentials to access your autonomous clusters.
            </p>
          </motion.div>

          {/* Steps list */}
          <motion.div variants={itemVariants} className="space-y-4">
            <StepItem number={1} text="Authenticate identity" active />
            <StepItem number={2} text="Synchronize settings" />
            <StepItem number={3} text="Access dashboard" />
          </motion.div>
        </motion.div>
      </div>

      {/* Right Column (Sign In Form) */}
      <div className="flex-1 flex flex-col items-center justify-center py-12 lg:py-6 px-4 sm:px-12 lg:px-16 xl:px-24 overflow-y-auto lg:overflow-hidden relative">

        {/* Sign In Form Content */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="w-full max-w-xl space-y-8 lg:space-y-6 sm:space-y-10"
        >
          {/* Header */}
          <div className="space-y-2 text-left w-full">
            <h2 className="text-3xl font-medium tracking-tight text-foreground">
              {requiresMfa ? "Verify it’s you" : "Sign In to ZeroOps"}
            </h2>
            <p className="text-foreground-muted text-sm">
              {requiresMfa
                ? "Enter a code from your authenticator app or one of your recovery codes."
                : "Input your account details to resume the journey."}
            </p>
          </div>

          {/* Social login buttons */}
          {!requiresMfa && <div className="grid grid-cols-2 gap-4 w-full">
            <SocialButton
              icon={ChromeIcon}
              label={isGoogleRedirecting ? "Redirecting..." : "Google"}
              disabled={isGoogleRedirecting}
              loading={isGoogleRedirecting}
              onClick={() => {
                setIsGoogleRedirecting(true);
                loginWithGoogle();
              }}
            />
            <button
              type="button"
              onClick={() => {
                setIsGitHubRedirecting(true);
                loginWithGitHub();
              }}
              disabled={isGitHubRedirecting}
              className="flex items-center justify-center gap-2.5 h-12 bg-card hover:bg-card-hover border border-border/80 text-foreground font-medium rounded-xl transition-all duration-200 w-full cursor-pointer focus:ring-2 focus:ring-primary/25 disabled:opacity-60"
            >
              {isGitHubRedirecting ? (
                <div className="w-4 h-4 border-2 border-foreground-muted border-t-transparent rounded-full animate-spin" />
              ) : (
                <GithubIcon size={18} />
              )}
              <span className="text-sm">{isGitHubRedirecting ? "Redirecting..." : "GitHub"}</span>
            </button>
          </div>}

          {/* Divider */}
          {!requiresMfa && <div className="relative w-full flex py-2 items-center justify-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border/40"></div>
            </div>
            <span className="relative z-10 bg-background px-4 text-xs font-medium text-foreground-muted uppercase tracking-widest">
              Or
            </span>
          </div>}

          {/* Form */}
          <form onSubmit={requiresMfa ? handleMfaSubmit : handleSubmit} className="space-y-4 w-full text-left">
            {error && (
              <div role="alert" aria-live="assertive" className="p-3 bg-danger/10 border border-danger/25 text-danger rounded-xl text-xs font-medium">
                {error}
              </div>
            )}
            {requiresMfa ? (
              <>
                <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 text-xs leading-5 text-foreground-muted">
                  <div className="mb-2 flex items-center gap-2 font-semibold text-foreground"><ShieldCheck size={16} className="text-primary" /> Multi-factor authentication</div>
                  Use the current six-digit code from your authenticator app. If you do not have it, enter an unused recovery code in the format <span className="font-mono text-foreground">XXXX-XXXX</span>.
                </div>
                <InputGroup
                  label="Authentication code"
                  placeholder="123456 or XXXX-XXXX"
                  type="text"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  autoFocus
                  required
                />
                <button type="submit" disabled={isSubmitting || !mfaCode.trim()} className="w-full h-14 bg-primary hover:bg-primary-hover text-white font-semibold rounded-xl active:scale-[0.98] mt-4 flex items-center justify-center gap-2 cursor-pointer transition-all duration-200 glow-blue shadow-lg shadow-primary/20 disabled:cursor-not-allowed disabled:opacity-60">
                  {isSubmitting ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <><span>Verify and continue</span><ArrowRight size={16} /></>}
                </button>
              </>
            ) : (
              <>
            <InputGroup
              label="Email"
              placeholder="name@company.com"
              type="email"
              name="email"
              value={formData.email}
              onChange={handleInputChange}
              required
            />

            <div className="space-y-1">
              <InputGroup
                label="Password"
                placeholder="••••••••"
                type={showPassword ? "text" : "password"}
                name="password"
                value={formData.password}
                onChange={handleInputChange}
                required
                rightElement={
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="text-foreground-muted hover:text-foreground p-1 transition-colors focus:outline-none"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                }
              />
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full h-14 bg-primary hover:bg-primary-hover text-white font-semibold rounded-xl active:scale-[0.98] mt-4 flex items-center justify-center gap-2 cursor-pointer transition-all duration-200 glow-blue shadow-lg shadow-primary/20"
            >
              {isSubmitting ? (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
              </>
            )}
          </form>

          {/* Footer Link */}
          {requiresMfa ? (
            <button type="button" onClick={() => window.location.assign("/login")} className="w-full text-center text-sm text-foreground-muted hover:text-primary transition-all">
              Use a different sign-in method
            </button>
          ) : (
            <p className="text-sm text-foreground-muted text-center w-full">
              New to ZeroOps?{" "}
              <Link href="/signup" className="text-foreground font-medium hover:underline hover:text-primary transition-all">Create account</Link>
            </p>
          )}
        </motion.div>
      </div>
    </main>
  );
}

// 1. StepItem Component
function StepItem({
  number,
  text,
  active = false,
}: {
  number: number;
  text: string;
  active?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-4 px-4 py-3 rounded-2xl transition-all duration-300 w-full border ${
        active
          ? "bg-white text-black border-white shadow-lg"
          : "bg-brand-gray text-white border-transparent"
      }`}
    >
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${
          active ? "bg-black text-white" : "bg-white/10 text-white/40"
        }`}
      >
        {number}
      </div>
      <span className="text-sm font-medium tracking-wide">{text}</span>
    </div>
  );
}

// 2. SocialButton Component
function SocialButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  loading,
}: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex items-center justify-center gap-2.5 h-12 bg-card hover:bg-card-hover border border-border/80 text-foreground font-medium rounded-xl transition-all duration-200 w-full cursor-pointer focus:ring-2 focus:ring-primary/25 disabled:opacity-60"
    >
      {loading ? (
        <div className="w-4 h-4 border-2 border-foreground-muted border-t-transparent rounded-full animate-spin" />
      ) : (
        <Icon size={18} />
      )}
      <span className="text-sm">{label}</span>
    </button>
  );
}

// Custom SVGs for Chrome/Google and GitHub (since brand icons aren't in this lucide version)
function ChromeIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="4" />
      <line x1="21.17" y1="8" x2="12" y2="8" />
      <line x1="3.95" y1="6.06" x2="8.54" y2="14" />
      <line x1="10.88" y1="21.94" x2="15.46" y2="14" />
    </svg>
  );
}

function GithubIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="currentColor"
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

// 3. InputGroup Component
interface InputGroupProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  helperText?: string;
  rightElement?: React.ReactNode;
}

function InputGroup({
  label,
  helperText,
  rightElement,
  ...props
}: InputGroupProps) {
  const inputId = props.id || props.name;
  return (
    <div className="flex flex-col gap-2 w-full">
      <label htmlFor={inputId} className="text-sm font-medium text-foreground">{label}</label>
      <div className="relative w-full">
        <input
          {...props}
          id={inputId}
          className="w-full bg-brand-gray border border-border/40 rounded-xl h-11 px-4 text-foreground placeholder:text-foreground-muted/40 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all duration-200"
        />
        {rightElement && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center">
            {rightElement}
          </div>
        )}
      </div>
      {helperText && (
        <p className="text-[11px] text-foreground-muted">{helperText}</p>
      )}
    </div>
  );
}
