"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronDown,
  FolderKanban,
  Info,
  LogOut,
  Menu,
  Search,
  Settings,
  UserRound,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useAuth } from "@/lib/AuthContext";
import { cn } from "@/lib/utils";

type TopBarProps = {
  onOpenNavigation: () => void;
};

const routeLabels: Record<string, string> = {
  dashboard: "Overview",
  projects: "Projects",
  repositories: "New project",
  deployments: "Deployments",
  monitoring: "Monitoring",
  architect: "AI Architect",
  activity: "Activity",
  settings: "Settings",
  profile: "Profile",
  billing: "Plan & billing",
  infrastructure: "Architecture",
  security: "Security",
  logs: "Logs",
  incidents: "Incidents",
  autoscaling: "Capacity",
  "ai-analysis": "Analysis",
  "cost-optimization": "Cost",
  apps: "Project",
};

const searchableRoutes = [
  { label: "Overview", description: "Projects and actions requiring attention", href: "/dashboard" },
  { label: "Projects", description: "All connected repositories and uploads", href: "/dashboard/projects" },
  { label: "Deployments", description: "Progress, logs, and deployment history", href: "/dashboard/deployments" },
  { label: "Monitoring", description: "Health and runtime telemetry", href: "/dashboard/monitoring" },
  { label: "AI Architect", description: "Explain or propose architecture changes", href: "/dashboard/architect" },
  { label: "Activity", description: "Audit history for workspace actions", href: "/dashboard/activity" },
  { label: "Settings", description: "Connections, secrets, access, and preferences", href: "/dashboard/settings" },
] as const;

const notificationIcons = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  critical: AlertCircle,
};

type WorkspaceSearchResult = {
  label: string;
  description: string;
  href: string;
};

