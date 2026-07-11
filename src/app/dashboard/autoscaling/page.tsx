"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Cpu, Database, HardDrive, Loader2, Sliders } from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";
import { api, getErrorMessage, type Project } from "@/lib/api";

interface HPAStatus {
  available?: boolean;
  message?: string;
  minReplicas?: number | null;
  maxReplicas?: number | null;
  currentReplicas?: number | null;
  targetCPU?: number | null;
  currentCPU?: number | null;
  targetMemory?: number | null;
  currentMemory?: number | null;
}

export default function AutoscalingPage() {
  const { addToast, addNotification, hasDeployed, projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [loading, setLoading] = useState(false);
  const [hpaLoading, setHpaLoading] = useState(false);
  const [hpa, setHpa] = useState<HPAStatus>({});
  const [replicas, setReplicas] = useState(2);
  const [isScaling, setIsScaling] = useState(false);

  useEffect(() => {
    if (!hasDeployed || projects.length === 0) return;
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [hasDeployed, projects, selectedProjectId]);

  const fetchHPAStatus = useCallback(() => {
    if (!selectedProjectId) return;
    setHpaLoading(true);
    api.getAutoscalingStatus(selectedProjectId)
      .then((data) => {
        const next = data as HPAStatus;
        setHpa(next);
        if (typeof next.currentReplicas === "number") setReplicas(next.currentReplicas);
      })
      .catch((err) => {
        console.error("Failed to load HPA status:", err);
        setHpa({ available: false, message: "Failed to load HPA status." });
      })
      .finally(() => setHpaLoading(false));
  }, [selectedProjectId]);

  useEffect(() => {
    fetchHPAStatus();
    const interval = setInterval(fetchHPAStatus, 60000);
    return () => clearInterval(interval);
  }, [fetchHPAStatus]);

  const handleApplyManualScale = async () => {
    if (!selectedProjectId) return;
    setIsScaling(true);
    try {
      await api.configureAutoscaling({
        projectId: selectedProjectId,
        minReplicas: replicas,
        maxReplicas: replicas,
        cpuTarget: hpa.targetCPU || 80,
      });
      addToast(`Replica target updated to ${replicas}.`, "success");
      addNotification({
        title: "Manual Scaling Complete",
        message: `Updated replica target to ${replicas}.`,
        type: "success",
        category: "scaling",
        action_url: "/dashboard/autoscaling",
      });
      fetchHPAStatus();
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to execute scaling command."), "error");
    } finally {
      setIsScaling(false);
    }
  };

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Autoscaling & Replicas" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading autoscaling configuration...</p>
      </div>
    );
  }

  const hasHPA = hpa.available === true;
  const minReplicas = hpa.minReplicas ?? 1;
  const maxReplicas = hpa.maxReplicas ?? Math.max(replicas, 1);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Autoscaling Context</h2>
            <p className="text-[10px] text-foreground-muted">Reads and updates Kubernetes HPA state through the backend.</p>
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

      {hpaLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 bg-card border border-border rounded-xl shadow-sm">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-xs text-foreground-muted">Retrieving HPA status from Kubernetes...</p>
        </div>
      ) : !hasHPA ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center shadow-sm">
          <AlertTriangle className="w-10 h-10 mx-auto text-foreground-muted/40 mb-3" />
          <h3 className="text-sm font-bold text-foreground mb-1">Autoscaling data unavailable</h3>
          <p className="text-xs text-foreground-muted max-w-md mx-auto">
            {hpa.message || "No HPA is configured for this project, or the backend cannot reach Kubernetes."}
          </p>
        </div>
      ) : (
        <>
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-6 text-center shadow-sm flex flex-col justify-between min-h-[220px]">
              <div>
                <p className="text-[10px] uppercase font-bold text-foreground-muted tracking-wider">Current Replicas</p>
                <p className="text-6xl font-bold text-primary my-4">{hpa.currentReplicas ?? "N/A"}</p>
              </div>
              <p className="text-xs font-semibold text-foreground-muted">Min: {hpa.minReplicas ?? "N/A"} / Max: {hpa.maxReplicas ?? "N/A"}</p>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-card border border-border rounded-xl p-6 space-y-4 shadow-sm">
              <h3 className="text-sm font-bold text-foreground mb-2">HPA Thresholds</h3>
              {[
                { label: "CPU Utilization", target: hpa.targetCPU, current: hpa.currentCPU, icon: Cpu, color: "bg-primary" },
                { label: "Memory Usage", target: hpa.targetMemory, current: hpa.currentMemory, icon: HardDrive, color: "bg-accent" },
              ].map((metric) => (
                <div key={metric.label}>
                  <div className="flex items-center justify-between text-xs font-semibold mb-1.5">
                    <span className="flex items-center gap-2 text-foreground-muted">
                      <metric.icon size={14} />
                      {metric.label}
                    </span>
                    <span className="text-foreground">{metric.current ?? "N/A"} / {metric.target ?? "N/A"}</span>
                  </div>
                  <div className="h-2 bg-background-secondary rounded-full overflow-hidden relative border border-border/40">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(100, Math.max(0, metric.current ?? 0))}%` }}
                      transition={{ duration: 1 }}
                      className={`h-full rounded-full ${metric.color}`}
                    />
                  </div>
                </div>
              ))}
            </motion.div>
          </div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-6 shadow-sm max-w-xl">
            <h3 className="text-sm font-bold text-foreground mb-4 flex items-center gap-2">
              <Sliders size={16} />
              Manual Replica Override
            </h3>
            <div className="flex items-center gap-4 mb-5">
              <input
                type="range"
                min={minReplicas}
                max={maxReplicas}
                value={replicas}
                onChange={(event) => setReplicas(Number(event.target.value))}
                className="flex-1 h-1.5 bg-background-secondary rounded-lg appearance-none cursor-pointer accent-primary border border-border/60"
              />
              <span className="text-2xl font-bold text-primary w-8 text-center font-mono">{replicas}</span>
            </div>
            <button
              onClick={handleApplyManualScale}
              disabled={isScaling}
              className="w-full py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover disabled:opacity-50 transition cursor-pointer shadow-sm"
            >
              {isScaling ? "Applying..." : "Set Manual Scale Target"}
            </button>
          </motion.div>
        </>
      )}
    </div>
  );
}
