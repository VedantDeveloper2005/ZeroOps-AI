"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, X, TrendingUp, Shield, Rocket, DollarSign, Heart, RefreshCw, Activity, Lock, ShieldCheck, Cpu, Maximize, CheckCircle, AlertTriangle, BarChart3 } from "lucide-react";
import { aiActions } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

const iconMap: Record<string, React.ElementType> = {
  TrendingUp, Shield, RotateCcw: RefreshCw, AlertTriangle, RefreshCw, Heart, DollarSign, Lock, Activity, Rocket, BarChart3, Cpu, ShieldCheck, Maximize, CheckCircle,
};

const typeColors: Record<string, string> = {
  scaling: "text-primary border-l-primary",
  security: "text-danger border-l-danger",
  deployment: "text-success border-l-success",
  optimization: "text-accent border-l-accent",
  healing: "text-info border-l-info",
  monitoring: "text-warning border-l-warning",
};

const filters = ["All", "Scaling", "Security", "Deployments", "AI"] as const;

interface AIActionFeedProps { isOpen: boolean; onClose: () => void; }

export function AIActionFeed({ isOpen, onClose }: AIActionFeedProps) {
  const [activeFilter, setActiveFilter] = useState<string>("All");

  const filtered = activeFilter === "All"
    ? aiActions
    : aiActions.filter(a => {
      if (activeFilter === "AI") return a.type === "optimization" || a.type === "healing";
      return a.type === activeFilter.toLowerCase().replace("s", "");
    });

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 340, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
          className="h-full border-l border-border bg-background-secondary overflow-hidden flex flex-col flex-shrink-0"
        >
          {/* Header */}
          <div className="p-4 border-b border-border flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-2">
              <Brain size={18} className="text-primary" />
              <span className="font-semibold text-sm">Autonomous Actions</span>
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-success/10 text-success text-[10px] font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                LIVE
              </span>
            </div>
            <button onClick={onClose} className="p-1 rounded hover:bg-card text-foreground-muted"><X size={16} /></button>
          </div>

          {/* Filters */}
          <div className="flex gap-1 p-3 border-b border-border flex-shrink-0">
            {filters.map(f => (
              <button key={f} onClick={() => setActiveFilter(f)}
                className={cn("px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
                  activeFilter === f ? "bg-primary-subtle text-primary" : "text-foreground-muted hover:text-foreground hover:bg-card"
                )}>
                {f}
              </button>
            ))}
          </div>

          {/* Feed */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2 no-scrollbar">
            {filtered.map((action, i) => {
              const IconComp = iconMap[action.icon] || Activity;
              const colors = typeColors[action.type] || "text-foreground-muted border-l-border";
              return (
                <motion.div
                  key={action.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05, duration: 0.3 }}
                  className={cn("glass-subtle rounded-lg p-3 border-l-2 flex gap-3", colors)}
                >
                  <IconComp size={16} className={cn("flex-shrink-0 mt-0.5", colors.split(" ")[0])} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-foreground leading-relaxed">{action.message}</p>
                    <span className="text-[10px] text-foreground-muted mt-1 block">{action.timestamp}</span>
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* Footer */}
          <div className="p-3 border-t border-border flex-shrink-0">
            <button className="w-full text-xs text-primary hover:text-primary-hover font-medium py-2">
              View Full Timeline →
            </button>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
