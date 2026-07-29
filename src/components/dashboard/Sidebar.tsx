"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Boxes,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  LayoutDashboard,
  ListChecks,
  Plus,
  Settings,
  X,
} from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { cn } from "@/lib/utils";

type SidebarProps = {
  collapsed: boolean;
  mobileOpen: boolean;
  onMobileClose: () => void;
  onToggle: () => void;
};

const navigation = [
  {
    label: "Overview",
    href: "/dashboard",
    icon: LayoutDashboard,
    matches: (pathname: string) => pathname === "/dashboard",
  },
  {
    label: "Projects",
    href: "/dashboard/projects",
    icon: FolderKanban,
    matches: (pathname: string) =>
      pathname.startsWith("/dashboard/projects") ||
      pathname.startsWith("/dashboard/repositories") ||
      pathname.startsWith("/dashboard/apps/") ||
      pathname.startsWith("/dashboard/ai-analysis") ||
      pathname.startsWith("/dashboard/infrastructure") ||
      pathname.startsWith("/dashboard/security") ||
      pathname.startsWith("/dashboard/logs") ||
      pathname.startsWith("/dashboard/incidents") ||
      pathname.startsWith("/dashboard/cost-optimization") ||
      pathname.startsWith("/dashboard/autoscaling"),
  },
  {
    label: "Deployments",
    href: "/dashboard/deployments",
    icon: Boxes,
    matches: (pathname: string) => pathname.startsWith("/dashboard/deployments"),
  },
  {
    label: "Monitoring",
    href: "/dashboard/monitoring",
    icon: Activity,
    matches: (pathname: string) => pathname.startsWith("/dashboard/monitoring"),
  },
  {
    label: "AI Architect",
    href: "/dashboard/architect",
    icon: Bot,
    matches: (pathname: string) => pathname.startsWith("/dashboard/architect"),
  },
  {
    label: "Activity",
    href: "/dashboard/activity",
    icon: ListChecks,
    matches: (pathname: string) => pathname.startsWith("/dashboard/activity"),
  },
  {
    label: "Settings",
    href: "/dashboard/settings",
    icon: Settings,
    matches: (pathname: string) =>
      pathname.startsWith("/dashboard/settings") ||
      pathname.startsWith("/dashboard/profile") ||
      pathname.startsWith("/dashboard/billing"),
  },
] as const;

export function Sidebar({
  collapsed,
  mobileOpen,
  onMobileClose,
  onToggle,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      aria-label="Application navigation"
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex w-[280px] shrink-0 -translate-x-full flex-col border-r border-border bg-sidebar shadow-xl transition-[transform,width] duration-200 ease-out lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0 lg:shadow-none",
        mobileOpen && "translate-x-0",
        collapsed ? "lg:w-[76px]" : "lg:w-[244px]",
      )}
    >
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-border px-4">
        <BrandMark href="/dashboard" compact={collapsed} />
        <button
          type="button"
          onClick={onMobileClose}
          aria-label="Close navigation"
          className="grid min-h-11 min-w-11 place-items-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground lg:hidden"
        >
          <X size={19} />
        </button>
      </div>

      <div className="px-3 pb-2 pt-4">
        <Link
          href="/dashboard/repositories"
          className={cn(
            "flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover",
            collapsed && "lg:px-0",
          )}
          title={collapsed ? "New project" : undefined}
        >
          <Plus size={17} />
          <span className={cn(collapsed && "lg:sr-only")}>New project</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-3">
        <p
          className={cn(
            "mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-foreground-subtle",
            collapsed && "lg:sr-only",
          )}
        >
          Workspace
        </p>
        <ul className="space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = item.matches(pathname);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "group relative flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                    active
                      ? "bg-primary-subtle text-primary"
                      : "text-foreground-muted hover:bg-surface-raised hover:text-foreground",
                    collapsed && "lg:justify-center lg:px-0",
                  )}
                >
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary"
                    />
                  )}
                  <Icon size={18} strokeWidth={1.8} className="shrink-0" />
                  <span className={cn("truncate", collapsed && "lg:sr-only")}>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border p-3">
        <div
          className={cn(
            "rounded-lg border border-border bg-surface-subtle px-3 py-3",
            collapsed && "lg:hidden",
          )}
        >
          <p className="text-xs font-semibold text-foreground">Approval stays with you</p>
          <p className="mt-1 text-[11px] leading-4 text-foreground-muted">
            Code and cloud changes remain reviewable before execution.
          </p>
        </div>
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          className="mt-2 hidden min-h-11 w-full items-center justify-center gap-2 rounded-lg text-xs font-medium text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground lg:flex"
        >
          {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
