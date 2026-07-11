"use client";

import { usePathname } from "next/navigation";
import { Bell, Search, Info, CheckCircle2, AlertTriangle, AlertCircle, Trash2, Check } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useAuth } from "@/lib/AuthContext";


const typeIcons = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  critical: AlertCircle,
};

const typeBgColors = {
  info: "bg-primary/10",
  success: "bg-success/10",
  warning: "bg-warning/10",
  critical: "bg-danger/10",
};

const typeTextColors = {
  info: "text-primary",
  success: "text-success",
  warning: "text-warning",
  critical: "text-danger",
};

export function TopBar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const segments = pathname.split("/").filter(Boolean);
  const currentPage = segments[segments.length - 1] || "dashboard";
  const pageName = currentPage.split("-").map(w => w === "ai" ? "AI" : w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

  const firstName = user?.firstName || user?.first_name || "";
  const lastName = user?.lastName || user?.last_name || "";

  const initials = firstName && lastName
    ? `${firstName[0].toUpperCase()}${lastName[0].toUpperCase()}`
    : firstName
    ? firstName[0].toUpperCase()
    : user?.email
    ? user.email[0].toUpperCase()
    : "U";

  const { notifications, unreadCount, markAsRead, markAllAsRead, clearAll } = useNotifications();
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  // Click outside notification panel handler
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotifOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="h-16 border-b border-border flex items-center justify-between px-4 sm:px-6 bg-background/75 backdrop-blur-xl flex-shrink-0 relative">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-foreground-muted">Dashboard</span>
        {segments.length > 1 && (
          <>
            <span className="text-foreground-muted">/</span>
            <span className="text-foreground font-medium">{pageName}</span>
          </>
        )}
      </div>

      {/* Search */}
      <div className="hidden md:flex items-center glass-subtle rounded-xl px-4 py-2 gap-2 w-72">
        <Search size={16} className="text-foreground-muted" />
        <input aria-label="Search deployments and repositories" type="text" placeholder="Search deployments, repos..." className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full" />
        <kbd className="text-[10px] text-foreground-muted bg-card px-1.5 py-0.5 rounded border border-border">⌘K</kbd>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        {/* Notifications Bell Dropdown */}
        <div className="relative" ref={notifRef}>
          <button 
            onClick={() => setNotifOpen(!notifOpen)}
            aria-label={notifOpen ? "Close notifications" : "Open notifications"}
            aria-expanded={notifOpen}
            className={`p-2 rounded-lg transition-colors relative ${notifOpen ? "bg-card text-foreground" : "hover:bg-card text-foreground-muted hover:text-foreground"}`}
          >
            <Bell size={20} />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-danger text-[9px] text-white flex items-center justify-center font-bold">
                {unreadCount}
              </span>
            )}
          </button>

          {/* Notifications Dropdown Panel */}
          {notifOpen && (
            <div className="absolute right-0 mt-2 w-80 glass border border-border rounded-xl shadow-xl z-50 flex flex-col max-h-[400px]">
              {/* Header */}
              <div className="p-3 border-b border-border flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">Notifications</span>
                {unreadCount > 0 && (
                  <button 
                    onClick={markAllAsRead} 
                    className="text-[10px] text-primary hover:text-primary-hover font-semibold flex items-center gap-0.5 transition-colors"
                  >
                    <Check size={10} /> Mark all read
                  </button>
                )}
              </div>

              {/* List */}
              <div className="flex-1 overflow-y-auto no-scrollbar py-1 max-h-[280px]">
                {notifications.length === 0 ? (
                  <div className="p-6 text-center text-xs text-foreground-muted">
                    No notifications
                  </div>
                ) : (
                  notifications.map((n) => {
                    const Icon = typeIcons[n.type] || Info;
                    return (
                      <div
                        key={n.id}
                        onClick={() => markAsRead(n.id)}
                        className={`p-3 border-b border-border/50 last:border-b-0 hover:bg-card-hover/30 transition-colors cursor-pointer flex gap-2.5 items-start ${!n.read ? "bg-primary/5" : ""}`}
                      >
                        <div className={`mt-0.5 p-1 rounded-md ${typeBgColors[n.type] || "bg-card"}`}>
                          <Icon size={12} className={typeTextColors[n.type] || "text-foreground-muted"} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <p className={`text-xs font-semibold truncate ${!n.read ? "text-foreground" : "text-foreground-muted"}`}>
                              {n.title}
                            </p>
                            {!n.read && (
                              <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
                            )}
                          </div>
                          <p className="text-[10px] text-foreground-muted leading-normal mt-0.5">
                            {n.message}
                          </p>
                          <span className="text-[9px] text-foreground-muted/60 mt-1 block">
                            {n.created_at ? new Date(n.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ""}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Footer */}
              {notifications.length > 0 && (
                <div className="p-2 border-t border-border flex justify-between gap-2">
                  <button 
                    onClick={clearAll} 
                    className="text-[10px] text-danger hover:text-danger-hover font-semibold flex items-center justify-center gap-1 py-1 w-full hover:bg-card rounded transition-colors"
                  >
                    <Trash2 size={10} /> Clear all
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div aria-label="Current user" className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center text-xs font-bold text-foreground cursor-pointer">
          {initials}
        </div>
      </div>
    </div>
  );
}
