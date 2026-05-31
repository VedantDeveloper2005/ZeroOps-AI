"use client";

import { motion } from "framer-motion";
import {
  Brain, TrendingUp, Cpu, Activity,
  ArrowRight, Sparkles, Loader2, DollarSign
} from "lucide-react";
import { useState, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { api, type Project, type HealthScore, type CostOptimization, type TelemetryMetric } from "@/lib/api";
import { AreaChart } from "@/components/ui/AreaChart";
import { GaugeChart } from "@/components/ui/GaugeChart";

export default function AIAnalysisPage() {
  const { addToast } = useNotifications();
  
  // Projects list
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingProjects, setLoadingProjects] = useState(true);

  // Dynamic metrics & score states
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [costOpt, setCostOpt] = useState<CostOptimization | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryMetric | null>(null);
  
  const [loadingData, setLoadingData] = useState(false);
  const [applyingOpt, setApplyingOpt] = useState<string | null>(null);

  // Fetch Projects list
  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await api.getProjects();
        setProjects(data);
        if (data.length > 0) {
          setSelectedProjectId(data[0].id);
        }
      } catch (err) {
        console.error("Failed to load projects", err);
      } finally {
        setLoadingProjects(false);
      }
    }
    loadProjects();
  }, []);

  // Fetch analysis data when project changes
  useEffect(() => {
    if (!selectedProjectId) return;

    async function loadAnalysisData() {
      setLoadingData(true);
      try {
        const [scoreRes, costRes, telemetryRes] = await Promise.allSettled([
          api.getHealthScore(selectedProjectId),
          api.getCostOptimization(selectedProjectId),
          api.getProjectMetrics(selectedProjectId)
        ]);

        if (scoreRes.status === "fulfilled") setHealthScore(scoreRes.value);
        if (costRes.status === "fulfilled") setCostOpt(costRes.value);
        if (telemetryRes.status === "fulfilled") setTelemetry(telemetryRes.value);
      } catch (err) {
        console.error("Failed to fetch project analysis", err);
      } finally {
        setLoadingData(false);
      }
    }

    loadAnalysisData();
  }, [selectedProjectId]);

  const handleApplyOptimization = (optTitle: string) => {
    setApplyingOpt(optTitle);
    addToast(`Automatic remediation is not connected for "${optTitle}" yet. Review the recorded recommendation before making changes.`, "warning");
    setApplyingOpt(null);
  };

  const score = healthScore?.score ?? 0;
  const hasCostTelemetry = Boolean(costOpt && (
    costOpt.current_cost > 0 ||
    costOpt.recommended_cost > 0 ||
    costOpt.savings > 0 ||
    costOpt.recommendations.length > 0
  ));
  const hasCpuData = (telemetry?.cpu.length ?? 0) > 0;
  const hasMemoryData = (telemetry?.memory.length ?? 0) > 0;

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      {/* Header and project selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">AI Insights & Optimization</h1>
          <p className="text-xs text-foreground-muted">
            Check real-time application score evaluations and AI auto-tuning recommendations.
          </p>
        </div>

        {!loadingProjects && projects.length > 0 && (
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none cursor-pointer font-semibold"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        )}
      </div>

      {loadingProjects || (loadingData && !healthScore) ? (
        <div className="flex items-center justify-center py-20 text-xs font-semibold text-foreground-muted gap-2">
          <Loader2 size={16} className="animate-spin text-primary" /> Analyzing repository footprints and telemetry metrics...
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-border rounded-2xl bg-card/20 space-y-3">
          <Brain size={40} className="text-foreground-muted mx-auto" />
          <h3 className="font-extrabold text-sm text-foreground">No active apps monitored</h3>
          <p className="text-xs text-foreground-muted max-w-xs mx-auto">
            Connect a GitHub repository to trigger the AI code scanner and build recommendations.
          </p>
        </div>
      ) : (
        <>
          {/* Row 1: Health Score Center & Breakdown */}
          <div className="grid md:grid-cols-3 gap-6">
            {/* Health Score Gauge */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col items-center justify-center text-center space-y-4"
            >
              <h3 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">Application Health Score</h3>
              <GaugeChart 
                value={score} 
                label="Health Index" 
                size={140} 
                color={score >= 90 ? "var(--success)" : score >= 75 ? "var(--warning)" : "var(--danger)"} 
              />
              <div className={`text-xs font-bold px-3 py-1 mt-1 border rounded-lg uppercase ${
                score >= 90 
                  ? "text-success bg-success/10 border-success/20" 
                  : "text-warning bg-warning/10 border-warning/20"
              }`}>
                {healthScore?.status || "No data"}
              </div>
            </motion.div>

            {/* Breakdown parameters */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}
              className="md:col-span-2 bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4 justify-between flex flex-col"
            >
              <h3 className="text-xs font-bold text-foreground-muted uppercase tracking-wider border-b border-border/40 pb-2">
                Optimization Category Breakdown
              </h3>
              <div className="space-y-3.5">
                {[
                  { label: "Performance", score: healthScore?.breakdown.performance ?? 0, color: "bg-primary" },
                  { label: "Security & Isolation", score: healthScore?.breakdown.security ?? 0, color: "bg-success" },
                  { label: "Reliability & Uptime", score: healthScore?.breakdown.reliability ?? 0, color: "bg-info" },
                  { label: "Scalability Bounds", score: healthScore?.breakdown.scalability ?? 0, color: "bg-accent" },
                  { label: "Cost Efficiency", score: healthScore?.breakdown.cost ?? 0, color: "bg-purple-500" }
                ].map((cat) => (
                  <div key={cat.label} className="text-xs">
                    <div className="flex justify-between font-semibold mb-1">
                      <span className="text-foreground-muted">{cat.label}</span>
                      <span className="text-foreground">{cat.score}%</span>
                    </div>
                    <div className="h-2 bg-background-secondary rounded-full overflow-hidden border border-border/40">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${cat.score}%` }}
                        transition={{ duration: 0.8 }}
                        className={`h-full rounded-full ${cat.color}`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* Cost Savings Overview Banner */}
          {hasCostTelemetry && costOpt && (
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="p-5 bg-gradient-to-r from-primary/10 via-accent/5 to-transparent border border-primary/20 rounded-2xl shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
            >
              <div className="space-y-1">
                <h4 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                  <DollarSign size={16} className="text-primary animate-pulse" /> Cost Signals Recorded
                </h4>
                <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                  These values come from the backend cost optimization endpoint for the selected project.
                </p>
              </div>
              <div className="flex items-center gap-4 text-xs font-bold border-l border-border/40 pl-4">
                <div>
                  <p className="text-foreground-muted text-[10px] uppercase">Current Billing</p>
                  <p className="text-foreground text-sm font-extrabold">${costOpt.current_cost}/mo</p>
                </div>
                <div>
                  <p className="text-primary text-[10px] uppercase">AI Target</p>
                  <p className="text-primary text-sm font-extrabold">${costOpt.recommended_cost}/mo</p>
                </div>
                <div className="bg-success/15 border border-success/20 rounded-lg px-2.5 py-1 text-success">
                  Save ${costOpt.savings}/mo
                </div>
              </div>
            </motion.div>
          )}

          {/* Row 2: AI Recommendations matching user spec */}
          <div className="space-y-4">
            <div className="border-b border-border/40 pb-2">
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles size={14} className="text-primary" /> AI Recommendations
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              {/* Cost recommendations */}
              {costOpt?.recommendations.map((rec) => (
                <motion.div
                  key={rec.title}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="p-5 rounded-2xl border border-border bg-card shadow-sm space-y-4 hover:border-primary/40 transition-colors flex flex-col justify-between"
                >
                  <div className="space-y-2">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] font-bold text-purple-500 bg-purple-500/10 border border-purple-500/20 rounded-full px-2.5 py-0.5 uppercase tracking-wider">
                        Cost Optimization
                      </span>
                      <span className="text-xs text-success font-bold">Save ${rec.savings}/month</span>
                    </div>
                    <h4 className="font-extrabold text-sm text-foreground">{rec.title}</h4>
                    <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                      {rec.description}
                    </p>
                  </div>
                  <button
                    disabled={applyingOpt === rec.title}
                    onClick={() => handleApplyOptimization(rec.title)}
                    className="flex items-center gap-1.5 text-xs text-primary font-bold hover:underline w-fit cursor-pointer self-end disabled:opacity-50"
                  >
                    {applyingOpt === rec.title ? "Recording Review..." : "Review Recommendation"} <ArrowRight size={14} />
                  </button>
                </motion.div>
              ))}

              {/* Health recommendations */}
              {healthScore?.recommendations.map((rec, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="p-5 rounded-2xl border border-border bg-card shadow-sm space-y-4 hover:border-primary/40 transition-colors flex flex-col justify-between"
                >
                  <div className="space-y-2">
                    <div className="flex justify-between items-start">
                      <span className="text-[10px] font-bold text-primary bg-primary/10 border border-primary/20 rounded-full px-2.5 py-0.5 uppercase tracking-wider">
                        Reliability & Health
                      </span>
                      <span className="text-xs text-info font-bold">Severity: Medium</span>
                    </div>
                    <h4 className="font-extrabold text-sm text-foreground">Recommended Remediation</h4>
                    <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                      {rec}
                    </p>
                  </div>
                  <button
                    disabled={applyingOpt === rec}
                    onClick={() => handleApplyOptimization(rec)}
                    className="flex items-center gap-1.5 text-xs text-primary font-bold hover:underline w-fit cursor-pointer self-end disabled:opacity-50"
                  >
                    {applyingOpt === rec ? "Recording Review..." : "Review Recommendation"} <ArrowRight size={14} />
                  </button>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Row 3: Performance Trend Charts matching user spec */}
          <div className="space-y-4">
            <div className="border-b border-border/40 pb-2">
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                <TrendingUp size={14} className="text-primary" /> Live Telemetry Charts
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              {/* Chart 1: CPU Usage */}
              <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Cpu size={16} className="text-primary animate-pulse" />
                    <h3 className="font-bold text-foreground text-xs">CPU Utilization (%)</h3>
                  </div>
                  {telemetry && (
                    <span className="font-mono text-xs text-foreground-muted">{telemetry.cpu[telemetry.cpu.length - 1]?.value || 0}%</span>
                  )}
                </div>
                {hasCpuData && telemetry ? (
                  <AreaChart data={telemetry.cpu} color="#3b82f6" height={150} />
                ) : (
                  <div className="h-[150px] flex items-center justify-center rounded-lg border border-dashed border-border text-xs text-foreground-muted">
                    No CPU data points recorded.
                  </div>
                )}
              </div>

              {/* Chart 2: Memory Usage */}
              <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity size={16} className="text-accent" />
                    <h3 className="font-bold text-foreground text-xs">Memory Utilization (%)</h3>
                  </div>
                  {telemetry && (
                    <span className="font-mono text-xs text-foreground-muted">{telemetry.memory[telemetry.memory.length - 1]?.value || 0}%</span>
                  )}
                </div>
                {hasMemoryData && telemetry ? (
                  <AreaChart data={telemetry.memory} color="#8b5cf6" height={150} />
                ) : (
                  <div className="h-[150px] flex items-center justify-center rounded-lg border border-dashed border-border text-xs text-foreground-muted">
                    No memory data points recorded.
                  </div>
                )}
              </div>
            </div>

            {/* Performance Stats Cards */}
            {telemetry && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-bold text-center">
                <div className="bg-card border border-border p-4 rounded-xl shadow-sm space-y-1">
                  <p className="text-foreground-muted text-[10px] uppercase">Service Uptime</p>
                  <p className="text-success text-base font-extrabold">{telemetry.uptime}</p>
                </div>
                <div className="bg-card border border-border p-4 rounded-xl shadow-sm space-y-1">
                  <p className="text-foreground-muted text-[10px] uppercase">Average Latency</p>
                  <p className="text-foreground text-base font-extrabold">{telemetry.response_time}</p>
                </div>
                <div className="bg-card border border-border p-4 rounded-xl shadow-sm space-y-1">
                  <p className="text-foreground-muted text-[10px] uppercase">HTTP Error Rate</p>
                  <p className="text-danger text-base font-extrabold">{telemetry.error_rate}</p>
                </div>
                <div className="bg-card border border-border p-4 rounded-xl shadow-sm space-y-1">
                  <p className="text-foreground-muted text-[10px] uppercase">Total Requests (24h)</p>
                  <p className="text-primary text-base font-extrabold">{telemetry.request_count.toLocaleString()}</p>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
