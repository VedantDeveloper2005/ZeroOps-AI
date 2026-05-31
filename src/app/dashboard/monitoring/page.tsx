"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, AlertTriangle, Clock, Cpu, Database, HardDrive, Loader2, Wifi } from "lucide-react";
import { AreaChart } from "@/components/ui/AreaChart";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";
import { api, type DeploymentLog, type Project, type TelemetryMetric } from "@/lib/api";

const timeRanges = ["1h", "6h", "24h", "7d", "30d"];

export default function MonitoringPage() {
  const { hasDeployed } = useNotifications();
  const [timeRange, setTimeRange] = useState("24h");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [metrics, setMetrics] = useState<TelemetryMetric | null>(null);
  const [latestLogs, setLatestLogs] = useState<DeploymentLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [metricsLoading, setMetricsLoading] = useState(false);

  useEffect(() => {
    if (!hasDeployed) return;
    async function loadProjects() {
      setLoading(true);
      try {
        const data = await api.getProjects();
        setProjects(data);
        if (data.length > 0) setSelectedProjectId(data[0].id);
      } catch {
        setProjects([]);
      } finally {
        setLoading(false);
      }
    }
    loadProjects();
  }, [hasDeployed]);

  useEffect(() => {
    if (!selectedProjectId) return;
    async function loadTelemetry() {
      setMetricsLoading(true);
      try {
        const data = await api.getProjectMetrics(selectedProjectId);
        setMetrics(data);

        const deployments = await api.getDeployments(20);
        const projectDeployment = deployments.find((deployment) => deployment.project_id === selectedProjectId);
        if (projectDeployment) {
          const detail = await api.getDeployment(projectDeployment.id);
          setLatestLogs(detail.logs.slice(-15));
        } else {
          setLatestLogs([]);
        }
      } catch {
        setMetrics(null);
        setLatestLogs([]);
      } finally {
        setMetricsLoading(false);
      }
    }
    loadTelemetry();
  }, [selectedProjectId]);

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Monitoring & Observability" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading health dashboard...</p>
      </div>
    );
  }

  const hasMetricPoints = Boolean(metrics && (metrics.cpu.length > 0 || metrics.memory.length > 0));
  const errVal = metrics?.error_rate && metrics.error_rate !== "No data" ? parseFloat(metrics.error_rate) : null;
  const healthStatus = errVal == null
    ? { label: "No telemetry", color: "text-foreground-muted" }
    : errVal > 5
      ? { label: "Degraded", color: "text-danger" }
      : errVal > 1
        ? { label: "Warning", color: "text-warning" }
        : { label: "Healthy", color: "text-success" };

  const topMetrics = [
    { icon: Clock, label: "Response Time", value: metrics?.response_time || "No data", color: "text-primary" },
    { icon: AlertTriangle, label: "Error Rate", value: metrics?.error_rate || "No data", color: errVal && errVal > 1 ? "text-warning" : "text-success" },
    { icon: Activity, label: "Total Requests", value: metrics?.request_count ? metrics.request_count.toLocaleString() : "0", color: "text-info" },
    { icon: Wifi, label: "Uptime", value: metrics?.uptime || "No data", color: "text-foreground-muted" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Application Health</h2>
            <p className="text-[10px] text-foreground-muted">Shows database-backed telemetry and deployment logs only.</p>
          </div>
        </div>

        <div className="flex items-center gap-3 self-end sm:self-auto flex-wrap">
          <select
            value={selectedProjectId}
            onChange={(event) => setSelectedProjectId(event.target.value)}
            className="bg-background-secondary border border-border text-xs rounded-lg px-3 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-semibold max-w-[240px]"
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.full_name}</option>
            ))}
          </select>

          <div className="flex gap-1 bg-background-secondary p-0.5 rounded-lg border border-border">
            {timeRanges.map((range) => (
              <button key={range} onClick={() => setTimeRange(range)} className={`px-2.5 py-1 rounded-md text-[10px] font-semibold transition-colors ${timeRange === range ? "bg-card text-foreground shadow-sm" : "text-foreground-muted hover:text-foreground"}`}>
                {range}
              </button>
            ))}
          </div>
        </div>
      </div>

      {metricsLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 bg-card border border-border rounded-xl shadow-sm">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-xs text-foreground-muted">Loading metrics...</p>
        </div>
      ) : (
        <>
          {!hasMetricPoints && (
            <div className="bg-card border border-border rounded-xl p-8 text-center shadow-sm">
              <AlertTriangle className="w-10 h-10 mx-auto text-foreground-muted/40 mb-3" />
              <h3 className="text-sm font-bold text-foreground mb-1">No telemetry recorded</h3>
              <p className="text-xs text-foreground-muted">Launch a deployment with metrics collection enabled to populate charts and health summaries.</p>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-5 shadow-sm text-center">
              <Activity size={20} className={`${healthStatus.color} mx-auto mb-2`} />
              <p className="text-xl font-bold text-foreground">{healthStatus.label}</p>
              <p className="text-[10px] text-foreground-muted uppercase tracking-wider font-bold mt-0.5">Health</p>
            </motion.div>
            {topMetrics.map((metric, index) => (
              <motion.div key={metric.label} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: (index + 1) * 0.04 }} className="bg-card border border-border rounded-xl p-5 shadow-sm text-center">
                <metric.icon size={20} className={`${metric.color} mx-auto mb-2`} />
                <p className="text-xl font-bold text-foreground">{metric.value}</p>
                <p className="text-[10px] text-foreground-muted uppercase tracking-wider font-bold mt-0.5">{metric.label}</p>
              </motion.div>
            ))}
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4"><Cpu size={16} className="text-primary" /><h3 className="font-bold text-foreground text-sm">CPU Usage (%)</h3></div>
              {metrics && metrics.cpu.length > 0 ? (
                <AreaChart data={metrics.cpu} color="#3b82f6" height={180} />
              ) : (
                <div className="h-[180px] flex items-center justify-center text-xs text-foreground-muted">No CPU data points found</div>
              )}
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4"><HardDrive size={16} className="text-accent" /><h3 className="font-bold text-foreground text-sm">Memory Usage (%)</h3></div>
              {metrics && metrics.memory.length > 0 ? (
                <AreaChart data={metrics.memory} color="#8b5cf6" height={180} />
              ) : (
                <div className="h-[180px] flex items-center justify-center text-xs text-foreground-muted">No memory data points found</div>
              )}
            </motion.div>
          </div>

          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-border bg-background-secondary/40 flex items-center justify-between">
              <span className="text-xs font-bold text-foreground">Console Log History</span>
              <span className="text-[9px] uppercase font-bold text-foreground-muted">Last 15 database log records</span>
            </div>
            <div className="p-4 font-mono text-[11px] leading-6 bg-zinc-950 text-zinc-300 max-h-[250px] overflow-y-auto no-scrollbar">
              {latestLogs.length > 0 ? (
                latestLogs.map((log, index) => (
                  <p key={index} className={log.level === "ERROR" ? "text-danger" : log.level === "WARN" ? "text-warning" : "text-zinc-300"}>
                    <span className="text-zinc-500 mr-2">[{log.timestamp ? log.timestamp.split("T")[1]?.slice(0, 8) : ""}]</span>
                    <span className="text-primary-light mr-1">[{log.level}]</span>
                    {log.message}
                  </p>
                ))
              ) : (
                <p className="text-zinc-500">No logs found for this project. Launch a deployment to write log lines to the database.</p>
              )}
            </div>
          </motion.div>
        </>
      )}
    </div>
  );
}
