"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Activity, Clock, AlertTriangle, Wifi, Cpu, HardDrive, Loader2, Database } from "lucide-react";
import { AreaChart } from "@/components/ui/AreaChart";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";
import { api, type Project, type TelemetryMetric, type DeploymentLog } from "@/lib/api";

const timeRanges = ["1h", "6h", "24h", "7d", "30d"];

const tracingSpans = [
  { id: "span-1", service: "api-gateway", operation: "GET /api/deployments", duration: 47, start: 0, color: "#3b82f6" },
  { id: "span-2", service: "auth-service", operation: "validateToken", duration: 8, start: 2, color: "#8b5cf6" },
  { id: "span-3", service: "api-gateway", operation: "fetchDeployments", duration: 28, start: 12, color: "#3b82f6" },
  { id: "span-4", service: "database", operation: "SELECT deployments", duration: 15, start: 14, color: "#06b6d4" },
  { id: "span-5", service: "cache-redis", operation: "GET cache:deployments", duration: 2, start: 13, color: "#f59e0b" },
  { id: "span-6", service: "api-gateway", operation: "serialize response", duration: 5, start: 40, color: "#3b82f6" },
];

export default function MonitoringPage() {
  const { hasDeployed } = useNotifications();
  const [timeRange, setTimeRange] = useState("24h");
  
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [metrics, setMetrics] = useState<TelemetryMetric | null>(null);
  const [latestLogs, setLatestLogs] = useState<DeploymentLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [metricsLoading, setMetricsLoading] = useState(false);

  useEffect(() => {
    if (!hasDeployed) return;

    async function loadProjects() {
      try {
        const projs = await api.getProjects();
        setProjects(projs);
        if (projs.length > 0) {
          setSelectedProjectId(projs[0].id);
        }
      } catch (err) {
        console.error("Failed to load projects", err);
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
        // Fetch project metrics
        const data = await api.getProjectMetrics(selectedProjectId);
        setMetrics(data);

        // Fetch latest deployment logs for live log container simulation
        const deps = await api.getDeployments(20);
        const projDep = deps.find(d => d.project_id === selectedProjectId);
        if (projDep) {
          const detail = await api.getDeployment(projDep.id);
          setLatestLogs(detail.logs.slice(-15)); // Get last 15 lines
        } else {
          setLatestLogs([]);
        }
      } catch (err) {
        console.error("Failed to load telemetry", err);
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
        <p className="text-foreground-muted text-sm font-medium">Loading telemetry dashboard...</p>
      </div>
    );
  }

  const selectedProject = projects.find(p => p.id === selectedProjectId);

  const topMetrics = [
    { icon: Clock, label: "Avg Response", value: metrics?.response_time || "45ms", color: "text-primary" },
    { icon: AlertTriangle, label: "Error Rate", value: metrics?.error_rate || "0.0%", color: "text-success" },
    { icon: Activity, label: "Total Requests", value: metrics?.request_count ? metrics.request_count.toLocaleString() : "1,200", color: "text-info" },
    { icon: Wifi, label: "Uptime", value: metrics?.uptime || "99.99%", color: "text-success" },
  ];

  const pods = selectedProject ? [
    { id: "pod-1", name: `${selectedProject.name}-prod-a1b2c`, status: selectedProject.status === "failed" ? "failed" : "healthy", cpu: 12, memory: 65 },
    { id: "pod-2", name: `${selectedProject.name}-prod-d3e4f`, status: selectedProject.status === "failed" ? "failed" : "healthy", cpu: 18, memory: 68 },
    { id: "pod-3", name: `${selectedProject.name}-prod-g5h6i`, status: selectedProject.status === "failed" ? "failed" : "healthy", cpu: 5, memory: 60 },
  ] : [];

  return (
    <div className="space-y-6">
      {/* Header with Project Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Project Telemetry Source</h2>
            <p className="text-[10px] text-foreground-muted">Select connected deployment to view real-time logs and metrics.</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3 self-end sm:self-auto">
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="bg-background-secondary border border-border text-xs rounded-lg px-3 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-semibold max-w-[200px]"
          >
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.full_name}</option>
            ))}
          </select>

          <div className="flex gap-1 bg-background-secondary p-0.5 rounded-lg border border-border">
            {timeRanges.map(t => (
              <button key={t} onClick={() => setTimeRange(t)} className={`px-2.5 py-1 rounded-md text-[10px] font-semibold transition-colors ${timeRange === t ? "bg-card text-foreground shadow-sm" : "text-foreground-muted hover:text-foreground"}`}>{t}</button>
            ))}
          </div>
        </div>
      </div>

      {metricsLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 bg-card border border-border rounded-xl shadow-sm">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-xs text-foreground-muted">Fetching project metrics from database...</p>
        </div>
      ) : (
        <>
          {/* Top metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {topMetrics.map((m, i) => (
              <motion.div key={m.label} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="bg-card border border-border rounded-xl p-5 shadow-sm">
                <m.icon size={18} className={`${m.color} mb-2`} />
                <p className="text-2xl font-bold text-foreground">{m.value}</p>
                <p className="text-[10px] text-foreground-muted uppercase tracking-wider font-bold mt-0.5">{m.label}</p>
              </motion.div>
            ))}
          </div>

          {/* Charts */}
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4"><Cpu size={16} className="text-primary" /><h3 className="font-bold text-foreground text-sm">CPU Usage (%)</h3></div>
              {metrics && metrics.cpu.length > 0 ? (
                <AreaChart data={metrics.cpu} color="#3b82f6" height={180} />
              ) : (
                <div className="h-[180px] flex items-center justify-center text-xs text-foreground-muted">No CPU data points found</div>
              )}
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4"><HardDrive size={16} className="text-accent" /><h3 className="font-bold text-foreground text-sm">Memory Usage (%)</h3></div>
              {metrics && metrics.memory.length > 0 ? (
                <AreaChart data={metrics.memory} color="#8b5cf6" height={180} />
              ) : (
                <div className="h-[180px] flex items-center justify-center text-xs text-foreground-muted">No memory data points found</div>
              )}
            </motion.div>
          </div>

          {/* Latency + Pod Health */}
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.14 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <h3 className="font-bold text-foreground text-sm mb-4">Latency Percentiles</h3>
              <div className="space-y-4">
                {[{ label: "P50", value: metrics?.response_time ? parseInt(metrics.response_time) : 23, max: 300 },
                  { label: "P95", value: metrics?.response_time ? Math.round(parseInt(metrics.response_time) * 1.8) : 89, max: 300 },
                  { label: "P99", value: metrics?.response_time ? Math.round(parseInt(metrics.response_time) * 4.5) : 234, max: 300 }].map(p => (
                  <div key={p.label}>
                    <div className="flex justify-between text-xs mb-1"><span className="text-foreground-muted font-semibold">{p.label}</span><span className="text-foreground font-bold">{p.value}ms</span></div>
                    <div className="h-2 bg-background-secondary rounded-full overflow-hidden border border-border/40">
                      <motion.div initial={{ width: 0 }} animate={{ width: `${(p.value / p.max) * 100}%` }} transition={{ duration: 1 }}
                        className={`h-full rounded-full ${p.value < 50 ? "bg-success" : p.value < 150 ? "bg-warning" : "bg-danger"}`} />
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
            
            <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <h3 className="font-bold text-foreground text-sm mb-4">Pod Health</h3>
              <div className="grid grid-cols-3 gap-3">
                {pods.map((pod, i) => (
                  <motion.div key={pod.id} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.2 + i * 0.04 }}
                    className="flex flex-col items-center gap-2 p-3 rounded-lg border border-border bg-background-secondary/30 group cursor-pointer hover:bg-card-hover/40 transition-colors" title={`${pod.name} — CPU: ${pod.cpu}% MEM: ${pod.memory}%`}>
                    <div className={`w-8 h-8 rounded-full ${pod.status === "healthy" ? "bg-success/15 border border-success/30" : "bg-danger/15 border border-danger/30"} flex items-center justify-center`}>
                      <div className={`w-2.5 h-2.5 rounded-full ${pod.status === "healthy" ? "bg-success" : "bg-danger"}`} />
                    </div>
                    <span className="text-[10px] font-mono text-foreground font-semibold truncate max-w-[90px]">{pod.name.split("-").slice(-2).join("-")}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* Distributed Tracing */}
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
            <h3 className="font-bold text-foreground text-sm mb-4">Distributed Tracing — GET /api/deployments</h3>
            <div className="space-y-3">
              {tracingSpans.map((span, i) => (
                <motion.div key={span.id} initial={{ opacity: 0, scaleX: 0 }} animate={{ opacity: 1, scaleX: 1 }} transition={{ delay: 0.2 + i * 0.05, duration: 0.4 }}
                  className="flex items-center gap-3" style={{ transformOrigin: "left" }}>
                  <span className="text-[11px] text-foreground-muted w-28 text-right truncate font-medium">{span.service}</span>
                  <div className="flex-1 h-6 relative">
                    <div className="absolute h-full rounded" style={{ left: `${(span.start / 47) * 100}%`, width: `${Math.max((span.duration / 47) * 100, 4)}%`, backgroundColor: span.color + "25", border: `1px solid ${span.color}45` }}>
                      <span className="text-[9px] text-foreground font-semibold px-2 leading-6 whitespace-nowrap">{span.operation}</span>
                    </div>
                  </div>
                  <span className="text-[11px] text-foreground-muted w-14 text-right font-mono font-bold">{span.duration}ms</span>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Live Logs */}
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-border bg-background-secondary/40 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" />
                <span className="text-xs font-bold text-foreground">Console Log History</span>
              </div>
              <span className="text-[9px] uppercase font-bold text-foreground-muted">Last 15 database log records</span>
            </div>
            <div className="p-4 font-mono text-[11px] leading-6 bg-zinc-950 text-zinc-300 max-h-[250px] overflow-y-auto no-scrollbar">
              {latestLogs.length > 0 ? (
                latestLogs.map((log, idx) => (
                  <p key={idx} className={log.level === "ERROR" ? "text-danger" : log.level === "WARN" ? "text-warning" : "text-zinc-300"}>
                    <span className="text-zinc-500 mr-2">[{log.timestamp ? log.timestamp.split("T")[1].slice(0, 8) : ""}]</span>
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
