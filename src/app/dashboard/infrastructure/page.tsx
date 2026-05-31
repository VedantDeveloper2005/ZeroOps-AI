"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Box, Database, Loader2, Server } from "lucide-react";
import { api, type ClusterResourceMetrics, type Project } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

export default function InfrastructurePage() {
  const { hasDeployed } = useNotifications();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metrics, setMetrics] = useState<ClusterResourceMetrics | null>(null);

  useEffect(() => {
    if (!hasDeployed) {
      setLoading(false);
      return;
    }

    let active = true;
    async function loadProjects() {
      setLoading(true);
      try {
        const projs = await api.getProjects();
        if (!active) return;
        setProjects(projs);
        setSelectedProjectId(projs[0]?.id || "");
      } catch (err) {
        console.error("Failed to load projects", err);
        if (active) setProjects([]);
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadProjects();
    return () => {
      active = false;
    };
  }, [hasDeployed]);

  useEffect(() => {
    if (!selectedProjectId) {
      setMetrics(null);
      return;
    }

    let active = true;
    async function loadMetrics() {
      setMetricsLoading(true);
      try {
        const data = await api.getMetrics(selectedProjectId);
        if (active) setMetrics(data);
      } catch (err) {
        console.error("Failed to load infrastructure metrics", err);
        if (active) setMetrics({ available: false, message: "Infrastructure metrics endpoint is unavailable." });
      } finally {
        if (active) setMetricsLoading(false);
      }
    }

    void loadMetrics();
    return () => {
      active = false;
    };
  }, [selectedProjectId]);

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Infrastructure Topology" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading infrastructure context...</p>
      </div>
    );
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const isAvailable = metrics?.available === true;
  const podsHealthy = metrics?.podsHealthy ?? 0;
  const podsTotal = metrics?.podsTotal ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Infrastructure Metrics</h2>
            <p className="text-[10px] text-foreground-muted">Reads Kubernetes state from the backend. No synthetic topology is shown.</p>
          </div>
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
          <p className="text-xs text-foreground-muted">Querying Kubernetes metrics...</p>
        </div>
      ) : !isAvailable ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center shadow-sm">
          <AlertTriangle className="w-10 h-10 mx-auto text-foreground-muted/40 mb-3" />
          <h3 className="text-sm font-bold text-foreground mb-1">Infrastructure metrics unavailable</h3>
          <p className="text-xs text-foreground-muted max-w-md mx-auto">
            {metrics?.message || "The backend cannot reach an active Kubernetes context for this project."}
          </p>
        </div>
      ) : (
        <>
          <div className="grid md:grid-cols-4 gap-4">
            {[
              { label: "Project", value: selectedProject?.name || "Unknown", icon: Server, color: "text-primary" },
              { label: "Pods Healthy", value: `${podsHealthy}/${podsTotal}`, icon: Box, color: podsHealthy === podsTotal ? "text-success" : "text-warning" },
              { label: "Node CPU", value: metrics?.cpu == null ? "No data" : `${metrics.cpu}%`, icon: Activity, color: "text-info" },
              { label: "Node Memory", value: metrics?.memory == null ? "No data" : `${metrics.memory}%`, icon: Database, color: "text-accent" },
            ].map((stat, index) => {
              const Icon = stat.icon;
              return (
                <motion.div
                  key={stat.label}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.04 }}
                  className="bg-card border border-border rounded-xl p-5 shadow-sm"
                >
                  <Icon size={18} className={`${stat.color} mb-3`} />
                  <p className="text-xl font-bold text-foreground">{stat.value}</p>
                  <p className="text-[10px] text-foreground-muted uppercase tracking-wider font-bold mt-1">{stat.label}</p>
                </motion.div>
              );
            })}
          </div>

          <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
            <h3 className="text-sm font-bold text-foreground mb-2">Topology View</h3>
            <p className="text-xs text-foreground-muted">
              The backend currently exposes aggregate Kubernetes metrics only. Detailed node, service, and pod topology will appear here after a real topology endpoint is connected.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
