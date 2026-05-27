"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { AlertTriangle, CheckCircle, Clock, Brain, FileText, RefreshCw, X, Copy } from "lucide-react";
import { incidents } from "@/lib/mock-data";
import { AIThinkingIndicator } from "@/components/ui/AIThinkingIndicator";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

const severityConfig: Record<string, { color: string; bg: string; border: string }> = {
  critical: { color: "text-danger", bg: "bg-danger/10", border: "border-l-danger" },
  warning: { color: "text-warning", bg: "bg-warning/10", border: "border-l-warning" },
  resolved: { color: "text-success", bg: "bg-success/10", border: "border-l-success" },
};

const recoverySteps = [
  { label: "Identifying Root Cause", status: "completed" as const },
  { label: "Scaling Resources", status: "completed" as const },
  { label: "Redirecting Traffic", status: "active" as const },
  { label: "Validating Recovery", status: "pending" as const },
];

const aiDiagnosisText = [
  "Analyzing incident: API Gateway High Latency",
  "Root cause: Connection pool exhaustion under traffic spike",
  "Affected services: api-gateway (primary), web-app (secondary)",
  "Impact: P99 latency exceeded 500ms threshold at 08:42 AM",
  "AI Action: Increasing connection pool size from 50 to 100",
  "AI Action: Enabling connection recycling (max-age: 30s)",
  "AI Action: Scaling api-gateway from 3 to 5 replicas",
  "Recovery ETA: ~3 minutes",
];

