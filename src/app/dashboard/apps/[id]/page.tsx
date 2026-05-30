"use client";

import * as React from "react";
import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Globe, Clock, Cpu, HardDrive, ShieldCheck, ExternalLink,
  RefreshCw, Calendar, ArrowLeft, Brain,
  Activity, ChevronRight, Zap, AlertTriangle, GitBranch
} from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, type Project, type Deployment, type AIAnalysis, type TelemetryMetric, type CustomDomain, type ProjectActivity, type HealthScore } from "@/lib/api";
import { ArchitectureDiagram } from "@/components/dashboard/ArchitectureDiagram";
import { liveUrlForProject, normalizeProjectId } from "@/lib/demo-runtime";

export default function AppDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = React.use(params);
  const { addToast } = useNotifications();
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [metrics, setMetrics] = useState<TelemetryMetric | null>(null);
  const [domains, setDomains] = useState<CustomDomain[]>([]);
  const [activities, setActivities] = useState<ProjectActivity[]>([]);
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [redeploying, setRedeploying] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const proj = await api.getProject(id);
      setProject(proj);

      const [analysisData, depsData, metricsData, domainsData, activitiesData, scoreData] = await Promise.allSettled([
        api.getAIAnalysis(id),
        api.getDeployments(50),
        api.getProjectMetrics(id),
        api.getProjectDomains(id),
        api.getProjectActivity(id),
        api.getHealthScore(id)
      ]);

      if (analysisData.status === "fulfilled") setAnalysis(analysisData.value);
      if (depsData.status === "fulfilled") {
        const filtered = depsData.value.filter(d => d.project_id === id);
        setDeployments(filtered);
      }
      if (metricsData.status === "fulfilled") setMetrics(metricsData.value);
      if (domainsData.status === "fulfilled") setDomains(domainsData.value);
      if (activitiesData.status === "fulfilled") setActivities(activitiesData.value);
      if (scoreData.status === "fulfilled") setHealthScore(scoreData.value);
    } catch (err) {
      console.error("Failed to load project details:", err);
      addToast("Failed to load application details.", "error");
    } finally {
      setLoading(false);
    }
  }, [id, addToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRedeploy = async () => {
    if (!project || redeploying) return;
    setRedeploying(true);
    addToast(`Initializing redeployment for ${project.name}...`, "info");
    try {
      const res = await api.startDeployment({
        project_id: project.id,
        branch: project.branch || "main",
        environment: "production",
      });
      addToast("Deployment successfully initialized.", "success");
      router.push(`/dashboard/deployments?id=${res.deployment_id}&repo=${encodeURIComponent(project.full_name)}`);
    } catch (err) {
      console.error(err);
      addToast("Failed to initialize redeployment.", "error");
    } finally {
      setRedeploying(false);
    }
  };

  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    addToast("URL copied to clipboard!", "success");
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="text-foreground-muted text-sm font-medium">Loading application dashboard...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertTriangle className="w-12 h-12 text-warning" />
        <p className="text-foreground-muted text-sm">Application not found.</p>
        <button
          onClick={() => router.push("/dashboard")}
          className="px-4 py-2 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
        >
          Return to Overview
        </button>
      </div>
    );
  }

  const pId = normalizeProjectId(project.full_name);
  const liveUrl = liveUrlForProject(pId);

  // Parse custom domain display
  const primaryCustomDomain = domains.find(d => d.dns_verified);
  const domainName = primaryCustomDomain ? primaryCustomDomain.name : `${project.name}.zeroops.dev`;
  const isSslActive = primaryCustomDomain ? primaryCustomDomain.ssl : false;

  const isHealthy = project.status === "active" || project.latest_deployment_status === "running";

  // Telemetry aggregates
  const cpuVal = metrics?.cpu && metrics.cpu.length > 0 ? metrics.cpu[metrics.cpu.length - 1].value : 8;
  const cpuStatus = cpuVal > 80 ? "Critical" : cpuVal > 50 ? "Moderate Load" : "Healthy";
  const cpuColor = cpuVal > 80 ? "bg-danger" : cpuVal > 50 ? "bg-warning" : "bg-success";

  const memVal = metrics?.memory && metrics.memory.length > 0 ? metrics.memory[metrics.memory.length - 1].value : 42;
  const memStatus = memVal > 90 ? "Critical" : memVal > 70 ? "Warning" : "Stable";
  const memColor = memVal > 90 ? "bg-danger" : memVal > 70 ? "bg-warning" : "bg-success";

  const errRateStr = metrics?.error_rate || "0.0%";
  const errVal = parseFloat(errRateStr.replace("%", "")) || 0.0;
  const netStatus = errVal > 1.0 ? "Degraded" : "Excellent";
  const netColor = errVal > 1.0 ? "bg-danger" : "bg-success";

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      {/* Header and Back navigation */}
      <div className="space-y-4">
        <button
          onClick={() => router.push("/dashboard")}
          className="flex items-center gap-1 text-xs text-foreground-muted hover:text-foreground transition cursor-pointer"
        >
          <ArrowLeft size={14} /> Back to Overview
        </button>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-extrabold tracking-tight text-foreground">{project.name}</h1>
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${
                isHealthy
                  ? "bg-success/15 border-success/30 text-success"
                  : "bg-warning/15 border-warning/30 text-warning"
              }`}>
                {isHealthy ? "🟢 Live & Healthy" : "Idle"}
              </span>
            </div>
            <p className="text-xs text-foreground-muted flex items-center gap-1.5 font-mono">
              <GitBranch size={12} /> {project.full_name} ({project.branch})
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <a
              href={liveUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-xs transition shadow-lg shadow-primary/10"
            >
              <ExternalLink size={14} /> Open Application
            </a>
            <button
              onClick={() => handleCopyUrl(liveUrl)}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
            >
              Copy URL
            </button>
            <button
              disabled={redeploying}
              onClick={handleRedeploy}
              className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw size={14} className={redeploying ? "animate-spin" : ""} /> Redeploy
            </button>
          </div>
        </div>
      </div>

      {/* Row 1: Outcomes details */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Core details card */}
        <div className="md:col-span-2 glass rounded-2xl border border-border/60 p-6 bg-gradient-to-b from-card to-card/40 space-y-5 shadow-sm">
          <div className="grid sm:grid-cols-2 gap-5 text-xs">
            <div className="space-y-1">
              <p className="font-bold text-foreground-muted uppercase tracking-wider text-[9px]">Live URL</p>
              <div className="flex items-center gap-2">
                <Globe size={14} className="text-primary" />
                <a href={liveUrl} target="_blank" rel="noopener noreferrer" className="font-mono text-primary hover:underline truncate max-w-[220px]">
                  {liveUrl.replace("https://", "")}
                </a>
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-bold text-foreground-muted uppercase tracking-wider text-[9px]">Custom Domain Mapping</p>
              <div className="flex items-center gap-2 text-foreground">
                <ShieldCheck size={14} className={isSslActive ? "text-success" : "text-foreground-muted"} />
                <span className="font-mono truncate">{domainName}</span>
                {isSslActive && (
                  <span className="text-[8px] bg-success/15 border border-success/30 text-success px-1.5 py-0.2 rounded-full font-bold uppercase">SSL Active</span>
                )}
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-bold text-foreground-muted uppercase tracking-wider text-[9px]">Environment</p>
              <p className="font-semibold text-foreground flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span> Production
              </p>
            </div>
            <div className="space-y-1">
              <p className="font-bold text-foreground-muted uppercase tracking-wider text-[9px]">Version Tag</p>
              <p className="font-semibold text-foreground font-mono text-[11px] truncate">
                {deployments[0]?.commit_sha ? `sha-${deployments[0].commit_sha.slice(0, 7)}` : "v1.0.0"}
              </p>
            </div>
          </div>
        </div>

        {/* AI Observability Agent Summary */}
        <div className="glass rounded-2xl border border-primary/20 p-6 bg-gradient-to-b from-primary/5 via-accent/5 to-transparent flex flex-col justify-between shadow-sm space-y-4">
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
              <Brain size={14} className="animate-pulse text-primary" /> AI Health Summary
            </h4>
            <div className="text-xs text-foreground-muted leading-relaxed font-medium space-y-2">
              <p>
                Application health score: <span className="text-primary font-bold">{healthScore?.score || 94}/100</span> ({healthScore?.status || "Strong Reliability"}).
              </p>
              {healthScore?.recommendations && healthScore.recommendations.length > 0 && (
                <p className="text-[10px] border-t border-border/20 pt-2 text-primary font-semibold flex items-center gap-1 leading-normal">
                  <Zap size={12} className="flex-shrink-0" /> {healthScore.recommendations[0]}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Human-Friendly Resource Metrics */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* CPU/Application Load */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">Application Load</span>
            <Cpu size={14} className="text-primary" />
          </div>
          <div>
            <p className="text-lg font-bold text-foreground">{cpuStatus}</p>
            <p className="text-[10px] text-foreground-muted mt-0.5">CPU footprint utilization is at {cpuVal}%.</p>
          </div>
          <div className="h-1.5 bg-background-secondary rounded-full overflow-hidden border border-border/40">
            <div className={`h-full ${cpuColor}`} style={{ width: `${Math.min(100, Math.max(5, cpuVal))}%` }} />
          </div>
        </div>

        {/* Memory Usage */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">Memory Usage</span>
            <HardDrive size={14} className="text-accent" />
          </div>
          <div>
            <p className="text-lg font-bold text-foreground">{memStatus}</p>
            <p className="text-[10px] text-foreground-muted mt-0.5">Active memory consumption is at {memVal}%.</p>
          </div>
          <div className="h-1.5 bg-background-secondary rounded-full overflow-hidden border border-border/40">
            <div className={`h-full ${memColor}`} style={{ width: `${Math.min(100, Math.max(5, memVal))}%` }} />
          </div>
        </div>

        {/* Network Bandwidth */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">Network Health</span>
            <Activity size={14} className="text-success" />
          </div>
          <div>
            <p className="text-lg font-bold text-foreground">{netStatus}</p>
            <p className="text-[10px] text-foreground-muted mt-0.5">Error rate over 24h: {errRateStr}.</p>
          </div>
          <div className="h-1.5 bg-background-secondary rounded-full overflow-hidden border border-border/40">
            <div className={`h-full ${netColor}`} style={{ width: `${Math.min(100, Math.max(5, 100 - errVal))}%` }} />
          </div>
        </div>
      </div>

      {/* Row 3: SVG System Architecture */}
      <div className="space-y-4">
        <div className="border-b border-border/40 pb-2">
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Project System Architecture</h2>
        </div>
        <ArchitectureDiagram 
          repo={project.full_name}
          branch={project.branch || "main"}
          framework={project.framework}
          runtime={analysis?.runtime || "Node.js 22"}
          database={analysis?.database_dependencies?.[0] || "None"}
          liveUrl={liveUrl}
        />
      </div>

      {/* Row 4: Deployment History & Recent Activity Feed */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Left: Deployment History Timeline */}
        <div className="md:col-span-2 glass rounded-2xl border border-border/60 p-6 bg-card/20 space-y-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">Deployment History</h3>
          
          {deployments.length === 0 ? (
            <div className="text-center py-8 text-xs text-foreground-muted">
              No recent deployments found.
            </div>
          ) : (
            <div className="relative border-l border-border/40 pl-5 ml-2.5 space-y-6">
              {deployments.slice(0, 4).map((dep, idx) => {
                const dateObj = dep.started_at ? new Date(dep.started_at) : new Date();
                const dateStr = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                const timeStr = dateObj.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

                return (
                  <div key={dep.id} className="relative group">
                    <div className={`absolute -left-[27px] top-1.5 w-3.5 h-3.5 rounded-full border-2 border-zinc-950 transition-colors ${
                      dep.status === "running" ? "bg-success" :
                      dep.status === "failed" ? "bg-danger" :
                      dep.status === "building" ? "bg-warning animate-pulse" :
                      "bg-foreground-muted"
                    }`} />

                    <div
                      onClick={() => router.push(`/dashboard/deployments?id=${dep.id}&repo=${encodeURIComponent(project.full_name)}`)}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-xl border border-border/40 bg-card hover:bg-card-hover/40 transition cursor-pointer"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-foreground">Build #{deployments.length - idx}</span>
                          <span className={`text-[9px] font-mono font-bold px-1.5 py-0.2 rounded border ${
                            dep.status === "running" ? "bg-success/15 border-success/30 text-success" :
                            dep.status === "failed" ? "bg-danger/15 border-danger/30 text-danger" :
                            "bg-zinc-800 border-zinc-700 text-foreground-muted"
                          }`}>
                            {dep.status}
                          </span>
                        </div>
                        <p className="text-[10px] text-foreground-muted mt-0.5 font-mono">
                          {dep.duration || "2m 13s"}
                        </p>
                      </div>

                      <div className="flex items-center gap-3 text-right">
                        <div className="text-xs">
                          <p className="text-foreground-muted">{dateStr}</p>
                          <p className="text-[10px] text-foreground-muted/60 mt-0.5">{timeStr}</p>
                        </div>
                        <ChevronRight size={14} className="text-foreground-muted group-hover:text-primary transition-all" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: Recent Operations Activity Feed */}
        <div className="glass rounded-2xl border border-border/60 p-6 bg-card/20 space-y-4 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-bold text-foreground uppercase tracking-wider border-b border-border/40 pb-2 mb-3">Recent Activity</h3>
            {activities.length > 0 ? (
              <div className="space-y-4 text-xs overflow-y-auto max-h-[280px] pr-1">
                {activities.slice(0, 5).map((act) => {
                  const actDate = new Date(act.created_at);
                  const dateStr = actDate.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  const timeStr = actDate.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
                  
                  const isHealed = act.action.toLowerCase().includes("healing") || act.action.toLowerCase().includes("rollback") || act.action.toLowerCase().includes("mitigated");
                  const isFailure = act.action.toLowerCase().includes("failed") || act.action.toLowerCase().includes("error") || act.action.toLowerCase().includes("critical");
                  const isDomain = act.action.toLowerCase().includes("domain");
                  const borderClass = isFailure 
                    ? "border-danger" 
                    : isHealed 
                    ? "border-warning" 
                    : isDomain 
                    ? "border-primary" 
                    : "border-success";

                  return (
                    <div key={act.id} className={`border-l-2 ${borderClass} pl-3 py-1 space-y-0.5`}>
                      <p className="font-bold text-foreground">{act.action}</p>
                      <p className="text-[10px] text-foreground-muted leading-snug">{act.details}</p>
                      <span className="text-[9px] text-foreground-muted/60 font-medium">{dateStr} at {timeStr}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-foreground-muted py-6 font-medium">
                No recent activity events logged.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
