"use client";

import { motion } from "framer-motion";
import { 
  Activity, Clock, Rocket, Server, ShieldCheck, 
  ExternalLink, RefreshCw, RotateCcw, FileText, 
  CheckCircle2, AlertTriangle, XCircle 
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, type DashboardStats, type Deployment, getErrorMessage } from "@/lib/api";

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
  const { projects, isLoading: contextLoading, addToast, refreshProjects } = useNotifications();
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

  const handleRedeploy = async (projectId: string, projectName: string) => {
    try {
      await api.startDeployment({ project_id: projectId });
      addToast(`Redeployment initiated for ${projectName}`, "success");
      refreshProjects();
    } catch (err) {
      addToast(`Failed to redeploy: ${getErrorMessage(err, "unknown error")}`, "error");
    }
  };

  const handleRollback = async (projectId: string, projectName: string) => {
    try {
      await api.startDeployment({ project_id: projectId });
      addToast(`Rollback initiated for ${projectName}`, "success");
      refreshProjects();
    } catch (err) {
      addToast(`Failed to rollback: ${getErrorMessage(err, "unknown error")}`, "error");
    }
  };

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

  const latestDeploymentByProject = useMemo(() => {
    const byProject = new Map<string, Deployment>();
    deployments.forEach((deployment) => {
      const existing = byProject.get(deployment.project_id);
      const deploymentTime = new Date(deployment.completed_at || deployment.started_at || 0).getTime();
      const existingTime = existing ? new Date(existing.completed_at || existing.started_at || 0).getTime() : 0;
      if (!existing || deploymentTime > existingTime) {
        byProject.set(deployment.project_id, deployment);
      }
    });
    return byProject;
  }, [deployments]);

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
          <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border/60 bg-muted/20 text-[10px] font-bold text-foreground-muted uppercase tracking-wider">
                    <th className="py-4 px-5">Application</th>
                    <th className="py-4 px-4">Status</th>
                    <th className="py-4 px-4">Live URL</th>
                    <th className="py-4 px-4">Last Deployment</th>
                    <th className="py-4 px-4">Deploy Health</th>
                    <th className="py-4 px-4 text-center">Latency</th>
                    <th className="py-4 px-4">Environment</th>
                    <th className="py-4 px-5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-xs">
                  {projects.map((project, idx) => {
                    const isBuilding = project.latest_deployment_status === "building" || project.latest_deployment_status === "deploying" || project.status === "building";
                    const isLive = project.status === "active" || project.latest_deployment_status === "running";
                    
                    let statusLabel = "Idle";
                    let statusClass = "bg-warning/15 text-warning border border-warning/20";
                    if (isBuilding) {
                      statusLabel = "Building";
                      statusClass = "bg-accent/15 text-accent border border-accent/20 animate-pulse";
                    } else if (isLive) {
                      statusLabel = "Running";
                      statusClass = "bg-success/15 text-success border border-success/20";
                    }

                    const latestDeployment = latestDeploymentByProject.get(project.id);
                    const liveUrl = latestDeployment?.live_url || "";

                    // Deploy health pills
                    let healthLabel = "No signal";
                    let healthIcon = <AlertTriangle size={12} className="text-foreground-muted mr-1" />;
                    let healthClass = "bg-muted text-foreground-muted border border-border/50";

                    if (project.latest_deployment_status === "failed") {
                      healthLabel = "Critical";
                      healthIcon = <XCircle size={12} className="text-danger mr-1" />;
                      healthClass = "bg-danger/10 text-danger border border-danger/20";
                    } else if (isBuilding) {
                      healthLabel = "Warning";
                      healthIcon = <AlertTriangle size={12} className="text-warning mr-1" />;
                      healthClass = "bg-warning/10 text-warning border border-warning/20";
                    } else if (isLive) {
                      healthLabel = "Running";
                      healthIcon = <CheckCircle2 size={12} className="text-success mr-1" />;
                      healthClass = "bg-success/10 text-success border border-success/20";
                    }

                    return (
                      <motion.tr
                        key={project.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        className="hover:bg-muted/10 transition-colors"
                      >
                        <td className="py-4 px-5">
                          <div className="font-extrabold text-foreground">{project.name}</div>
                          <div className="text-[10px] text-foreground-muted font-medium">{project.framework || "Not detected"} • {project.language || "Not detected"}</div>
                        </td>
                        <td className="py-4 px-4">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${statusClass}`}>
                            {statusLabel}
                          </span>
                        </td>
                        <td className="py-4 px-4">
                          {liveUrl ? (
                            <a
                              href={liveUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center text-primary hover:underline font-semibold"
                            >
                              <span>{liveUrl.replace(/^https?:\/\//, "")}</span>
                              <ExternalLink size={10} className="ml-1" />
                            </a>
                          ) : (
                            <span className="text-foreground-muted font-semibold">Not recorded</span>
                          )}
                        </td>
                        <td className="py-4 px-4 text-foreground-muted font-medium">
                          {formatDate(project.last_deployed_at)}
                        </td>
                        <td className="py-4 px-4">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold ${healthClass}`}>
                            {healthIcon}
                            {healthLabel}
                          </span>
                        </td>
                        <td className="py-4 px-4 text-center text-foreground font-semibold">
                          No data
                        </td>
                        <td className="py-4 px-4">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-muted text-foreground-muted text-[10px] font-bold border border-border/50">
                            Production
                          </span>
                        </td>
                        <td className="py-4 px-5">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => router.push(`/dashboard/apps/${project.id}`)}
                              title="Open Workspace"
                              className="p-1.5 rounded-lg border border-border text-foreground-muted hover:text-foreground hover:bg-card-hover transition cursor-pointer"
                            >
                              <FileText size={14} />
                            </button>
                            <button
                              onClick={() => handleRedeploy(project.id, project.name)}
                              title="Redeploy"
                              className="p-1.5 rounded-lg border border-border text-foreground-muted hover:text-foreground hover:bg-card-hover transition cursor-pointer"
                            >
                              <RefreshCw size={14} />
                            </button>
                            <button
                              onClick={() => handleRollback(project.id, project.name)}
                              title="Rollback"
                              className="p-1.5 rounded-lg border border-border text-foreground-muted hover:text-foreground hover:bg-card-hover transition cursor-pointer"
                            >
                              <RotateCcw size={14} />
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
