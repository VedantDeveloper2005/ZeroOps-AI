"use client";

import { motion } from "framer-motion";
import { Activity, Clock, AlertTriangle, Wifi, Cpu, HardDrive } from "lucide-react";
import { cpuMetrics, memoryMetrics, tracingSpans, logEntries, infraNodes } from "@/lib/mock-data";
import { AreaChart } from "@/components/ui/AreaChart";
import { useState } from "react";

const timeRanges = ["1h", "6h", "24h", "7d", "30d"];
const topMetrics = [
  { icon: Clock, label: "Avg Response", value: "47ms", color: "text-primary" },
  { icon: AlertTriangle, label: "Error Rate", value: "0.2%", color: "text-success" },
  { icon: Activity, label: "Requests/s", value: "1.2K", color: "text-info" },
  { icon: Wifi, label: "Uptime", value: "99.99%", color: "text-success" },
];

const pods = infraNodes.filter(n => n.type === "pod");

export default function MonitoringPage() {
  const [timeRange, setTimeRange] = useState("24h");
  const levelColor: Record<string, string> = { INFO: "bg-primary/10 text-primary", WARN: "bg-warning/10 text-warning", ERROR: "bg-danger/10 text-danger", DEBUG: "bg-foreground-muted/10 text-foreground-muted" };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-bold">Monitoring</h1><p className="text-foreground-muted text-sm mt-1">Real-time observability, tracing, and service health</p></div>
        <div className="flex gap-1">
          {timeRanges.map(t => (
            <button key={t} onClick={() => setTimeRange(t)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${timeRange === t ? "bg-primary-subtle text-primary" : "text-foreground-muted hover:text-foreground hover:bg-card"}`}>{t}</button>
          ))}
        </div>
      </div>

      {/* Top metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {topMetrics.map((m, i) => (
          <motion.div key={m.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }} className="glass rounded-xl p-5">
            <m.icon size={18} className={`${m.color} mb-2`} />
            <p className="text-2xl font-bold text-foreground">{m.value}</p>
            <p className="text-xs text-foreground-muted">{m.label}</p>
          </motion.div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4"><Cpu size={16} className="text-primary" /><h3 className="font-semibold">CPU Usage</h3></div>
          <AreaChart data={cpuMetrics} color="#3b82f6" height={180} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4"><HardDrive size={16} className="text-accent" /><h3 className="font-semibold">Memory Usage</h3></div>
          <AreaChart data={memoryMetrics} color="#8b5cf6" height={180} />
        </motion.div>
      </div>

      {/* Latency + Pod Health */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4">Latency Percentiles</h3>
          <div className="space-y-4">
            {[{ label: "P50", value: 23, max: 300 }, { label: "P95", value: 89, max: 300 }, { label: "P99", value: 234, max: 300 }].map(p => (
              <div key={p.label}>
                <div className="flex justify-between text-sm mb-1"><span className="text-foreground-muted">{p.label}</span><span className="text-foreground font-medium">{p.value}ms</span></div>
                <div className="h-2 bg-card rounded-full overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(p.value / p.max) * 100}%` }} transition={{ duration: 1 }}
                    className={`h-full rounded-full ${p.value < 50 ? "bg-success" : p.value < 100 ? "bg-warning" : "bg-danger"}`} />
                </div>
              </div>
            ))}
          </div>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4">Pod Health</h3>
          <div className="grid grid-cols-5 gap-3">
            {pods.map((pod, i) => (
              <motion.div key={pod.id} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.5 + i * 0.05 }}
                className="flex flex-col items-center gap-1 group cursor-pointer" title={`${pod.name} — CPU: ${pod.cpu}% MEM: ${pod.memory}%`}>
                <div className={`w-8 h-8 rounded-full ${pod.status === "healthy" ? "bg-success/20 border border-success/30" : pod.status === "warning" ? "bg-warning/20 border border-warning/30" : "bg-danger/20 border border-danger/30"} flex items-center justify-center`}>
                  <div className={`w-3 h-3 rounded-full ${pod.status === "healthy" ? "bg-success" : pod.status === "warning" ? "bg-warning" : "bg-danger"}`} />
                </div>
                <span className="text-[9px] text-foreground-muted truncate max-w-[60px]">{pod.name.split("-").slice(0, 2).join("-")}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Distributed Tracing */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4">Distributed Tracing — GET /api/deployments</h3>
        <div className="space-y-2">
          {tracingSpans.map((span, i) => (
            <motion.div key={span.id} initial={{ opacity: 0, scaleX: 0 }} animate={{ opacity: 1, scaleX: 1 }} transition={{ delay: 0.5 + i * 0.1, duration: 0.4 }}
              className="flex items-center gap-3" style={{ transformOrigin: "left" }}>
              <span className="text-xs text-foreground-muted w-28 text-right truncate">{span.service}</span>
              <div className="flex-1 h-6 relative">
                <div className="absolute h-full rounded" style={{ left: `${(span.start / 47) * 100}%`, width: `${Math.max((span.duration / 47) * 100, 4)}%`, backgroundColor: span.color + "40", border: `1px solid ${span.color}60` }}>
                  <span className="text-[10px] text-foreground px-1 leading-6 whitespace-nowrap">{span.operation}</span>
                </div>
              </div>
              <span className="text-xs text-foreground-muted w-14 text-right">{span.duration}ms</span>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Live Logs */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="glass rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse" /><span className="text-sm font-medium">Live Log Stream</span>
        </div>
        <div className="p-4 font-mono text-xs leading-6 bg-black/20 max-h-[200px] overflow-y-auto no-scrollbar">
          {logEntries.slice(0, 5).map(log => (
            <div key={log.id} className="flex gap-3">
              <span className="text-foreground-muted w-24 flex-shrink-0">{log.timestamp}</span>
              <span className={`w-12 text-center rounded text-[10px] font-medium ${levelColor[log.level]}`}>{log.level}</span>
              <span className="text-foreground-muted w-36 truncate flex-shrink-0">{log.pod}</span>
              <span className="text-foreground">{log.message}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
