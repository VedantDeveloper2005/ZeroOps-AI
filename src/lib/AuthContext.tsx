"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useNotifications } from "@/lib/NotificationContext";

export interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  firstName?: string;
  lastName?: string;
  provider: string;
  provider_id?: string;
  avatar_url?: string;
  plan: string;
  created_at?: string;
  github_connected?: boolean;
  github_username?: string;
  mfa_enabled?: boolean;
  mfa_method?: string;
  email_verified?: boolean;
}

export interface MfaChallenge {
  mfa_required: true;
  mfa_method?: string;
}

export interface EmailVerificationPending {
  email_verification_required: true;
  email: string;
}

export type LoginResult = User | MfaChallenge;
export type SignupResult = User | EmailVerificationPending;

export function isMfaChallenge(result: LoginResult): result is MfaChallenge {
  return "mfa_required" in result && result.mfa_required === true;
}

export function isEmailVerificationPending(result: SignupResult): result is EmailVerificationPending {
  return "email_verification_required" in result && result.email_verification_required === true;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (code: string) => Promise<User>;
  signup: (firstName: string, lastName: string, email: string, password: string) => Promise<SignupResult>;
  verifyEmail: (token: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
  resendMfaOtp: () => Promise<void>;
  loginWithGitHub: () => void;
  loginWithGoogle: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
const GITHUB_OAUTH_PENDING_KEY = "zeroops.githubOAuth.pending";
const GOOGLE_OAUTH_PENDING_KEY = "zeroops.googleOAuth.pending";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const nameEQ = name + "=";
  const ca = document.cookie.split(";");
  for (let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) === " ") c = c.substring(1, c.length);
    if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
  }
  return null;
}

function notifyAuthenticationSucceeded() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("zeroops:authenticated"));
  }
}

