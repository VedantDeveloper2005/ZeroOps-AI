"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { Repository } from "./mock-data";
<<<<<<< HEAD
import { fallbackRepositories } from "./demo-runtime";
=======
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "critical";
  timestamp: string;
  read: boolean;
}

export interface Toast {
  id: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
}

interface NotificationContextProps {
  notifications: Notification[];
  unreadCount: number;
  addNotification: (notification: Omit<Notification, "id" | "timestamp" | "read">) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
  toasts: Toast[];
  addToast: (message: string, type?: Toast["type"]) => void;
  removeToast: (id: string) => void;
  repositories: Repository[];
  addRepository: (repo: Omit<Repository, "id" | "deploymentStatus" | "stars" | "totalDeployments" | "lastCommit" | "lastCommitMessage" | "lastCommitAuthor">) => void;
}

const NotificationContext = createContext<NotificationContextProps | undefined>(undefined);

// Pure helper function declared outside the component to satisfy the linter
function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([
    {
      id: "init-notif-1",
      title: "API Gateway High Latency",
      message: "P99 latency exceeded 500ms threshold on api-gateway.",
      type: "critical",
      timestamp: "25 min ago",
      read: false,
    },
    {
      id: "init-notif-2",
      title: "Security Threat Mitigated",
      message: "Firewall rule applied: blocked 45.33.21.x (DDoS attempt).",
      type: "critical",
      timestamp: "15 min ago",
      read: false,
    },
    {
      id: "init-notif-3",
      title: "Autoscale Event",
      message: "AI optimized scaling for api-gateway: scaled 3 → 5 pods.",
      type: "info",
      timestamp: "2 min ago",
      read: false,
    },
    {
      id: "init-notif-4",
      title: "Self-Healing Resolved",
      message: "payments-service pod recovered from OOMKill. Replicas healthy.",
      type: "success",
      timestamp: "2 hours ago",
      read: true,
    },
  ]);

  const [toasts, setToasts] = useState<Toast[]>([]);
<<<<<<< HEAD
  const [repositories, setRepositories] = useState<Repository[]>(fallbackRepositories());
=======
  const [repositories, setRepositories] = useState<Repository[]>([]);
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2

  // Fetch repositories from FastAPI backend on mount
  useEffect(() => {
    fetch("/api/github/repos")
      .then((res) => {
        if (!res.ok) throw new Error("API response error");
        return res.json();
      })
      .then((data) => setRepositories(data))
<<<<<<< HEAD
      .catch((err) => {
        console.error("Failed to load connected repositories; using demo repositories:", err);
        setRepositories(fallbackRepositories());
      });
=======
      .catch((err) => console.error("Failed to load connected repositories:", err));
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
  }, []);

  // Directly derive the unread count instead of using an effect
  const unreadCount = notifications.filter((n) => !n.read).length;

  const addNotification = (notif: Omit<Notification, "id" | "timestamp" | "read">) => {
    const newNotif: Notification = {
      ...notif,
      id: generateId("notif"),
      timestamp: "Just now",
      read: false,
    };
    setNotifications((prev) => [newNotif, ...prev]);
  };

  const markAsRead = (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  };

  const markAllAsRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const clearAll = () => {
    setNotifications([]);
  };

  const addToast = (message: string, type: Toast["type"] = "info") => {
    const id = generateId("toast");
    const newToast: Toast = { id, message, type };
    setToasts((prev) => [...prev, newToast]);

    // Auto-remove toast after 3.5 seconds
    setTimeout(() => {
      removeToast(id);
    }, 3500);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const addRepository = async (repo: Omit<Repository, "id" | "deploymentStatus" | "stars" | "totalDeployments" | "lastCommit" | "lastCommitMessage" | "lastCommitAuthor">) => {
    try {
      const res = await fetch("/api/github/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(repo),
      });
      if (!res.ok) throw new Error("Failed to post repo");
      const newRepo = await res.json();
      setRepositories((prev) => [newRepo, ...prev]);
    } catch (err) {
      console.error("Failed to connect repository via backend:", err);
      // Fallback client state
      const fallbackRepo: Repository = {
        ...repo,
        id: generateId("repo"),
<<<<<<< HEAD
        deploymentStatus: "stopped",
        stars: 0,
        totalDeployments: 0,
=======
        deploymentStatus: "running",
        stars: 0,
        totalDeployments: 1,
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
        lastCommit: "Just now",
        lastCommitMessage: "Initial commit managed by ZeroOps",
        lastCommitAuthor: "Vedant S.",
      };
      setRepositories((prev) => [fallbackRepo, ...prev]);
    }
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
        repositories,
        addRepository,
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
<<<<<<< HEAD
=======

>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
