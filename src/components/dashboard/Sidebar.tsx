"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, GitBranch, Rocket, Brain, DollarSign,
  Shield, Activity, TrendingUp, Network, Terminal,
  AlertTriangle, CreditCard, Settings, ChevronLeft, ChevronRight,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

const navSections = [
  {
    label: "CORE",
    items: [
      { name: "Dashboard", icon: LayoutDashboard, href: "/dashboard" },
      { name: "Repositories", icon: GitBranch, href: "/dashboard/repositories" },
      { name: "Deployments", icon: Rocket, href: "/dashboard/deployments" },
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [
      { name: "AI Analysis", icon: Brain, href: "/dashboard/ai-analysis" },
      { name: "Cost Optimization", icon: DollarSign, href: "/dashboard/cost-optimization" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { name: "Security Center", icon: Shield, href: "/dashboard/security" },
      { name: "Monitoring", icon: Activity, href: "/dashboard/monitoring" },
      { name: "Autoscaling", icon: TrendingUp, href: "/dashboard/autoscaling" },
      { name: "Infrastructure", icon: Network, href: "/dashboard/infrastructure" },
      { name: "Logs", icon: Terminal, href: "/dashboard/logs" },
    ],
  },
  {
    label: "PLATFORM",
    items: [
      { name: "Incidents", icon: AlertTriangle, href: "/dashboard/incidents" },
      { name: "Billing", icon: CreditCard, href: "/dashboard/billing" },
      { name: "Settings", icon: Settings, href: "/dashboard/settings" },
    ],
  },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  };

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 260 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="h-full bg-background-secondary border-r border-border flex flex-col overflow-hidden flex-shrink-0"
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
      <nav className="flex-1 overflow-y-auto py-4 px-3 no-scrollbar">
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
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg mb-0.5 transition-all duration-200 group relative",
                    active
                      ? "bg-primary-subtle text-primary"
                      : "text-foreground-muted hover:text-foreground hover:bg-card"
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
          onClick={onToggle}
          className="w-full flex items-center justify-center p-2 rounded-lg hover:bg-card transition-colors text-foreground-muted hover:text-foreground"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* User profile */}
      <div className="border-t border-border p-3">
        <div className={cn("flex items-center gap-3", collapsed && "justify-center")}>
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center text-sm font-bold text-foreground flex-shrink-0 relative">
            VS
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
                <p className="text-sm font-medium text-foreground truncate">Vedant S.</p>
                <p className="text-[10px] text-foreground-muted">Admin</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.aside>
  );
}
