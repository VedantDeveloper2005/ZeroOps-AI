"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, X, TrendingUp, Shield, Rocket, DollarSign, Heart, RefreshCw, Activity, Lock, ShieldCheck, Cpu, Maximize, CheckCircle, AlertTriangle, BarChart3, Loader2 } from "lucide-react";
import { api, type AIAction } from "@/lib/api";
import { cn } from "@/lib/utils";

const iconMap: Record<string, React.ElementType> = {
  TrendingUp, Shield, RotateCcw: RefreshCw, AlertTriangle, RefreshCw, Heart, DollarSign, Lock, Activity, Rocket, BarChart3, Cpu, ShieldCheck, Maximize, CheckCircle, Brain,
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
  const [actions, setActions] = useState<AIAction[]>([]);
  const [loading, setLoading] = useState(true);

  // Fetch real AI actions from the backend
  useEffect(() => {
    if (!isOpen) return;

    async function loadActions() {
      setLoading(true);
      try {
        const data = await api.getAIActions({ limit: 30 });
        setActions(data);
      } catch {
        setActions([]);
      } finally {
        setLoading(false);
      }
    }
    loadActions();
  }, [isOpen]);

  const filtered = activeFilter === "All"
    ? actions
    : actions.filter(a => {
      if (activeFilter === "AI") return a.type === "optimization" || a.type === "healing";
      return a.type === activeFilter.toLowerCase().replace("s", "");
    });

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return "Just now";
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return `${Math.floor(diffHr / 24)}d ago`;
  };

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
              {actions.length > 0 && (
                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-success/10 text-success text-[10px] font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                  LIVE
                </span>
              )}
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
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Brain className="w-8 h-8 text-white/15 mb-3" />
                <p className="text-xs text-white/40">No autonomous actions yet</p>
                <p className="text-[10px] text-white/25 mt-1">AI will generate actions after deployments</p>
              </div>
            ) : (
              filtered.map((action, i) => {
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
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-foreground-muted">{formatTime(action.created_at)}</span>
                        {action.status === "pending" && (
                          <div className="flex gap-1">
                            <button
                              onClick={() => { api.applyAIAction(action.id); setActions(prev => prev.filter(a => a.id !== action.id)); }}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-success/10 text-success hover:bg-success/20"
                            >Apply</button>
                            <button
                              onClick={() => { api.dismissAIAction(action.id); setActions(prev => prev.filter(a => a.id !== action.id)); }}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/40 hover:bg-white/10"
                            >Dismiss</button>
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="p-3 border-t border-border flex-shrink-0">
            <p className="w-full text-xs text-foreground-muted text-center py-2">
              {actions.length} action{actions.length !== 1 ? "s" : ""} recorded
            </p>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
