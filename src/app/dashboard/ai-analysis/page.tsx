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
import { useMemo, useState } from "react";
import { GaugeChart } from "@/components/ui/GaugeChart";
import { useNotifications } from "@/lib/NotificationContext";
import {
  AnalysisResult,
  DEFAULT_PROJECT_ID,
  createFallbackAnalysis,
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

export default function AIAnalysisPage() {
  const router = useRouter();
  const { repositories, addToast, addNotification } = useNotifications();
  const [repo, setRepo] = useState("acme/web-app");
  const [analysis, setAnalysis] = useState<AnalysisResult>(() => createFallbackAnalysis("acme/web-app"));
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const projectId = normalizeProjectId(repo || DEFAULT_PROJECT_ID);
  const namespace = namespaceForProject(projectId);
  const host = hostForProject(projectId);

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
      const res = await fetch("/api/ai/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, branch: "main" }),
      });
      if (!res.ok) throw new Error("Backend analysis unavailable");
      const data = await res.json();
      setAnalysis({ ...createFallbackAnalysis(repo), ...data });
      addToast(`AI analysis complete for ${repo}.`, "success");
      addNotification({
        title: "AI Analysis Complete",
        message: `Generated deployment plan for ${repo} in namespace ${namespace}.`,
        type: "success",
      });
    } catch (error) {
      console.error("AI analysis fallback activated:", error);
      const fallback = createFallbackAnalysis(repo);
      setAnalysis(fallback);
      addToast("Backend AI unavailable. Local deployment analysis completed.", "warning");
      addNotification({
        title: "Fallback Analysis Complete",
        message: `ZeroOps generated a demo-safe plan for ${repo} without blocking the deployment flow.`,
        type: "info",
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDeploy = async () => {
    setIsDeploying(true);
    addToast(`Starting autonomous deployment for ${repo}...`, "info");
    try {
      const res = await fetch("/api/deployments/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, branch: "main" }),
      });
      if (!res.ok) throw new Error("Deploy trigger unavailable");
      const data = await res.json();
      router.push(`/dashboard/deployments?id=${data.deployment_id}&repo=${encodeURIComponent(repo)}`);
    } catch (error) {
      console.error("Deployment fallback activated:", error);
      addToast("Backend unavailable. Starting guided deployment simulation.", "warning");
      router.push(`/dashboard/deployments?id=demo-${projectId}&repo=${encodeURIComponent(repo)}&mode=fallback`);
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
          <select
            value={repo}
            onChange={(event) => {
              setRepo(event.target.value);
              setAnalysis(createFallbackAnalysis(event.target.value));
            }}
            className="rounded-xl border border-border bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
          >
            {repositories.map((item) => (
              <option key={item.id} value={item.fullName}>
                {item.fullName}
              </option>
            ))}
          </select>
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium glass hover:bg-card-hover disabled:opacity-60"
          >
            {isAnalyzing ? <Loader2 size={16} className="animate-spin" /> : <Brain size={16} />}
            Run Full Analysis
          </button>
          <button
            onClick={handleDeploy}
            disabled={isDeploying}
            className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white glow-blue transition hover:bg-primary-hover disabled:opacity-60"
          >
            {isDeploying ? <Loader2 size={16} className="animate-spin" /> : <Rocket size={16} />}
            Deploy Now
          </button>
        </div>
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-border bg-white/5">
            <Brain size={28} className="text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">{analysis.framework} {analysis.version} Detected</h3>
            <p className="text-sm text-foreground-muted">
              {analysis.language} / App Router / Tailwind CSS v4 / namespace {namespace}
            </p>
          </div>
          <span className="sm:ml-auto rounded-full bg-success/10 px-3 py-1 text-xs font-medium text-success">
            {analysis.confidence}% Confidence
          </span>
        </div>
      </motion.div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { icon: Cpu, label: "CPU", value: analysis.resources.cpu, rec: "Recommended" },
          { icon: HardDrive, label: "Memory", value: analysis.resources.memory, rec: "Recommended" },
          { icon: Database, label: "Storage", value: analysis.resources.storage, rec: "Estimated" },
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
            {analysis.vulnerabilities.length} recommendations
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {analysis.dependencies.map((dep) => (
            <div key={dep} className="flex items-center gap-2 rounded-lg bg-card/50 px-3 py-2 text-xs">
              <Check size={12} className="text-success" />
              <span className="font-mono text-foreground-muted">{dep}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          {analysis.vulnerabilities.map((item) => (
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
    </div>
  );
}
