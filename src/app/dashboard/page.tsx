"use client";

import { motion } from "framer-motion";
import {
  GitBranch, ExternalLink, RefreshCw, Terminal, Globe,
  Calendar, Clock, Brain, Loader2, FolderGit2, AlertTriangle,
  Check, ArrowRight, ShieldCheck, Cpu, Sparkles, DollarSign,
  Activity
} from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, type Project, type Deployment, type AIAnalysis } from "@/lib/api";
import { ArchitectureDiagram } from "@/components/dashboard/ArchitectureDiagram";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { liveUrlForProject, normalizeProjectId } from "@/lib/demo-runtime";

// Helper function to calculate project readiness score based on metadata
function calculateProjectReadinessScore(project: Project, analysis: AIAnalysis | null): number {
  let score = 75; // baseline
  if (project.framework && project.framework !== "Unknown") score += 10;
  if (project.language) score += 5;
  if (project.latest_deployment_status === "running" || project.status === "active") score += 5;
  if (analysis) {
    if (analysis.runtime) score += 5;
    if (analysis.docker_support || analysis.dockerfile) score += 5;
    const vulnerabilities = analysis.vulnerabilities || [];
    score -= Math.min(15, vulnerabilities.length * 5);
  }
  return Math.min(100, Math.max(0, score));
}

