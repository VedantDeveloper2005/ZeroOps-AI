"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, AlertTriangle, Loader2, Wifi } from "lucide-react";
import { api, type Project, type TelemetryMetric } from "@/lib/api";

export default function MonitoringPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [metrics, setMetrics] = useState<TelemetryMetric | null>(null);
  const [loading, setLoading] = useState(true);
  const [metricsLoading, setMetricsLoading] = useState(false);

  useEffect(() => {
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
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    async function loadTelemetry() {
      setMetricsLoading(true);
      try {
        const data = await api.getProjectMetrics(selectedProjectId);
        setMetrics(data);
      } catch {
        setMetrics(null);
      } finally {
        setMetricsLoading(false);
      }
    }
    loadTelemetry();
  }, [selectedProjectId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading monitoring overview...</p>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="bg-card border border-border rounded-2xl p-10 text-center space-y-3">
        <AlertTriangle className="w-10 h-10 mx-auto text-foreground-muted/40" />
        <h3 className="text-sm font-bold text-foreground">No applications to monitor</h3>
        <p className="text-xs text-foreground-muted">Deploy an application to unlock health metrics.</p>
      </div>
    );
  }

  const errVal = metrics?.error_rate && metrics.error_rate !== "No data" ? parseFloat(metrics.error_rate) : null;
  const healthStatus = errVal == null
    ? { label: "No data", color: "text-foreground-muted" }
    : errVal > 5
      ? { label: "Critical", color: "text-danger" }
      : errVal > 1
        ? { label: "Warning", color: "text-warning" }
        : { label: "Healthy", color: "text-success" };

  const cards = [
    { label: "Application Health", value: healthStatus.label, color: healthStatus.color, icon: Activity },
    { label: "Response Time", value: metrics?.response_time || "—", color: "text-primary", icon: Activity },
    { label: "Availability", value: metrics?.uptime || "—", color: "text-success", icon: Wifi },
    { label: "Requests", value: metrics?.request_count ? metrics.request_count.toLocaleString() : "—", color: "text-info", icon: Activity },
    { label: "Errors", value: metrics?.error_rate || "—", color: "text-warning", icon: AlertTriangle },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div>
          <h2 className="text-sm font-bold text-foreground">Application Health</h2>
          <p className="text-[10px] text-foreground-muted">Plain-language monitoring signals.</p>
        </div>
        <select
          value={selectedProjectId}
          onChange={(event) => setSelectedProjectId(event.target.value)}
          className="bg-background-secondary border border-border text-xs rounded-lg px-3 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-semibold max-w-[240px]"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.full_name}</option>
          ))}
        </select>
      </div>

      {metricsLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 bg-card border border-border rounded-xl shadow-sm">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-xs text-foreground-muted">Loading health data...</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {cards.map((card, index) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.04 }}
              className="bg-card border border-border rounded-xl p-5 shadow-sm text-center"
            >
              <card.icon size={20} className={`${card.color} mx-auto mb-2`} />
              <p className={`text-xl font-bold ${card.color}`}>{card.value}</p>
              <p className="text-[10px] text-foreground-muted uppercase tracking-wider font-bold mt-0.5">
                {card.label}
              </p>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
