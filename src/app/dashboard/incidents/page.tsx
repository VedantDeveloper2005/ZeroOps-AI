"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { AlertTriangle, CheckCircle, Clock, Brain, FileText, RefreshCw, X, Copy } from "lucide-react";
interface Incident {
  id: string;
  title: string;
  severity: "critical" | "warning" | "resolved";
  affectedServices: string[];
  startTime: string;
  duration: string;
  status: "active" | "investigating" | "resolved";
  description: string;
}
import { api } from "@/lib/api";
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
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [diagnosisLines, setDiagnosisLines] = useState(0);
  const [isReportOpen, setIsReportOpen] = useState(false);

  useEffect(() => {
    if (!hasDeployed) return;

    async function loadIncidents() {
      try {
        const notifs = await api.getNotifications("incident");
        const mapped = notifs.map((n: any) => {
          let severity: "critical" | "warning" | "resolved" = "warning";
          if (n.type === "critical") severity = "critical";
          else if (n.type === "success" || n.read) severity = "resolved";

          let status: "active" | "investigating" | "resolved" = "active";
          if (n.read) status = "resolved";
          else if (n.type === "warning") status = "investigating";

          const date = new Date(n.created_at || Date.now());
          return {
            id: n.id,
            title: n.title,
            severity,
            affectedServices: ["aks-cluster"],
            startTime: date.toLocaleTimeString() + " " + date.toLocaleDateString(),
            duration: "N/A",
            status,
            description: n.message
          };
        });
        setIncidents(mapped);
      } catch (err) {
        console.error("Failed to load incidents", err);
      } finally {
        setLoading(false);
      }
    }
    loadIncidents();
  }, [hasDeployed]);

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

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Incident Management" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading incidents...</p>
      </div>
    );
  }

  const activeIncidents = incidents.filter(i => i.status !== "resolved");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <button 
          onClick={() => setIsReportOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 bg-background-secondary border border-border/80 rounded-md text-xs font-semibold hover:bg-background transition cursor-pointer shadow-sm select-none"
        >
          <FileText size={14} /> Create Post-Mortem Report
        </button>
      </div>

      {/* Active Incident Banner */}
      {activeIncidents.length > 0 && (
        <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}
          className="bg-card border border-border border-l-4 border-l-warning rounded-xl p-5 relative overflow-hidden shadow-sm">
          <div className="absolute inset-0 bg-warning/5 pointer-events-none" />
          <div className="relative flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-warning/10 flex items-center justify-center shrink-0"><AlertTriangle size={20} className="text-warning" /></div>
            <div>
              <p className="text-sm font-bold text-foreground">{activeIncidents.length} Active Incident{activeIncidents.length > 1 ? "s" : ""}</p>
              <p className="text-xs text-foreground-muted mt-0.5">{activeIncidents.map(i => i.title).join(", ")}</p>
            </div>
          </div>
        </motion.div>
      )}

      {/* AI Diagnosis + Recovery */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <Brain size={16} className="text-accent" />
            <span className="text-xs font-bold text-foreground">AI Diagnostics Live Feed</span>
            <AIThinkingIndicator size="sm" label="" className="ml-auto" />
          </div>
          <div className="p-4 font-mono text-xs leading-6 bg-background-secondary h-[280px] overflow-y-auto no-scrollbar">
            {aiDiagnosisText.slice(0, diagnosisLines).map((line, i) => (
              <motion.p key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                className={line.includes("Root cause") ? "text-danger" : line.includes("AI Action") ? "text-success font-semibold" : line.includes("ETA") ? "text-primary font-bold" : "text-foreground-muted"}>
                {line.startsWith("AI Action") ? `✓ ${line}` : `▸ ${line}`}
              </motion.p>
            ))}
            {diagnosisLines < aiDiagnosisText.length && <span className="inline-block w-1.5 h-3.5 bg-accent animate-pulse" />}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-6">Autonomic Healing Recovery Progress</h3>
          <div className="space-y-0">
            {recoverySteps.map((step, i) => (
              <div key={i} className="flex items-start gap-4 relative">
                {i < recoverySteps.length - 1 && <div className="absolute left-[15px] top-[36px] bottom-0 w-px bg-border" />}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 relative z-10 ${step.status === "completed" ? "bg-success/10 border border-success/30" : step.status === "active" ? "bg-primary/10 border border-primary/30" : "bg-card border border-border"}`}>
                  {step.status === "completed" ? <CheckCircle size={14} className="text-success" /> : step.status === "active" ? <RefreshCw size={14} className="text-primary animate-spin" /> : <Clock size={14} className="text-foreground-muted" />}
                </div>
                <div className="pb-8">
                  <p className={`text-xs font-bold ${step.status === "pending" ? "text-foreground-muted" : "text-foreground"}`}>{step.label}</p>
                  <p className="text-[10px] text-foreground-muted mt-0.5 font-medium">{step.status === "completed" ? "Completed" : step.status === "active" ? "In progress..." : "Waiting"}</p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Incident Timeline */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
        <h3 className="text-sm font-bold text-foreground mb-4">Incident Event log</h3>
        <div className="space-y-3">
          {incidents.length === 0 ? (
            <div className="p-8 text-center space-y-2 bg-card/20 border border-border rounded-xl">
              <CheckCircle size={32} className="text-success mx-auto" />
              <p className="text-sm font-semibold text-foreground">All Systems Operational</p>
              <p className="text-xs text-foreground-muted">No active outages or performance alerts detected.</p>
            </div>
          ) : (
            incidents.map((incident, i) => {
              const config = severityConfig[incident.severity] || severityConfig.resolved;
              return (
                <motion.div key={incident.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.1 }}
                  className={`rounded-xl p-4 border border-border border-l-4 ${config.border} bg-background-secondary`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${incident.severity === "critical" ? "bg-danger" : incident.severity === "warning" ? "bg-warning animate-pulse" : "bg-success"}`} />
                      <h4 className="text-xs font-bold text-foreground">{incident.title}</h4>
                      <span className={`text-[9px] uppercase px-2 py-0.5 rounded-full font-bold bg-card border border-border/80 ${config.color}`}>{incident.status}</span>
                    </div>
                    <span className="text-[10px] text-foreground-muted font-mono font-semibold">{incident.startTime} • {incident.duration}</span>
                  </div>
                  <p className="text-xs text-foreground-muted mb-3 leading-relaxed">{incident.description}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {incident.affectedServices.map(s => (
                      <span key={s} className="text-[9px] font-bold px-2 py-0.5 rounded-md bg-card border border-border/60 text-foreground-muted font-mono">{s}</span>
                    ))}
                  </div>
                </motion.div>
              );
            })
          )}
        </div>
      </motion.div>

      {/* Incident Report Generation Modal */}
      {isReportOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} 
            animate={{ opacity: 1, scale: 1 }} 
            className="bg-card border border-border max-w-lg w-full p-6 rounded-xl shadow-2xl relative flex flex-col max-h-[90vh]"
          >
            <button 
              onClick={() => setIsReportOpen(false)}
              className="absolute top-4 right-4 text-foreground-muted hover:text-foreground cursor-pointer transition"
            >
              <X size={16} />
            </button>
            
            <h3 className="text-sm font-bold text-foreground mb-1 flex items-center gap-2">
              <FileText size={18} className="text-primary" />
              Incident Post-Mortem Report
            </h3>
            <p className="text-[10px] text-foreground-muted font-semibold uppercase tracking-wider mb-4">
              Generated by ZeroOps Autonomic Diagnosis Engine
            </p>

            <div className="flex-1 overflow-y-auto bg-background-secondary border border-border/60 rounded-lg p-4 font-mono text-[11px] text-foreground space-y-4 no-scrollbar">
              <div>
                <span className="text-primary font-bold"># ZEROOPS AI INCIDENT POST-MORTEM</span>
                <p className="text-foreground-muted mt-1">Incident ID: INC-001</p>
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
                <div className="space-y-1 mt-1 pl-2 text-foreground-muted border-l border-border/40">
                  <p><span className="text-success font-semibold">08:43:10 AM:</span> Analyzed logs and metrics; isolated pool lockup.</p>
                  <p><span className="text-success font-semibold">08:43:15 AM:</span> Dispatched configuration change: pool limit 50 → 100.</p>
                  <p><span className="text-success font-semibold">08:43:20 AM:</span> Configured connection recycle policy (30s max lifetime).</p>
                  <p><span className="text-success font-semibold">08:44:00 AM:</span> Scaled api-gateway service to 5 pods (+2 replicas).</p>
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
                className="px-3.5 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-background-secondary transition cursor-pointer"
              >
                Close
              </button>
              <button 
                onClick={handleCopyReport}
                className="px-3.5 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer shadow-sm"
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
