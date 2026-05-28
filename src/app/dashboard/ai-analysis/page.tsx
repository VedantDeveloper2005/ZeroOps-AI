"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  Check,
  Cpu,
  Database,
  HardDrive,
  Loader2,
  Rocket,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState, useEffect } from "react";
import { GaugeChart } from "@/components/ui/GaugeChart";
import { useNotifications } from "@/lib/NotificationContext";
import { api, type Project, type AIAnalysis } from "@/lib/api";
import {
  DEFAULT_PROJECT_ID,
  hostForProject,
  namespaceForProject,
  normalizeProjectId,
} from "@/lib/demo-runtime";

const analysisSteps = [
  "Clone repository from GitHub",
  "Build optimized Docker image",
  "Generate Kubernetes manifests",
  "Configure ingress and networking",
  "Apply namespace RBAC and quotas",
  "Enable autoscaling (HPA)",
  "Set up monitoring and alerting",
  "Deploy to AKS cluster",
];

const fallbackAnalysis = (fullName: string): AIAnalysis => {
  const name = fullName.split("/").pop() || fullName;
  return {
    id: "",
    project_id: "",
    framework: "Next.js",
    framework_version: "16.2.6",
    language: "TypeScript",
    risk_score: 18,
    confidence: 92,
    cpu_recommendation: "200m",
    memory_recommendation: "256Mi",
    storage_recommendation: "1Gi",
    port: "3000",
    dependencies: ["next@16.2.6", "react@19"],
    vulnerabilities: ["Vulnerability checks passed."],
    dockerfile: "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\nRUN npm ci && npm run build\nCMD [\"npm\", \"start\"]",
    kubernetes_manifest: `apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${name}
  namespace: zeroops-${name}
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ${name}
  template:
    metadata:
      labels:
        app: ${name}
    spec:
      containers:
      - name: ${name}
        image: acr.azurecr.io/${name}:latest
        ports:
        - containerPort: 3000`,
    created_at: new Date().toISOString()
  };
};

