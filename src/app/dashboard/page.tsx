"use client";

import { motion } from "framer-motion";
import {
  TrendingUp, TrendingDown, ArrowUpRight, Rocket, Shield,
  Brain, Cpu, Zap, Loader2, FolderGit2, Activity, AlertTriangle
} from "lucide-react";
import { useState, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, type DashboardStats, type Deployment, type AIAction } from "@/lib/api";

const statIcons: Record<string, React.ElementType> = {
  blue: Rocket, green: Shield, cyan: Zap, purple: Brain, amber: Cpu, red: TrendingDown
};

export default function DashboardHome() {
  const { hasDeployed, isLoading: contextLoading } = useNotifications();
  const router = useRouter();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentDeps, setRecentDeps] = useState<Deployment[]>([]);
  const [aiActions, setAIActions] = useState<AIAction[]>([]);
  const [loading, setLoading] = useState(true);

  // Redirect to onboarding if no deployments
  useEffect(() => {
    if (!contextLoading && !hasDeployed) {
      router.replace("/dashboard/repositories");
    }
  }, [contextLoading, hasDeployed, router]);

  // Fetch dashboard data
  useEffect(() => {
    if (!hasDeployed) return;

    async function loadDashboard() {
      setLoading(true);
      try {
        const [statsData, depsData, actionsData] = await Promise.allSettled([
          api.getDashboardStats(),
          api.getDeployments(5),
          api.getAIActions({ status: "pending", limit: 5 }),
        ]);
        if (statsData.status === "fulfilled") setStats(statsData.value);
        if (depsData.status === "fulfilled") setRecentDeps(depsData.value);
        if (actionsData.status === "fulfilled") setAIActions(actionsData.value);
      } finally {
        setLoading(false);
      }
    }
    loadDashboard();
  }, [hasDeployed]);

  // Loading state
  if (contextLoading || loading || !hasDeployed) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading dashboard...</p>
      </div>
    );
  }

  const dashboardCards = stats ? [
    { label: "Active Deployments", value: String(stats.active_deployments), change: "", trend: "up" as const, color: "blue" },
    { label: "Total Projects", value: String(stats.total_projects), change: "", trend: "up" as const, color: "green" },
    { label: "Security Score", value: stats.security_score > 0 ? String(stats.security_score) : "—", change: "", trend: "up" as const, color: "cyan" },
    { label: "AI Actions Pending", value: String(stats.pending_ai_actions), change: "", trend: "neutral" as const, color: "purple" },
    { label: "Total Deployments", value: String(stats.total_deployments), change: "", trend: "up" as const, color: "amber" },
    { label: "Failed Deployments", value: String(stats.failed_deployments), change: "", trend: stats.failed_deployments > 0 ? "up" as const : "neutral" as const, color: "red" },
  ] : [];

  const statusColors: Record<string, string> = {
    running: "bg-success/10 text-success border-success/20",
    building: "bg-warning/10 text-warning border-warning/20",
    deploying: "bg-primary/10 text-primary border-primary/20",
    failed: "bg-danger/10 text-danger border-danger/20",
    stopped: "bg-foreground-muted/10 text-foreground-muted border-border",
    queued: "bg-accent/10 text-accent border-accent/20",
  };

  return (
    <div className="space-y-6">
      {/* Dynamic Title for Overview (Overview doesn't render SubPageHeader, so we show page header here) */}
      <div className="mb-4">
        <h1 className="text-xl font-bold tracking-tight text-foreground">System Overview</h1>
        <p className="mt-1 text-xs text-foreground-muted">High-level operational stats, recent deployments, and autonomic tuning recommendations.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {dashboardCards.map((stat, i) => {
          const IconComponent = statIcons[stat.color] || Rocket;
          return (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.3 }}
              className="relative overflow-hidden rounded-xl border border-border bg-card p-4 hover:bg-card-hover transition-all duration-200 group shadow-sm"
            >
              <div className="flex items-start justify-between mb-3">
                <div className={`p-1.5 rounded-md bg-primary-subtle`}>
                  <IconComponent className={`w-4 h-4 text-primary`} />
                </div>
                {stat.trend === "up" && stat.color !== "red" && (
                  <TrendingUp className="w-3.5 h-3.5 text-success" />
                )}
                {stat.trend === "up" && stat.color === "red" && (
                  <TrendingDown className="w-3.5 h-3.5 text-danger" />
                )}
              </div>
              <div className="text-2xl font-bold text-foreground mb-1">{stat.value}</div>
              <div className="text-xs text-foreground-muted">{stat.label}</div>
            </motion.div>
          );
        })}
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Deployments */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl border border-border bg-card overflow-hidden shadow-sm"
        >
          <div className="flex items-center justify-between p-4 border-b border-border">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              <h2 className="text-sm font-bold text-foreground">Recent Deployments</h2>
            </div>
            <button
              onClick={() => router.push("/dashboard/deployments")}
              className="text-xs text-primary hover:text-primary-hover font-semibold flex items-center gap-1 transition-colors"
            >
              View All <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {recentDeps.length === 0 ? (
            <div className="p-8 text-center">
              <FolderGit2 className="w-8 h-8 text-foreground-muted/30 mx-auto mb-3" />
              <p className="text-sm text-foreground-muted">No deployments yet</p>
            </div>
          ) : (
            <div className="divide-y divide-border/60">
              {recentDeps.map((dep) => (
                <div
                  key={dep.id}
                  className="flex items-center justify-between p-4 hover:bg-card-hover/40 transition-colors cursor-pointer"
                  onClick={() => router.push("/dashboard/deployments")}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${
                      dep.status === "running" ? "bg-success" :
                      dep.status === "failed" ? "bg-danger" :
                      dep.status === "building" ? "bg-warning animate-pulse" :
                      "bg-foreground-muted"
                    }`} />
                    <div>
                      <p className="text-sm font-semibold text-foreground">{dep.project_name || "Project"}</p>
                      <p className="text-xs text-foreground-muted">{dep.environment} • {dep.branch}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${statusColors[dep.status] || statusColors.stopped}`}>
                      {dep.status}
                    </span>
                    <p className="text-[10px] text-foreground-muted mt-1">{dep.duration || "—"}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        {/* AI Recommendations */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="rounded-xl border border-border bg-card overflow-hidden shadow-sm"
        >
          <div className="flex items-center justify-between p-4 border-b border-border">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-bold text-foreground">AI Recommendations</h2>
            </div>
          </div>

          {aiActions.length === 0 ? (
            <div className="p-8 text-center">
              <Brain className="w-8 h-8 text-foreground-muted/30 mx-auto mb-3" />
              <p className="text-sm text-foreground-muted">No pending recommendations</p>
              <p className="text-xs text-foreground-muted/70 mt-1">AI will generate insights after deployments</p>
            </div>
          ) : (
            <div className="divide-y divide-border/60">
              {aiActions.map((action) => (
                <div key={action.id} className="flex items-start gap-3 p-4 hover:bg-card-hover/40 transition-colors">
                  <div className={`p-1.5 rounded-md mt-0.5 ${
                    action.severity === "critical" ? "bg-danger/10" :
                    action.severity === "warning" ? "bg-warning/10" :
                    action.severity === "success" ? "bg-success/10" :
                    "bg-primary/10"
                  }`}>
                    <AlertTriangle className={`w-3.5 h-3.5 ${
                      action.severity === "critical" ? "text-danger" :
                      action.severity === "warning" ? "text-warning" :
                      action.severity === "success" ? "text-success" :
                      "text-primary"
                    }`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-foreground/80 leading-relaxed">{action.message}</p>
                    <p className="text-[10px] text-foreground-muted mt-1 uppercase font-semibold">{action.type}</p>
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => api.applyAIAction(action.id)}
                      className="text-[10px] font-bold px-2.5 py-1 rounded bg-primary text-white hover:bg-primary-hover transition-colors"
                    >
                      Apply
                    </button>
                    <button
                      onClick={() => api.dismissAIAction(action.id)}
                      className="text-[10px] font-bold px-2.5 py-1 rounded bg-background-secondary text-foreground-muted hover:bg-card-hover transition-colors border border-border"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
