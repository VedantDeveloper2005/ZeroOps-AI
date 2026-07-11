"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";

interface TabItem {
  label: string;
  href: string;
}

interface NavGroup {
  title: string;
  description: string;
  tabs: TabItem[];
}

const navGroups: Record<string, NavGroup> = {
  delivery: {
    title: "Launch",
    description: "Bring in your code, then choose when to go live.",
    tabs: [
      { label: "New application", href: "/dashboard/repositories" },
      { label: "Activity", href: "/dashboard/deployments" },
    ],
  },
  settings: {
    title: "Account",
    description: "Manage your account, preferences, and paid actions.",
    tabs: [
      { label: "Preferences", href: "/dashboard/settings" },
      { label: "Plan & billing", href: "/dashboard/billing" },
      { label: "Profile", href: "/dashboard/profile" },
    ],
  },
};

export function SubPageHeader() {
  const pathname = usePathname();

  // Determine current active group
  let activeGroupKey = "";
  let activeGroup: NavGroup | null = null;

  for (const [key, group] of Object.entries(navGroups)) {
    if (group.tabs.some((tab) => pathname === tab.href || pathname.startsWith(tab.href + "/"))) {
      activeGroupKey = key;
      activeGroup = group;
      break;
    }
  }

  if (!activeGroup) return null;

  return (
    <div className="mb-6 flex flex-col gap-4 border-b border-border/60 pb-5 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-foreground">{activeGroup.title}</h1>
        <p className="mt-1 text-xs text-foreground-muted">{activeGroup.description}</p>
      </div>

      {/* Segmented Control (macOS Style) */}
      <div className="inline-flex rounded-lg bg-background-secondary p-0.5 border border-border/50 shrink-0 self-start md:self-auto">
        {activeGroup.tabs.map((tab) => {
          const isActive = pathname === tab.href || pathname.startsWith(tab.href + "/");
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className="relative px-3.5 py-1.5 text-xs font-semibold rounded-md transition-colors select-none outline-none focus-visible:ring-2 focus-visible:ring-primary"
              style={{
                WebkitTapHighlightColor: "transparent",
              }}
            >
              {isActive && (
                <motion.span
                  layoutId={`active-tab-${activeGroupKey}`}
                  className="absolute inset-0 bg-card rounded-md shadow-sm border border-border/40"
                  transition={{ type: "spring", bounce: 0.15, duration: 0.38 }}
                />
              )}
              <span className={`relative z-10 transition-colors duration-200 ${isActive ? "text-foreground font-bold" : "text-foreground-muted hover:text-foreground"}`}>
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