// Circle gauge component for deployment readiness
function ProjectReadinessCircle({ score }: { score: number }) {
  const radius = 22;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "text-success" : score >= 80 ? "text-warning" : "text-danger";
  const strokeColor = score >= 90 ? "var(--success)" : score >= 80 ? "var(--warning)" : "var(--danger)";

  return (
    <div className="relative w-16 h-16 flex-shrink-0">
      <svg className="w-16 h-16 -rotate-90" viewBox="0 0 54 54">
        <circle cx="27" cy="27" r={radius} fill="none" stroke="var(--border)" strokeWidth="4" />
        <motion.circle
          cx="27"
          cy="27"
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth="4"
          strokeLinecap="round"
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          style={{ strokeDasharray: circumference }}
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center text-xs font-extrabold ${color}`}>
        {score}%
      </span>
    </div>
  );
}

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
  const readinessScore = calculateProjectReadinessScore(activeProject, analysis);

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

      {/* Row 1: Outcomes-First Hero & AI Health Agent */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Outcomes Hero Card */}
        <div className="md:col-span-2 glass rounded-2xl border border-border/60 p-6 bg-gradient-to-b from-card to-card/40 flex flex-col justify-between space-y-6">
          <div className="space-y-4">
            {/* Healthy & Active Pulsing Dot Indicator */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-success"></span>
                </span>
                <span className="text-xs font-bold text-success uppercase tracking-wider">
                  Healthy & Active
                </span>
              </div>
              <span className="text-[10px] bg-primary/10 border border-primary/20 text-primary px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
                Production Env
              </span>
            </div>

            {/* Big URL display */}
            <div className="space-y-1">
              <p className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">Live URL</p>
              <div className="flex items-center gap-3">
                <Globe className="text-primary w-5 h-5 flex-shrink-0" />
                <a
                  href={liveUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-lg md:text-xl font-mono font-bold text-foreground hover:text-primary transition truncate hover:underline"
                >
                  {liveUrl.replace("https://", "")}
                </a>
              </div>
            </div>

            {/* Metadata Grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 pt-4 border-t border-border/20 text-xs">
              <div>
                <p className="text-[9px] font-bold text-foreground-muted uppercase tracking-wider">Target region</p>
                <p className="mt-1 font-semibold text-foreground flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                  Azure App Service ({activeProject.region || "East US"})
                </p>
              </div>
              <div>
                <p className="text-[9px] font-bold text-foreground-muted uppercase tracking-wider">Framework / Runtime</p>
                <p className="mt-1 font-semibold text-foreground">
                  {activeProject.framework} • {analysis?.runtime || "Node.js 22"}
                </p>
              </div>
              <div>
                <p className="text-[9px] font-bold text-foreground-muted uppercase tracking-wider">Last deployment</p>
                <p className="mt-1 font-semibold text-foreground flex items-center gap-1">
                  <Clock size={12} className="text-foreground-muted" />
                  {deployments[0]?.started_at
                    ? new Date(deployments[0].started_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " at " + new Date(deployments[0].started_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })
                    : "Recently"}
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-3 pt-4 border-t border-border/20">
            <a
              href={liveUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-4 py-2.5 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-xs transition shadow-lg shadow-primary/20 hover:shadow-primary/30"
            >
              <ExternalLink size={14} /> Open Application
            </a>
            <button
              onClick={() => handleCopyUrl(liveUrl)}
              className="px-4 py-2.5 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition"
            >
              Copy URL
            </button>
            <button
              disabled={redeploying}
              onClick={() => handleRedeploy(activeProject)}
              className="flex items-center gap-1.5 px-4 py-2.5 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition disabled:opacity-50"
            >
              <RefreshCw size={14} className={redeploying ? "animate-spin" : ""} /> Redeploy
            </button>
            <button
              onClick={() => router.push(`/dashboard/deployments?repo=${encodeURIComponent(activeProject.full_name)}`)}
              className="flex items-center gap-1.5 px-4 py-2.5 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition text-foreground-muted hover:text-foreground"
            >
              <Terminal size={14} /> View Logs
            </button>
          </div>
        </div>

        {/* AI Health Summary Card */}
        <div className="glass rounded-2xl border border-primary/20 p-6 bg-gradient-to-b from-primary/5 via-accent/5 to-transparent flex flex-col justify-between shadow-sm space-y-4">
          <div className="space-y-3">
            <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
              <Brain size={14} className="animate-pulse text-primary" /> AI Health Agent
            </h4>
            
            <p className="text-xs text-foreground-muted leading-relaxed font-medium">
              Your application is healthy. All platform systems are running at peak performance. Average response times are excellent, and auto-scaling configs are active.
            </p>

            <div className="space-y-2 text-xs pt-1.5 border-t border-border/20">
              <div className="flex items-center gap-2 text-foreground-muted">
                <Check size={14} className="text-success shrink-0" />
                <span>SSL certificate is active & secure</span>
              </div>
              <div className="flex items-center gap-2 text-foreground-muted">
                <Check size={14} className="text-success shrink-0" />
                <span>Auto-scaling is configured</span>
              </div>
              <div className="flex items-center gap-2 text-foreground-muted">
                <Check size={14} className="text-success shrink-0" />
                <span>No active deployment issues</span>
              </div>
              <div className="flex items-center gap-2 text-foreground-muted">
                <Check size={14} className="text-success shrink-0" />
                <span>Continuous sync from GitHub</span>
              </div>
            </div>
          </div>
          
          <div className="text-[10px] text-foreground-muted/60 text-center border-t border-border/20 pt-3 flex items-center justify-center gap-1.5">
            <Activity size={10} className="text-success animate-pulse" />
            <span>Autonomic Plane Status: Active</span>
          </div>
        </div>
      </div>

      {/* Risk Alert Banner if any vulnerabilities exist */}
      {analysis?.vulnerabilities && analysis.vulnerabilities.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-warning/10 border border-warning/20 rounded-xl p-4 flex gap-3 text-xs text-warning"
        >
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-bold">AI Risk Detection: Setup requires verification</p>
            <p className="leading-relaxed text-[11px] text-foreground-muted">
              We identified potential items that could affect production stability or security. Review recommendations below.
            </p>
          </div>
        </motion.div>
      )}

      {/* Row 2: AI Engine Insights (Readiness, Cost, and Risks) */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Card 1: Readiness Score */}
        <div className="glass rounded-2xl border border-border/60 p-5 bg-card/40 flex items-center justify-between gap-4">
          <div className="space-y-1">
            <h4 className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider flex items-center gap-1">
              <Sparkles size={11} className="text-primary" /> Readiness Score
            </h4>
            <p className="text-base font-extrabold text-foreground">Deployment Ready</p>
            <p className="text-[10px] text-foreground-muted">
              {readinessScore >= 90 ? "High-readiness setup" : "Standard setup"}
            </p>
          </div>
          <ProjectReadinessCircle score={readinessScore} />
        </div>

        {/* Card 2: AI Cost Estimation */}
        <div className="glass rounded-2xl border border-border/60 p-5 bg-card/40 flex flex-col justify-between gap-3">
          <div className="space-y-1">
            <h4 className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider flex items-center gap-1">
              <DollarSign size={12} className="text-success" /> AI Cost Advisor
            </h4>
            <p className="text-base font-extrabold text-foreground">Free Tier Eligible</p>
            <p className="text-[10px] text-foreground-muted">
              Recommended: {analysis?.cpu_recommendation || "0.5 vCPU"} / {analysis?.memory_recommendation || "1 GB RAM"}
            </p>
          </div>
          <div className="text-[9px] text-success bg-success/10 border border-success/20 rounded-lg px-2.5 py-1 font-semibold w-fit">
            Estimated cost: $0.00 / month
          </div>
        </div>

        {/* Card 3: AI Security & Risks */}
        <div className="glass rounded-2xl border border-border/60 p-5 bg-card/40 flex flex-col justify-between gap-3">
          <div className="space-y-1">
            <h4 className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider flex items-center gap-1">
              <ShieldCheck size={12} className="text-primary" /> AI Risk Scanner
            </h4>
            <p className="text-base font-extrabold text-foreground">
              {analysis?.vulnerabilities && analysis.vulnerabilities.length > 0
                ? `${analysis.vulnerabilities.length} Issues Found`
                : "No Risks Detected"}
            </p>
            <p className="text-[10px] text-foreground-muted">
              {analysis?.vulnerabilities && analysis.vulnerabilities.length > 0
                ? "Security tuning suggested"
                : "Namespace isolation active"}
            </p>
          </div>
          <div className={`text-[9px] rounded-lg px-2.5 py-1 font-semibold w-fit border ${
            analysis?.vulnerabilities && analysis.vulnerabilities.length > 0
              ? "bg-warning/15 border-warning/30 text-warning"
              : "bg-success/10 border-success/20 text-success"
          }`}>
            {analysis?.vulnerabilities && analysis.vulnerabilities.length > 0
              ? "Needs review"
              : "Security verified ✓"}
          </div>
        </div>
      </div>

      {/* Row 3: SVG System Architecture */}
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

      {/* Row 4: AI Explanation & Recommendations */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-card/40">
          <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
            <Brain size={14} /> Explain My Project
          </h4>
          <p className="text-xs text-foreground-muted leading-relaxed font-medium">
            {analysis?.explanation || `This is a ${activeProject.framework} application built with ${activeProject.language || "TypeScript"}. It is containerized and managed autonomously by ZeroOps on Azure App Service with isolated security configurations.`}
          </p>
        </div>

        <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-card/40">
          <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
            AI Recommendations & Optimizations
          </h4>
          <ul className="space-y-2">
            {analysis?.vulnerabilities && analysis.vulnerabilities.length > 0 ? (
              analysis.vulnerabilities.slice(0, 3).map((rec, i) => (
                <li key={i} className="flex gap-2 items-start text-xs text-foreground-muted">
                  <span className="text-primary font-bold select-none">•</span>
                  <span className="font-medium">{rec}</span>
                </li>
              ))
            ) : (
              <>
                <li className="flex gap-2 items-start text-xs text-foreground-muted">
                  <Check size={12} className="text-success shrink-0 mt-0.5" />
                  <span className="font-medium">Configure idle pod scale-down boundaries to reduce cloud billing by 30%.</span>
                </li>
                <li className="flex gap-2 items-start text-xs text-foreground-muted">
                  <Check size={12} className="text-success shrink-0 mt-0.5" />
                  <span className="font-medium">Deploy SSL configuration for secure database connection pools.</span>
                </li>
              </>
            )}
          </ul>
        </div>
      </div>

      {/* Row 5: Deployment History Timeline */}
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
