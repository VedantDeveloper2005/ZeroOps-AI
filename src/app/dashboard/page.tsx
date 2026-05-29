"use client";

import { motion } from "framer-motion";
import {
  GitBranch, ExternalLink, RefreshCw, Terminal, Globe,
  Calendar, Clock, Brain, Loader2, FolderGit2, AlertTriangle,
  Check, ArrowRight, ShieldCheck, Cpu
} from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, type Project, type Deployment, type AIAnalysis } from "@/lib/api";
import { ArchitectureDiagram } from "@/components/dashboard/ArchitectureDiagram";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { liveUrlForProject, normalizeProjectId } from "@/lib/demo-runtime";

export default function DashboardHome() {
  const { projects, hasDeployed, isLoading: contextLoading, refreshProjects, addToast } = useNotifications();
  const router = useRouter();

  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [redeploying, setRedeploying] = useState(false);

  // Redirect to onboarding if no deployments exist
  useEffect(() => {
    if (!contextLoading && !hasDeployed) {
      router.replace("/dashboard/repositories");
    }
  }, [contextLoading, hasDeployed, router]);

  // Set default selected project
  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  // Load project specific details
  const loadProjectDetails = useCallback(async (projId: string) => {
    setLoading(true);
    try {
      const [analysisData, depsData] = await Promise.allSettled([
        api.getAIAnalysis(projId),
        api.getDeployments(50) // load recent runs
      ]);

      if (analysisData.status === "fulfilled") {
        setAnalysis(analysisData.value);
      } else {
        setAnalysis(null);
      }

      if (depsData.status === "fulfilled") {
        const filtered = depsData.value.filter((d) => d.project_id === projId);
        setDeployments(filtered);
      } else {
        setDeployments([]);
      }
    } catch (err) {
      console.error("Failed to load project details:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadProjectDetails(selectedProjectId);
    }
  }, [selectedProjectId, loadProjectDetails]);

  // Handle Redeploy action
  const handleRedeploy = async (project: Project) => {
    if (redeploying) return;
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

  // Copy Live URL to Clipboard
  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    addToast("URL copied to clipboard!", "success");
  };

  // Loading state
  if (contextLoading || !hasDeployed || (selectedProjectId && loading && !analysis)) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading project home...</p>
      </div>
    );
  }

  const activeProject = projects.find((p) => p.id === selectedProjectId) || projects[0];

  if (!activeProject) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <FolderGit2 className="w-12 h-12 text-foreground-muted/30" />
        <p className="text-foreground-muted text-sm">No connected projects found.</p>
        <button
          onClick={() => router.push("/dashboard/repositories")}
          className="px-4 py-2 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition"
        >
          Connect a Repository
        </button>
      </div>
    );
  }

  const pId = normalizeProjectId(activeProject.full_name);
  const liveUrl = liveUrlForProject(pId);
  const customDomain = `${pId}.zeroops.app`;

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Project Selector & Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground">{activeProject.name}</h1>
            <StatusBadge status={activeProject.status || "active"} />
          </div>
          <p className="text-xs text-foreground-muted flex items-center gap-1.5 font-mono">
            <GitBranch size={12} /> {activeProject.full_name} ({activeProject.branch})
          </p>
        </div>

        {/* Project Selector dropdown if multiple projects exist */}
        {projects.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-foreground-muted font-medium">Project:</span>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none cursor-pointer font-semibold"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Vercel-style Outcomes & Status Card */}
      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 glass rounded-2xl border border-border/60 p-6 bg-gradient-to-b from-card to-card/40 space-y-5">
          <div className="grid sm:grid-cols-2 gap-4 text-xs">
            <div className="space-y-1">
              <p className="font-semibold text-foreground-muted uppercase tracking-wider text-[9px]">Deployment URL</p>
              <div className="flex items-center gap-2">
                <Globe size={14} className="text-primary" />
                <a href={liveUrl} target="_blank" rel="noopener noreferrer" className="font-mono text-primary hover:underline truncate max-w-[200px]">
                  {liveUrl.replace("https://", "")}
                </a>
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-semibold text-foreground-muted uppercase tracking-wider text-[9px]">Custom Domain</p>
              <div className="flex items-center gap-2 text-foreground">
                <ShieldCheck size={14} className="text-success" />
                <span className="font-mono truncate">{customDomain}</span>
                <span className="text-[9px] bg-success/15 border border-success/30 text-success px-1.5 py-0.2 rounded-full font-bold">Active</span>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-border/20 flex flex-wrap gap-3">
            <a
              href={liveUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-xs transition glow-blue"
            >
              <ExternalLink size={14} /> Open Application
            </a>
            <button
              onClick={() => handleCopyUrl(liveUrl)}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition"
            >
              Copy URL
            </button>
            <button
              disabled={redeploying}
              onClick={() => handleRedeploy(activeProject)}
              className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition disabled:opacity-50"
            >
              <RefreshCw size={14} className={redeploying ? "animate-spin" : ""} /> Redeploy
            </button>
            <button
              onClick={() => router.push(`/dashboard/deployments?repo=${encodeURIComponent(activeProject.full_name)}`)}
              className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition text-foreground-muted hover:text-foreground"
            >
              <Terminal size={14} /> View Logs
            </button>
          </div>
        </div>

        {/* AI Health & Meta Card */}
        <div className="glass rounded-2xl border border-border/60 p-6 bg-gradient-to-b from-primary/5 to-accent/5 flex flex-col justify-between shadow-sm">
          <div className="space-y-3">
            <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
              <Brain size={14} className="animate-pulse" /> Autonomic Health Status
            </h4>
            <div className="space-y-2.5 text-xs pt-1">
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-foreground-muted">Platform Target</span>
                <span className="font-semibold text-foreground">{activeProject.framework}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-foreground-muted">Scaling Status</span>
                <span className="font-semibold text-success flex items-center gap-1"><Cpu size={12} /> Auto-Scaling</span>
              </div>
              <div className="flex justify-between">
                <span className="text-foreground-muted">Deployment target</span>
                <span className="font-semibold text-foreground">Azure App Service</span>
              </div>
            </div>
          </div>
          <div className="text-[10px] text-foreground-muted/60 text-center border-t border-border/40 pt-3">
            ZeroOps Autonomic Control Plane Active
          </div>
        </div>
      </div>

      {/* SVG System Architecture & Project Explanation */}
      <div className="space-y-4">
        <div className="border-b border-border/40 pb-2">
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Project System Architecture</h2>
        </div>
        <ArchitectureDiagram 
          repo={activeProject.full_name}
          branch={activeProject.branch || "main"}
          framework={activeProject.framework}
          runtime={analysis?.runtime || "Node.js 20"}
          database={analysis?.database_dependencies?.[0] || "None"}
          liveUrl={liveUrl}
        />
      </div>

      {/* AI Explanation & Recommendations */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-card/40">
          <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
            <Brain size={14} /> Explain This Project
          </h4>
          <p className="text-xs text-foreground-muted leading-relaxed">
            {analysis?.explanation || `This is a ${activeProject.framework} application built with ${activeProject.language || "TypeScript"}. It is containerized and managed autonomously by ZeroOps on Azure App Service with isolated security configurations.`}
          </p>
        </div>

        <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-card/40">
          <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
            Recommendations & Optimizations
          </h4>
          <ul className="space-y-2">
            {analysis?.vulnerabilities && analysis.vulnerabilities.length > 0 ? (
              analysis.vulnerabilities.slice(0, 3).map((rec, i) => (
                <li key={i} className="flex gap-2 items-start text-xs text-foreground-muted">
                  <span className="text-primary font-bold select-none">•</span>
                  <span>{rec}</span>
                </li>
              ))
            ) : (
              <>
                <li className="flex gap-2 items-start text-xs text-foreground-muted">
                  <Check size={12} className="text-success shrink-0 mt-0.5" />
                  <span>Configure idle pod scale-down boundaries to reduce cloud billing by 30%.</span>
                </li>
                <li className="flex gap-2 items-start text-xs text-foreground-muted">
                  <Check size={12} className="text-success shrink-0 mt-0.5" />
                  <span>Deploy SSL configuration for secure database connection pools.</span>
                </li>
              </>
            )}
          </ul>
        </div>
      </div>

      {/* Deployment History Timeline */}
      <div className="glass rounded-2xl border border-border/60 p-6 bg-card/20 space-y-4">
        <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">Deployment Timeline</h3>
        
        {deployments.length === 0 ? (
          <div className="text-center py-8 text-xs text-foreground-muted">
            No recent deployments found for this project.
          </div>
        ) : (
          <div className="relative border-l border-border/40 pl-5 ml-2.5 space-y-6">
            {deployments.slice(0, 5).map((dep, idx) => {
              const dateObj = dep.started_at ? new Date(dep.started_at) : new Date();
              const dateStr = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });
              const timeStr = dateObj.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

              return (
                <div key={dep.id} className="relative group">
                  {/* Timeline Dot */}
                  <div className={`absolute -left-[27px] top-1.5 w-3.5 h-3.5 rounded-full border-2 border-zinc-950 transition-colors ${
                    dep.status === "running" ? "bg-success" :
                    dep.status === "failed" ? "bg-danger" :
                    dep.status === "building" ? "bg-warning animate-pulse" :
                    "bg-foreground-muted"
                  }`} />

                  {/* Content Row */}
                  <div
                    onClick={() => router.push(`/dashboard/deployments?id=${dep.id}&repo=${encodeURIComponent(activeProject.full_name)}`)}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3.5 rounded-xl border border-border/40 bg-card hover:bg-card-hover/60 transition cursor-pointer"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-foreground">Deployment #{deployments.length - idx}</span>
                        <span className={`text-[9px] font-mono font-bold px-1.5 py-0.2 rounded border ${
                          dep.status === "running" ? "bg-success/15 border-success/30 text-success" :
                          dep.status === "failed" ? "bg-danger/15 border-danger/30 text-danger" :
                          "bg-zinc-800 border-zinc-700 text-foreground-muted"
                        }`}>
                          {dep.status}
                        </span>
                      </div>
                      <p className="text-[10px] text-foreground-muted mt-1 flex items-center gap-1.5 font-mono">
                        <Clock size={10} /> {dep.duration || "2m 13s"}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 text-right">
                      <div className="text-xs">
                        <p className="text-foreground-muted flex items-center gap-1 justify-end"><Calendar size={10} /> {dateStr}</p>
                        <p className="text-[10px] text-foreground-muted/60 mt-0.5">{timeStr}</p>
                      </div>
                      <ArrowRight size={14} className="text-foreground-muted group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
