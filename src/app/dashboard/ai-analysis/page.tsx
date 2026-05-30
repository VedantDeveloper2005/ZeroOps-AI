"use client";

import { motion } from "framer-motion";
import {
  Brain, ShieldCheck, Zap, TrendingUp, Cpu, Activity,
  Clock, AlertTriangle, ArrowRight, Sparkles, Database, CheckCircle
} from "lucide-react";
import { useState, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { api, type Project } from "@/lib/api";
import { AreaChart } from "@/components/ui/AreaChart";
import { GaugeChart } from "@/components/ui/GaugeChart";

export default function AIAnalysisPage() {
  const { projects } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const selectedProject = projects.find(p => p.id === selectedProjectId) || projects[0];

  // Performance trends data simulation
  const responseTimeData = [
    { time: "10:00", value: 48 },
    { time: "11:00", value: 44 },
    { time: "12:00", value: 52 },
    { time: "13:00", value: 41 },
    { time: "14:00", value: 45 },
    { time: "15:00", value: 39 },
  ];

  const requestsData = [
    { time: "10:00", value: 120 },
    { time: "11:00", value: 150 },
    { time: "12:00", value: 180 },
    { time: "13:00", value: 110 },
    { time: "14:00", value: 130 },
    { time: "15:00", value: 165 },
  ];

  const errorData = [
    { time: "10:00", value: 0.05 },
    { time: "11:00", value: 0.02 },
    { time: "12:00", value: 0.08 },
    { time: "13:00", value: 0.01 },
    { time: "14:00", value: 0.03 },
    { time: "15:00", value: 0.02 },
  ];

  const resourceData = [
    { time: "10:00", value: 14 },
    { time: "11:00", value: 15 },
    { time: "12:00", value: 18 },
    { time: "13:00", value: 12 },
    { time: "14:00", value: 13 },
    { time: "15:00", value: 12 },
  ];

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

        {projects.length > 1 && (
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

      {/* Row 1: Health Score Center & Breakdown */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Health Score Gauge */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col items-center justify-center text-center space-y-4"
        >
          <h3 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">Application Health Score</h3>
          <GaugeChart value={92} label="Health Index" size={140} color="var(--success)" />
          <div className="text-xs font-bold text-success bg-success/10 border border-success/20 rounded-lg px-3 py-1 mt-1">
            Excellent Standing ✓
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
              { label: "Performance", score: 95, color: "bg-primary" },
              { label: "Security & Isolation", score: 90, color: "bg-success" },
              { label: "Reliability & Uptime", score: 94, color: "bg-info" },
              { label: "Scalability Bounds", score: 88, color: "bg-accent" },
              { label: "Cost Efficiency", score: 93, color: "bg-purple-500" }
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

      {/* Row 2: AI Recommendations matching user spec */}
      <div className="space-y-4">
        <div className="border-b border-border/40 pb-2">
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles size={14} className="text-primary" /> AI Recommendations
          </h2>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          {/* Card 1: Enable caching */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="p-5 rounded-2xl border border-border bg-card shadow-sm space-y-4 hover:border-primary/40 transition-colors flex flex-col justify-between"
          >
            <div className="space-y-2">
              <div className="flex justify-between items-start">
                <span className="text-[10px] font-bold text-primary bg-primary/10 border border-primary/20 rounded-full px-2.5 py-0.5 uppercase tracking-wider">
                  Performance Tune
                </span>
                <span className="text-xs text-success font-bold">Estimated improvement: 38%</span>
              </div>
              <h4 className="font-extrabold text-sm text-foreground">Enable Static Asset Caching</h4>
              <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                We detected that static JS and CSS modules are loaded directly without edge caching headers.
              </p>
            </div>
            <button className="flex items-center gap-1.5 text-xs text-primary font-bold hover:underline w-fit cursor-pointer self-end">
              Apply Optimization <ArrowRight size={14} />
            </button>
          </motion.div>

          {/* Card 2: Reduce image size */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="p-5 rounded-2xl border border-border bg-card shadow-sm space-y-4 hover:border-primary/40 transition-colors flex flex-col justify-between"
          >
            <div className="space-y-2">
              <div className="flex justify-between items-start">
                <span className="text-[10px] font-bold text-accent bg-accent/10 border border-accent/20 rounded-full px-2.5 py-0.5 uppercase tracking-wider">
                  Build Optimization
                </span>
                <span className="text-xs text-success font-bold">Estimated improvement: 21%</span>
              </div>
              <h4 className="font-extrabold text-sm text-foreground">Reduce Image & Media Size</h4>
              <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                Compactor identified 12 high-resolution image files in the source branch that are not optimized.
              </p>
            </div>
            <button className="flex items-center gap-1.5 text-xs text-primary font-bold hover:underline w-fit cursor-pointer self-end">
              Apply Optimization <ArrowRight size={14} />
            </button>
          </motion.div>
        </div>
      </div>

      {/* Row 3: Performance Trend Charts matching user spec */}
      <div className="space-y-4">
        <div className="border-b border-border/40 pb-2">
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
            <TrendingUp size={14} className="text-primary" /> Performance Trends
          </h2>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Chart 1: Response Time */}
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-primary" />
              <h3 className="font-bold text-foreground text-xs">Response Time (ms)</h3>
            </div>
            <AreaChart data={responseTimeData} color="#3b82f6" height={150} />
          </div>

          {/* Chart 2: Requests */}
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
            <div className="flex items-center gap-2">
              <Activity size={16} className="text-success" />
              <h3 className="font-bold text-foreground text-xs">Requests / Minute</h3>
            </div>
            <AreaChart data={requestsData} color="#22c55e" height={150} />
          </div>

          {/* Chart 3: Errors */}
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-danger" />
              <h3 className="font-bold text-foreground text-xs">Errors (%)</h3>
            </div>
            <AreaChart data={errorData} color="#ef4444" height={150} />
          </div>

          {/* Chart 4: Resource Usage */}
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
            <div className="flex items-center gap-2">
              <Cpu size={16} className="text-accent" />
              <h3 className="font-bold text-foreground text-xs">Resource Usage (CPU %)</h3>
            </div>
            <AreaChart data={resourceData} color="#8b5cf6" height={150} />
          </div>
        </div>
      </div>
    </div>
  );
}
