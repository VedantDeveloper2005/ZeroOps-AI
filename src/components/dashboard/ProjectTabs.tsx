"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";

type ProjectTabsProps = {
  projectId: string;
};

const tabs = [
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
  {
    label: "Security",
    path: (id: string) => `/dashboard/security?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/security"),
  },
  {
    label: "Activity",
    path: (id: string) => `/dashboard/activity?project=${id}`,
    matches: (pathname: string) => pathname.startsWith("/dashboard/activity"),
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
      <label className="block rounded-xl border border-border bg-card p-3 shadow-sm sm:hidden">
        <span className="mb-1.5 block text-xs font-semibold text-foreground-muted">
          Project section
        </span>
        <select
          aria-label="Project section"
          value={activeTab?.path(projectId) ?? tabs[0].path(projectId)}
          onChange={(event) => router.push(event.target.value)}
          className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle px-3 text-sm font-medium text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15"
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

      <nav aria-label="Project sections" className="hidden sm:block">
        <ul className="flex flex-wrap gap-x-1 border-b border-border">
          {tabs.map((tab) => {
            const href = tab.path(projectId);
            const active = activeTab?.label === tab.label;
            return (
              <li key={tab.label}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex min-h-11 items-center px-3 text-xs font-medium transition-colors",
                    active
                      ? "text-primary"
                      : "text-foreground-muted hover:text-foreground",
                  )}
                >
                  {tab.label}
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary"
                    />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
