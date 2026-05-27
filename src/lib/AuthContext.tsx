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
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  signup: (firstName: string, lastName: string, email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

// Global fetch interceptor to automatically route client-side relative API requests to backend
if (typeof window !== "undefined") {
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    if (API_BASE_URL && typeof input === "string" && input.startsWith("/api/")) {
      input = `${API_BASE_URL}${input}`;
    }
    return originalFetch(input, init);
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
        headers: {
          "Accept": "application/json",
        },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
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

    if (!user && isDashboardRoute) {
      addToast("Please sign in to access the dashboard", "warning");
      router.push("/login");
    } else if (user && isAuthRoute) {
      // Route based on onboarding state: new users go to onboarding wizard
      const deployed = typeof window !== "undefined" && localStorage.getItem("zo_has_deployed") === "true";
      if (deployed) {
        router.push("/dashboard");
      } else {
        router.push("/dashboard/repositories");
      }
    }
  }, [user, loading, pathname, router]);

  // Login handler
  const login = async (email: string, password: string): Promise<User> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(errorData.detail || "Invalid email or password");
    }

    const data = await res.json();
    setUser(data);
    addToast("Successfully logged in", "success");
    return data;
  };

  // Signup handler
  const signup = async (
    firstName: string,
    lastName: string,
    email: string,
    password: string
  ): Promise<User> => {
    const res = await fetch(`${API_BASE_URL}/api/auth/signup`, {
      method: "POST",
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
    setUser(data);
    addToast("Successfully registered account", "success");
    return data;
  };

  // Logout handler
  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/auth/logout`, { method: "POST" });
    } catch (err) {
      console.error("Error during logout endpoint call:", err);
    }
    setUser(null);
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
        signup,
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
