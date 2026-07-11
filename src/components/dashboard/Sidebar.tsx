"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  Activity,
  BarChart3,
  Brain,
  ChevronLeft,
  ChevronRight,
  DollarSign,
  FileText,
  Gauge,
  LayoutDashboard,
  LogOut,
  Network,
  ReceiptText,
  Rocket,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/lib/AuthContext";

type NavItem = {
  name: string;
  icon: React.ElementType;
  href: string;
  activePaths: string[];
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const navSections: NavSection[] = [
  {
    label: "WORKSPACE",
    items: [
      { name: "Home", icon: LayoutDashboard, href: "/dashboard", activePaths: ["/dashboard"] },
      { name: "New application", icon: Rocket, href: "/dashboard/repositories", activePaths: ["/dashboard/repositories"] },
      { name: "Deployments", icon: Activity, href: "/dashboard/deployments", activePaths: ["/dashboard/deployments"] },
    ],
  },
  {
    label: "OPERATE",
    items: [
      { name: "Monitoring", icon: BarChart3, href: "/dashboard/monitoring", activePaths: ["/dashboard/monitoring"] },
      { name: "Incidents", icon: Activity, href: "/dashboard/incidents", activePaths: ["/dashboard/incidents"] },
      { name: "Logs", icon: FileText, href: "/dashboard/logs", activePaths: ["/dashboard/logs"] },
      { name: "Infrastructure", icon: Network, href: "/dashboard/infrastructure", activePaths: ["/dashboard/infrastructure"] },
      { name: "Autoscaling", icon: Gauge, href: "/dashboard/autoscaling", activePaths: ["/dashboard/autoscaling"] },
    ],
  },
  {
    label: "OPTIMIZE",
    items: [
      { name: "AI analysis", icon: Brain, href: "/dashboard/ai-analysis", activePaths: ["/dashboard/ai-analysis"] },
      { name: "Security", icon: ShieldCheck, href: "/dashboard/security", activePaths: ["/dashboard/security"] },
      { name: "Cost optimization", icon: DollarSign, href: "/dashboard/cost-optimization", activePaths: ["/dashboard/cost-optimization"] },
    ],
  },
  {
    label: "ACCOUNT",
    items: [
      { name: "Settings", icon: Settings, href: "/dashboard/settings", activePaths: ["/dashboard/settings"] },
      { name: "Plan & billing", icon: ReceiptText, href: "/dashboard/billing", activePaths: ["/dashboard/billing"] },
    ],
  },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const firstName = user?.firstName || user?.first_name || "";
  const lastName = user?.lastName || user?.last_name || "";

  const initials = firstName && lastName
    ? `${firstName[0].toUpperCase()}${lastName[0].toUpperCase()}`
    : firstName
      ? firstName[0].toUpperCase()
      : user?.email
        ? user.email[0].toUpperCase()
        : "U";

  const fullName = firstName && lastName
    ? `${firstName} ${lastName}`
    : firstName
      ? firstName
      : user?.email
        ? user.email.split("@")[0]
        : "User";

  const isActive = (activePaths: string[]) => {
    return activePaths.some(path => {
      if (path === "/dashboard") return pathname === "/dashboard";
      return pathname.startsWith(path);
    });
  };

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 260 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="h-full border-r border-border bg-background-secondary/90 flex flex-col overflow-hidden flex-shrink-0 shadow-[12px_0_38px_rgba(15,23,42,0.04)]"
    >
      {/* Logo */}
      <div className="h-16 flex items-center px-4 border-b border-border gap-3">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center flex-shrink-0">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L21.5 7.5V16.5L12 22L2.5 16.5V7.5L12 2Z" stroke="white" strokeWidth="1.5" fill="none" />
            <path d="M12 8L16 10.5V15.5L12 18L8 15.5V10.5L12 8Z" stroke="white" strokeWidth="1.5" fill="rgba(255,255,255,0.2)" />
          </svg>
        </div>
        <AnimatePresence>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="text-lg font-bold tracking-tight text-foreground"
            >
              ZEROOPS
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <nav aria-label="Workspace navigation" className="flex-1 overflow-y-auto py-4 px-3 no-scrollbar">
        {navSections.map((section) => (
          <div key={section.label} className="mb-4">
            <AnimatePresence>
              {!collapsed && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-[10px] font-semibold text-foreground-muted tracking-widest px-3 mb-2"
                >
                  {section.label}
                </motion.p>
              )}
            </AnimatePresence>
            {section.items.map((item) => {
              const active = isActive(item.activePaths);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-xl mb-0.5 transition-all duration-200 group relative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background-secondary",
                    active
                      ? "bg-primary-subtle text-primary"
                      : "text-foreground-muted hover:text-foreground hover:bg-card",
                  )}
                >
                  {active && (
                    <motion.div
                      layoutId="activeNav"
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 bg-primary rounded-r-full"
                      transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
                    />
                  )}
                  <Icon size={20} className="flex-shrink-0" />
                  <AnimatePresence>
                    {!collapsed && (
                      <motion.span
                        initial={{ opacity: 0, x: -5 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -5 }}
                        className="text-sm font-medium whitespace-nowrap"
                      >
                        {item.name}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Actions */}
      <div className="border-t border-border p-3 flex flex-col gap-2">
        <ThemeToggle collapsed={collapsed} />
        <button
          onClick={logout}
          aria-label="Sign out"
          title="Sign Out"
          className="w-full flex items-center justify-center p-2 rounded-lg hover:bg-card transition-colors text-danger hover:text-danger-hover"
        >
          <LogOut size={18} className="flex-shrink-0" />
          {!collapsed && <span className="text-xs font-semibold ml-2">Sign Out</span>}
        </button>
        <button
          onClick={onToggle}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          className="w-full flex items-center justify-center p-2 rounded-lg hover:bg-card transition-colors text-foreground-muted hover:text-foreground"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* User profile */}
      <Link href="/dashboard/profile" className="border-t border-border p-3 block hover:bg-card/40 transition-colors">
        <div className={cn("flex items-center gap-3", collapsed && "justify-center")}>
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center text-sm font-bold text-foreground flex-shrink-0 relative">
            {initials}
            <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-success border-2 border-background-secondary" />
          </div>
          <AnimatePresence>
            {!collapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="overflow-hidden"
              >
                <p className="text-sm font-medium text-foreground truncate">{fullName}</p>
                <p className="text-[10px] text-foreground-muted">{user?.plan ? user.plan.charAt(0).toUpperCase() + user.plan.slice(1) : "Starter"}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </Link>
    </motion.aside>
  );
}
