"use client";

import { motion } from "framer-motion";
import { Activity, Clock, Rocket, Server, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, type DashboardStats, type Deployment } from "@/lib/api";

const formatDate = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

const parseDurationSeconds = (duration?: string | null) => {
  if (!duration) return null;
  const matches = duration.match(/\d+(?:\.\d+)?/g);
  if (!matches || matches.length !== 1) return null;
  const numeric = Number.parseFloat(matches[0]);
  return Number.isFinite(numeric) ? numeric : null;
};

export default function DashboardHome() {
  const { projects, isLoading: contextLoading } = useNotifications();
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function loadDashboardData() {
      setLoading(true);
      try {
        const [statsRes, deploymentsRes] = await Promise.allSettled([
          api.getDashboardStats(),
          api.getDeployments(200),
        ]);
        if (!active) return;
        if (statsRes.status === "fulfilled") setStats(statsRes.value);
        if (deploymentsRes.status === "fulfilled") setDeployments(deploymentsRes.value);
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        if (active) setLoading(false);
      }
    }
    loadDashboardData();
    return () => {
      active = false;
    };
  }, []);

  const { monthlyDeployments, avgDeployTimeSeconds } = useMemo(() => {
    if (deployments.length === 0) {
      return { monthlyDeployments: 0, avgDeployTimeSeconds: null };
    }
    const now = new Date();
    const cutoff = new Date(now);
    cutoff.setDate(now.getDate() - 30);
    const monthly = deployments.filter((deployment) => {
      const stamp = deployment.started_at || deployment.completed_at;
      if (!stamp) return false;
      const date = new Date(stamp);
      return !Number.isNaN(date.getTime()) && date >= cutoff;
    });
    const durations = monthly
      .map((deployment) => deployment.duration_seconds ?? parseDurationSeconds(deployment.duration))
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    const avg = durations.length > 0
      ? Math.round(durations.reduce((sum, value) => sum + value, 0) / durations.length)
      : null;
    return { monthlyDeployments: monthly.length, avgDeployTimeSeconds: avg };
  }, [deployments]);

  const totalDeploys = stats?.total_deployments ?? 0;
  const failedDeploys = stats?.failed_deployments ?? 0;
  const successRate = totalDeploys > 0
    ? `${Math.round(((totalDeploys - failedDeploys) / totalDeploys) * 100)}%`
    : "—";

  if (contextLoading || loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="text-foreground-muted text-sm font-medium">Loading portfolio dashboard...</p>
      </div>
    );
  }

  const metrics = [
    {
      label: "Total Applications",
      value: String(stats?.total_projects ?? projects.length),
      detail: "Across all environments",
      icon: Server,
      color: "text-primary",
    },
    {
      label: "Live Applications",
      value: String(stats?.active_deployments ?? projects.filter((project) => project.status === "active").length),
      detail: "Currently serving traffic",
      icon: Activity,
      color: "text-success",
    },
    {
      label: "Deployments This Month",
      value: String(monthlyDeployments),
      detail: "Last 30 days",
      icon: Rocket,
      color: "text-accent",
    },
    {
      label: "Success Rate",
      value: successRate,
      detail: totalDeploys > 0 ? `From ${totalDeploys} deployments` : "No deployments yet",
      icon: ShieldCheck,
      color: "text-info",
    },
    {
      label: "Average Deploy Time",
      value: avgDeployTimeSeconds ? `${avgDeployTimeSeconds}s` : "—",
      detail: avgDeployTimeSeconds ? "Recent deployments" : "No timing data",
      icon: Clock,
      color: "text-foreground",
    },
  ];

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">Portfolio Dashboard</h1>
          <p className="text-xs text-foreground-muted">
            Track every application, deployment, and live experience in one place.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {metrics.map((stat, i) => {
          const StatIcon = stat.icon;
          return (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-card border border-border rounded-2xl p-4 shadow-sm space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">{stat.label}</span>
                <StatIcon size={16} className={`${stat.color} opacity-80`} />
              </div>
              <div className="space-y-1">
                <p className="text-2xl font-extrabold text-foreground tracking-tight">{stat.value}</p>
                <p className="text-[10px] text-foreground-muted font-medium">{stat.detail}</p>
              </div>
            </motion.div>
          );
        })}
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between border-b border-border/40 pb-2">
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Applications</h2>
        </div>

        {projects.length === 0 ? (
          <div className="text-center py-12 bg-card border border-border rounded-2xl space-y-4">
            <Rocket size={32} className="text-foreground-muted/30 mx-auto" />
            <div className="space-y-1">
              <p className="text-sm font-bold text-foreground">No applications deployed yet</p>
              <p className="text-xs text-foreground-muted">Deploy your first application in minutes.</p>
            </div>
            <button
              onClick={() => router.push("/dashboard/repositories")}
              className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-md shadow-primary/10"
            >
              Deploy Application
            </button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => {
              const isLive = project.status === "active" || project.latest_deployment_status === "running";
              return (
                <motion.div
                  key={project.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-4"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-extrabold text-foreground">{project.name}</p>
                      <p className="text-[10px] text-foreground-muted">{project.full_name}</p>
                    </div>
                    <span className={`text-[10px] px-2 py-1 rounded-full font-bold ${isLive ? "bg-success/15 text-success" : "bg-warning/15 text-warning"}`}>
                      {isLive ? "Live" : "Idle"}
                    </span>
                  </div>
                  <div className="space-y-1 text-xs text-foreground-muted">
                    <p><span className="font-semibold text-foreground">Framework:</span> {project.framework || "Not detected"}</p>
                    <p><span className="font-semibold text-foreground">Last Deploy:</span> {formatDate(project.last_deployed_at)}</p>
                  </div>
                  <button
                    onClick={() => router.push(`/dashboard/apps/${project.id}`)}
                    className="w-full py-2 rounded-xl border border-border text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Open App
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
