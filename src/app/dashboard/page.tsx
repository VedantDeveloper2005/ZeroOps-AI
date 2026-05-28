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
        <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
        <p className="text-white/50 text-sm">Loading dashboard...</p>
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
    running: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    building: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    deploying: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
    stopped: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
    queued: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  };

  return (
    <div className="space-y-8">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {dashboardCards.map((stat, i) => {
          const IconComponent = statIcons[stat.color] || Rocket;
          return (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.4 }}
              className="relative overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-sm p-4 hover:bg-white/[0.05] transition-all duration-300 group"
            >
              <div className="flex items-start justify-between mb-3">
                <div className={`p-2 rounded-lg bg-${stat.color}-500/10`}>
                  <IconComponent className={`w-4 h-4 text-${stat.color}-400`} />
                </div>
                {stat.trend === "up" && stat.color !== "red" && (
                  <TrendingUp className="w-3 h-3 text-emerald-400" />
                )}
                {stat.trend === "up" && stat.color === "red" && (
                  <TrendingDown className="w-3 h-3 text-red-400" />
                )}
              </div>
              <div className="text-2xl font-bold text-white mb-1">{stat.value}</div>
              <div className="text-xs text-white/40">{stat.label}</div>
            </motion.div>
          );
        })}
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Deployments */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm overflow-hidden"
        >
          <div className="flex items-center justify-between p-5 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold text-white">Recent Deployments</h2>
            </div>
            <button
              onClick={() => router.push("/dashboard/deployments")}
              className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
            >
              View All <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>

          {recentDeps.length === 0 ? (
            <div className="p-8 text-center">
              <FolderGit2 className="w-8 h-8 text-white/20 mx-auto mb-3" />
              <p className="text-sm text-white/40">No deployments yet</p>
            </div>
          ) : (
            <div className="divide-y divide-white/[0.04]">
              {recentDeps.map((dep) => (
                <div
                  key={dep.id}
                  className="flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors cursor-pointer"
                  onClick={() => router.push("/dashboard/deployments")}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${
                      dep.status === "running" ? "bg-emerald-400" :
                      dep.status === "failed" ? "bg-red-400" :
                      dep.status === "building" ? "bg-amber-400 animate-pulse" :
                      "bg-zinc-400"
                    }`} />
                    <div>
                      <p className="text-sm font-medium text-white">{dep.project_name || "Project"}</p>
                      <p className="text-xs text-white/40">{dep.environment} • {dep.branch}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`text-xs px-2 py-1 rounded-full border ${statusColors[dep.status] || statusColors.stopped}`}>
                      {dep.status}
                    </span>
                    <p className="text-xs text-white/30 mt-1">{dep.duration || "—"}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        {/* AI Recommendations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="rounded-xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm overflow-hidden"
        >
          <div className="flex items-center justify-between p-5 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-400" />
              <h2 className="text-sm font-semibold text-white">AI Recommendations</h2>
            </div>
          </div>

          {aiActions.length === 0 ? (
            <div className="p-8 text-center">
              <Brain className="w-8 h-8 text-white/20 mx-auto mb-3" />
              <p className="text-sm text-white/40">No pending recommendations</p>
              <p className="text-xs text-white/25 mt-1">AI will generate insights after deployments</p>
            </div>
          ) : (
            <div className="divide-y divide-white/[0.04]">
              {aiActions.map((action) => (
                <div key={action.id} className="flex items-start gap-3 p-4 hover:bg-white/[0.02] transition-colors">
                  <div className={`p-1.5 rounded-lg mt-0.5 ${
                    action.severity === "critical" ? "bg-red-500/10" :
                    action.severity === "warning" ? "bg-amber-500/10" :
                    action.severity === "success" ? "bg-emerald-500/10" :
                    "bg-cyan-500/10"
                  }`}>
                    <AlertTriangle className={`w-3.5 h-3.5 ${
                      action.severity === "critical" ? "text-red-400" :
                      action.severity === "warning" ? "text-amber-400" :
                      action.severity === "success" ? "text-emerald-400" :
                      "text-cyan-400"
                    }`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white/80 line-clamp-2">{action.message}</p>
                    <p className="text-xs text-white/30 mt-1">{action.type}</p>
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => api.applyAIAction(action.id)}
                      className="text-xs px-2.5 py-1 rounded-md bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 transition-colors"
                    >
                      Apply
                    </button>
                    <button
                      onClick={() => api.dismissAIAction(action.id)}
                      className="text-xs px-2.5 py-1 rounded-md bg-white/5 text-white/40 hover:bg-white/10 transition-colors"
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
