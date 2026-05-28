"use client";

import { Suspense, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { Circle, CheckCircle, XCircle, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

export default function GitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-background flex items-center justify-center p-4">
          <div className="text-center space-y-4">
            <Loader2 size={32} className="animate-spin text-primary mx-auto" />
            <p className="text-sm text-foreground-muted">Initializing callback handler...</p>
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
  const { refreshUser } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [step, setStep] = useState(1);

  useEffect(() => {
    const token = searchParams.get("token");
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
        server_error: "An internal database error occurred. Please try again.",
      };
      setErrorMessage(messages[error] || `GitHub authentication failed: ${error}`);
      return;
    }

    const processSession = async (sessionToken: string | null) => {
      try {
        if (sessionToken) {
          // 1. Store JWT securely
          localStorage.setItem("session_token", sessionToken);
          
          // Write client-side session cookie to propagate automatically in requests
          const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
          document.cookie = `session_token=${sessionToken}; path=/; max-age=2592000; SameSite=Lax${isLocal ? "" : "; Secure"}`;
        }

        // 2. Connecting GitHub Account - Fetch user profile
        await refreshUser();
        setStep(2); // Move to loading repositories

        // 3. Load repositories automatically
        try {
          await api.getGitHubRepos({ page: 1, per_page: 10 });
        } catch (err) {
          console.error("Repository pre-load failed or fetch error:", err);
          // Proceed anyway to repository page if authentication is valid
        }

        setStep(3); // Successfully loaded
        setStatus("success");
        
        setTimeout(() => {
          router.push("/dashboard/repositories");
        }, 1200);

      } catch (e: any) {
        setStatus("error");
        setErrorMessage(e.message || "An error occurred while setting up your session.");
      }
    };

    if (token) {
      processSession(token);
    } else if (success === "true") {
      // Fallback: cookie was set directly by backend RedirectResponse redirect cookies
      processSession(null);
    } else {
      setStatus("error");
      setErrorMessage("Invalid callback parameters received from server.");
    }
  }, [searchParams, router, refreshUser]);

  return (
    <main className="min-h-screen bg-background flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-sm text-center space-y-8"
      >
        {/* Brand Logo */}
        <div className="flex items-center justify-center gap-2">
          <Circle className="fill-primary text-primary w-6 h-6" />
          <span className="text-lg font-bold tracking-tight text-foreground">
            ZeroOps AI
          </span>
        </div>

        {/* Status Card */}
        <div className="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          {status === "loading" && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-6"
            >
              <div className="w-12 h-12 mx-auto rounded-lg bg-primary/10 flex items-center justify-center">
                <Loader2 size={24} className="text-primary animate-spin" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-foreground">
                  {step === 1 ? "Connecting GitHub Account" : "Loading GitHub Repositories"}
                </h2>
                <p className="text-xs text-foreground-muted mt-1">
                  {step === 1 
                    ? "Securing your authentication session..." 
                    : "Fetching and syncing your repository catalog..."}
                </p>
              </div>

              {/* Progress Steps (macOS style checklist) */}
              <div className="text-left space-y-3 pt-2 border-t border-border/60">
                <div className="flex items-center gap-3 text-xs">
                  {step > 1 ? (
                    <CheckCircle size={14} className="text-success" />
                  ) : (
                    <Loader2 size={14} className="text-primary animate-spin" />
                  )}
                  <span className={`font-semibold ${step >= 1 ? "text-foreground" : "text-foreground-muted"}`}>
                    Connecting GitHub Account
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {step > 2 ? (
                    <CheckCircle size={14} className="text-success" />
                  ) : step === 2 ? (
                    <Loader2 size={14} className="text-primary animate-spin" />
                  ) : (
                    <Circle size={14} className="text-border" />
                  )}
                  <span className={`font-semibold ${step >= 2 ? "text-foreground" : "text-foreground-muted"}`}>
                    Loading repositories
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {step > 3 ? (
                    <CheckCircle size={14} className="text-success" />
                  ) : (
                    <Circle size={14} className="text-border" />
                  )}
                  <span className={`font-semibold ${step >= 3 ? "text-foreground" : "text-foreground-muted"}`}>
                    Entering workspace
                  </span>
                </div>
              </div>
            </motion.div>
          )}

          {status === "success" && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-4"
            >
              <div className="w-12 h-12 mx-auto rounded-lg bg-success/10 border border-success/30 flex items-center justify-center">
                <CheckCircle size={24} className="text-success" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-foreground">
                  Session Established
                </h2>
                <p className="text-xs text-foreground-muted mt-1">
                  GitHub connected successfully. Redirecting you...
                </p>
              </div>

              {/* Progress Indicator */}
              <div className="w-full h-1 bg-background-secondary border border-border/40 rounded-full overflow-hidden mt-4">
                <motion.div
                  className="h-full bg-success rounded-full"
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 1.2, ease: "easeInOut" }}
                />
              </div>
            </motion.div>
          )}

          {status === "error" && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-4"
            >
              <div className="w-12 h-12 mx-auto rounded-lg bg-danger/10 border border-danger/30 flex items-center justify-center">
                <XCircle size={24} className="text-danger" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-foreground">
                  Authentication Failed
                </h2>
                <p className="text-xs text-foreground-muted mt-1.5 leading-relaxed font-semibold">
                  {errorMessage}
                </p>
              </div>
              <div className="flex gap-3 justify-center pt-3">
                <button
                  onClick={() => router.push("/login")}
                  className="px-4 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-background-secondary transition cursor-pointer"
                >
                  Back to Login
                </button>
                <button
                  onClick={() => {
                    window.location.href = `${process.env.NEXT_PUBLIC_API_BASE_URL || ""}/api/auth/github`;
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition cursor-pointer shadow-sm flex items-center gap-1.5"
                >
                  <RefreshCw size={12} />
                  Try Again
                </button>
              </div>
            </motion.div>
          )}
        </div>

        {/* Security Info Footer */}
        <p className="text-[10px] text-foreground-muted/60 max-w-xs mx-auto font-semibold">
          Your credentials are encrypted and stored securely. ZeroOps never exposes raw GitHub tokens.
        </p>
      </motion.div>
    </main>
  );
}
