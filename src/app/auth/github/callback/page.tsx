"use client";

import { Suspense, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { Circle, CheckCircle, XCircle, Loader2 } from "lucide-react";

export default function GitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-background flex items-center justify-center p-4">
          <div className="text-center space-y-4">
            <Loader2 size={32} className="animate-spin text-primary mx-auto" />
            <p className="text-sm text-foreground-muted">Connecting to GitHub...</p>
          </div>
        </main>
      }
    >
      <GitHubCallbackContent />
    </Suspense>
  );
}

function GitHubCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refreshUser, user } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const success = searchParams.get("success");
    const error = searchParams.get("error");

    if (error) {
      setStatus("error");
      const messages: Record<string, string> = {
        missing_params: "Missing authorization parameters from GitHub.",
        invalid_state: "Security validation failed. Please try again.",
        token_exchange_failed: "Failed to authenticate with GitHub. Please try again.",
        github_user_fetch_failed: "Could not retrieve your GitHub profile.",
        no_email: "No verified email found on your GitHub account. Please add a verified email to GitHub and try again.",
        server_error: "An internal error occurred. Please try again.",
      };
      setErrorMessage(messages[error] || `GitHub authentication failed: ${error}`);
      return;
    }

    if (success === "true") {
      setStatus("success");
      // Refresh user session then navigate
      refreshUser().then(() => {
        // Small delay for the success animation
        setTimeout(() => {
          // Check if user has deployed
          fetch("/api/dashboard/stats", { credentials: "include" })
            .then((res) => (res.ok ? res.json() : { has_deployed: false }))
            .then((stats) => {
              if (stats.has_deployed) {
                router.push("/dashboard");
              } else {
                router.push("/dashboard/repositories");
              }
            })
            .catch(() => router.push("/dashboard/repositories"));
        }, 1500);
      });
    } else {
      // No success and no error — shouldn't happen normally
      setStatus("error");
      setErrorMessage("Invalid callback. Please try logging in again.");
    }
  }, [searchParams]);

  return (
    <main className="min-h-screen bg-background flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="w-full max-w-md text-center space-y-8"
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5">
          <Circle className="fill-primary text-primary w-7 h-7" />
          <span className="text-xl font-semibold tracking-tight text-foreground">
            ZeroOps
          </span>
        </div>

        {/* Status Card */}
        <div className="glass rounded-2xl border border-border/40 p-8 shadow-2xl space-y-6">
          {status === "loading" && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-4"
            >
              <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center glow-blue">
                <Loader2 size={28} className="text-white animate-spin" />
              </div>
              <h2 className="text-xl font-bold text-foreground">
                Connecting GitHub
              </h2>
              <p className="text-sm text-foreground-muted">
                Securing your session and syncing repositories...
              </p>

              {/* Animated progress dots */}
              <div className="flex items-center justify-center gap-1.5 pt-2">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-2 h-2 rounded-full bg-primary"
                    animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
                    transition={{
                      duration: 1.2,
                      repeat: Infinity,
                      delay: i * 0.2,
                    }}
                  />
                ))}
              </div>
            </motion.div>
          )}

          {status === "success" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="space-y-4"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 15, delay: 0.1 }}
                className="w-16 h-16 mx-auto rounded-2xl bg-success/10 border border-success/30 flex items-center justify-center"
              >
                <CheckCircle size={32} className="text-success" />
              </motion.div>
              <h2 className="text-xl font-bold text-foreground">
                GitHub Connected
              </h2>
              <p className="text-sm text-foreground-muted">
                {user?.github_username
                  ? `Authenticated as @${user.github_username}`
                  : "Authentication successful"}
                . Redirecting to your workspace...
              </p>

              {/* Redirect progress bar */}
              <div className="w-full h-1 bg-border/40 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-success rounded-full"
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 1.5, ease: "easeInOut" }}
                />
              </div>
            </motion.div>
          )}

          {status === "error" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="space-y-4"
            >
              <div className="w-16 h-16 mx-auto rounded-2xl bg-danger/10 border border-danger/30 flex items-center justify-center">
                <XCircle size={32} className="text-danger" />
              </div>
              <h2 className="text-xl font-bold text-foreground">
                Authentication Failed
              </h2>
              <p className="text-sm text-foreground-muted">
                {errorMessage}
              </p>
              <div className="flex gap-3 justify-center pt-2">
                <button
                  onClick={() => router.push("/login")}
                  className="px-5 py-2.5 border border-border rounded-xl text-sm font-semibold hover:bg-card-hover transition cursor-pointer"
                >
                  Back to Login
                </button>
                <button
                  onClick={() => {
                    window.location.href = "/api/auth/github";
                  }}
                  className="px-5 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-semibold transition glow-blue cursor-pointer"
                >
                  Try Again
                </button>
              </div>
            </motion.div>
          )}
        </div>

        {/* Security note */}
        <p className="text-xs text-foreground-muted/50 max-w-xs mx-auto">
          Your GitHub credentials are encrypted and stored securely. ZeroOps never exposes your access token.
        </p>
      </motion.div>
    </main>
  );
}
