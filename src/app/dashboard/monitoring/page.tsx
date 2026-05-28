"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Activity, Clock, AlertTriangle, Wifi, Cpu, HardDrive } from "lucide-react";
import { AreaChart } from "@/components/ui/AreaChart";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

const timeRanges = ["1h", "6h", "24h", "7d", "30d"];
const topMetrics = [
  { icon: Clock, label: "Avg Response", value: "47ms", color: "text-primary" },
  { icon: AlertTriangle, label: "Error Rate", value: "0.2%", color: "text-success" },
  { icon: Activity, label: "Requests/s", value: "1.2K", color: "text-info" },
  { icon: Wifi, label: "Uptime", value: "99.99%", color: "text-success" },
];

function generateMetricData(points: number, min: number, max: number) {
  const data: { time: string; value: number }[] = [];
  let current = (min + max) / 2;
  for (let i = 0; i < points; i++) {
    const noise = (Math.sin(i * 0.7) * 0.5) * (max - min) * 0.3;
    current = Math.max(min, Math.min(max, current + noise));
    const hour = Math.floor(i / (points / 24));
    data.push({ time: `${String(hour).padStart(2, "0")}:${String((i * 60 / points * 24) % 60 | 0).padStart(2, "0")}`, value: Math.round(current * 10) / 10 });
  }
  return data;
}

const cpuMetrics = generateMetricData(48, 20, 85);
const memoryMetrics = generateMetricData(48, 40, 78);

const tracingSpans = [
  { id: "span-1", service: "api-gateway", operation: "GET /api/deployments", duration: 47, start: 0, color: "#3b82f6" },
  { id: "span-2", service: "auth-service", operation: "validateToken", duration: 8, start: 2, color: "#8b5cf6" },
  { id: "span-3", service: "api-gateway", operation: "fetchDeployments", duration: 28, start: 12, color: "#3b82f6" },
  { id: "span-4", service: "database", operation: "SELECT deployments", duration: 15, start: 14, color: "#06b6d4" },
  { id: "span-5", service: "cache-redis", operation: "GET cache:deployments", duration: 2, start: 13, color: "#f59e0b" },
  { id: "span-6", service: "api-gateway", operation: "serialize response", duration: 5, start: 40, color: "#3b82f6" },
];

const pods = [
  { id: "pod-1", name: "web-app-7c8d9f-a1b2c", status: "healthy", cpu: 12, memory: 65 },
  { id: "pod-2", name: "web-app-7c8d9f-d3e4f", status: "healthy", cpu: 18, memory: 68 },
  { id: "pod-3", name: "web-app-7c8d9f-g5h6i", status: "healthy", cpu: 5, memory: 60 },
];

export default function MonitoringPage() {
  const { hasDeployed } = useNotifications();
  const [timeRange, setTimeRange] = useState("24h");
  const levelColor: Record<string, string> = { INFO: "bg-primary/10 text-primary", WARN: "bg-warning/10 text-warning", ERROR: "bg-danger/10 text-danger", DEBUG: "bg-foreground-muted/10 text-foreground-muted" };

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Monitoring & Observability" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <div className="flex gap-1 bg-background-secondary p-0.5 rounded-lg border border-border">
          {timeRanges.map(t => (
            <button key={t} onClick={() => setTimeRange(t)} className={`px-3 py-1 rounded-md text-[11px] font-semibold transition-colors ${timeRange === t ? "bg-card text-foreground shadow-sm" : "text-foreground-muted hover:text-foreground"}`}>{t}</button>
          ))}
        </div>
      </div>

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
          <div className="flex items-center gap-2 mb-4"><Cpu size={16} className="text-primary" /><h3 className="font-bold text-foreground text-sm">CPU Usage</h3></div>
          <AreaChart data={cpuMetrics} color="#3b82f6" height={180} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4"><HardDrive size={16} className="text-accent" /><h3 className="font-bold text-foreground text-sm">Memory Usage</h3></div>
          <AreaChart data={memoryMetrics} color="#8b5cf6" height={180} />
        </motion.div>
      </div>

      {/* Latency + Pod Health */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.14 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="font-bold text-foreground text-sm mb-4">Latency Percentiles</h3>
          <div className="space-y-4">
            {[{ label: "P50", value: 23, max: 300 }, { label: "P95", value: 89, max: 300 }, { label: "P99", value: 234, max: 300 }].map(p => (
              <div key={p.label}>
                <div className="flex justify-between text-xs mb-1"><span className="text-foreground-muted font-semibold">{p.label}</span><span className="text-foreground font-bold">{p.value}ms</span></div>
                <div className="h-2 bg-background-secondary rounded-full overflow-hidden border border-border/40">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(p.value / p.max) * 100}%` }} transition={{ duration: 1 }}
                    className={`h-full rounded-full ${p.value < 50 ? "bg-success" : p.value < 100 ? "bg-warning" : "bg-danger"}`} />
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
        <div className="px-4 py-3 border-b border-border bg-background-secondary/40 flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" /><span className="text-xs font-bold text-foreground">Live Log Stream</span>
        </div>
        <div className="p-4 font-mono text-[11px] leading-6 bg-zinc-950 text-zinc-300 max-h-[200px] overflow-y-auto no-scrollbar">
            <p className="text-zinc-500">Waiting for live log data from active deployments...</p>
        </div>
      </motion.div>
    </div>
  );
}
