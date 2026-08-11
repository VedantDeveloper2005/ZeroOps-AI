"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { usePathname } from "next/navigation";
import { api, type Notification, type Project, type DashboardStats } from "./api";

export type { Notification };

export interface Toast {
  id: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
}

export type WorkspaceDataState = "idle" | "loading" | "ready" | "error";

interface NotificationContextProps {
  notifications: Notification[];
  notificationsState: WorkspaceDataState;
  unreadCount: number;
  addNotification: (notification: Omit<Notification, "id" | "created_at" | "read">) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
  toasts: Toast[];
  addToast: (message: string, type?: Toast["type"]) => void;
  removeToast: (id: string) => void;
  projects: Project[];
  projectsState: WorkspaceDataState;
  refreshProjects: () => Promise<void>;
  hasDeployed: boolean;
  dashboardStats: DashboardStats | null;
  dashboardStatsState: WorkspaceDataState;
  refreshStats: () => Promise<void>;
  refreshNotifications: () => Promise<void>;
  isLoading: boolean;
  resetOnboarding: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextProps | undefined>(undefined);

function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isDashboardRoute = pathname.startsWith("/dashboard");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [notificationsState, setNotificationsState] =
    useState<WorkspaceDataState>("idle");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsState, setProjectsState] =
    useState<WorkspaceDataState>("idle");
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  const [dashboardStatsState, setDashboardStatsState] =
    useState<WorkspaceDataState>("idle");
  const [isLoading, setIsLoading] = useState(true);

  const hasDeployed = projects.some(
    (project) =>
      project.deployment_count > 0 ||
      project.last_deployed_at !== null ||
      project.latest_deployment_status !== null,
  );

  // ── Fetch from API on mount ──
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      // Skip API calls when no session exists — prevents 3× 401 cascades
      // that hit the rate limiter and pollute the browser console.
      setIsLoading(true);
      setNotificationsState("loading");
      setProjectsState("loading");
      setDashboardStatsState("loading");
      try {
        const [notifData, projectData, statsData] = await Promise.allSettled([
          api.getNotifications(),
          api.getProjects(),
          api.getDashboardStats(),
        ]);

        if (cancelled) return;

        if (notifData.status === "fulfilled") {
          setNotifications(notifData.value);
          setNotificationsState("ready");
        } else {
          setNotificationsState("error");
        }
        if (projectData.status === "fulfilled") {
          setProjects(projectData.value);
          setProjectsState("ready");
        } else {
          setProjectsState("error");
        }
        if (statsData.status === "fulfilled") {
          setDashboardStats(statsData.value);
          setDashboardStatsState("ready");
        } else {
          setDashboardStatsState("error");
        }
      } catch {
        if (!cancelled) {
          setNotificationsState("error");
          setProjectsState("error");
          setDashboardStatsState("error");
        }
        // User may not be authenticated yet — that's OK
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    if (isDashboardRoute) {
      void loadData();
    } else {
      setIsLoading(false);
    }
    window.addEventListener("zeroops:authenticated", loadData);
    return () => {
      cancelled = true;
      window.removeEventListener("zeroops:authenticated", loadData);
    };
  }, [isDashboardRoute]);

  // Directly derive unread count
  const unreadCount = notifications.filter((n) => !n.read).length;

  // ── Refresh helpers ──
  const refreshProjects = useCallback(async () => {
    setProjectsState("loading");
    try {
      const data = await api.getProjects();
      setProjects(data);
      setProjectsState("ready");
    } catch {
      setProjectsState("error");
    }
  }, []);

  const refreshStats = useCallback(async () => {
    setDashboardStatsState("loading");
    try {
      const data = await api.getDashboardStats();
      setDashboardStats(data);
      setDashboardStatsState("ready");
    } catch {
      setDashboardStatsState("error");
    }
  }, []);

  const refreshNotifications = useCallback(async () => {
    setNotificationsState("loading");
    try {
      const data = await api.getNotifications();
      setNotifications(data);
      setNotificationsState("ready");
    } catch {
      setNotificationsState("error");
    }
  }, []);

  // ── Notification actions ──
  const addNotification = useCallback((notif: Omit<Notification, "id" | "created_at" | "read">) => {
    const newNotif: Notification = {
      ...notif,
      id: generateId("notif"),
      created_at: new Date().toISOString(),
      read: false,
    };
    setNotifications((prev) => [newNotif, ...prev]);
  }, []);

  const markAsRead = useCallback(async (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
    try { await api.markNotificationRead(id); } catch { /* best-effort */ }
  }, []);

  const markAllAsRead = useCallback(async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    try { await api.markAllNotificationsRead(); } catch { /* best-effort */ }
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  // ── Toast actions ──
  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message: string, type: Toast["type"] = "info") => {
    const id = generateId("toast");
    const newToast: Toast = { id, message, type };
    setToasts((prev) => [...prev, newToast]);
    setTimeout(() => {
      removeToast(id);
    }, 3500);
  }, [removeToast]);

  const resetOnboarding = async () => {
    await api.resetOnboarding();
    await Promise.all([refreshProjects(), refreshStats(), refreshNotifications()]);
  };

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        notificationsState,
        unreadCount,
        addNotification,
        markAsRead,
        markAllAsRead,
        clearAll,
        toasts,
        addToast,
        removeToast,
        projects,
        projectsState,
        refreshProjects,
        hasDeployed,
        dashboardStats,
        dashboardStatsState,
        refreshStats,
        refreshNotifications,
        isLoading,
        resetOnboarding,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error("useNotifications must be used within a NotificationProvider");
  }
  return context;
}
