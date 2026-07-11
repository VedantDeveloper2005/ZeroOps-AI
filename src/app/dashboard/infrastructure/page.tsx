"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Database, Loader2, Server, Zap } from "lucide-react";
import { api, type RuntimeResourceMetrics } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

export default function InfrastructurePage() {
  const { hasDeployed, projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [loading, setLoading] = useState(false);
  const [metrics, setMetrics] = useState<RuntimeResourceMetrics | null>(null);

  useEffect(() => {
    if (hasDeployed && projects.length && !selectedProjectId) setSelectedProjectId(projects[0].id);
  }, [hasDeployed, projects, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    let active = true;
    setLoading(true);
    api.getMetrics(selectedProjectId)
      .then((data) => active && setMetrics(data))
      .catch(() => active && setMetrics({ available: false, message: "Runtime metrics are not available yet." }))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [selectedProjectId]);

  if (!hasDeployed) return <LockedView featureName="Runtime signals" />;
  if (projectsLoading) {
    return <div className="flex h-[60vh] items-center justify-center gap-3 text-sm font-medium text-foreground-muted"><Loader2 className="h-6 w-6 animate-spin text-primary" />Loading runtime signals…</div>;
  }

  const project = projects.find((item) => item.id === selectedProjectId);
  const stats = [
    { label: "Project", value: project?.name || "Unknown", icon: Server, color: "text-primary" },
    { label: "CPU", value: metrics?.cpu == null ? "No data" : `${metrics.cpu}%`, icon: Activity, color: "text-info" },
    { label: "Memory", value: metrics?.memory == null ? "No data" : `${metrics.memory}%`, icon: Database, color: "text-accent" },
    { label: "Requests", value: metrics?.traffic == null ? "No data" : String(metrics.traffic), icon: Zap, color: "text-success" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-bold text-foreground">Runtime signals</h2>
          <p className="text-[10px] text-foreground-muted">Only recorded application telemetry is shown here.</p>
        </div>
        <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} className="max-w-[240px] rounded-lg border border-border bg-background-secondary px-3 py-1.5 text-xs font-semibold text-foreground outline-none focus:ring-1 focus:ring-primary">
          {projects.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-border bg-card py-20 text-xs text-foreground-muted"><Loader2 className="h-5 w-5 animate-spin text-primary" />Loading recorded metrics…</div>
      ) : !metrics?.available ? (
        <div className="rounded-xl border border-border bg-card p-10 text-center shadow-sm"><AlertTriangle className="mx-auto mb-3 h-10 w-10 text-foreground-muted/40" /><h3 className="text-sm font-bold text-foreground">No runtime data yet</h3><p className="mx-auto mt-1 max-w-md text-xs text-foreground-muted">{metrics?.message || "Deploy the application and connect telemetry to see real runtime signals."}</p></div>
      ) : (
        <div className="grid gap-4 md:grid-cols-4">
          {stats.map((stat, index) => {
            const Icon = stat.icon;
            return <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} className="rounded-xl border border-border bg-card p-5 shadow-sm"><Icon className={`${stat.color} mb-3`} size={18} /><p className="text-xl font-bold text-foreground">{stat.value}</p><p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-foreground-muted">{stat.label}</p></motion.div>;
          })}
        </div>
      )}
    </div>
  );
}
