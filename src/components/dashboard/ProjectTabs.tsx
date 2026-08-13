"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

type ProjectTabsProps = {
  projectId: string;
};

const primaryTabs = [
  {
    label: "Overview",
    path: (id: string) => `/dashboard/apps/${id}`,
    matches: (pathname: string, id: string) => pathname === `/dashboard/apps/${id}`,
  },
  {
    label: "Analysis",
    path: (id: string) => `/dashboard/ai-analysis?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/ai-analysis"),
  },
  {
    label: "Architecture",
    path: (id: string) => `/dashboard/architect?project=${id}`,
    matches: (pathname: string) =>
      pathname.startsWith("/dashboard/architect") ||
      pathname.startsWith("/dashboard/infrastructure"),
  },
  {
    label: "Deployments",
    path: (id: string) => `/dashboard/deployments?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/deployments"),
  },
  {
    label: "Monitoring",
    path: (id: string) => `/dashboard/monitoring?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/monitoring"),
  },
] as const;

const secondaryTabs = [
  {
    label: "Logs",
    path: (id: string) => `/dashboard/logs?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/logs"),
  },
  {
    label: "Security",
    path: (id: string) => `/dashboard/security?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/security"),
  },
  {
    label: "Incidents",
    path: (id: string) => `/dashboard/incidents?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/incidents"),
  },
  {
    label: "Activity",
    path: (id: string) => `/dashboard/activity?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/activity"),
  },
  {
    label: "Cost",
    path: (id: string) => `/dashboard/cost-optimization?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/cost-optimization"),
  },
  {
    label: "Capacity",
    path: (id: string) => `/dashboard/autoscaling?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/autoscaling"),
  },
  {
    label: "Settings",
    path: (id: string) => `/dashboard/settings?project=${id}`,
    matches: (pathname: string) =>
      pathname.startsWith("/dashboard/settings") ||
      pathname.startsWith("/dashboard/profile") ||
      pathname.startsWith("/dashboard/billing"),
  },
] as const;

const tabs = [...primaryTabs, ...secondaryTabs] as const;

export function ProjectTabs({ projectId }: ProjectTabsProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedProject = searchParams.get("project");
  const activeTab = tabs.find(
    (tab) =>
      tab.matches(pathname, projectId) &&
      (pathname.startsWith("/dashboard/apps/") ||
        !requestedProject ||
        requestedProject === projectId),
  );

  return (
    <>
      <label className="ops-surface block p-3 sm:hidden">
        <span className="mb-1.5 block text-xs font-semibold text-foreground-muted">
          Project section
        </span>
        <select
          aria-label="Project section"
          value={activeTab?.path(projectId) ?? tabs[0].path(projectId)}
          onChange={(event) => router.push(event.target.value)}
          className="ops-input bg-surface-subtle font-medium"
        >
          {tabs.map((tab) => {
            const href = tab.path(projectId);
            return (
              <option key={tab.label} value={href}>
                {tab.label}
              </option>
            );
          })}
        </select>
      </label>

      <nav aria-label="Project sections" className="ops-surface hidden p-1.5 sm:block">
        <div className="flex items-center gap-1">
          <ul className="flex min-w-0 flex-1 gap-1 overflow-x-auto no-scrollbar">
          {primaryTabs.map((tab) => {
            const href = tab.path(projectId);
            const active = activeTab?.label === tab.label;
            return (
              <li key={tab.label}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex min-h-11 items-center rounded-lg px-3 text-xs font-semibold transition-colors",
                    active
                      ? "bg-primary-subtle text-primary shadow-sm"
                      : "text-foreground-muted hover:bg-surface-subtle hover:text-foreground",
                  )}
                >
                  {tab.label}
                </Link>
              </li>
            );
          })}
          </ul>

          <details className="group relative shrink-0">
            <summary
              className={cn(
                "flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-lg px-3 text-xs font-semibold transition-colors marker:hidden",
                secondaryTabs.some((tab) => tab.label === activeTab?.label)
                  ? "bg-primary-subtle text-primary shadow-sm"
                  : "text-foreground-muted hover:bg-surface-subtle hover:text-foreground",
              )}
            >
              More
              <ChevronDown
                size={14}
                aria-hidden="true"
                className="transition-transform group-open:rotate-180"
              />
            </summary>
            <ul className="absolute right-0 z-30 mt-2 w-48 rounded-xl border border-border bg-card p-1.5 shadow-lg">
              {secondaryTabs.map((tab) => {
                const href = tab.path(projectId);
                const active = activeTab?.label === tab.label;
                return (
                  <li key={tab.label}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex min-h-11 items-center rounded-lg px-3 text-xs font-semibold transition-colors",
                        active
                          ? "bg-primary-subtle text-primary"
                          : "text-foreground-muted hover:bg-surface-subtle hover:text-foreground",
                      )}
                    >
                      {tab.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </details>
        </div>
      </nav>
    </>
  );
}
