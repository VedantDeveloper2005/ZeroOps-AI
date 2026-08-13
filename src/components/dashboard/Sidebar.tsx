"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Boxes,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  LayoutDashboard,
  ListChecks,
  Plus,
  ReceiptText,
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
    label: "Workspace",
    items: [
      { label: "Overview", href: "/dashboard", icon: LayoutDashboard, matches: (path: string) => path === "/dashboard" },
      {
        label: "Projects",
        href: "/dashboard/projects",
        icon: FolderKanban,
        matches: (path: string) =>
          path.startsWith("/dashboard/projects") ||
          path.startsWith("/dashboard/apps/") ||
          path.startsWith("/dashboard/ai-analysis") ||
          path.startsWith("/dashboard/architect") ||
          path.startsWith("/dashboard/infrastructure") ||
          path.startsWith("/dashboard/logs") ||
          path.startsWith("/dashboard/security") ||
          path.startsWith("/dashboard/incidents"),
      },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Deployments", href: "/dashboard/deployments", icon: Boxes, matches: (path: string) => path.startsWith("/dashboard/deployments") },
      { label: "Monitoring", href: "/dashboard/monitoring", icon: Activity, matches: (path: string) => path.startsWith("/dashboard/monitoring") },
      { label: "Activity", href: "/dashboard/activity", icon: ListChecks, matches: (path: string) => path.startsWith("/dashboard/activity") },
    ],
  },
  {
    label: "Account",
    items: [
      {
        label: "Settings",
        href: "/dashboard/settings",
        icon: Settings,
        matches: (path: string) =>
          path.startsWith("/dashboard/settings") ||
          path.startsWith("/dashboard/profile") ||
          path.startsWith("/dashboard/cost-optimization") ||
          path.startsWith("/dashboard/autoscaling"),
      },
      {
        label: "Billing",
        href: "/dashboard/billing",
        icon: ReceiptText,
        matches: (path: string) => path.startsWith("/dashboard/billing"),
      },
    ],
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
      id="application-navigation"
      aria-label="Application navigation"
      className={cn(
        "dashboard-sidebar fixed inset-y-0 left-0 z-40 flex w-[288px] shrink-0 -translate-x-full flex-col border-r border-border bg-sidebar shadow-xl transition-[transform,width] duration-200 ease-out motion-reduce:transition-none lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0 lg:shadow-none",
        mobileOpen && "translate-x-0",
        collapsed ? "lg:w-[76px]" : "lg:w-[244px]",
      )}
    >
      <div className="flex h-[72px] shrink-0 items-center justify-between border-b border-border px-4">
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
            "flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-3 text-sm font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-primary-hover",
            collapsed && "lg:px-0",
          )}
          title={collapsed ? "New project" : undefined}
        >
          <Plus size={17} />
          <span className={cn(collapsed && "lg:sr-only")}>New project</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-3">
        {navigation.map((group, groupIndex) => (
          <div
            key={group.label}
            className={cn(groupIndex > 0 && "mt-5 border-t border-border/70 pt-4")}
          >
            <p
              className={cn(
                "mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-foreground-subtle",
                collapsed && "lg:sr-only",
              )}
            >
              {group.label}
            </p>
            <ul className="space-y-1">
              {group.items.map((item) => {
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
                        <span aria-hidden="true" className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary" />
                      )}
                      <Icon size={18} strokeWidth={1.8} className="shrink-0" />
                      <span className={cn("min-w-0 flex-1 truncate", collapsed && "lg:sr-only")}>{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <div
          className={cn(
            "rounded-lg border border-border bg-surface-subtle px-3 py-3",
            collapsed && "lg:hidden",
          )}
        >
          <p className="text-xs font-semibold text-foreground">Review before release</p>
          <p className="mt-1 text-xs leading-5 text-foreground-muted">
            Required approvals stay pinned to the exact commit and target.
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