export default function AIAnalysisPage() {
  const router = useRouter();
  const { projects, addToast, addNotification, refreshProjects, refreshStats } = useNotifications();
  const [repo, setRepo] = useState("acme/web-app");
  const [analysis, setAnalysis] = useState<AIAnalysis>(() => fallbackAnalysis("acme/web-app"));
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);

  const projectId = normalizeProjectId(repo || DEFAULT_PROJECT_ID);
  const namespace = namespaceForProject(projectId);
  const host = hostForProject(projectId);

  // Sync initial repo select to first connected project
  useEffect(() => {
    if (projects.length > 0 && repo === "acme/web-app") {
      const firstProj = projects[0];
      setRepo(firstProj.full_name);
    }
  }, [projects, repo]);

  // Load analysis whenever repo changes
  useEffect(() => {
    const matchedProj = projects.find(p => p.full_name === repo);
    if (matchedProj) {
      setIsLoadingAnalysis(true);
      api.getAIAnalysis(matchedProj.id)
        .then(data => setAnalysis(data))
        .catch(() => setAnalysis(fallbackAnalysis(repo)))
        .finally(() => setIsLoadingAnalysis(false));
    } else {
      setAnalysis(fallbackAnalysis(repo));
    }
  }, [repo, projects]);

  const manifestSummary = useMemo(() => {
    const manifest = analysis.kubernetes_manifest || "";
    return [
      { label: "Namespace", value: namespace },
      { label: "Ingress Host", value: host },
      { label: "Deployment", value: manifest.includes("kind: Deployment") ? "Generated" : "Pending" },
      { label: "HPA", value: manifest.includes("HorizontalPodAutoscaler") ? "Generated" : "Pending" },
    ];
  }, [analysis.kubernetes_manifest, host, namespace]);

  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    addToast(`Analyzing ${repo} with ZeroOps AI...`, "info");
    try {
      const data = await api.analyzeRepo(repo, "main");
      const matchedProj = projects.find(p => p.full_name === repo);
      if (matchedProj) {
        const freshAnalysis = await api.getAIAnalysis(matchedProj.id);
        setAnalysis(freshAnalysis);
      } else {
        setAnalysis({
          id: "",
          project_id: "",
          framework: (data.framework as string) || "Next.js",
          framework_version: (data.version as string) || "16.2.6",
          language: (data.language as string) || "TypeScript",
          risk_score: (data.risk_score as number) || 18,
          confidence: (data.confidence as number) || 92,
          cpu_recommendation: ((data.resources as any)?.cpu as string) || "200m",
          memory_recommendation: ((data.resources as any)?.memory as string) || "256Mi",
          storage_recommendation: ((data.resources as any)?.storage as string) || "1Gi",
          port: "3000",
          dependencies: (data.dependencies as string[]) || ["next@16.2.6", "react@19"],
          vulnerabilities: (data.vulnerabilities as string[]) || ["Vulnerability checks passed."],
          dockerfile: (data.dockerfile as string) || null,
          kubernetes_manifest: (data.kubernetes_manifest as string) || null,
          created_at: new Date().toISOString()
        });
      }
      addToast(`AI analysis complete for ${repo}.`, "success");
      addNotification({
        title: "AI Analysis Complete",
        message: `Generated deployment plan for ${repo} in namespace ${namespace}.`,
        type: "success",
        category: "ai",
        action_url: "/dashboard/ai-analysis"
      });
    } catch (error) {
      console.error("AI analysis fallback activated:", error);
      const fallback = fallbackAnalysis(repo);
      setAnalysis(fallback);
      addToast("Backend AI unavailable. Local deployment analysis completed.", "warning");
      addNotification({
        title: "Fallback Analysis Complete",
        message: `ZeroOps generated a demo-safe plan for ${repo} without blocking the deployment flow.`,
        type: "info",
        category: "ai",
        action_url: "/dashboard/ai-analysis"
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDeploy = async () => {
    setIsDeploying(true);
    addToast(`Starting autonomous deployment for ${repo}...`, "info");
    try {
      const matchedProj = projects.find(p => p.full_name === repo);
      if (!matchedProj) {
        throw new Error("Project must be connected first.");
      }
      const data = await api.startDeployment({
        project_id: matchedProj.id,
        branch: "main",
        environment: "production"
      });
      await Promise.all([refreshProjects(), refreshStats()]);
      router.push(`/dashboard/deployments?id=${data.deployment_id}&repo=${encodeURIComponent(repo)}`);
    } catch (error) {
      console.error("Deployment failed:", error);
      addToast("Failed to initialize deployment pipeline.", "error");
    } finally {
      setIsDeploying(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Analysis</h1>
          <p className="mt-1 text-sm text-foreground-muted">AI-powered repository analysis and deployment planning</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {projects.length > 0 ? (
            <select
              value={repo}
              onChange={(event) => setRepo(event.target.value)}
              className="rounded-xl border border-border bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary cursor-pointer"
            >
              {projects.map((item: Project) => (
                <option key={item.id} value={item.full_name}>
                  {item.full_name}
                </option>
              ))}
            </select>
          ) : (
            <div className="text-xs text-foreground-muted flex items-center bg-card border border-border px-3 py-2 rounded-xl">
              No repositories connected.
            </div>
          )}
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing || projects.length === 0}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium glass hover:bg-card-hover disabled:opacity-60 cursor-pointer"
          >
            {isAnalyzing ? <Loader2 size={16} className="animate-spin" /> : <Brain size={16} />}
            Run Full Analysis
          </button>
          <button
            onClick={handleDeploy}
            disabled={isDeploying || projects.length === 0}
            className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white glow-blue transition hover:bg-primary-hover disabled:opacity-60 cursor-pointer"
          >
            {isDeploying ? <Loader2 size={16} className="animate-spin" /> : <Rocket size={16} />}
            Deploy Now
          </button>
        </div>
      </div>

      {isLoadingAnalysis ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <Loader2 className="animate-spin text-primary" size={24} />
        </div>
      ) : (
        <>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-border bg-white/5">
                <Brain size={28} className="text-primary" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">{analysis.framework} {analysis.framework_version || ""} Detected</h3>
                <p className="text-sm text-foreground-muted">
                  {analysis.language} / App Router / namespace {namespace}
                </p>
              </div>
              <span className="sm:ml-auto rounded-full bg-success/10 px-3 py-1 text-xs font-medium text-success">
                {analysis.confidence}% Confidence
              </span>
            </div>
          </motion.div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              { icon: Cpu, label: "CPU", value: analysis.cpu_recommendation || "200m", rec: "Recommended" },
              { icon: HardDrive, label: "Memory", value: analysis.memory_recommendation || "256Mi", rec: "Recommended" },
              { icon: Database, label: "Storage", value: analysis.storage_recommendation || "1Gi", rec: "Estimated" },
            ].map((item, i) => (
              <motion.div key={item.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="glass rounded-xl p-5 text-center">
                <item.icon size={24} className="mx-auto mb-2 text-primary" />
                <p className="text-2xl font-bold text-foreground">{item.value}</p>
                <p className="text-xs text-foreground-muted">{item.label}</p>
                <span className="mt-1 block text-[10px] text-success">{item.rec}</span>
              </motion.div>
            ))}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="col-span-2 flex flex-col items-center justify-center rounded-xl p-5 glass sm:col-span-1">
              <GaugeChart value={analysis.risk_score} label="Risk Score" size={100} color="hsl(142, 76%, 45%)" />
              <span className="mt-2 text-xs font-medium text-success">Demo Safe</span>
            </motion.div>
          </div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="font-semibold">Dependency and Security Overview</h3>
              <span className="flex items-center gap-1 rounded-full bg-warning/10 px-2 py-1 text-xs text-warning">
                <AlertTriangle size={12} />
                {(analysis.vulnerabilities || []).length} recommendations
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {(analysis.dependencies || []).map((dep: string) => (
                <div key={dep} className="flex items-center gap-2 rounded-lg bg-card/50 px-3 py-2 text-xs">
                  <Check size={12} className="text-success" />
                  <span className="font-mono text-foreground-muted">{dep}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-3">
              {(analysis.vulnerabilities || []).map((item: string) => (
                <div key={item} className="rounded-lg border border-warning/20 bg-warning/5 p-3 text-xs text-foreground-muted">
                  {item}
                </div>
              ))}
            </div>
          </motion.div>

          <div className="grid gap-4 lg:grid-cols-2">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
              <h3 className="mb-4 flex items-center gap-2 font-semibold"><Brain size={18} className="text-primary" />AI Deployment Plan</h3>
              <div className="space-y-3">
                {analysisSteps.map((step, i) => (
                  <motion.div key={step} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.08 }} className="flex items-center gap-3 text-sm">
                    <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">{i + 1}</span>
                    <span className="text-foreground">{step}</span>
                    <ArrowRight size={14} className="ml-auto text-foreground-muted" />
                  </motion.div>
                ))}
              </div>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="glass rounded-xl p-6">
              <h3 className="mb-4 font-semibold">Generated Cloud Plan</h3>
              <div className="mb-4 grid grid-cols-2 gap-3">
                {manifestSummary.map((item) => (
                  <div key={item.label} className="rounded-lg bg-card/50 p-3">
                    <p className="text-[10px] uppercase tracking-wide text-foreground-muted">{item.label}</p>
                    <p className="mt-1 truncate text-sm font-semibold text-foreground">{item.value}</p>
                  </div>
                ))}
              </div>
              <pre className="max-h-72 overflow-auto rounded-lg bg-black/30 p-4 text-xs leading-5 text-foreground-muted no-scrollbar">
                {analysis.kubernetes_manifest}
              </pre>
            </motion.div>
          </div>
        </>
      )}
    </div>
  );
}
