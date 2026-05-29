"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api, type Notification, type Project, type DashboardStats } from "./api";

export type { Notification };

export interface Toast {
  id: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
}

interface NotificationContextProps {
  notifications: Notification[];
  unreadCount: number;
  addNotification: (notification: Omit<Notification, "id" | "created_at" | "read">) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
  toasts: Toast[];
  addToast: (message: string, type?: Toast["type"]) => void;
  removeToast: (id: string) => void;
  projects: Project[];
  refreshProjects: () => Promise<void>;
  hasDeployed: boolean;
  dashboardStats: DashboardStats | null;
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
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Derive hasDeployed from actual DB state (true if user has at least one connected project)
  const hasDeployed = projects.length > 0;

  // ── Fetch from API on mount ──
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setIsLoading(true);
      try {
        const [notifData, projectData, statsData] = await Promise.allSettled([
          api.getNotifications(),
          api.getProjects(),
          api.getDashboardStats(),
        ]);

        if (cancelled) return;

        if (notifData.status === "fulfilled") {
          setNotifications(notifData.value);
        }
        if (projectData.status === "fulfilled") {
          setProjects(projectData.value);
        }
        if (statsData.status === "fulfilled") {
          setDashboardStats(statsData.value);
        }
      } catch {
        // User may not be authenticated yet — that's OK
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadData();
    return () => { cancelled = true; };
  }, []);

  // Directly derive unread count
  const unreadCount = notifications.filter((n) => !n.read).length;

  // ── Refresh helpers ──
  const refreshProjects = useCallback(async () => {
    try {
      const data = await api.getProjects();
      setProjects(data);
    } catch { /* ignore if not authenticated */ }
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      const data = await api.getDashboardStats();
      setDashboardStats(data);
    } catch { /* ignore */ }
  }, []);

  const refreshNotifications = useCallback(async () => {
    try {
      const data = await api.getNotifications();
      setNotifications(data);
    } catch { /* ignore */ }
  }, []);

  // ── Notification actions ──
  const addNotification = (notif: Omit<Notification, "id" | "created_at" | "read">) => {
    const newNotif: Notification = {
      ...notif,
      id: generateId("notif"),
      created_at: new Date().toISOString(),
      read: false,
    };
    setNotifications((prev) => [newNotif, ...prev]);
  };

  const markAsRead = async (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
    try { await api.markNotificationRead(id); } catch { /* best-effort */ }
  };

  const markAllAsRead = async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    try { await api.markAllNotificationsRead(); } catch { /* best-effort */ }
  };

  const clearAll = () => {
    setNotifications([]);
  };

  // ── Toast actions ──
  const addToast = (message: string, type: Toast["type"] = "info") => {
    const id = generateId("toast");
    const newToast: Toast = { id, message, type };
    setToasts((prev) => [...prev, newToast]);
    setTimeout(() => {
      removeToast(id);
    }, 3500);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const resetOnboarding = async () => {
    await api.resetOnboarding();
    await Promise.all([refreshProjects(), refreshStats(), refreshNotifications()]);
  };

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        addNotification,
        markAsRead,
        markAllAsRead,
        clearAll,
        toasts,
        addToast,
        removeToast,
        projects,
        refreshProjects,
        hasDeployed,
        dashboardStats,
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
