"use client";

import { motion } from "framer-motion";
import { ArrowUp, ArrowDown, Cpu, HardDrive, Brain, Sliders, Loader2, Database } from "lucide-react";
import { AreaChart } from "@/components/ui/AreaChart";
import { useCallback, useEffect, useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";
import { api, type Project } from "@/lib/api";

interface MetricPoint {
  time: string;
  value: number;
}

function generateMetricData(points: number, min: number, max: number, trend: "up" | "down" | "stable" = "stable"): MetricPoint[] {
  const data: MetricPoint[] = [];
  let current = (min + max) / 2;
  const pseudoRandom = (seed: number) => {
    const x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
  };
  for (let i = 0; i < points; i++) {
    const seed = i + min + max + (trend === "up" ? 1 : trend === "down" ? 2 : 3);
    const noise = (pseudoRandom(seed) - 0.5) * (max - min) * 0.3;
    const trendBias = trend === "up" ? 0.5 : trend === "down" ? -0.5 : 0;
    current = Math.max(min, Math.min(max, current + noise + trendBias));
    const hour = Math.floor(i / (points / 24));
    data.push({
      time: `${String(hour).padStart(2, "0")}:${String((i * 60 / points * 24) % 60 | 0).padStart(2, "0")}`,
      value: Math.round(current * 10) / 10,
    });
  }
  return data;
}

const trafficMetrics = generateMetricData(48, 200, 1400, "up");

const scalingHistory = [
  { time: "09:00", event: "Scale Up", service: "web-app", from: 2, to: 4, trigger: "CPU > 75%" },
  { time: "08:30", event: "Scale Up", service: "api-gateway", from: 3, to: 5, trigger: "AI Prediction" },
  { time: "07:45", event: "Scale Down", service: "ml-pipeline", from: 4, to: 2, trigger: "Low Traffic" },
  { time: "06:00", event: "Scale Up", service: "payments-service", from: 2, to: 3, trigger: "Queue Length" },
  { time: "03:00", event: "Scale Down", service: "web-app", from: 4, to: 2, trigger: "Off-Peak" },
];

export default function AutoscalingPage() {
  const { addToast, addNotification, hasDeployed } = useNotifications();

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Autoscaling & Replicas" />
      </div>
    );
  }

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [hpaLoading, setHpaLoading] = useState(false);
  const [hpa, setHpa] = useState({
    minReplicas: 2,
    maxReplicas: 10,
    currentReplicas: 4,
    targetCPU: 70,
    currentCPU: 45,
    targetMemory: 80,
    currentMemory: 60
  });
  const [replicas, setReplicas] = useState(hpa.currentReplicas);
  const [isScaling, setIsScaling] = useState(false);

  useEffect(() => {
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
  }, []);

  const fetchHPAStatus = useCallback(() => {
    if (!selectedProjectId) return;
    setHpaLoading(true);
    api.getAutoscalingStatus(selectedProjectId)
      .then((data: any) => {
        setHpa({
          minReplicas: data.minReplicas ?? 2,
          maxReplicas: data.maxReplicas ?? 10,
          currentReplicas: data.currentReplicas ?? 4,
          targetCPU: data.targetCPU ?? 70,
          currentCPU: data.currentCPU ?? 45,
          targetMemory: data.targetMemory ?? 80,
          currentMemory: data.currentMemory ?? 60
        });
        setReplicas((prev) => (isScaling ? prev : data.currentReplicas ?? 4));
      })
      .catch((err) => console.error("Failed to load HPA status:", err))
      .finally(() => setHpaLoading(false));
  }, [selectedProjectId, isScaling]);

  useEffect(() => {
    fetchHPAStatus();
    const interval = setInterval(fetchHPAStatus, 60000); // refresh every minute
    return () => clearInterval(interval);
  }, [fetchHPAStatus]);

  const handleApplyManualScale = async () => {
    if (!selectedProjectId) return;
    setIsScaling(true);
    addToast(`Adjusting deployment scale to ${replicas} replicas...`, "info");
    try {
      await api.configureAutoscaling({
        projectId: selectedProjectId,
        minReplicas: replicas,
        maxReplicas: replicas,
        cpuTarget: hpa.targetCPU
      });

      addToast(`Successfully adjusted replica target: ${replicas} pods.`, "success");
      addNotification({
        title: "Manual Scaling Complete",
        message: `Scaled ${appName} replicas to ${replicas}.`,
        type: "success",
        category: "scaling",
        action_url: "/dashboard/autoscaling"
      });
      fetchHPAStatus();
    } catch (err) {
      console.error(err);
      addToast("Failed to execute scaling command.", "error");
    } finally {
      setIsScaling(false);
    }
  };

  const handleApplyRecommendation = async (text: string, min: number, max: number, cpu: number) => {
    if (!selectedProjectId) return;
    addToast(`Applying AI Autoscale Tuning...`, "info");
    try {
      await api.configureAutoscaling({ 
        projectId: selectedProjectId, 
        minReplicas: min, 
        maxReplicas: max, 
        cpuTarget: cpu 
      });

      addToast("AI Autoscale recommendation successfully applied.", "success");
      addNotification({
        title: "AI Autoscale Tuned",
        message: `Applied autoscale recommendation: ${text}`,
        type: "success",
        category: "scaling",
        action_url: "/dashboard/autoscaling"
      });
      fetchHPAStatus();
    } catch (err) {
      console.error(err);
      addToast("Failed to apply recommendation.", "error");
    }
  };

  const selectedProject = projects.find(p => p.id === selectedProjectId);
  const appName = selectedProject?.name || "web-app";

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading autoscaling configurations...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header and selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Autoscaling Context</h2>
            <p className="text-[10px] text-foreground-muted">Select active project to tune scaling parameters and configure Kubernetes HPA limits.</p>
          </div>
        </div>
        
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="bg-background-secondary border border-border text-xs rounded-lg px-3 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-semibold max-w-[200px]"
        >
          {projects.map(p => (
            <option key={p.id} value={p.id}>{p.full_name}</option>
          ))}
        </select>
      </div>

      {hpaLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 bg-card border border-border rounded-xl shadow-sm">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-xs text-foreground-muted">Retrieving HPA status from Kubernetes...</p>
        </div>
      ) : (
        <>
          {/* Current Pod Count + HPA */}
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-6 text-center shadow-sm flex flex-col justify-between min-h-[220px]">
              <div>
                <p className="text-[10px] uppercase font-bold text-foreground-muted tracking-wider">Current Replicas</p>
                <p className="text-6xl font-bold text-primary my-4">{hpa.currentReplicas}</p>
              </div>
              <div>
                <div className="flex items-center justify-center gap-2.5 mb-3">
                  {Array.from({ length: hpa.maxReplicas }).map((_, i) => (
                    <motion.div
                      key={i}
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ delay: i * 0.05 }}
                      className={`w-3 h-3 rounded-full ${i < hpa.currentReplicas ? "bg-primary" : "bg-background-secondary border border-border"}`}
                    />
                  ))}
                </div>
                <p className="text-xs font-semibold text-foreground-muted">Min: {hpa.minReplicas} • Max: {hpa.maxReplicas}</p>
              </div>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-card border border-border rounded-xl p-6 space-y-4 shadow-sm">
              <h3 className="text-sm font-bold text-foreground mb-2">HPA Thresholds</h3>
              {[
                { label: "CPU Utilization", target: hpa.targetCPU, current: hpa.currentCPU, icon: Cpu, color: "bg-primary" },
                { label: "Memory Usage", target: hpa.targetMemory, current: hpa.currentMemory, icon: HardDrive, color: "bg-accent" },
              ].map((m) => (
                <div key={m.label}>
                  <div className="flex items-center justify-between text-xs font-semibold mb-1.5">
                    <span className="flex items-center gap-2 text-foreground-muted">
                      <m.icon size={14} />
                      {m.label}
                    </span>
                    <span className="text-foreground">{m.current}% / {m.target}%</span>
                  </div>
                  <div className="h-2 bg-background-secondary rounded-full overflow-hidden relative border border-border/40">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${m.current}%` }}
                      transition={{ duration: 1 }}
                      className={`h-full rounded-full ${m.color}`}
                    />
                    <div className="absolute top-0 h-full w-0.5 bg-foreground/30" style={{ left: `${m.target}%` }} />
                  </div>
                </div>
              ))}
            </motion.div>
          </div>

          {/* Traffic Prediction */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
            <h3 className="text-sm font-bold text-foreground mb-4 font-bold">Traffic Prediction & Scaling Capacity</h3>
            <AreaChart data={trafficMetrics} color="#3b82f6" height={200} />
          </motion.div>

          {/* Scaling History + Manual */}
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
              <h3 className="text-sm font-bold text-foreground mb-4 font-bold">Scaling Events</h3>
              <div className="space-y-3">
                {scalingHistory.map((event, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.4 + i * 0.08 }}
                    className="flex items-center gap-3 p-3 rounded-lg bg-background-secondary border border-border/50"
                  >
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${event.event.includes("Up") ? "bg-primary/10" : "bg-accent/10"}`}>
                      {event.event.includes("Up") ? <ArrowUp size={14} className="text-primary" /> : <ArrowDown size={14} className="text-accent" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-foreground truncate">{appName}: {event.from}→{event.to} pods</p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">{event.trigger}</p>
                    </div>
                    <span className="text-[10px] font-semibold text-foreground-muted font-mono">{event.time}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="space-y-4">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
                <h3 className="text-sm font-bold text-foreground mb-4 flex items-center gap-2">
                  <Sliders size={16} />
                  Manual Replica Override
                </h3>
                <div className="flex items-center gap-4 mb-5">
                  <input
                    type="range"
                    min={hpa.minReplicas}
                    max={hpa.maxReplicas}
                    value={replicas}
                    onChange={(e) => setReplicas(+e.target.value)}
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
              </div>

              <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
                <h3 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                  <Brain size={16} className="text-primary" />
                  AI Recommendations
                </h3>
                <div className="space-y-3">
                  <div className="p-3 rounded-lg bg-background-secondary border border-border/50 flex flex-col justify-between">
                    <p className="text-xs font-semibold text-foreground leading-relaxed">Increase max replicas to 15 during peak traffic spikes</p>
                    <div className="flex justify-end mt-2">
                      <button
                        onClick={() => handleApplyRecommendation("Increase max replicas to 15 during peak traffic spikes", hpa.minReplicas, 15, hpa.targetCPU)}
                        className="text-[10px] font-bold text-primary hover:underline cursor-pointer"
                      >
                        Apply Recommendation →
                      </button>
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-background-secondary border border-border/50 flex flex-col justify-between">
                    <p className="text-xs font-semibold text-foreground leading-relaxed">Optimize predictive scaling: target 60% CPU utilization ceiling</p>
                    <div className="flex justify-end mt-2">
                      <button
                        onClick={() => handleApplyRecommendation("Optimize predictive scaling to 60% CPU target", hpa.minReplicas, hpa.maxReplicas, 60)}
                        className="text-[10px] font-bold text-primary hover:underline cursor-pointer"
                      >
                        Apply Recommendation →
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </div>
  );
}