function SearchResultList({
  results,
  onSelect,
}: {
  results: readonly WorkspaceSearchResult[];
  onSelect: (href: string) => void;
}) {
  if (results.length === 0) {
    return (
      <p className="px-3 py-6 text-center text-sm text-foreground-muted">
        No matching pages or projects.
      </p>
    );
  }

  return (
    <ul aria-label="Search results">
      {results.map((result) => (
        <li key={result.href}>
          <button
            type="button"
            onClick={() => onSelect(result.href)}
            className="flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-left transition-colors hover:bg-surface-raised"
          >
            <FolderKanban
              size={16}
              className="shrink-0 text-foreground-subtle"
              aria-hidden="true"
            />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-foreground">
                {result.label}
              </span>
              <span className="block truncate text-[11px] text-foreground-muted">
                {result.description}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function TopBar({ onOpenNavigation }: TopBarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    projects,
  } = useNotifications();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const notificationsRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchButtonRef = useRef<HTMLButtonElement>(null);
  const desktopSearchInputRef = useRef<HTMLInputElement>(null);
  const mobileSearchInputRef = useRef<HTMLInputElement>(null);

  const segments = pathname.split("/").filter(Boolean);
  const lastSegment = segments.at(-1) || "dashboard";
  const pageLabel =
    routeLabels[lastSegment] ||
    (segments.includes("apps") ? "Project" : lastSegment.replaceAll("-", " "));

  const firstName = user?.firstName || user?.first_name || "";
  const lastName = user?.lastName || user?.last_name || "";
  const displayName = [firstName, lastName].filter(Boolean).join(" ") || user?.email || "Account";
  const initials = `${firstName[0] || ""}${lastName[0] || ""}`.toUpperCase() || user?.email?.[0]?.toUpperCase() || "U";

  const searchResults = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const routes = searchableRoutes.filter((item) =>
      !normalized ||
      item.label.toLowerCase().includes(normalized) ||
      item.description.toLowerCase().includes(normalized),
    );
    const projectResults = projects
      .filter((project) =>
        !normalized ||
        project.name.toLowerCase().includes(normalized) ||
        project.full_name.toLowerCase().includes(normalized),
      )
      .map((project) => ({
        label: project.name,
        description: project.full_name,
        href: `/dashboard/apps/${project.id}`,
      }));
    return [...projectResults, ...routes].slice(0, 8);
  }, [projects, query]);

  const openSearch = useCallback(() => {
    setNotificationsOpen(false);
    setProfileOpen(false);
    setSearchOpen(true);
    window.setTimeout(() => {
      const input = window.matchMedia("(min-width: 1280px)").matches
        ? desktopSearchInputRef.current
        : mobileSearchInputRef.current;
      input?.focus();
    }, 0);
  }, []);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (notificationsRef.current && !notificationsRef.current.contains(target)) setNotificationsOpen(false);
      if (profileRef.current && !profileRef.current.contains(target)) setProfileOpen(false);
      if (searchRef.current && !searchRef.current.contains(target)) setSearchOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openSearch();
      }
      if (event.key === "Escape") {
        setNotificationsOpen(false);
        setProfileOpen(false);
        setSearchOpen(false);
        if (!window.matchMedia("(min-width: 1280px)").matches) {
          window.setTimeout(() => searchButtonRef.current?.focus(), 0);
        }
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openSearch]);

  const navigateFromSearch = (href: string) => {
    setSearchOpen(false);
    setQuery("");
    router.push(href);
  };

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/92 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-2 px-3 sm:gap-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onOpenNavigation}
          aria-label="Open navigation"
          className="grid min-h-11 min-w-11 place-items-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground lg:hidden"
        >
          <Menu size={20} />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm">
            <span className="hidden text-foreground-subtle sm:inline">Workspace</span>
            <span aria-hidden="true" className="hidden text-foreground-subtle sm:inline">/</span>
            <span className="truncate font-medium capitalize text-foreground">{pageLabel}</span>
          </div>
        </div>

        <div ref={searchRef} className="relative xl:w-full xl:max-w-sm">
          <button
            ref={searchButtonRef}
            type="button"
            onClick={openSearch}
            aria-label="Search pages and projects"
            aria-expanded={searchOpen}
            aria-controls="workspace-search-panel"
            className={cn(
              "grid min-h-11 min-w-11 place-items-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground xl:hidden",
              searchOpen && "bg-surface-raised text-foreground",
            )}
          >
            <Search size={19} aria-hidden="true" />
          </button>

          {searchOpen && (
            <section
              id="workspace-search-panel"
              aria-label="Search pages and projects"
              className="fixed inset-x-3 top-[68px] z-50 overflow-hidden rounded-xl border border-border bg-card p-2 shadow-xl xl:hidden"
            >
              <div className="relative">
                <Search
                  aria-hidden="true"
                  size={17}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-foreground-subtle"
                />
                <input
                  ref={mobileSearchInputRef}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  aria-label="Search query"
                  placeholder="Search pages and projects"
                  autoComplete="off"
                  className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle py-2 pl-10 pr-12 text-base text-foreground outline-none transition-colors placeholder:text-foreground-subtle focus:border-primary focus:bg-card focus:ring-2 focus:ring-primary/15 sm:text-sm"
                />
                <button
                  type="button"
                  aria-label="Close search"
                  onClick={() => {
                    setSearchOpen(false);
                    searchButtonRef.current?.focus();
                  }}
                  className="absolute right-0 top-1/2 grid min-h-11 min-w-11 -translate-y-1/2 place-items-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground"
                >
                  <X size={17} aria-hidden="true" />
                </button>
              </div>
              <div className="mt-2 max-h-[min(60vh,24rem)] overflow-y-auto p-0.5">
                <SearchResultList
                  results={searchResults}
                  onSelect={navigateFromSearch}
                />
              </div>
            </section>
          )}

          <div className="relative hidden xl:block">
            <Search
              aria-hidden="true"
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-foreground-subtle"
            />
            <input
              ref={desktopSearchInputRef}
              value={query}
              onFocus={openSearch}
              onChange={(event) => {
                setQuery(event.target.value);
                setSearchOpen(true);
              }}
              aria-label="Search pages and projects"
              placeholder="Search pages and projects"
              autoComplete="off"
              className="min-h-10 w-full rounded-lg border border-border bg-surface-subtle py-2 pl-9 pr-14 text-sm text-foreground outline-none transition-colors placeholder:text-foreground-subtle focus:border-primary focus:bg-card focus:ring-2 focus:ring-primary/15"
            />
            <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-border bg-card px-1.5 py-0.5 text-[10px] text-foreground-subtle">
              Ctrl K
            </kbd>
            {searchOpen && (
              <div className="absolute left-0 right-0 top-12 overflow-hidden rounded-xl border border-border bg-card p-1.5 shadow-xl">
                <SearchResultList
                  results={searchResults}
                  onSelect={navigateFromSearch}
                />
              </div>
            )}
          </div>
        </div>

        <div ref={notificationsRef} className="relative">
          <button
            type="button"
            onClick={() => {
              setNotificationsOpen((open) => !open);
              setProfileOpen(false);
              setSearchOpen(false);
            }}
            aria-label={notificationsOpen ? "Close notifications" : "Open notifications"}
            aria-expanded={notificationsOpen}
            className={cn(
              "relative grid min-h-11 min-w-11 place-items-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground",
              notificationsOpen && "bg-surface-raised text-foreground",
            )}
          >
            <Bell size={19} />
            {unreadCount > 0 && (
              <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[9px] font-bold text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {notificationsOpen && (
            <section
              aria-label="Notifications"
              className="fixed inset-x-3 top-[68px] z-50 overflow-hidden rounded-xl border border-border bg-card shadow-xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-[360px]"
            >
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">Notifications</h2>
                  <p className="text-[11px] text-foreground-muted">{unreadCount} unread</p>
                </div>
                <div className="flex items-center gap-1">
                  {unreadCount > 0 && (
                    <button
                      type="button"
                      onClick={() => void markAllAsRead()}
                      className="min-h-9 rounded-lg px-2.5 text-xs font-medium text-primary transition-colors hover:bg-primary-subtle"
                    >
                      Mark all read
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label="Close notifications"
                    onClick={() => setNotificationsOpen(false)}
                    className="grid min-h-9 min-w-9 place-items-center rounded-lg text-foreground-muted hover:bg-surface-raised"
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>
              <div className="max-h-[min(420px,65vh)] overflow-y-auto p-1.5">
                {notifications.length === 0 ? (
                  <div className="px-5 py-10 text-center">
                    <CheckCircle2 size={24} className="mx-auto text-success" />
                    <p className="mt-3 text-sm font-medium text-foreground">You’re up to date</p>
                    <p className="mt-1 text-xs text-foreground-muted">Deployment and incident updates will appear here.</p>
                  </div>
                ) : (
                  notifications.slice(0, 20).map((notification) => {
                    const Icon = notificationIcons[notification.type] || Info;
                    const content = (
                      <>
                        <Icon
                          size={17}
                          className={cn(
                            "mt-0.5 shrink-0",
                            notification.type === "critical" && "text-danger",
                            notification.type === "warning" && "text-warning",
                            notification.type === "success" && "text-success",
                            notification.type === "info" && "text-info",
                          )}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-start justify-between gap-3">
                            <span className="text-xs font-semibold text-foreground">{notification.title}</span>
                            {!notification.read && <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                          </span>
                          <span className="mt-1 block text-[11px] leading-4 text-foreground-muted">{notification.message}</span>
                          <span className="mt-1.5 block text-[10px] text-foreground-subtle">
                            {notification.created_at
                              ? new Date(notification.created_at).toLocaleString(undefined, {
                                  month: "short",
                                  day: "numeric",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })
                              : "Time not recorded"}
                          </span>
                        </span>
                      </>
                    );
                    const className = cn(
                      "flex min-h-11 w-full gap-3 rounded-lg px-3 py-3 text-left transition-colors hover:bg-surface-raised",
                      !notification.read && "bg-primary-subtle/45",
                    );
                    const internalActionUrl =
                      notification.action_url?.startsWith("/dashboard")
                        ? notification.action_url
                        : null;
                    return internalActionUrl ? (
                      <Link
                        key={notification.id}
                        href={internalActionUrl}
                        onClick={() => {
                          void markAsRead(notification.id);
                          setNotificationsOpen(false);
                        }}
                        className={className}
                      >
                        {content}
                      </Link>
                    ) : (
                      <button
                        type="button"
                        key={notification.id}
                        onClick={() => void markAsRead(notification.id)}
                        className={className}
                      >
                        {content}
                      </button>
                    );
                  })
                )}
              </div>
            </section>
          )}
        </div>

        <div ref={profileRef} className="relative">
          <button
            type="button"
            onClick={() => {
              setProfileOpen((open) => !open);
              setNotificationsOpen(false);
              setSearchOpen(false);
            }}
            aria-label="Open account menu"
            aria-expanded={profileOpen}
            className="flex min-h-11 items-center gap-2 rounded-lg px-1.5 text-left transition-colors hover:bg-surface-raised sm:px-2"
          >
            <span className="grid h-8 w-8 place-items-center rounded-full bg-primary-subtle text-xs font-semibold text-primary">
              {initials}
            </span>
            <ChevronDown size={14} className="hidden text-foreground-subtle sm:block" />
          </button>
          {profileOpen && (
            <div className="absolute right-0 top-12 w-64 rounded-xl border border-border bg-card p-1.5 shadow-xl">
              <div className="border-b border-border px-3 py-3">
                <p className="truncate text-sm font-semibold text-foreground">{displayName}</p>
                <p className="mt-0.5 truncate text-[11px] text-foreground-muted">{user?.email}</p>
              </div>
              <Link
                href="/dashboard/profile"
                className="mt-1 flex min-h-11 items-center gap-2.5 rounded-lg px-3 text-sm text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground"
              >
                <UserRound size={17} /> Profile and security
              </Link>
              <Link
                href="/dashboard/settings"
                className="flex min-h-11 items-center gap-2.5 rounded-lg px-3 text-sm text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground"
              >
                <Settings size={17} /> Settings
              </Link>
              <button
                type="button"
                onClick={() => void logout()}
                className="flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-sm text-danger transition-colors hover:bg-danger-subtle"
              >
                <LogOut size={17} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
