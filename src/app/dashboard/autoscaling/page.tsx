"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, ArrowUp, ArrowDown, Cpu, HardDrive, Brain, Sliders } from "lucide-react";
import { scalingHistory, trafficMetrics } from "@/lib/mock-data";
import { AreaChart } from "@/components/ui/AreaChart";
import { useState, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";

export default function AutoscalingPage() {
  const { addToast, addNotification } = useNotifications();
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

  const fetchHPAStatus = () => {
    fetch("/api/autoscaling/web-frontend")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load HPA");
        return res.json();
      })
      .then((data) => {
        setHpa(data);
        // Sync replicas slider to current replicas initially
        setReplicas((prev) => (isScaling ? prev : data.currentReplicas));
      })
      .catch((err) => console.error("Failed to load HPA status:", err));
  };

  useEffect(() => {
    fetchHPAStatus();
    const interval = setInterval(fetchHPAStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleApplyManualScale = async () => {
    setIsScaling(true);
    addToast(`Adjusting deployment scale to ${replicas} replicas...`, "info");
    try {
      const res = await fetch("/api/deployments/scale", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "web-frontend", replicas }),
      });
      if (!res.ok) throw new Error("Failed to scale deployment");

      addToast(`Successfully adjusted replica target: ${replicas} pods.`, "success");
      addNotification({
        title: "Manual Scaling Complete",
        message: `Scaled web-frontend replicas: ${hpa.currentReplicas} → ${replicas}.`,
        type: "success",
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
    addToast(`Applying AI Autoscale Tuning...`, "info");
    try {
      const res = await fetch("/api/autoscaling/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId: "web-frontend", minReplicas: min, maxReplicas: max, cpuTarget: cpu }),
      });
      if (!res.ok) throw new Error("Failed");

      addToast("AI Autoscale recommendation successfully applied.", "success");
      addNotification({
        title: "AI Autoscale Tuned",
        message: `Applied autoscale recommendation: ${text}`,
        type: "success",
      });
      fetchHPAStatus();
    } catch (err) {
      console.error(err);
      addToast("Failed to apply recommendation.", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Autoscaling</h1>
        <p className="text-foreground-muted text-sm mt-1">AI-powered horizontal pod autoscaling</p>
      </div>

      {/* Current Pod Count + HPA */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6 text-center">
          <p className="text-foreground-muted text-sm mb-2">Current Replicas</p>
          <p className="text-6xl font-bold text-primary mb-4">{hpa.currentReplicas}</p>
          <div className="flex items-center justify-center gap-2">
            {Array.from({ length: hpa.maxReplicas }).map((_, i) => (
              <motion.div
                key={i}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.05 }}
                className={`w-4 h-4 rounded-full ${i < hpa.currentReplicas ? "bg-primary" : "bg-card border border-border"}`}
                style={{
                  filter: i < hpa.currentReplicas ? "drop-shadow(0 0 4px hsla(217,91%,60%,0.4))" : undefined,
                }}
              />
            ))}
          </div>
          <p className="text-xs text-foreground-muted mt-3">Min: {hpa.minReplicas} • Max: {hpa.maxReplicas}</p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-xl p-6 space-y-4">
          <h3 className="font-semibold">HPA Thresholds</h3>
          {[
            { label: "CPU", target: hpa.targetCPU, current: hpa.currentCPU, icon: Cpu, color: "#3b82f6" },
            { label: "Memory", target: hpa.targetMemory, current: hpa.currentMemory, icon: HardDrive, color: "#8b5cf6" },
          ].map((m) => (
            <div key={m.label}>
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="flex items-center gap-2 text-foreground-muted">
                  <m.icon size={14} />
                  {m.label}
                </span>
                <span className="text-foreground">{m.current}% / {m.target}%</span>
              </div>
              <div className="h-2 bg-card rounded-full overflow-hidden relative">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${m.current}%` }}
                  transition={{ duration: 1 }}
                  className="h-full rounded-full"
                  style={{ backgroundColor: m.color }}
                />
                <div className="absolute top-0 h-full w-0.5 bg-foreground/30" style={{ left: `${m.target}%` }} />
              </div>
            </div>
          ))}
        </motion.div>
      </div>

      {/* Traffic Prediction */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4">Traffic Prediction</h3>
        <AreaChart data={trafficMetrics} color="#3b82f6" height={200} />
      </motion.div>

      {/* Scaling History + Manual */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4">Scaling History</h3>
          <div className="space-y-3">
            {scalingHistory.map((event, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + i * 0.08 }}
                className="flex items-center gap-3 p-3 rounded-lg bg-card/50"
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${event.event.includes("Up") ? "bg-primary/10" : "bg-accent/10"}`}>
                  {event.event.includes("Up") ? <ArrowUp size={16} className="text-primary" /> : <ArrowDown size={16} className="text-accent" />}
                </div>
                <div className="flex-1">
                  <p className="text-sm text-foreground">{event.service}: {event.from}→{event.to} pods</p>
                  <p className="text-xs text-foreground-muted">{event.trigger}</p>
                </div>
                <span className="text-xs text-foreground-muted">{event.time}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="space-y-4">
          <div className="glass rounded-xl p-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <Sliders size={16} />
              Manual Scale
            </h3>
            <div className="flex items-center gap-4 mb-4">
              <input
                type="range"
                min={hpa.minReplicas}
                max={hpa.maxReplicas}
                value={replicas}
                onChange={(e) => setReplicas(+e.target.value)}
                className="flex-1 accent-primary"
              />
              <span className="text-2xl font-bold text-primary w-8 text-center">{replicas}</span>
            </div>
            <button
              onClick={handleApplyManualScale}
              disabled={isScaling}
              className="w-full py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover disabled:opacity-50 transition cursor-pointer"
            >
              {isScaling ? "Scaling..." : "Apply Scale"}
            </button>
          </div>

          <div className="glass rounded-xl p-6">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <Brain size={16} className="text-primary" />
              AI Recommendations
            </h3>
            <div className="space-y-3">
              <div className="p-3 rounded-lg bg-card/50">
                <p className="text-sm text-foreground">Increase max replicas to 15 during peak hours (9-11 AM)</p>
                <button
                  onClick={() => handleApplyRecommendation("Increase max replicas to 15 during peak hours", hpa.minReplicas, 15, hpa.targetCPU)}
                  className="text-xs text-primary mt-2 font-medium cursor-pointer"
                >
                  Apply →
                </button>
              </div>
              <div className="p-3 rounded-lg bg-card/50">
                <p className="text-sm text-foreground">Optimize predictive scaling for web-frontend (target 60% CPU)</p>
                <button
                  onClick={() => handleApplyRecommendation("Optimize predictive scaling to 60% CPU target", hpa.minReplicas, hpa.maxReplicas, 60)}
                  className="text-xs text-primary mt-2 font-medium cursor-pointer"
                >
                  Apply →
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