export default function IncidentsPage() {
  const { addToast, hasDeployed } = useNotifications();

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Incident Management</h1>
          <p className="text-foreground-muted text-sm mt-1">AI-powered incident detection, diagnosis, and recovery</p>
        </div>
        <LockedView featureName="Incident Management" />
      </div>
    );
  }

  const activeIncidents = incidents.filter(i => i.status !== "resolved");
  const [diagnosisLines, setDiagnosisLines] = useState(0);
  const [isReportOpen, setIsReportOpen] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setDiagnosisLines(p => { if (p >= aiDiagnosisText.length) { clearInterval(timer); return p; } return p + 1; });
    }, 300);
    return () => clearInterval(timer);
  }, []);

  const handleCopyReport = () => {
    const reportText = `ZEROOPS AI INCIDENT POST-MORTEM
=================================
Incident ID: INC-001
Title: API Gateway High Latency
Severity: Warning
Status: Investigating
Start Time: 25 min ago
Affected Services: api-gateway, web-app

ROOT CAUSE ANALYSIS:
Connection pool exhaustion under traffic spike. Diagnostic engines isolated the issue to connection pool starvation (50/50 connections allocated).

MITIGATION DETAILS:
AI deployed actions:
- Increased connection pool size from 50 to 100
- Enabled connection recycling (max-age: 30s)
- Scaled api-gateway from 3 to 5 replicas

STATUS:
Autonomic healing tasks executed. Recovery validation in progress.`;

    navigator.clipboard.writeText(reportText);
    addToast("Post-mortem report copied to clipboard!", "success");
    setIsReportOpen(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-bold">Incident Management</h1><p className="text-foreground-muted text-sm mt-1">AI-powered incident detection, diagnosis, and recovery</p></div>
        <button 
          onClick={() => setIsReportOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 glass rounded-xl text-sm font-medium hover:bg-card-hover transition cursor-pointer"
        >
          <FileText size={16} />Create Report
        </button>
      </div>

      {/* Active Incident Banner */}
      {activeIncidents.length > 0 && (
        <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}
          className="glass rounded-xl p-5 border border-warning/30 glow-red relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-warning/5 to-transparent" />
          <div className="relative flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-warning/10 flex items-center justify-center"><AlertTriangle size={24} className="text-warning" /></div>
            <div><p className="text-lg font-bold text-foreground">{activeIncidents.length} Active Incident{activeIncidents.length > 1 ? "s" : ""}</p><p className="text-sm text-foreground-muted">{activeIncidents.map(i => i.title).join(", ")}</p></div>
          </div>
        </motion.div>
      )}

      {/* AI Diagnosis + Recovery */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl overflow-hidden glow-purple">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <Brain size={18} className="text-accent" /><span className="text-sm font-semibold">AI Diagnosis</span>
            <AIThinkingIndicator size="sm" label="" className="ml-auto" />
          </div>
          <div className="p-4 font-mono text-xs leading-6 bg-black/20 h-[280px] overflow-y-auto no-scrollbar">
            {aiDiagnosisText.slice(0, diagnosisLines).map((line, i) => (
              <motion.p key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                className={line.includes("Root cause") ? "text-danger" : line.includes("AI Action") ? "text-success" : line.includes("ETA") ? "text-primary font-bold" : "text-foreground-muted"}>
                {line.startsWith("AI Action") ? `✓ ${line}` : `▸ ${line}`}
              </motion.p>
            ))}
            {diagnosisLines < aiDiagnosisText.length && <span className="inline-block w-2 h-4 bg-accent animate-pulse" />}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-6">Recovery Progress</h3>
          <div className="space-y-0">
            {recoverySteps.map((step, i) => (
              <div key={i} className="flex items-start gap-4 relative">
                {i < recoverySteps.length - 1 && <div className="absolute left-[15px] top-[36px] bottom-0 w-px bg-border" />}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 relative z-10 ${step.status === "completed" ? "bg-success/10 border border-success/30" : step.status === "active" ? "bg-primary/10 border border-primary/30" : "bg-card border border-border"}`}>
                  {step.status === "completed" ? <CheckCircle size={14} className="text-success" /> : step.status === "active" ? <RefreshCw size={14} className="text-primary animate-spin" /> : <Clock size={14} className="text-foreground-muted" />}
                </div>
                <div className="pb-8">
                  <p className={`text-sm font-medium ${step.status === "pending" ? "text-foreground-muted" : "text-foreground"}`}>{step.label}</p>
                  <p className="text-xs text-foreground-muted mt-0.5">{step.status === "completed" ? "Completed" : step.status === "active" ? "In progress..." : "Waiting"}</p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Incident Timeline */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4">Incident Timeline</h3>
        <div className="space-y-3">
          {incidents.map((incident, i) => {
            const config = severityConfig[incident.severity] || severityConfig.resolved;
            return (
              <motion.div key={incident.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.1 }}
                className={`rounded-xl p-4 border-l-2 ${config.bg} ${config.border}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${incident.severity === "critical" ? "bg-danger" : incident.severity === "warning" ? "bg-warning animate-pulse" : "bg-success"}`} />
                    <h4 className="text-sm font-semibold text-foreground">{incident.title}</h4>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${config.bg} ${config.color}`}>{incident.status}</span>
                  </div>
                  <span className="text-xs text-foreground-muted">{incident.startTime} • {incident.duration}</span>
                </div>
                <p className="text-xs text-foreground-muted mb-2">{incident.description}</p>
                <div className="flex gap-1.5">
                  {incident.affectedServices.map(s => (
                    <span key={s} className="text-[10px] px-2 py-0.5 rounded-full bg-card text-foreground-muted">{s}</span>
                  ))}
                </div>
              </motion.div>
            );
          })}
        </div>
      </motion.div>

      {/* Incident Report Generation Modal */}
      {isReportOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} 
            animate={{ opacity: 1, scale: 1 }} 
            className="glass max-w-lg w-full p-6 rounded-xl border border-border shadow-2xl relative flex flex-col max-h-[90vh]"
          >
            <button 
              onClick={() => setIsReportOpen(false)}
              className="absolute top-4 right-4 text-foreground-muted hover:text-foreground cursor-pointer"
            >
              <X size={18} />
            </button>
            
            <h3 className="text-lg font-bold mb-1 flex items-center gap-2">
              <FileText size={20} className="text-primary" />
              Incident Post-Mortem Report
            </h3>
            <p className="text-xs text-foreground-muted mb-4">
              Generated by ZeroOps Autonomic Diagnosis Engine
            </p>

            <div className="flex-1 overflow-y-auto bg-black/30 border border-border/60 rounded-lg p-4 font-mono text-xs text-foreground space-y-4 no-scrollbar">
              <div>
                <span className="text-primary font-bold"># ZEROOPS AI INCIDENT POST-MORTEM</span>
                <p className="text-foreground-muted">Incident ID: INC-001</p>
                <p className="text-foreground-muted">Incident Title: API Gateway High Latency</p>
                <p className="text-foreground-muted">Target Service: api-gateway, web-app</p>
                <p className="text-foreground-muted">Audited At: 2026-05-25 19:15 UTC</p>
              </div>

              <div>
                <span className="text-warning font-bold">## 1. Summary of Outage</span>
                <p className="text-foreground-muted leading-relaxed mt-1">
                  At 08:42 AM, the AI monitoring system detected P99 latency on the API gateway exceeding the 500ms safety threshold (peaking at 780ms). Autonomous diagnosis isolated the issue to connection pool starvation (50/50 connections utilized).
                </p>
              </div>

              <div>
                <span className="text-success font-bold">## 2. Autonomic Recovery Log</span>
                <div className="space-y-1 text-[11px] mt-1 pl-2 text-foreground-muted border-l border-border/40">
                  <p><span className="text-success">08:43:10 AM:</span> Analyzed logs and metrics; isolated pool lockup.</p>
                  <p><span className="text-success">08:43:15 AM:</span> Dispatched configuration change: pool limit 50 → 100.</p>
                  <p><span className="text-success">08:43:20 AM:</span> Configured connection recycle policy (30s max lifetime).</p>
                  <p><span className="text-success">08:44:00 AM:</span> Scaled api-gateway service to 5 pods (+2 replicas).</p>
                </div>
              </div>

              <div>
                <span className="text-info font-bold">## 3. Prevention & Remediation</span>
                <p className="text-foreground-muted leading-relaxed mt-1">
                  Predictive scaling threshold adjusted to 65% utilization. Connection recycle timeout added to default Helm values for api-gateway deployments.
                </p>
              </div>
            </div>

            <div className="flex gap-3 justify-end pt-4 mt-2">
              <button 
                onClick={() => setIsReportOpen(false)} 
                className="px-4 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
              >
                Close
              </button>
              <button 
                onClick={handleCopyReport}
                className="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition glow-blue flex items-center gap-1.5 cursor-pointer"
              >
                <Copy size={12} />
                Copy Report
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
