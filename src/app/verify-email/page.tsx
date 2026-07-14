"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircle2, XCircle, Loader2, ArrowRight, Mail, Sparkles } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { getErrorMessage } from "@/lib/api";

function VerifyEmailContent() {
  const { verifyEmail, verifyPhone, resendVerification, resendPhoneVerification } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"loading" | "phone" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [email, setEmail] = useState("");
  const [phoneHint, setPhoneHint] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [isResending, setIsResending] = useState(false);
  const [isVerifyingPhone, setIsVerifyingPhone] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMsg("No verification token was provided in the link.");
      return;
    }

    const performVerification = async () => {
      try {
        const result = await verifyEmail(token);
        if ("phone_verification_required" in result) {
          setPhoneHint(result.phone_hint);
          setStatus("phone");
        } else {
          setStatus("success");
        }
      } catch (err) {
        setStatus("error");
        setErrorMsg(getErrorMessage(err, "The verification link is invalid or has expired. Please request a new link below."));
      }
    };

    performVerification();
  }, [token, verifyEmail]);

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setIsResending(true);
    setResendSuccess(false);
    setErrorMsg("");
    try {
      await resendVerification(email);
      setResendSuccess(true);
    } catch (err) {
      setErrorMsg(getErrorMessage(err, "Could not resend verification email. Please try again."));
    } finally {
      setIsResending(false);
    }
  };

  const handleVerifyPhone = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsVerifyingPhone(true);
    setErrorMsg("");
    try {
      const result = await verifyPhone(phoneCode);
      if ("id" in result) {
        router.replace("/dashboard/repositories");
        return;
      }
      setStatus("success");
    } catch (err) {
      setErrorMsg(getErrorMessage(err, "The code is invalid or has expired. Please try again."));
    } finally {
      setIsVerifyingPhone(false);
    }
  };

  const handleResendPhone = async () => {
    setIsResending(true);
    setErrorMsg("");
    try {
      const result = await resendPhoneVerification();
      setPhoneHint(result.phone_hint);
      setResendSuccess(true);
    } catch (err) {
      setErrorMsg(getErrorMessage(err, "Could not resend the phone verification code. Please try again."));
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="w-full max-w-md p-6 bg-slate-900/60 rounded-3xl border border-slate-800 backdrop-blur-xl shadow-2xl relative overflow-hidden">
      {/* Decorative top blur */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-1 bg-gradient-to-r from-transparent via-primary/50 to-transparent blur-sm" />

      <div className="flex flex-col items-center text-center">
        {status === "loading" && (
          <>
            <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-6 animate-pulse">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white mb-2">
              Verifying your email
            </h1>
            <p className="text-sm text-slate-400 max-w-sm">
              We are verifying your account credentials. This will only take a moment...
            </p>
          </>
        )}

        {status === "phone" && (
          <>
            <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-6">
              <Mail className="h-8 w-8" />
            </motion.div>
            <h1 className="text-2xl font-bold tracking-tight text-white mb-2">Verify your phone</h1>
            <p className="text-sm text-slate-400 max-w-sm mb-6">Your email is verified. Enter the six-digit code sent to <span className="font-semibold text-white">{phoneHint}</span>.</p>
            {errorMsg && <div role="alert" aria-live="assertive" className="mb-4 w-full rounded-xl border border-red-500/25 bg-red-500/10 p-3 text-xs font-medium text-red-200">{errorMsg}</div>}
            {resendSuccess && <div className="mb-4 w-full rounded-xl border border-emerald-500/25 bg-emerald-500/10 p-3 text-xs font-medium text-emerald-300">A new verification code has been sent.</div>}
            <form onSubmit={handleVerifyPhone} className="w-full space-y-4">
              <label className="block text-left text-xs font-semibold text-slate-300" htmlFor="phone-verification-code">Verification code</label>
              <input id="phone-verification-code" type="text" value={phoneCode} onChange={(event) => setPhoneCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} placeholder="123456" required autoFocus className="w-full rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3 text-center font-mono text-lg tracking-[0.3em] text-white placeholder:tracking-normal placeholder:text-slate-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20" />
              <button type="submit" disabled={isVerifyingPhone || phoneCode.trim().length !== 6} className="w-full flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60">
                {isVerifyingPhone ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Verify phone <ArrowRight className="h-4 w-4" /></>}
              </button>
            </form>
            <button type="button" disabled={isResending} onClick={handleResendPhone} className="mt-5 min-h-11 text-xs font-semibold text-primary hover:underline disabled:opacity-60">
              {isResending ? "Sending..." : "Resend code"}
            </button>
          </>
        )}

        {status === "success" && (
          <>
            <motion.div 
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="h-16 w-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-400 mb-6"
            >
              <CheckCircle2 className="h-8 w-8" />
            </motion.div>
            <h1 className="text-2xl font-bold tracking-tight text-white mb-2">
              Email Verified!
            </h1>
            <p className="text-sm text-slate-400 max-w-sm mb-8">
              Your contact details are verified and your ZeroOps AI account is ready to use.
            </p>
            <Link
              href="/login"
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white transition hover:bg-primary-hover shadow-lg shadow-primary/20"
            >
              Go to Sign In <ArrowRight className="h-4 w-4" />
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <motion.div 
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="h-16 w-16 rounded-2xl bg-red-500/10 flex items-center justify-center text-red-400 mb-6"
            >
              <XCircle className="h-8 w-8" />
            </motion.div>
            <h1 className="text-2xl font-bold tracking-tight text-white mb-2">
              Verification Failed
            </h1>
            <p className="text-sm text-red-200/80 max-w-sm mb-6 font-medium">
              {errorMsg}
            </p>

            {resendSuccess ? (
              <div className="w-full p-4 bg-emerald-500/10 border border-emerald-500/25 rounded-2xl text-emerald-400 text-xs font-semibold text-left mb-6">
                Verification link resent! Check your inbox (and spam folder) for the instructions.
              </div>
            ) : null}

            <form onSubmit={handleResend} className="w-full space-y-4">
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email address"
                  required
                  className="w-full rounded-xl border border-slate-800 bg-slate-950/60 py-3 pl-10 pr-4 text-sm text-white placeholder:text-slate-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                />
                <Mail className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-500" />
              </div>

              <button
                type="submit"
                disabled={isResending}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-800 border border-slate-700/60 px-4 py-3 text-sm font-bold text-white transition hover:bg-slate-700 disabled:opacity-60"
              >
                {isResending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>Resend Verification Link <ArrowRight className="h-4 w-4" /></>
                )}
              </button>
            </form>

            <Link href="/login" className="mt-6 text-xs font-semibold text-slate-400 hover:text-white transition">
              Back to Login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className="dark min-h-screen w-full bg-slate-950 flex flex-col items-center justify-center p-4 text-foreground relative overflow-hidden">
      {/* Dynamic glow backgrounds */}
      <div className="pointer-events-none absolute left-1/4 top-1/4 h-96 w-96 rounded-full bg-indigo-500/10 blur-[120px]" />
      <div className="pointer-events-none absolute right-1/4 bottom-1/4 h-96 w-96 rounded-full bg-purple-500/10 blur-[120px]" />

      <div className="mb-8 flex flex-col items-center">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[10px] font-bold tracking-wide text-primary mb-4">
          <Sparkles size={12} /> ACCOUNT SECURITY
        </span>
        <div className="text-3xl font-extrabold text-white tracking-tight">ZeroOps AI</div>
      </div>

      <Suspense fallback={
        <div className="w-full max-w-md p-6 bg-slate-900/60 rounded-3xl border border-slate-800 flex flex-col items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }>
        <VerifyEmailContent />
      </Suspense>
    </main>
  );
}