// Global fetch interceptor to automatically route client-side relative API requests to backend
if (typeof window !== "undefined") {
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    const initCopy = init ? { ...init } : {};
    const headers = new Headers(initCopy.headers || {});
    
    let targetInput = input;
    if (API_BASE_URL && typeof targetInput === "string" && targetInput.startsWith("/api/")) {
      targetInput = `${API_BASE_URL}${targetInput}`;
    }
    
    // Automatically include credentials for same-origin and configured cross-origin API calls
    if (typeof targetInput === "string" && (targetInput.startsWith("/api/") || (API_BASE_URL && targetInput.startsWith(API_BASE_URL)))) {
      initCopy.credentials = "include";
    }
    
    // Automatically inject CSRF token header for state-changing calls
    const method = initCopy.method ? initCopy.method.toUpperCase() : "GET";
    if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
      const csrfToken = getCookie("csrf_token") || sessionStorage.getItem("csrf_token");
      if (csrfToken) {
        headers.set("X-CSRF-Token", csrfToken);
      }
    }
    
    initCopy.headers = headers;
    const response = await originalFetch(targetInput, initCopy);
    
    // Capture CSRF token from response headers if present (e.g. in cross-domain configurations)
    const responseCsrf = response.headers.get("X-CSRF-Token");
    if (responseCsrf) {
      sessionStorage.setItem("csrf_token", responseCsrf);
    }
    
    return response;
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();
  const { addToast } = useNotifications();

  // Fetch current user details on load
  const fetchCurrentUser = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
        credentials: "include",
        headers: {
          "Accept": "application/json",
        },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
        if (data?.github_connected === true) {
          sessionStorage.removeItem(GITHUB_OAUTH_PENDING_KEY);
        }
      } else {
        setUser(null);
      }
    } catch (err) {
      console.error("Error checking session:", err);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCurrentUser();
  }, []);

  // Protected route redirects
  useEffect(() => {
    if (loading) return;

    const isAuthRoute = pathname === "/login" || pathname === "/signup";
    const isDashboardRoute = pathname.startsWith("/dashboard");
    const isGitHubCallback = pathname.startsWith("/auth/github/callback");

    // Don't redirect on the GitHub callback page — it handles its own routing
    if (isGitHubCallback) return;

    if (!user && isDashboardRoute) {
      addToast("Please sign in to access the dashboard", "warning");
      router.push("/login");
    } else if (user && isAuthRoute) {
      // Check deployment state from backend API instead of localStorage
      fetch(`${API_BASE_URL}/api/dashboard/stats`, { credentials: "include" })
        .then((res) => res.ok ? res.json() : { has_deployed: false })
        .then((stats) => {
          if (stats.has_deployed) {
            router.push("/dashboard");
          } else {
            router.push("/dashboard/repositories");
          }
        })
        .catch(() => router.push("/dashboard/repositories"));
    }
  }, [user, loading, pathname, router, addToast]);

  // Login handler
  const login = async (email: string, password: string): Promise<LoginResult> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(errorData.detail || "Invalid email or password");
    }

    const data = await res.json() as LoginResult;
    if (isMfaChallenge(data)) {
      setUser(null);
      return data;
    }
    setUser(data);
    notifyAuthenticationSucceeded();
    addToast("Successfully logged in", "success");
    return data;
  };

  const verifyMfa = async (code: string): Promise<User> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/mfa/verify`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Verification failed" }));
      throw new Error(errorData.detail || "Unable to verify your authentication code");
    }

    const data = await res.json() as User;
    setUser(data);
    notifyAuthenticationSucceeded();
    addToast("Identity verified", "success");
    return data;
  };

  // Signup handler
  const signup = async (
    firstName: string,
    lastName: string,
    email: string,
    password: string
  ): Promise<SignupResult> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/signup`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        firstName,
        lastName,
        email,
        password,
      }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Signup failed" }));
      throw new Error(errorData.detail || "Failed to create account");
    }

    const data = await res.json();
    if (isEmailVerificationPending(data)) {
      addToast("Account created. Please check your email for a verification link.", "info");
      return data;
    }

    setUser(data);
    notifyAuthenticationSucceeded();
    addToast("Successfully registered account", "success");
    return data;
  };

  const verifyEmail = async (token: string): Promise<void> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/verify-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Verification failed" }));
      throw new Error(errorData.detail || "Verification failed");
    }
    
    addToast("Email verified successfully! You can now log in.", "success");
  };

  const resendVerification = async (email: string): Promise<void> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/resend-verification`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Failed to resend verification email" }));
      throw new Error(errorData.detail || "Failed to resend verification email");
    }

    addToast("Verification email has been resent.", "success");
  };

  const resendMfaOtp = async (): Promise<void> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/mfa/resend-otp`, {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Failed to resend verification code" }));
      throw new Error(errorData.detail || "Failed to resend verification code");
    }

    addToast("Verification code resent to your email.", "success");
  };

  // GitHub OAuth login — redirects to backend which redirects to GitHub
  const loginWithGitHub = () => {
    sessionStorage.setItem(GITHUB_OAUTH_PENDING_KEY, "true");
    const githubAuthUrl = `${API_BASE_URL}/api/auth/github`;
    window.location.href = githubAuthUrl;
  };

  const loginWithGoogle = () => {
    sessionStorage.setItem(GOOGLE_OAUTH_PENDING_KEY, "true");
    const googleAuthUrl = `${API_BASE_URL}/api/auth/google`;
    window.location.href = googleAuthUrl;
  };

  // Logout handler
  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch (err) {
      console.error("Error during logout endpoint call:", err);
    }
    setUser(null);
    sessionStorage.removeItem(GITHUB_OAUTH_PENDING_KEY);
    sessionStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY);
    addToast("Logged out successfully", "info");
    router.push("/login");
  };

  const refreshUser = async () => {
    await fetchCurrentUser();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        verifyMfa,
        signup,
        verifyEmail,
        resendVerification,
        resendMfaOtp,
        loginWithGitHub,
        loginWithGoogle,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
